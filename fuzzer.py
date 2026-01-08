"""
模糊器主程序
集成所有 6 个组件，实现核心模糊测试循环
"""

import os
import sys
import time
import signal
from pathlib import Path

from config import CONFIG
from components.executor import TestExecutor
from components.monitor import ExecutionMonitor
from components.scheduler import SeedScheduler
from components.mutator import Mutator
from components.evaluator import Evaluator
from utils import count_coverage_bits


class Fuzzer:
    """
    覆盖率引导的变异式模糊器
    """

    def __init__(self, target_id: str, target_path: str, target_args: str,
                 seed_dir: str, output_dir: str):
        """
        初始化模糊器

        Args:
            target_id: 目标ID（如 't01'）
            target_path: 目标程序路径
            target_args: 命令行参数模板
            seed_dir: 初始种子目录
            output_dir: 输出目录
        """
        self.target_id = target_id
        self.target_path = target_path
        self.target_args = target_args

        # 初始化各组件
        self.executor = TestExecutor(
            target_path,
            target_args,
            timeout=CONFIG['timeout'],
            use_coverage=True  # 启用覆盖率
        )
        self.monitor = ExecutionMonitor(output_dir, use_coverage=True)
        self.scheduler = SeedScheduler()
        self.evaluator = Evaluator(output_dir)

        # 统计信息
        self.start_time = time.time()
        self.last_snapshot_time = self.start_time
        self.last_coverage = 0
        self.last_execs = 0  # 上次统计的执行次数
        self.seed_dir = Path(seed_dir)

        # 信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """处理中断信号"""
        print("\n[!] Fuzzer interrupted, saving results...")
        self._finalize()
        sys.exit(0)

    def _process_seed(self, seed_data: bytes, is_initial: bool = False) -> bool:
        """
        执行并处理种子的通用方法

        Args:
            seed_data: 种子数据
            is_initial: 是否是初始种子

        Returns:
            是否成功处理（未超过大小限制且成功执行）
        """
        # 检查种子大小
        if len(seed_data) > CONFIG['max_seed_size']:
            return False

        # 执行种子
        exec_result = self.executor.execute(seed_data)

        # 监控执行结果（检测崩溃/hang/新覆盖率）
        is_interesting = self.monitor.process_execution(seed_data, exec_result)

        # 决定是否加入种子队列
        should_add = is_initial or is_interesting  # 初始种子总是加入，变异种子仅在有趣时加入

        if should_add:
            coverage_bits = count_coverage_bits(exec_result.get('coverage'))
            self.scheduler.add_seed(seed_data, coverage_bits, exec_result['exec_time'])

        # 更新统计并打印新覆盖率
        if is_interesting:
            stats = self.monitor.stats
            if stats['total_coverage_bits'] > self.last_coverage:
                print(f"[+] New coverage: {stats['total_coverage_bits']} bits")
                self.last_coverage = stats['total_coverage_bits']

        # 定期输出统计信息和快照 (基于时间间隔)
        if time.time() - self.last_snapshot_time >= CONFIG['log_interval']:
            self._update_stats()

        return True

    def load_initial_seeds(self):
        """加载初始种子"""
        if not self.seed_dir.exists():
            print(f"[!] Seed directory not found: {self.seed_dir}")
            print("[*] Creating empty seed...")
            # 创建一个空种子
            self.scheduler.add_seed(b'', 0, 0.1)
            return

        # 递归寻找所有的文件作为种子（followlinks=True 自动处理符号链接）
        seed_files = []
        for dirpath, _, filenames in os.walk(self.seed_dir, followlinks=True):
            for filename in filenames:
                seed_files.append(Path(dirpath) / filename)

        if not seed_files:
            print(f"[!] No seeds found in {self.seed_dir}")
            self.scheduler.add_seed(b'', 0, 0.1)
            return

        print(f"[+] Loading {len(seed_files)} initial seeds...")

        # 使用队列总大小限制，让 scheduler 自动管理队列
        max_seeds = CONFIG.get('max_seeds', 10000)
        for seed_file in seed_files[:max_seeds]:
            if not seed_file.is_file():
                continue
            try:
                seed_data = seed_file.read_bytes()
                # 使用统一的种子处理方法
                self._process_seed(seed_data, is_initial=True)
            except Exception as e:
                print(f"[!] Error loading seed {seed_file}: {e}")
                continue

        print(f"[+] Loaded {len(self.scheduler.seeds)} seeds")

    def fuzz_loop(self, duration_seconds: int = 3600):
        """
        主模糊循环 - 模糊测试的核心工作流程

        工作流程：
        1. 加载初始种子集合，并执行一遍以获取初始覆盖率
        2. 进入主循环（持续到超时或用户中断）：
           a. 从调度器中选择能量最高的种子（O(log n) 堆操作）
           b. 根据种子能量决定变异次数（1-16次）
           c. 对每次变异：
              - 使用 Havoc 策略生成变异体
              - 执行变异体并收集覆盖率
              - 如果发现新覆盖率或崩溃，保存到队列
              - 将有价值的变异体加入种子库
           d. 定期输出统计信息和保存快照
        3. 测试结束后，生成报告和可视化图表

        Args:
            duration_seconds: 模糊测试持续时间（秒）
        """
        print(f"[+] Starting fuzzing on {self.target_id}...")
        print(f"[*] Duration: {duration_seconds}s ({duration_seconds/3600:.1f}h)")
        print(f"[*] Target: {self.target_path}")
        print(f"[*] Args: {self.target_args}")
        print()

        # 先加载并处理初始种子
        self.load_initial_seeds()

        iteration = 0
        while time.time() - self.start_time < duration_seconds:
            iteration += 1

            # 1. 选择种子
            seed = self.scheduler.select_next()
            if seed is None:
                print("[!] No seed to fuzz")
                break

            # 2. 执行变异和测试（能量已经在种子中计算）
            # 每个种子执行多次变异（基于能量，但限制在合理范围）
            energy = max(1, min(16, int(seed.energy)))
            for _ in range(energy):
                # 变异（使用配置的 havoc 迭代次数）
                iterations = CONFIG.get('havoc_iterations', 16)
                mutant = Mutator.mutate(seed.data, 'havoc', iterations=iterations)

                # 使用统一的种子处理方法（变异种子仅在有趣时加入队列）
                self._process_seed(mutant)

        # 模糊测试完成
        self._finalize()

    def _update_stats(self):
        """更新统计信息（输出日志并保存快照）"""
        current_time = time.time()
        elapsed_total = current_time - self.start_time
        elapsed_recent = current_time - self.last_snapshot_time

        stats = self.monitor.stats

        # 计算近期执行速率（自上次更新以来）
        recent_execs = stats['total_execs'] - self.last_execs
        exec_rate = recent_execs / elapsed_recent if elapsed_recent > 0 else 0

        # 输出进度日志
        hours = int(elapsed_total // 3600)
        minutes = int((elapsed_total % 3600) // 60)
        seconds = int(elapsed_total % 60)

        print(f"[*] Time: {hours}:{minutes:02d}:{seconds:02d} | "
              f"Execs: {stats['total_execs']:8d} | "
              f"Rate: {exec_rate:6.1f}/s | "
              f"Coverage: {stats['total_coverage_bits']:5d} | "
              f"Crashes: {stats['total_crashes']:3d} | "
              f"Hangs: {stats['total_hangs']:3d}")

        # 保存快照数据
        self.evaluator.record(
            total_execs=stats['total_execs'],
            exec_rate=exec_rate,
            total_crashes=stats['total_crashes'],
            total_hangs=stats['total_hangs'],
            coverage=stats['total_coverage_bits']
        )

        # 更新追踪变量
        self.last_snapshot_time = current_time
        self.last_execs = stats['total_execs']

    def _finalize(self):
        """完成模糊测试，保存结果"""
        print("\n[+] Finalizing...")

        # 保存最后的统计数据
        self.monitor.save_stats_to_file()

        # 生成报告
        elapsed = time.time() - self.start_time
        stats = self.monitor.stats
        final_report = {
            'target_id': self.target_id,
            'target_path': self.target_path,
            'duration': elapsed,
            'total_execs': stats['total_execs'],
            'total_crashes': stats['total_crashes'],
            'total_hangs': stats['total_hangs'],
            'unique_crashes': len(stats['unique_crashes']),
            'unique_hangs': len(stats['unique_hangs']),
            'total_coverage_bits': stats['total_coverage_bits'],
            'total_seeds': len(self.scheduler.seeds),
            'exec_rate': stats['total_execs'] / elapsed if elapsed > 0 else 0
        }
        self.evaluator.save_final_report(final_report)

        # 生成可视化图表
        print("[*] Generating visualizations...")
        self.evaluator.generate_plots()

        print(f"[+] Results saved to {self.monitor.output_dir}")

    def cleanup(self):
        """清理资源"""
        self.executor.cleanup()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Fuzzer for mutation-based fuzzing',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # 必选参数
    parser.add_argument('--target', required=True, help='Target program path')
    parser.add_argument('--args', required=True, help='Target program arguments')
    parser.add_argument('--seeds', required=True, help='Seed directory')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--duration', type=int, default=3600, help='Fuzzing duration (seconds)')
    parser.add_argument('--target-id', default='unknown', help='Target ID')

    # CONFIG 参数覆盖
    parser.add_argument('--timeout', type=float, help='Execution timeout (seconds)')
    parser.add_argument('--mem-limit', type=int, help='Memory limit for target (MB)')
    parser.add_argument('--bitmap-size', type=int, help='Coverage bitmap size')
    parser.add_argument('--max-seed-size', type=int, help='Max seed size (bytes) for initial and mutated seeds')
    parser.add_argument('--havoc-iterations', type=int, help='Havoc mutation iterations (higher = more mutations)')
    parser.add_argument('--seed-sort-strategy', choices=['energy', 'fifo'], help='Seed scheduling strategy')
    parser.add_argument('--max-seeds', type=int, help='Max seed count')
    parser.add_argument('--max-seeds-memory', type=int, help='Max seed set memory (MB)')
    parser.add_argument('--log-interval', type=int, help='Log update interval (seconds)')
    parser.add_argument('--stderr-max-len', type=int, help='Max stderr length (bytes)')
    parser.add_argument('--crash-info-max-len', type=int, help='Max crash info stderr length (bytes)')

    args = parser.parse_args()

    # 用命令行参数覆盖 CONFIG
    if args.timeout is not None:
        CONFIG['timeout'] = args.timeout
    if args.mem_limit is not None:
        CONFIG['mem_limit'] = args.mem_limit
    if args.bitmap_size is not None:
        CONFIG['bitmap_size'] = args.bitmap_size
    if args.havoc_iterations is not None:
        CONFIG['havoc_iterations'] = args.havoc_iterations
    if args.seed_sort_strategy is not None:
        CONFIG['seed_sort_strategy'] = args.seed_sort_strategy
    if args.max_seed_size is not None:
        CONFIG['max_seed_size'] = args.max_seed_size
    if args.max_seeds is not None:
        CONFIG['max_seeds'] = args.max_seeds
    if args.max_seeds_memory is not None:
        CONFIG['max_seeds_memory'] = args.max_seeds_memory
    if args.log_interval is not None:
        CONFIG['log_interval'] = args.log_interval
    if args.stderr_max_len is not None:
        CONFIG['stderr_max_len'] = args.stderr_max_len
    if args.crash_info_max_len is not None:
        CONFIG['crash_info_max_len'] = args.crash_info_max_len

    # 创建模糊器
    fuzzer = Fuzzer(
        target_id=args.target_id,
        target_path=args.target,
        target_args=args.args,
        seed_dir=args.seeds,
        output_dir=args.output
    )

    try:
        # 运行模糊测试
        fuzzer.fuzz_loop(duration_seconds=args.duration)
    finally:
        fuzzer.cleanup()


if __name__ == '__main__':
    main()
