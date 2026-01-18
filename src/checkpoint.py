"""
检查点管理模块
负责模糊测试状态的保存和恢复
"""

import json
import base64
import time
import heapq
from pathlib import Path
from typing import TypedDict, Optional
from datetime import datetime, timezone

from .config import CONFIG
from .components.monitor import STATS_FIELDS as MONITOR_STATS_FIELDS, BITMAP_FIELDS as MONITOR_BITMAP_FIELDS
from .components.scheduler import SEED_FIELDS as SCHEDULER_SEED_FIELDS


# ========== 检查点版本 ==========
CHECKPOINT_VERSION = 2


# ========== 字段定义（常量）==========
CHECKPOINT_MONITOR_STATS_FIELDS = (
    'total_execs',
    'total_crashes',
    'total_hangs',
    'saved_crashes',
    'saved_hangs',
    'interesting_inputs',
    'start_time',
)

CHECKPOINT_MONITOR_BITMAP_FIELDS = MONITOR_BITMAP_FIELDS
CHECKPOINT_SEED_FIELDS = SCHEDULER_SEED_FIELDS


# ========== 类型定义 ==========
class CheckpointMonitorStats(TypedDict):
    """监控器统计字段"""
    total_execs: int
    total_crashes: int
    total_hangs: int
    saved_crashes: int
    saved_hangs: int
    interesting_inputs: int
    start_time: float


class CheckpointMonitorBitmaps(TypedDict, total=False):
    """监控器位图字段"""
    virgin_bits: Optional[str]
    virgin_crash: Optional[str]
    virgin_tmout: Optional[str]


class CheckpointMonitor(TypedDict):
    """监控器状态"""
    stats: CheckpointMonitorStats
    virgin_bits: Optional[str]
    virgin_crash: Optional[str]
    virgin_tmout: Optional[str]


class CheckpointSeedEntry(TypedDict):
    """单个种子条目"""
    data: str
    exec_count: int
    coverage_bits: int
    exec_time: float
    energy: float


class CheckpointScheduler(TypedDict):
    """调度器状态"""
    strategy: str
    seeds: list[CheckpointSeedEntry]
    total_exec_time: float
    total_coverage: int
    total_memory: int
    fifo_index: int


class CheckpointRuntime(TypedDict):
    """运行时状态"""
    start_time: float
    last_snapshot_time: float
    last_coverage: int
    last_execs: int


class CheckpointState(TypedDict):
    """完整检查点状态"""
    version: int
    reason: str
    target_id: str
    target_path: str
    target_args: str
    seed_dir: str
    output_dir: str
    timestamp: str
    config: dict
    runtime: CheckpointRuntime
    monitor: CheckpointMonitor
    scheduler: CheckpointScheduler


# ========== 验证函数 ==========
def validate_fields():
    """验证字段定义的一致性"""
    assert set(CHECKPOINT_MONITOR_STATS_FIELDS).issubset(set(MONITOR_STATS_FIELDS)), \
        f"CHECKPOINT_MONITOR_STATS_FIELDS contains fields not in MONITOR_STATS_FIELDS"
    assert CHECKPOINT_MONITOR_BITMAP_FIELDS == MONITOR_BITMAP_FIELDS, \
        f"CHECKPOINT_MONITOR_BITMAP_FIELDS mismatch with MONITOR_BITMAP_FIELDS"
    assert CHECKPOINT_SEED_FIELDS == SCHEDULER_SEED_FIELDS, \
        f"CHECKPOINT_SEED_FIELDS mismatch with SCHEDULER_SEED_FIELDS"


# 模块初始化时验证
validate_fields()


