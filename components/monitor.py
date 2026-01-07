"""
执行结果监控组件 (Component 2/6)
职责：分析执行结果，检测崩溃、保存有趣的测试用例

更新版（覆盖率引导）：基于覆盖率增量筛选有趣的输入
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

from config import CONFIG

class ExecutionMonitor:
    """
    执行结果监控器
    记录崩溃、统计数据、追踪覆盖率
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

        # 全局覆盖率 bitmap（累积所有发现的边）
        self.global_coverage: Optional[bytearray] = None
        if use_coverage:
            from config import CONFIG
            bitmap_size = CONFIG.get('bitmap_size', 65536)
            self.global_coverage = bytearray(bitmap_size)

        # 统计数据
        self.stats = {
            'total_execs': 0,
            'total_crashes': 0,
            'total_hangs': 0,
            'unique_crashes': set(),
            'unique_hangs': set(),
            'start_time': datetime.now().isoformat(),
            'interesting_inputs': 0,
            'total_coverage_bits': 0
        }

        mode = "coverage-guided" if use_coverage else "blind"
        print(f"[Monitor] Initialized ({mode}). Output dir: {self.output_dir}")

    def process_execution(self, input_data: bytes, exec_result: Dict) -> bool:
        """
        处理一次执行结果

        Args:
            input_data: 输入数据
            exec_result: 执行结果（来自 executor）

        Returns:
            是否是有趣的执行（新覆盖率、崩溃或其他异常）
        """
        self.stats['total_execs'] += 1

        is_interesting = False

        # 检测崩溃
        if exec_result.get('crashed', False):
            self._handle_crash(input_data, exec_result)
            is_interesting = True

        # 检测超时（hang）
        if exec_result.get('timeout', False):
            self._handle_hang(input_data, exec_result)
            is_interesting = True

        # 检测新覆盖率
        if self.use_coverage and exec_result.get('coverage'):
            has_new_coverage = self._update_coverage(exec_result['coverage'])
            if has_new_coverage:
                self._save_interesting(input_data, 'new_coverage')
                is_interesting = True

        return is_interesting

    def _update_coverage(self, coverage_bitmap: bytes) -> bool:
        """
        更新全局覆盖率

        Args:
            coverage_bitmap: 本次执行的覆盖率

        Returns:
            是否发现了新的覆盖
        """
        if not self.global_coverage:
            return False

        has_new = False
        for i, byte_val in enumerate(coverage_bitmap):
            if byte_val != 0:
                # 如果全局 bitmap 中这个位置之前是0，现在变成非0，说明是新边
                if self.global_coverage[i] == 0:
                    has_new = True
                # 更新全局 bitmap
                self.global_coverage[i] |= byte_val

        if has_new:
            # 重新计算总覆盖位数
            self.stats['total_coverage_bits'] = sum(
                b.bit_count() for b in self.global_coverage
            )

        return has_new

    def _handle_crash(self, input_data: bytes, exec_result: Dict):
        """处理崩溃"""
        # 计算崩溃的哈希（用于去重）
        stderr = exec_result.get('stderr', b'')
        if isinstance(stderr, str):
            stderr = stderr.encode()

        crash_hash = hashlib.blake2s(stderr, digest_size=8).hexdigest()[:8]

        # 检测是否是新的崩溃
        if crash_hash not in self.stats['unique_crashes']:
            self.stats['unique_crashes'].add(crash_hash)
            self.stats['total_crashes'] = len(self.stats['unique_crashes'])

            # 保存崩溃输入
            crash_id = self.stats['total_execs']
            filename = f"crash_{crash_id}_{crash_hash}"
            crash_file = self.crashes_dir / filename

            crash_file.write_bytes(input_data)

            # 保存崩溃信息
            info_file = self.crashes_dir / f"{filename}.json"
            from config import CONFIG
            max_len = CONFIG.get('crash_info_max_len', 500)
            info = {
                'exec_id': crash_id,
                'hash': crash_hash,
                'return_code': exec_result.get('return_code'),
                'exec_time': exec_result.get('exec_time'),
                'stderr': stderr.decode('utf-8', errors='ignore')[:max_len]
            }
            info_file.write_text(json.dumps(info, indent=2))

            print(f"[Monitor] New CRASH found! ({self.stats['total_crashes']} unique)")

    def _handle_hang(self, input_data: bytes, exec_result: Dict):
        """处理超时（hang）"""
        # 计算 hang 的哈希（基于输入数据，因为 hang 通常没有 stderr）
        hang_hash = hashlib.blake2s(input_data).hexdigest()[:8]

        # 检测是否是新的 hang
        if hang_hash not in self.stats['unique_hangs']:
            self.stats['unique_hangs'].add(hang_hash)
            self.stats['total_hangs'] = len(self.stats['unique_hangs'])

            # 保存 hang 输入
            hang_id = self.stats['total_execs']
            filename = f"hang_{hang_id}_{hang_hash}"
            hang_file = self.hangs_dir / filename

            hang_file.write_bytes(input_data)

            # 保存 hang 信息
            info_file = self.hangs_dir / f"{filename}.json"
            info = {
                'exec_id': hang_id,
                'hash': hang_hash,
                'exec_time': exec_result.get('exec_time'),
                'timeout': CONFIG['timeout'],
                'input_size': len(input_data)
            }
            info_file.write_text(json.dumps(info, indent=2))

            print(f"[Monitor] New HANG found! ({self.stats['total_hangs']} unique)")

    def _save_interesting(self, input_data: bytes, reason: str):
        """保存有趣的输入（非崩溃但值得关注）"""
        self.stats['interesting_inputs'] += 1

        filename = f"{reason}_{self.stats['total_execs']}"
        queue_file = self.queue_dir / filename
        queue_file.write_bytes(input_data)

    def get_current_stats(self) -> Dict:
        """获取当前统计信息"""
        return {
            'total_execs': self.stats['total_execs'],
            'total_crashes': self.stats['total_crashes'],
            'total_hangs': self.stats['total_hangs'],
            'interesting_inputs': self.stats['interesting_inputs'],
            'start_time': self.stats['start_time']
        }

    def save_stats_to_file(self):
        """保存统计信息到文件"""
        stats_file = self.output_dir / 'stats.json'

        # 转换 set 为 list 以便 JSON 序列化
        exportable_stats = {
            'total_execs': self.stats['total_execs'],
            'total_crashes': self.stats['total_crashes'],
            'total_hangs': self.stats['total_hangs'],
            'unique_crashes': list(self.stats['unique_crashes']),
            'unique_hangs': list(self.stats['unique_hangs']),
            'start_time': self.stats['start_time'],
            'end_time': datetime.now().isoformat(),
            'interesting_inputs': self.stats['interesting_inputs']
        }

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
        normal_result = {
            'return_code': 0,
            'exec_time': 0.01,
            'crashed': False,
            'timeout': False
        }
        monitor.process_execution(b'normal input', normal_result)

        # 模拟崩溃
        crash_result = {
            'return_code': -11,
            'exec_time': 0.02,
            'crashed': True,
            'stderr': b'Segmentation fault'
        }
        monitor.process_execution(b'crash input', crash_result)

        # 打印统计
        stats = monitor.get_current_stats()
        print(f"\nStats: {stats}")

        # 保存统计
        monitor.save_stats_to_file()

    finally:
        # 清理
        shutil.rmtree(temp_dir)
        print(f"Cleaned up {temp_dir}")
