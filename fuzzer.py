"""
模糊器主程序
集成所有 6 个组件，实现核心模糊测试循环
"""

import os
import sys
import time
import json
import base64
import signal
import heapq
from pathlib import Path
from datetime import datetime, timezone

from config import CONFIG
from components.executor import TestExecutor
from components.monitor import ExecutionMonitor, STATS_FIELDS as MONITOR_STATS_FIELDS, BITMAP_FIELDS as MONITOR_BITMAP_FIELDS
from components.scheduler import SeedScheduler, SEED_FIELDS as SCHEDULER_SEED_FIELDS
from components.mutator import Mutator
from components.evaluator import Evaluator
from utils import count_coverage_bits


# ========== Checkpoint 字段定义 ==========
# 这些常量从各个模块导入，确保一致性
# 修改时必须同时更新对应模块中的定义

CHECKPOINT_VERSION = 2  # 版本号，用于检测不兼容的 checkpoint

# 从 monitor.py 导入的字段（用于 checkpoint）
# 注意：start_time 虽然在 MONITOR_STATS_FIELDS 中，但 checkpoint 只保存子集
CHECKPOINT_MONITOR_STATS_FIELDS = (
    'total_execs',
    'total_crashes',
    'total_hangs',
    'saved_crashes',
    'saved_hangs',
    'interesting_inputs',
    'start_time',
)

# 从 monitor.py 导入的 bitmap 字段
CHECKPOINT_MONITOR_BITMAP_FIELDS = MONITOR_BITMAP_FIELDS

# 从 scheduler.py 导入的 seed 字段
CHECKPOINT_SEED_FIELDS = SCHEDULER_SEED_FIELDS

# 启动时验证字段一致性
assert set(CHECKPOINT_MONITOR_STATS_FIELDS).issubset(set(MONITOR_STATS_FIELDS)), \
    f"CHECKPOINT_MONITOR_STATS_FIELDS contains fields not in MONITOR_STATS_FIELDS"
assert CHECKPOINT_MONITOR_BITMAP_FIELDS == MONITOR_BITMAP_FIELDS, \
    f"CHECKPOINT_MONITOR_BITMAP_FIELDS mismatch with MONITOR_BITMAP_FIELDS"
assert CHECKPOINT_SEED_FIELDS == SCHEDULER_SEED_FIELDS, \
    f"CHECKPOINT_SEED_FIELDS mismatch with SCHEDULER_SEED_FIELDS"