# ========== 检查点管理器 ==========
class CheckpointManager:
    """
    负责检查点的保存和加载
    """

    @staticmethod
    def save(checkpoint_dir: Path, fuzzer) -> None:
        """
        保存检查点

        Args:
            checkpoint_dir: 检查点保存目录
            fuzzer: Fuzzer 实例，包含所有需要保存的状态
        """
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 预先计算各部分的大小开销
        print("[*] Checkpoint size breakdown:")

        # 1. 种子队列大小
        total_seed_size = sum(len(s.data) for s in fuzzer.scheduler.seeds)
        print(f"  Seeds: {len(fuzzer.scheduler.seeds)} seeds, {total_seed_size} bytes")

        # 2. 覆盖率位图大小
        coverage_size = len(fuzzer.monitor.virgin_bits) if fuzzer.monitor.virgin_bits else 0
        print(f"  Coverage bitmap: {coverage_size} bytes")

        # 3. 构建 monitor stats
        monitor_stats: CheckpointMonitorStats = {
            'total_execs': 0,
            'total_crashes': 0,
            'total_hangs': 0,
            'saved_crashes': 0,
            'saved_hangs': 0,
            'interesting_inputs': 0,
            'start_time': 0.0,
        }
        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            assert hasattr(fuzzer.monitor.stats, field), f"Missing monitor stats field: {field}"
            monitor_stats[field] = getattr(fuzzer.monitor.stats, field)  # type: ignore

        # 4. 构建 monitor bitmaps
        monitor_bitmaps: CheckpointMonitorBitmaps = {}
        if fuzzer.monitor.use_coverage:
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                bitmap = getattr(fuzzer.monitor, field, None)
                assert bitmap is not None, f"Missing monitor bitmap: {field}"
                monitor_bitmaps[field] = base64.b64encode(bytes(bitmap)).decode()  # type: ignore
        else:
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                monitor_bitmaps[field] = None  # type: ignore

        # 5. 构建 seed 列表
        seeds_list: list[CheckpointSeedEntry] = []
        for s in fuzzer.scheduler.seeds:
            seed_dict: CheckpointSeedEntry = {
                'data': '',
                'exec_count': 0,
                'coverage_bits': 0,
                'exec_time': 0.0,
                'energy': 1.0,
            }
            seed_dict['data'] = base64.b64encode(s.data).decode()
            seed_dict['exec_count'] = s.exec_count
            seed_dict['coverage_bits'] = s.coverage_bits
            seed_dict['exec_time'] = s.exec_time
            seed_dict['energy'] = s.energy
            seeds_list.append(seed_dict)

        # 6. 构建完整状态字典
        state: CheckpointState = {
            'version': CHECKPOINT_VERSION,
            'reason': fuzzer._checkpoint_reason,
            'target_id': fuzzer.target_id,
            'target_path': fuzzer.target_path,
            'target_args': fuzzer.target_args,
            'seed_dir': str(fuzzer.seed_dir),
            'output_dir': str(fuzzer.monitor.output_dir),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'config': CONFIG,
            'runtime': {
                'start_time': fuzzer.start_time,
                'last_snapshot_time': fuzzer.last_snapshot_time,
                'last_coverage': fuzzer.last_coverage,
                'last_execs': fuzzer.last_execs,
            },
            'monitor': {
                'stats': monitor_stats,
                **monitor_bitmaps,  # type: ignore
            },
            'scheduler': {
                'strategy': fuzzer.scheduler.strategy,
                'seeds': seeds_list,
                'total_exec_time': fuzzer.scheduler.total_exec_time,
                'total_coverage': fuzzer.scheduler.total_coverage,
                'total_memory': fuzzer.scheduler.total_memory,
                'fifo_index': fuzzer.scheduler.fifo_index,
            },
        }

        # 验证完整性
        CheckpointManager._validate_state(state)

        checkpoint_file = checkpoint_dir / 'checkpoint.json'

        # 序列化并计算大小
        json_data = json.dumps(state, indent=2)
        json_size = len(json_data.encode('utf-8'))

        # Base64 编码开销估算
        b64_overhead = 0
        for s in fuzzer.scheduler.seeds:
            raw_size = len(s.data)
            b64_size = len(base64.b64encode(s.data).decode())
            b64_overhead += (b64_size - raw_size)
        if fuzzer.monitor.virgin_bits:
            raw_cov = len(fuzzer.monitor.virgin_bits)
            b64_cov = len(base64.b64encode(bytes(fuzzer.monitor.virgin_bits)).decode())
            b64_overhead += (b64_cov - raw_cov)

        print(f"  Base64 encoding overhead: {b64_overhead} bytes")
        print(f"  Final JSON size: {json_size} bytes")

        checkpoint_file.write_text(json_data)
        print(f"[*] Checkpoint saved to {checkpoint_file}")

    @staticmethod
    def load(checkpoint_path: Path, fuzzer) -> bool:
        """
        从检查点恢复状态

        Args:
            checkpoint_path: 检查点文件路径
            fuzzer: Fuzzer 实例，将状态恢复到该实例

        Returns:
            是否成功加载
        """
        if not checkpoint_path.exists():
            print(f"[!] Checkpoint not found: {checkpoint_path}")
            return False

        state: CheckpointState = json.loads(checkpoint_path.read_text())
        version = state.get('version', 1)

        # 版本兼容性检查
        if version < 1 or version > CHECKPOINT_VERSION:
            print(f"[!] Unsupported checkpoint version: {version} (expected <= {CHECKPOINT_VERSION})")
            return False

        if version < CHECKPOINT_VERSION:
            print(f"[!] Warning: Loading older checkpoint version {version}, some fields may be missing")

        # 覆盖 CONFIG 以保持一致性
        loaded_config = state.get('config', {})
        CONFIG.update(loaded_config)

        # 恢复运行时
        runtime = state.get('runtime', {})

        # 修正时间逻辑
        previous_start = runtime.get('start_time', time.time())
        previous_last_snap = runtime.get('last_snapshot_time', previous_start)
        previous_duration = previous_last_snap - previous_start

        current_time = time.time()
        fuzzer.start_time = current_time - previous_duration
        fuzzer.last_snapshot_time = current_time

        fuzzer.last_coverage = runtime.get('last_coverage', fuzzer.last_coverage)
        fuzzer.last_execs = runtime.get('last_execs', fuzzer.last_execs)
        try:
            fuzzer.evaluator.start_time = datetime.fromtimestamp(fuzzer.start_time)
        except Exception:
            pass

        # 恢复监控器
        monitor_state = state.get('monitor', {})
        stats = monitor_state.get('stats', {})

        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            if field in stats:
                setattr(fuzzer.monitor.stats, field, stats[field])
            else:
                print(f"[!] Warning: Missing {field} in checkpoint, using default")

        if fuzzer.monitor.use_coverage:
            # 恢复位图
            loaded_bitmaps = 0
            for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
                b64_data = monitor_state.get(field)
                if b64_data:
                    try:
                        bitmap = bytearray(base64.b64decode(b64_data))
                        setattr(fuzzer.monitor, field, bitmap)
                        loaded_bitmaps += 1
                    except Exception:
                        print(f"[!] Failed to load {field} from checkpoint")
                else:
                    print(f"[!] Warning: Missing {field} in checkpoint, deduplication may be affected")

            # 至少 virgin_bits 必须存在
            assert fuzzer.monitor.virgin_bits is not None, "virgin_bits is required for coverage-guided fuzzing"

            # 重新计算覆盖率
            fuzzer.monitor.stats.total_coverage_bits = sum(
                (0xFF ^ b).bit_count() for b in fuzzer.monitor.virgin_bits
            )

            print(f"[*] Loaded {loaded_bitmaps}/{len(CHECKPOINT_MONITOR_BITMAP_FIELDS)} coverage bitmaps")

        # 恢复调度器
        sched_state = state.get('scheduler', {})
        fuzzer.scheduler.strategy = sched_state.get('strategy', fuzzer.scheduler.strategy)
        fuzzer.scheduler.total_exec_time = sched_state.get('total_exec_time', 0.0)
        fuzzer.scheduler.total_coverage = sched_state.get('total_coverage', 0)
        fuzzer.scheduler.total_memory = 0
        fuzzer.scheduler.fifo_index = sched_state.get('fifo_index', 0)
        fuzzer.scheduler.seeds.clear()

        seeds_data = sched_state.get('seeds', [])
        from .components.scheduler import Seed
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
            seed.update_energy(seed.energy)
            fuzzer.scheduler.total_memory += len(data)
            if fuzzer.scheduler.strategy == 'fifo':
                fuzzer.scheduler.seeds.append(seed)
            else:
                heapq.heappush(fuzzer.scheduler.seeds, seed)

        print(f"[+] Checkpoint loaded from {checkpoint_path} | seeds: {len(fuzzer.scheduler.seeds)} | execs: {fuzzer.monitor.stats.total_execs}")
        return True

    @staticmethod
    def _validate_state(state: CheckpointState) -> None:
        """验证检查点状态的完整性"""
        assert 'monitor' in state and 'stats' in state['monitor'], "Missing monitor.stats in checkpoint"
        for field in CHECKPOINT_MONITOR_STATS_FIELDS:
            assert field in state['monitor']['stats'], f"Missing {field} in checkpoint monitor.stats"
        for field in CHECKPOINT_MONITOR_BITMAP_FIELDS:
            assert field in state['monitor'], f"Missing {field} in checkpoint monitor"
