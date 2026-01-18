"""
执行结果监控组件 (Component 2/6)
职责：分析执行结果，检测崩溃、保存有趣的测试用例

更新版（覆盖率引导）：基于覆盖率增量筛选有趣的输入

参考 AFL++ 实现:
- virgin_bits: 未被正常执行触发的路径
- virgin_crash: 未被 crash 触发的路径
- virgin_tmout: 未被 timeout 触发的路径
- simplify_trace: 简化覆盖率（只保留 0/非0）
- has_new_bits: 检查是否有新路径

类型安全设计：
- 使用 MonitorStats (dataclass) 管理统计数据
- 自动生成 to_dict() / update_from_dict() 方法
- STATS_FIELDS 自动从 dataclass 提取，无需手动同步

详见：docs/DESIGN.md（“字段一致性与类型安全”）
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict, fields

from config import CONFIG
from .executor import ExecutionResult


# ========== 数据结构定义 ==========
# 使用 dataclass 确保字段一致性，自动生成访问方法
@dataclass
class MonitorStats:
    """监控统计数据结构"""
    total_execs: int = 0
    total_crashes: int = 0
    total_hangs: int = 0
    saved_crashes: int = 0
    saved_hangs: int = 0
    start_time: str = ''  # ISO format
    interesting_inputs: int = 0
    total_coverage_bits: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    def update_from_dict(self, data: dict):
        """从字典更新字段"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

# 导出字段名称元组（兼容旧代码）
STATS_FIELDS = tuple(f.name for f in fields(MonitorStats))

# Monitor bitmap 字段
BITMAP_FIELDS = ('virgin_bits', 'virgin_crash', 'virgin_tmout')


# AFL++ 风格的 simplify lookup table
# 0 -> 1 (未命中), 1-255 -> 128 (命中)
SIMPLIFY_LOOKUP = bytes([1] + [128] * 255)


