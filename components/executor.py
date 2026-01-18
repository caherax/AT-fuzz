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
from typing import TypedDict, Optional, Any
from config import CONFIG
from utils import AFLSHM
from logger import get_logger

logger = get_logger(__name__)


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
        self.timeout = timeout if timeout is not None else CONFIG['timeout']
        self.use_coverage = use_coverage

        # 沙箱配置（使用 bubblewrap）
        self.use_sandbox = CONFIG['use_sandbox']
        if not self.use_sandbox:
            self.bwrap_path = None
        else:
            self.bwrap_path = shutil.which('bwrap')
            if not self.bwrap_path:
                raise RuntimeError(
                    "[Executor] ERROR: --use-sandbox enabled but 'bwrap' not found. "
                    "Please install bubblewrap or disable sandbox mode."
                )
            logger.info(f"Sandbox enabled: {self.bwrap_path}")

        # 使用 /tmp 作为临时目录
        self.temp_dir = tempfile.mkdtemp(prefix='fuzz_', dir='/tmp')
        self.input_file = os.path.join(self.temp_dir, 'input')

        # SHM 支持
        self.shm: Optional[AFLSHM] = None
        if use_coverage:
            bitmap_size = CONFIG['bitmap_size']
            self.shm = AFLSHM(bitmap_size=bitmap_size)
            logger.info(f"Coverage enabled, SHM ID: {self.shm.get_shm_id()}")

        # 验证目标程序存在
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"Target not found: {target_path}")

        logger.info(f"Initialized for {target_path}")
        logger.debug(f"Temp dir: {self.temp_dir}")

    def execute(self, input_data: bytes) -> ExecutionResult:
        """
        执行目标程序

        该方法通过子进程执行目标程序，收集其执行结果和覆盖率信息。
        支持文件输入（@@）和标准输入两种模式，可选启用沙箱隔离。

        工作流程：
            1. 清空共享内存中的覆盖率 bitmap
            2. 将输入数据写入临时文件
            3. 构建执行命令（替换 @@ 或使用 stdin）
            4. 配置环境变量（AFL_SHM_ID, AFL_NO_FORKSRV）
            5. 启动子进程（可选沙箱隔离）
            6. 等待执行完成或超时
            7. 收集覆盖率和错误信息

        Args:
            input_data: 输入测试数据（字节串）

        Returns:
            ExecutionResult: 包含以下字段的字典：
                - return_code (int): 进程返回码，崩溃时为负信号值
                - exec_time (float): 执行时间（秒）
                - crashed (bool): 是否崩溃（非零返回码或信号终止）
                - timeout (bool): 是否超时
                - stderr (bytes): 标准错误输出（截断到 stderr_max_len）
                - coverage (Optional[bytes]): 覆盖率 bitmap（如启用）

        Raises:
            不抛出异常，所有错误都封装在返回的 ExecutionResult 中

        Example:
            >>> executor = TestExecutor("/bin/cat", "cat @@", timeout=1.0)
            >>> result = executor.execute(b"Hello, World!")
            >>> print(result['return_code'])
            0
            >>> print(result['crashed'])
            False

        Note:
            - 沙箱模式需要 bubblewrap 工具（apt install bubblewrap）
            - 覆盖率收集需要目标程序使用 AFL++ 编译器插桩
            - 共享内存限制为 64KB (CONFIG['bitmap_size'])
        """
        # 1. 清空 SHM bitmap
        self._clear_shm_bitmap()

        # 2. 写入输入文件
        write_result = self._write_input_file(input_data)
        if write_result is not None:
            return write_result  # 写入失败，返回错误

        # 3. 准备命令和环境
        cmd, popen_args, popen_stdin, env = self._prepare_execution_context()

        # 4. 执行目标程序
        return self._execute_target(cmd, env, popen_args, popen_stdin)

    def _clear_shm_bitmap(self) -> None:
        """清空共享内存中的覆盖率 bitmap"""
        if self.shm:
            self.shm.clear()

    def _write_input_file(self, input_data: bytes) -> Optional[ExecutionResult]:
        """
        写入输入数据到临时文件

        Args:
            input_data: 输入数据

        Returns:
            如果写入失败，返回错误的 ExecutionResult；否则返回 None
        """
        try:
            with open(self.input_file, 'wb') as f:
                f.write(input_data)
            return None  # 写入成功
        except Exception as e:
            return ExecutionResult(
                return_code=-1,
                exec_time=0.0,
                crashed=True,
                timeout=False,
                stderr=f"Failed to write input: {str(e)}".encode(),
                coverage=None
            )

    def _prepare_execution_context(self) -> tuple[str | list[str], dict, Optional[Any], dict]:
        """
        准备执行上下文（命令、参数、环境变量）

        Returns:
            (cmd, popen_args, popen_stdin, env) 四元组
        """
        # 准备环境变量
        env = os.environ.copy()
        if self.shm:
            env['__AFL_SHM_ID'] = str(self.shm.get_shm_id())
            env['AFL_NO_FORKSRV'] = '1'

        popen_args = {}
        popen_stdin = None

        if not self.use_sandbox:
            # 非沙箱模式
            if '@@' in self.target_args:
                cmd = self.target_args.replace('@@', self.input_file)
                popen_stdin = None
            else:
                # 标准输入模式：直接传递 stdin 句柄
                cmd = self.target_args
                popen_stdin = open(self.input_file, 'rb')

            popen_args['shell'] = True
            popen_args['stdin'] = popen_stdin

        else:
            # 沙箱模式：使用 bubblewrap
            sandbox_cmd = [
                self.bwrap_path,
                '--ro-bind', '/', '/',
                '--dev', '/dev',
                '--proc', '/proc',
                '--tmpfs', '/tmp',
                '--bind', os.path.dirname(self.target_path), os.path.dirname(self.target_path),
                '--bind', self.temp_dir, self.temp_dir,
                '--unshare-pid',
                '--die-with-parent',
                '--new-session'
            ]

            real_cmd_str = self.target_args.replace('@@', self.input_file)
            input_from_stdin = '@@' not in self.target_args

            full_cmd = sandbox_cmd + ['--', '/bin/sh', '-c', real_cmd_str]

            if input_from_stdin:
                popen_stdin = open(self.input_file, 'rb')
                real_cmd_str = self.target_args
                full_cmd = sandbox_cmd + ['--', '/bin/sh', '-c', real_cmd_str]

            cmd = full_cmd
            popen_args['shell'] = False
            popen_args['stdin'] = popen_stdin

        return cmd, popen_args, popen_stdin, env

    def _execute_target(
        self,
        cmd: str | list[str],
        env: dict,
        popen_args: dict,
        popen_stdin: Optional[Any]
    ) -> ExecutionResult:
        """
        执行目标程序并收集结果

        Args:
            cmd: 执行命令
            env: 环境变量
            popen_args: Popen 参数字典
            popen_stdin: 标准输入文件句柄

        Returns:
            ExecutionResult 字典
        """
        def set_limits():
            # 设置内存限制（目前仅在非沙箱模式下启用，避免限制 bwrap 自身导致行为偏差）
            if not self.use_sandbox and hasattr(resource, 'RLIMIT_AS'):
                mem_bytes = CONFIG['mem_limit'] * 1024 * 1024  # MB -> bytes
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
                stdout=stdout_f,    # 重定向到文件
                stderr=stderr_f,    # 重定向到文件
                cwd=self.temp_dir,  # 关键：隔离工作目录，防止污染项目根目录
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
            stderr_max = CONFIG['stderr_max_len']
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
            stderr_max = CONFIG['stderr_max_len']
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
            logger.warning(f"Cleanup warning: {e}")

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
