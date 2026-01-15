"""
测试执行组件 (Component 1/6)
职责：执行目标程序，获取返回值、执行时间、覆盖率等信息

类型安全设计：
- 使用 ExecutionResult (TypedDict) 定义返回值结构
- IDE 和 mypy 自动验证字段完整性和类型正确性
- 无需手动同步字段定义与使用

详见：docs/DESIGN.md（“字段一致性与类型安全”）
"""

import subprocess
import tempfile
import time
import os
import signal
import resource
import shutil
from typing import TypedDict, Optional
from config import CONFIG
from utils import AFLSHM


# ========== 返回结果类型定义 ==========
# 使用 TypedDict 确保类型安全，避免手动同步字段
class ExecutionResult(TypedDict):
    """执行结果数据结构"""
    return_code: int        # 返回码
    exec_time: float        # 执行时间（秒）
    crashed: bool           # 是否崩溃
    timeout: bool           # 是否超时
    stderr: bytes           # 标准错误输出（截断）
    coverage: Optional[bytes]  # 覆盖率 bitmap（如果启用）


class TestExecutor:
    """
    测试执行器
    使用 subprocess 执行目标程序，支持超时、资源限制和覆盖率收集

    支持 AFL++ SHM 覆盖率获取
    """

    def __init__(self, target_path: str, target_args: str,
                 timeout: float | None = None, use_coverage: bool = False):
        """
        初始化执行器

        Args:
            target_path: 目标程序路径（绝对路径）
            target_args: 命令行参数模板，其中 @@ 表示输入文件位置
            timeout: 执行超时时间（秒）
            use_coverage: 是否启用覆盖率收集（需要目标使用 afl-cc 编译）
        """
        self.target_path = os.path.abspath(target_path)
        self.target_args = target_args
        self.timeout = timeout or CONFIG['timeout']
        self.use_coverage = use_coverage

        # 沙箱配置（使用 bubblewrap）
        self.use_sandbox = CONFIG.get('use_sandbox', False)
        self.bwrap_path = shutil.which('bwrap')
        if self.use_sandbox:
            if not self.bwrap_path:
                print("[Executor] Warning: 'use_sandbox' enabled but 'bwrap' not found. Sandbox disabled.")
                self.use_sandbox = False
            else:
                print(f"[Executor] Sandbox enabled: {self.bwrap_path}")

        # 使用 /tmp 作为临时目录
        self.temp_dir = tempfile.mkdtemp(prefix='fuzz_', dir='/tmp')
        self.input_file = os.path.join(self.temp_dir, 'input')

        # SHM 支持
        self.shm: Optional[AFLSHM] = None
        if use_coverage:
            bitmap_size = CONFIG.get('bitmap_size', 65536)
            self.shm = AFLSHM(bitmap_size=bitmap_size)
            print(f"[Executor] Coverage enabled, SHM ID: {self.shm.get_shm_id()}")

        # 验证目标程序存在
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Target not found: {target_path}")

        print(f"[Executor] Initialized for {target_path}")
        print(f"[Executor] Temp dir: {self.temp_dir}")

    def execute(self, input_data: bytes) -> ExecutionResult:
        """
        执行目标程序

        Args:
            input_data: 输入数据（字节）

        Returns:
            ExecutionResult 类型的字典（包含 return_code, exec_time, crashed, timeout, stderr, coverage）
        """
        # 清空 SHM bitmap
        if self.shm:
            self.shm.clear()

        # 写入输入文件
        try:
            with open(self.input_file, 'wb') as f:
                f.write(input_data)
        except Exception as e:
            return ExecutionResult(
                return_code=-1,
                exec_time=0.0,
                crashed=True,
                timeout=False,
                stderr=f"Failed to write input: {str(e)}".encode(),
                coverage=None
            )

        # 替换命令中的 @@ 为输入文件路径
        if '@@' in self.target_args:
            # 如果是沙箱模式，这里已经是正确的文件名（指向 self.temp_dir 中的 input），
            # 但在 shell=True 的情况下，我们需要传递完整的路径（或者我们调整 cwd）
            # 当前 execute 已经在 cwd=self.temp_dir 下运行，所以相对路径 'input' 也可以
            # 但为了安全，subprocess 使用绝对路径总是更好
            cmd = self.target_args.replace('@@', self.input_file)
        else:
            # 如果没有 @@，则通过 stdin 传递输入
            # 注意：沙箱模式下，< self.input_file 是由宿主机 shell 处理还是沙箱内部？
            # 如果 shell=True, 且 cmd 被 wrap 成了 bwrap ... bash -c 'target < input' ?
            # 最简单的方式是让 bwrap 直接执行 target，输入重定向由 python 处理
            # 但我们的 cmd 可能是 "target arg1 arg2 ..."
            # 如果通过 stdin，我们在 Popen 中传递 stdin 文件句柄即可
            cmd = f"{self.target_args} < {self.input_file}"

        # 准备环境变量
        env = os.environ.copy()
        if self.shm:
            env['__AFL_SHM_ID'] = str(self.shm.get_shm_id())
            # 关键：禁用 Forkserver，强制直接执行并写入 SHM
            env['AFL_NO_FORKSRV'] = '1'

        # --- 构建执行命令（支持沙箱）---
        # 此时 cmd 是一个字符串（因 shell=True）
        # 如果使用 bwrap，我们需要把 cmd 拆分或者让 bwrap 启动一个 shell

        popen_args = {}
        popen_stdin = None

        if self.use_sandbox:
            # 构造 bwrap 命令
            # --ro-bind / / : 根目录只读
            # --dev /dev, --proc /proc : 必要设备文件
            # --bind temp_dir temp_dir : 允许读写临时目录（包含 input/output）
            # --share-net : 允许网络（某些目标需要吗？这里默认允许，否则加 --unshare-net）
            # 注意：不使用 --unshare-ipc，以便 AFL SHM 工作

            # 由于 cmd 可能是 "target -a input"，我们需要让 bwrap 执行它
            # 不使用 shell=True，而是显式构造 ARGV
            # 但这里原始代码用的是 shell=True 用于处理 < 重定向

            sandbox_cmd = [
                self.bwrap_path,
                '--ro-bind', '/', '/',
                '--dev', '/dev',
                '--proc', '/proc',
                '--bind', self.temp_dir, self.temp_dir,
                '--unshare-pid',  # 隔离 PID 命名空间，确保清理所有子进程
                '--die-with-parent',
                '--new-session'
            ]

            # 如果目标需要写入其他位置（如 /dev/null），可能需要更多 bind
            # 这里是基本配置

            # 处理 Shell 命令的复杂性：
            # 如果 cmd 包含 "<" 重定向，直接用 Popen(stdin=...) 更好，而不是 shell 重定向
            # 我们重新解析 cmd 逻辑

            real_cmd_str = self.target_args.replace('@@', self.input_file)
            input_from_stdin = '@@' not in self.target_args

            # 使用 sh -c 来执行原命令，保持兼容性
            # bwrap ... -- sh -c "target args..."
            full_cmd = sandbox_cmd + ['--', '/bin/sh', '-c', real_cmd_str]

            if input_from_stdin:
                # 在 python 层打开 input 文件作为 stdin
                popen_stdin = open(self.input_file, 'rb')
                # 此时 cmd 字符串里不需要 < ...
                # 上面的 real_cmd_str 已经只包含 args
                # 但旧代码是 cmd = f"{...} < {...}"
                # 修正：如果 input_from_stdin，real_cmd_str 应该是原始 target_args
                real_cmd_str = self.target_args
                # full_cmd 依然是 sh -c "target_args"
                full_cmd = sandbox_cmd + ['--', '/bin/sh', '-c', real_cmd_str]

            # 更新为列表形式（shell=False）
            cmd = full_cmd
            popen_args['shell'] = False
            popen_args['stdin'] = popen_stdin

        else:
            # 非沙箱模式，保持原逻辑 (shell=True)
            # 但为了统一处理 redirect，如果 input_from_stdin，最好也用 Popen stdin
             # 替换命令中的 @@ 为输入文件路径
            if '@@' in self.target_args:
                cmd = self.target_args.replace('@@', self.input_file)
                popen_stdin = None
            else:
                # 标准输入模式：
                # 原始代码：cmd = f"{self.target_args} < {self.input_file}"
                # 新逻辑：直接传递 stdin 句柄
                cmd = self.target_args
                popen_stdin = open(self.input_file, 'rb')

            popen_args['shell'] = True
            popen_args['stdin'] = popen_stdin


        # 准备内存限制函数
        def set_limits():
            # 设置内存限制（仅限 Linux/Unix）
            if hasattr(resource, 'RLIMIT_AS'):
                mem_bytes = CONFIG.get('mem_limit', 256) * 1024 * 1024  # MB -> bytes
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                except ValueError:
                    pass

            # 禁止 Core Dump（防止崩溃文件填满磁盘）
            if hasattr(resource, 'RLIMIT_CORE'):
                try:
                    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                except ValueError:
                    pass

            # 创建新进程组（用于信号处理）
            if hasattr(os, 'setsid'):
                os.setsid()

        # 输出重定向文件（避免内存 OOM）
        stdout_path = os.path.join(self.temp_dir, 'stdout')
        stderr_path = os.path.join(self.temp_dir, 'stderr')

        # 执行目标程序
        # 使用 Popen 而非 run，以便在超时时能正确杀死整个进程组
        start_time = time.perf_counter()
        proc = None
        stdout_f = None
        stderr_f = None

        try:
            # 打开用于重定向的文件
            stdout_f = open(stdout_path, 'wb')
            stderr_f = open(stderr_path, 'wb')

            proc = subprocess.Popen(
                cmd,
                stdout=stdout_f,  # 重定向到文件
                stderr=stderr_f,  # 重定向到文件
                cwd=self.temp_dir, # 关键：隔离工作目录，防止污染项目根目录
                env=env,
                preexec_fn=set_limits,
                **popen_args
            )

            try:
                proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                # 超时：杀死整个进程组
                try:
                    # 获取进程组 ID（由 setsid 创建）
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                # 等待进程真正结束
                proc.wait()

                elapsed = time.perf_counter() - start_time
                # 读取覆盖率
                coverage = self.shm.read_bitmap() if self.shm else None
                return ExecutionResult(
                    return_code=-1,
                    exec_time=elapsed,
                    crashed=False,
                    timeout=True,
                    stderr=b'Execution timeout',
                    coverage=coverage
                )

            elapsed = time.perf_counter() - start_time

            # 读取覆盖率
            coverage = self.shm.read_bitmap() if self.shm else None

            # 判断是否崩溃
            crashed = (proc.returncode < 0  # Python subprocess signal
                    or proc.returncode >= 128)  # Shell signal convention (128 + signal)

            # 刷新并关闭文件句柄，确保内容写入磁盘
            stdout_f.close()
            stderr_f.close()

            # 从文件读取 stderr（避免内存溢出）
            stderr_max = CONFIG.get('stderr_max_len', 1000)
            stderr_content = b''
            try:
                # 读取前 N 字节
                with open(stderr_path, 'rb') as f:
                    stderr_content = f.read(stderr_max)
            except Exception:
                pass

            return ExecutionResult(
                return_code=proc.returncode,
                exec_time=elapsed,
                crashed=crashed,
                timeout=False,
                stderr=stderr_content,
                coverage=coverage
            )

        except Exception as e:
            # 确保清理子进程
            if proc is not None and proc.poll() is None:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    proc.wait(timeout=1)
                except Exception:
                    pass

            elapsed = time.perf_counter() - start_time
            stderr_max = CONFIG.get('stderr_max_len', 1000)
            return ExecutionResult(
                return_code=-1,
                exec_time=elapsed,
                crashed=True,
                timeout=False,
                stderr=str(e).encode()[:stderr_max],
                coverage=None
            )
        finally:
            # 确保清理残留进程（防止僵尸进程/后台进程泄漏）
            # 无论正常退出还是异常，都尝试清理进程组
            if proc:
                try:
                    # 使用 killpg 杀死整个进程组
                    # 由于 preexec_fn=os.setsid，pgid 通常等于 pid
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

            # 确保文件句柄关闭（包括超时和异常情况）
            if stdout_f and not stdout_f.closed: stdout_f.close()
            if stderr_f and not stderr_f.closed: stderr_f.close()

            # 关闭可能打开的 stdin 文件句柄
            stdin_f = popen_args.get('stdin') if 'popen_args' in locals() else None
            # 注意：如果 stdin_f 是 subprocess.PIPE/DEVNULL 等常量，没有 closed 属性
            # 但我们在代码中只传入了真实的文件对象或 None
            if stdin_f and hasattr(stdin_f, 'closed') and not stdin_f.closed:
                 stdin_f.close()

    def cleanup(self):
        """清理临时文件和 SHM"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            if self.shm:
                self.shm.cleanup()
                self.shm = None
        except Exception as e:
            print(f"[Executor] Cleanup warning: {e}")

    def __del__(self):
        """析构时自动清理"""
        self.cleanup()


# ========== 测试代码 ==========
if __name__ == '__main__':
    # 简单测试
    test_program = '/bin/cat'
    test_args = 'cat @@'

    executor = TestExecutor(test_program, test_args, timeout=5)

    # 执行测试
    result = executor.execute(b'Hello, Fuzzer!\n')

    print(f"Return Code: {result['return_code']}")
    print(f"Exec Time: {result['exec_time']:.3f}s")
    print(f"Crashed: {result['crashed']}")
    print(f"Timeout: {result.get('timeout', False)}")

    executor.cleanup()