class Fuzzer:
    """
    覆盖率引导的变异式模糊器
    """

    def __init__(self, target_id: str, target_path: str, target_args: str,
                 seed_dir: str, output_dir: str,
                 checkpoint_path: str | None = None,
                 resume_from: str | None = None):
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
        self.checkpoint_dir = Path(checkpoint_path) if checkpoint_path else (Path(output_dir) / 'checkpoints')
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.resume_flag = bool(resume_from)
        self.pause_requested = False
        self.force_exit = False
        self._loaded_checkpoint = resume_from

        # 信号处理
        # SIGINT: 请求暂停并保存检查点（便于直接 Ctrl+C）
        signal.signal(signal.SIGINT, self._pause_handler)
        # SIGTERM: 仍旧走正常收尾
        signal.signal(signal.SIGTERM, self._signal_handler)

        # 如指定恢复文件，则加载检查点
        if self._loaded_checkpoint:
            self._load_checkpoint(Path(self._loaded_checkpoint))

    def _signal_handler(self, signum, frame):
        """处理中断信号"""
        print("\n[!] Fuzzer interrupted, saving results...")
        self._finalize()
        sys.exit(0)

    def _pause_handler(self, signum, frame):
        """收到 SIGINT 时请求暂停并保存检查点"""
        if self.pause_requested or self.force_exit:
            print("\n[!] Force exit...")
            sys.exit(1)
        print("\n[*] Pause requested (SIGINT). Will save checkpoint and exit...")
        self.pause_requested = True

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
                print(f"[+] New coverage: {stats['total_coverage_bits']}")
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

        # 先加载并处理初始种子（如果未从检查点恢复）
        if not self.resume_flag:
            self.load_initial_seeds()
        else:
            print("[*] Resumed from checkpoint, skip initial seed loading")

        iteration = 0
        while time.time() - self.start_time < duration_seconds:
            iteration += 1

            # 检查暂停请求
            if self.pause_requested:
                self._save_checkpoint(reason="pause")
                print("[+] Checkpoint saved. Exiting for pause.")
                break

            # 1. 选择种子
            seed = self.scheduler.select_next()
            if seed is None:
                print("[!] No seed to fuzz")
                break

            # 2. 执行变异和测试（能量已经在种子中计算）
            # 每个种子执行多次变异（基于能量，但限制在合理范围）
            energy = max(1, min(16, int(seed.energy)))
            for _ in range(energy):
                # 在内层循环中也检查暂停请求，快速响应
                if self.pause_requested:
                    break

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
              f"Crashes: {stats['saved_crashes']}/{stats['total_crashes']} | "
              f"Hangs: {stats['saved_hangs']}/{stats['total_hangs']}")

        # 保存快照数据
        self.evaluator.record(
            total_execs=stats['total_execs'],
            exec_rate=exec_rate,
            total_crashes=stats['total_crashes'],
            saved_crashes=stats['saved_crashes'],
            total_hangs=stats['total_hangs'],
            saved_hangs=stats['saved_hangs'],
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
            'saved_crashes': stats['saved_crashes'],
            'saved_hangs': stats['saved_hangs'],
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

    # ========== 检查点支持 ==========
    def _save_checkpoint(self, reason: str = "manual"):
        """保存当前状态到检查点

        注意：修改保存逻辑时，必须同步修改 _load_checkpoint 和顶部的 CHECKPOINT_* 常量
        """
        # 预先计算各部分的大小开销
        print("[*] Checkpoint size breakdown:")

        # 1. 种子队列大小
        total_seed_size = sum(len(s.data) for s in self.scheduler.seeds)
        print(f"  Seeds: {len(self.scheduler.seeds)} seeds, {total_seed_size} bytes")

        # 2. 覆盖率位图大小
        coverage_size = len(self.monitor.virgin_bits) if self.monitor.virgin_bits else 0
        print(f"  Coverage bitmap: {coverage_size} bytes")

        # 3. 构建 monitor stats（使用常量定义的字段）
        monitor_stats = {}
        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            assert field in self.monitor.stats, f"Missing monitor stats field: {field}"
            monitor_stats[field] = self.monitor.stats[field]

        # 4. 构建 monitor bitmaps（使用常量定义的字段）
        monitor_bitmaps = {}
        if self.monitor.use_coverage:
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                bitmap = getattr(self.monitor, field, None)
                assert bitmap is not None, f"Missing monitor bitmap: {field}"
                monitor_bitmaps[field] = base64.b64encode(bytes(bitmap)).decode()
        else:
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                monitor_bitmaps[field] = None

        # 5. 构建 seed 列表（使用常量定义的字段）
        seeds_list = []
        for s in self.scheduler.seeds:
            seed_dict = {}
            for field in CHECKPOINT_SEED_FIELDS:
                if field == 'data':
                    seed_dict[field] = base64.b64encode(s.data).decode()
                else:
                    seed_dict[field] = getattr(s, field)
            seeds_list.append(seed_dict)

        # 6. 构建完整状态字典
        state = {
            'version': CHECKPOINT_VERSION,
            'reason': reason,
            'target_id': self.target_id,
            'target_path': self.target_path,
            'target_args': self.target_args,
            'seed_dir': str(self.seed_dir),
            'output_dir': str(self.monitor.output_dir),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'config': CONFIG,
            'runtime': {
                'start_time': self.start_time,
                'last_snapshot_time': self.last_snapshot_time,
                'last_coverage': self.last_coverage,
                'last_execs': self.last_execs,
            },
            'monitor': {
                'stats': monitor_stats,
                **monitor_bitmaps,  # virgin_bits, virgin_crash, virgin_tmout
            },
            'scheduler': {
                'strategy': self.scheduler.strategy,
                'seeds': seeds_list,
                'total_exec_time': self.scheduler.total_exec_time,
                'total_coverage': self.scheduler.total_coverage,
                'total_memory': self.scheduler.total_memory,
                'fifo_index': self.scheduler.fifo_index,
            }
        }

        # 断言：验证所有必要字段都已保存
        assert 'monitor' in state and 'stats' in state['monitor'], "Missing monitor.stats in checkpoint"
        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            assert field in state['monitor']['stats'], f"Missing {field} in checkpoint monitor.stats"
        for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
            assert field in state['monitor'], f"Missing {field} in checkpoint monitor"

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 序列化并计算大小
        json_data = json.dumps(state, indent=2)
        json_size = len(json_data.encode('utf-8'))

        # Base64 编码开销估算
        b64_overhead = 0
        for s in self.scheduler.seeds:
            raw_size = len(s.data)
            b64_size = len(base64.b64encode(s.data).decode())
            b64_overhead += (b64_size - raw_size)
        if self.monitor.virgin_bits:
            raw_cov = len(self.monitor.virgin_bits)
            b64_cov = len(base64.b64encode(bytes(self.monitor.virgin_bits)).decode())
            b64_overhead += (b64_cov - raw_cov)

        print(f"  Base64 encoding overhead: {b64_overhead} bytes")
        print(f"  Final JSON size: {json_size} bytes")

        checkpoint_file.write_text(json_data)
        print(f"[*] Checkpoint saved to {checkpoint_file}")

    def _load_checkpoint(self, checkpoint_path: Path):
        """从检查点恢复状态

        注意：修改加载逻辑时，必须同步修改 _save_checkpoint 和顶部的 CHECKPOINT_* 常量
        """
        if not checkpoint_path.exists():
            print(f"[!] Checkpoint not found: {checkpoint_path}")
            return

        state = json.loads(checkpoint_path.read_text())
        version = state.get('version', 1)

        # 版本兼容性检查
        if version < 1 or version > CHECKPOINT_VERSION:
            print(f"[!] Unsupported checkpoint version: {version} (expected <= {CHECKPOINT_VERSION})")
            return

        if version < CHECKPOINT_VERSION:
            print(f"[!] Warning: Loading older checkpoint version {version}, some fields may be missing")

        # 覆盖 CONFIG 以保持一致性
        loaded_config = state.get('config', {})
        CONFIG.update(loaded_config)

        # 恢复运行时
        runtime = state.get('runtime', {})

        # 修正时间逻辑：计算之前运行的时长，并调整 start_time 使其相对于当前时间正确
        # 这样 fuzz_loop 中的 (time.time() - self.start_time) 才能正确反映总运行时长
        previous_start = runtime.get('start_time', time.time())
        previous_last_snap = runtime.get('last_snapshot_time', previous_start)
        previous_duration = previous_last_snap - previous_start

        current_time = time.time()
        self.start_time = current_time - previous_duration
        self.last_snapshot_time = current_time # 重置快照时间为当前

        self.last_coverage = runtime.get('last_coverage', self.last_coverage)
        self.last_execs = runtime.get('last_execs', self.last_execs)
        try:
            self.evaluator.start_time = datetime.fromtimestamp(self.start_time)
        except Exception:
            pass

        # 恢复监控器
        monitor_state = state.get('monitor', {})
        stats = monitor_state.get('stats', {})

        # 使用常量定义的字段恢复 stats
        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            if field in stats:
                self.monitor.stats[field] = stats[field]
            else:
                print(f"[!] Warning: Missing {field} in checkpoint, using default")

        if self.monitor.use_coverage:
            # 使用常量定义的字段恢复 bitmaps
            loaded_bitmaps = 0
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                b64_data = monitor_state.get(field)
                if b64_data:
                    try:
                        bitmap = bytearray(base64.b64decode(b64_data))
                        setattr(self.monitor, field, bitmap)
                        loaded_bitmaps += 1
                    except Exception:
                        print(f"[!] Failed to load {field} from checkpoint")
                else:
                    print(f"[!] Warning: Missing {field} in checkpoint, deduplication may be affected")

            # 断言：至少 virgin_bits 必须存在
            assert self.monitor.virgin_bits is not None, "virgin_bits is required for coverage-guided fuzzing"

            # 重新计算覆盖率（已触发的位）
            self.monitor.stats['total_coverage_bits'] = sum(
                (0xFF ^ b).bit_count() for b in self.monitor.virgin_bits
            )

            print(f"[*] Loaded {loaded_bitmaps}/{len(CHECKPOINT_MONITOR_BITMAP_FIELDS)} coverage bitmaps")

        # 恢复调度器
        sched_state = state.get('scheduler', {})
        self.scheduler.strategy = sched_state.get('strategy', self.scheduler.strategy)
        self.scheduler.total_exec_time = sched_state.get('total_exec_time', 0.0)
        self.scheduler.total_coverage = sched_state.get('total_coverage', 0)
        self.scheduler.total_memory = 0
        self.scheduler.fifo_index = sched_state.get('fifo_index', 0)
        self.scheduler.seeds.clear()

        seeds_data = sched_state.get('seeds', [])
        from components.scheduler import Seed
        for s in seeds_data:
            try:
                data = base64.b64decode(s['data'])
            except Exception:
                continue
            seed = Seed(
                data=data,
                exec_count=s.get('exec_count', 0),
                coverage_bits=s.get('coverage_bits', 0),
                exec_time=s.get('exec_time', 0.0),
                energy=s.get('energy', 1.0),
            )
            # 保持 energy/sort_index 一致
            seed.update_energy(seed.energy)
            self.scheduler.total_memory += len(data)
            if self.scheduler.strategy == 'fifo':
                self.scheduler.seeds.append(seed)
            else:
                heapq.heappush(self.scheduler.seeds, seed)

        print(f"[+] Checkpoint loaded from {checkpoint_path} | seeds: {len(self.scheduler.seeds)} | execs: {self.monitor.stats['total_execs']}")
        self.resume_flag = True


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
    parser.add_argument('--checkpoint-path', help='Directory to save checkpoints (default: <output>/checkpoints)')
    parser.add_argument('--resume-from', help='Path to checkpoint.json to resume from')

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
        output_dir=args.output,
        checkpoint_path=args.checkpoint_path,
        resume_from=args.resume_from
    )

    try:
        # 运行模糊测试
        fuzzer.fuzz_loop(duration_seconds=args.duration)
    finally:
        fuzzer.cleanup()


if __name__ == '__main__':
    main()