class ExecutionMonitor:
    """
    执行结果监控器
    记录崩溃、统计数据、追踪覆盖率

    参考 AFL++ 的 afl-fuzz-bitmap.c 实现
    """

    def __init__(self, output_dir: str, use_coverage: bool = False):
        """
        初始化监控器

        Args:
            output_dir: 输出目录
            use_coverage: 是否启用覆盖率引导
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.use_coverage = use_coverage

        # 子目录
        self.crashes_dir = self.output_dir / 'crashes'
        self.hangs_dir = self.output_dir / 'hangs'
        self.queue_dir = self.output_dir / 'queue'
        self.crashes_dir.mkdir(exist_ok=True)
        self.hangs_dir.mkdir(exist_ok=True)
        self.queue_dir.mkdir(exist_ok=True)

        # AFL++ 风格的 virgin bitmaps
        # 初始值全为 0xFF，表示所有路径都"未被触发"
        bitmap_size = CONFIG.get('bitmap_size', 65536)

        if use_coverage:
            # virgin_bits: 正常执行未触发的路径
            self.virgin_bits: Optional[bytearray] = bytearray([0xFF] * bitmap_size)
            # virgin_crash: crash 未触发的路径（用于 crash 去重）
            self.virgin_crash: Optional[bytearray] = bytearray([0xFF] * bitmap_size)
            # virgin_tmout: timeout 未触发的路径（用于 hang 去重）
            self.virgin_tmout: Optional[bytearray] = bytearray([0xFF] * bitmap_size)
        else:
            self.virgin_bits = None
            self.virgin_crash = None
            self.virgin_tmout = None

        # 用于无覆盖率时的 hash 去重（fallback）
        self._crash_hashes: set[int] = set()
        self._hang_hashes: set[int] = set()

        # 覆盖率计算缓存（性能优化）
        self._coverage_cache: dict[int, int] = {}

        # 统计数据（使用 dataclass）
        self.stats = MonitorStats(start_time=datetime.now().isoformat())

        # 验证 bitmap 属性存在
        for field in BITMAP_FIELDS:
            assert hasattr(self, field), f"Missing bitmap attribute: {field}"

        mode = "coverage-guided" if use_coverage else "blind"
        print(f"[Monitor] Initialized ({mode}). Output dir: {self.output_dir}")

    def process_execution(self, input_data: bytes, exec_result: ExecutionResult) -> bool:
        """
        处理一次执行结果

        Args:
            input_data: 输入数据
            exec_result: 执行结果（来自 executor）

        Returns:
            是否是有趣的执行（新覆盖率、崩溃或其他异常）
        """
        self.stats.total_execs += 1

        is_interesting = False

        # 检测崩溃
        if exec_result.get('crashed', False):
            if self._handle_crash(input_data, exec_result):
                is_interesting = True

        # 检测超时（hang）
        elif exec_result.get('timeout', False):
            if self._handle_hang(input_data, exec_result):
                is_interesting = True

        # 检测新覆盖率（仅正常执行）
        elif self.use_coverage:
            coverage = exec_result.get('coverage')
            if coverage and self._has_new_bits(coverage, self.virgin_bits):
                self._save_interesting(input_data, 'new_coverage')
                is_interesting = True

        return is_interesting

    @staticmethod
    def _simplify_trace(trace: bytes) -> bytearray:
        """
        简化覆盖率 trace，参考 AFL++ simplify_trace

        将命中次数信息转换为简单的 0/非0：
        - 0 -> 1 (用于区分"从未命中")
        - 1-255 -> 128 (命中)
        """
        return bytearray(SIMPLIFY_LOOKUP[b] for b in trace)

    def _has_new_bits(self, trace: bytes, virgin: Optional[bytearray]) -> bool:
        """
        检查是否有新的覆盖位，参考 AFL++ has_new_bits

        Args:
            trace: 本次执行的覆盖率 bitmap
            virgin: virgin bitmap（未触发路径记录）

        Returns:
            是否发现了新路径
        """
        if virgin is None:
            return False

        has_new = False
        for i, byte_val in enumerate(trace):
            if byte_val != 0 and (virgin[i] & byte_val) != 0:
                # 发现新的边或新的命中次数
                has_new = True
                # 更新 virgin bitmap（清除已触发的位）
                virgin[i] &= ~byte_val

        if has_new and virgin is self.virgin_bits:
            # 重新计算总覆盖位数（仅对正常执行的 virgin_bits）
            # 计算已触发的位数 = 总位数 - 未触发位数
            self.stats.total_coverage_bits = sum(
                (0xFF ^ b).bit_count() for b in virgin
            )

        return has_new

    def _compute_hash(self, data: bytes) -> int:
        """计算64位整数哈希"""
        digest = hashlib.blake2s(data, digest_size=8).digest()
        return int.from_bytes(digest, byteorder='big')

    def _get_coverage_bits(self, coverage: Optional[bytes]) -> int:
        """
        获取覆盖率位数（带缓存）

        Args:
            coverage: 覆盖率 bitmap

        Returns:
            覆盖率位数
        """
        if not coverage:
            return 0

        # 使用哈希作为缓存键
        cache_key = hash(coverage)
        if cache_key in self._coverage_cache:
            return self._coverage_cache[cache_key]

        # 计算覆盖率
        from utils import count_coverage_bits
        bits = count_coverage_bits(coverage)

        # 缓存结果
        self._coverage_cache[cache_key] = bits

        # 限制缓存大小（防止内存溢出）
        if len(self._coverage_cache) > 10000:
            # 清空最旧的一半
            keys_to_remove = list(self._coverage_cache.keys())[:5000]
            for key in keys_to_remove:
                del self._coverage_cache[key]

        return bits

    def _handle_crash(self, input_data: bytes, exec_result: ExecutionResult) -> bool:
        """
        处理崩溃，参考 AFL++ save_if_interesting (FSRV_RUN_CRASH 分支)

        Returns:
            是否保存了新的 crash
        """
        self.stats.total_crashes += 1

        coverage = exec_result.get('coverage')
        stderr = exec_result.get('stderr', b'')
        if isinstance(stderr, memoryview):
            stderr = bytes(stderr)
        elif isinstance(stderr, str):
            stderr = stderr.encode('utf-8', errors='ignore')
        elif not isinstance(stderr, bytes):
            stderr = b''

        # AFL++ 策略：使用 simplify_trace + virgin_crash 去重
        if self.virgin_crash is not None and coverage:
            simplified = self._simplify_trace(coverage)
            if not self._has_new_bits(simplified, self.virgin_crash):
                # 没有新路径，跳过
                return False
        else:
            # Fallback：使用 hash 去重（无覆盖率时）
            data_to_hash = coverage if coverage else (stderr if stderr else input_data)
            crash_hash = self._compute_hash(data_to_hash)
            if crash_hash in self._crash_hashes:
                return False
            self._crash_hashes.add(crash_hash)

        # 保存新的 crash
        self.stats.saved_crashes += 1
        crash_id = self.stats.total_execs
        sig = abs(exec_result.get('return_code', 0))  # 信号编号

        filename = f"crash_{crash_id:06d}_sig{sig:02d}"
        crash_file = self.crashes_dir / filename
        crash_file.write_bytes(input_data)

        # 保存崩溃信息
        info_file = self.crashes_dir / f"{filename}.json"
        max_len = CONFIG.get('crash_info_max_len', 500)
        info = {
            'exec_id': crash_id,
            'signal': sig,
            'return_code': exec_result.get('return_code'),
            'exec_time': exec_result.get('exec_time'),
            'stderr': stderr.decode('utf-8', errors='ignore')[:max_len]
        }
        info_file.write_text(json.dumps(info, indent=2))

        print(f"[Monitor] New CRASH found! ({self.stats.saved_crashes} unique)")
        return True

    def _handle_hang(self, input_data: bytes, exec_result: ExecutionResult) -> bool:
        """
        处理超时（hang），参考 AFL++ save_if_interesting (FSRV_RUN_TMOUT 分支)

        Returns:
            是否保存了新的 hang
        """
        self.stats.total_hangs += 1

        coverage = exec_result.get('coverage')

        # AFL++ 策略：使用 simplify_trace + virgin_tmout 去重
        if self.virgin_tmout is not None and coverage:
            simplified = self._simplify_trace(coverage)
            if not self._has_new_bits(simplified, self.virgin_tmout):
                # 没有新路径，跳过
                return False
        else:
            # Fallback：使用 hash 去重（无覆盖率时）
            data_to_hash = coverage if coverage else input_data
            hang_hash = self._compute_hash(data_to_hash)
            if hang_hash in self._hang_hashes:
                return False
            self._hang_hashes.add(hang_hash)

        # 保存新的 hang
        self.stats.saved_hangs += 1
        hang_id = self.stats.total_execs

        filename = f"hang_{hang_id:06d}"
        hang_file = self.hangs_dir / filename
        hang_file.write_bytes(input_data)

        # 保存 hang 信息
        cov_hash = "no_coverage" if not coverage else f"{self._compute_hash(coverage):016x}"

        info_file = self.hangs_dir / f"{filename}.json"
        info = {
            'exec_id': hang_id,
            'exec_time': exec_result.get('exec_time'),
            'timeout': CONFIG['timeout'],
            'input_size': len(input_data),
            'coverage_hash': cov_hash,
        }
        info_file.write_text(json.dumps(info, indent=2))

        print(f"[Monitor] New HANG found! ({self.stats.saved_hangs} unique)")
        return True

    def _save_interesting(self, input_data: bytes, reason: str):
        """保存有趣的输入（非崩溃但值得关注）"""
        self.stats.interesting_inputs += 1

        filename = f"{reason}_{self.stats.total_execs}"
        queue_file = self.queue_dir / filename
        queue_file.write_bytes(input_data)

    def save_stats_to_file(self):
        """保存统计信息到文件"""
        stats_file = self.output_dir / 'stats.json'

        # 使用 dataclass 的 to_dict() 方法，自动包含所有字段
        exportable_stats = self.stats.to_dict()
        exportable_stats['end_time'] = datetime.now().isoformat()

        stats_file.write_text(json.dumps(exportable_stats, indent=2))
        print(f"[Monitor] Stats saved to {stats_file}")


# ========== 测试代码 ==========
if __name__ == '__main__':
    import tempfile
    import shutil

    # 创建临时输出目录
    temp_dir = tempfile.mkdtemp(prefix='monitor_test_')

    try:
        monitor = ExecutionMonitor(temp_dir)

        # 模拟正常执行
        normal_result: ExecutionResult = {
            'return_code': 0,
            'exec_time': 0.01,
            'crashed': False,
            'timeout': False,
            'stderr': b'',
            'coverage': None,
        }
        monitor.process_execution(b'normal input', normal_result)

        # 模拟崩溃
        crash_result: ExecutionResult = {
            'return_code': -11,
            'exec_time': 0.02,
            'crashed': True,
            'timeout': False,
            'stderr': b'Segmentation fault',
            'coverage': None,
        }
        monitor.process_execution(b'crash input', crash_result)

        # 打印统计
        print(f"\nStats: {monitor.stats.to_dict()}")

        # 保存统计
        monitor.save_stats_to_file()

    finally:
        # 清理
        shutil.rmtree(temp_dir)
        print(f"Cleaned up {temp_dir}")
