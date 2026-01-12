"""
测试执行组件 (Component 1/6)
职责：执行目标程序，获取返回值、执行时间、覆盖率等信息
"""

import subprocess
import tempfile
import time
import os
import resource
from typing import Dict, Optional
from config import CONFIG
from utils import AFLSHM


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

    def execute(self, input_data: bytes) -> Dict:
        """
        执行目标程序

        Args:
            input_data: 输入数据（字节）

        Returns:
            {
                'return_code': int,        # 返回码
                'exec_time': float,        # 执行时间（秒）
                'crashed': bool,           # 是否崩溃
                'timeout': bool,           # 是否超时
                'stderr': bytes,           # 标准错误输出（截断）
                'coverage': bytes or None  # 覆盖率 bitmap（如果启用）
            }
        """
        # 清空 SHM bitmap
        if self.shm:
            self.shm.clear()

        # 写入输入文件
        try:
            with open(self.input_file, 'wb') as f:
                f.write(input_data)
        except Exception as e:
            return {
                'return_code': -1,
                'exec_time': 0.0,
                'crashed': True,
                'timeout': False,
                'stderr': f"Failed to write input: {str(e)}".encode(),
                'coverage': None
            }

        # 替换命令中的 @@ 为输入文件路径
        if '@@' in self.target_args:
            cmd = self.target_args.replace('@@', self.input_file)
        else:
            # 如果没有 @@，则通过 stdin 传递输入
            cmd = f"{self.target_args} < {self.input_file}"

        # 准备环境变量
        env = os.environ.copy()
        if self.shm:
            env['__AFL_SHM_ID'] = str(self.shm.get_shm_id())
            # 关键：禁用 Forkserver，强制直接执行并写入 SHM
            env['AFL_NO_FORKSRV'] = '1'

        # 准备内存限制函数
        def set_limits():
            # 设置内存限制（仅限 Linux/Unix）
            if hasattr(resource, 'RLIMIT_AS'):
                mem_bytes = CONFIG.get('mem_limit', 256) * 1024 * 1024  # MB -> bytes
                resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # 创建新进程组（用于信号处理）
            if hasattr(os, 'setsid'):
                os.setsid()

        # 执行目标程序
        start_time = time.perf_counter()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                timeout=self.timeout,
                capture_output=True,
                # cwd=os.path.dirname(self.target_path), # 移除 cwd 切换，避免相对路径问题
                env=env,  # 传递环境变量
                preexec_fn=set_limits
            )
            elapsed = time.perf_counter() - start_time

            # 读取覆盖率
            coverage = self.shm.read_bitmap() if self.shm else None

            # 判断是否崩溃
            crashed = (result.returncode < 0 # Python subprocess signal
                    or result.returncode >= 128) # Shell signal convention (128 + signal)

            stderr_max = CONFIG.get('stderr_max_len', 1000)
            return {
                'return_code': result.returncode,
                'exec_time': elapsed,
                'crashed': crashed,
                'timeout': False,
                'stderr': result.stderr[:stderr_max] if result.stderr else b'',
                'coverage': coverage
            }

        except subprocess.TimeoutExpired:
            elapsed = time.perf_counter() - start_time
            return {
                'return_code': -1,
                'exec_time': elapsed,
                'crashed': False,
                'timeout': True,
                'stderr': b'Execution timeout',
                'coverage': None
            }

        except Exception as e:
            elapsed = time.perf_counter() - start_time
            stderr_max = CONFIG.get('stderr_max_len', 1000)
            return {
                'return_code': -1,
                'exec_time': elapsed,
                'crashed': True,
                'timeout': False,
                'stderr': str(e).encode()[:stderr_max],
                'coverage': None
            }

    def cleanup(self):
        """清理临时文件和 SHM"""
        try:
            if os.path.exists(self.input_file):
                os.remove(self.input_file)
            if os.path.exists(self.temp_dir):
                os.rmdir(self.temp_dir)
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
