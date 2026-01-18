"""
checkpoint.py 的单元测试
测试检查点保存和恢复功能
"""

from datetime import datetime
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import json
import base64
from pathlib import Path
from unittest.mock import MagicMock

from checkpoint import CheckpointManager, CHECKPOINT_VERSION
from components.monitor import MonitorStats
from components.scheduler import Seed


class MockFuzzer:
    """模拟的 Fuzzer 实例用于测试"""

    def __init__(self):
        self.target_id = 'test_target'
        self.target_path = '/bin/echo'
        self.target_args = 'echo @@'
        self.seed_dir = Path('/tmp/seeds')
        self.start_time = 1000.0
        self.last_snapshot_time = 1100.0
        self.last_coverage = 42
        self.last_execs = 100
        self._checkpoint_reason = 'test'

        # Mock monitor
        self.monitor = MagicMock()
        self.monitor.output_dir = '/tmp/output'
        self.monitor.use_coverage = True
        self.monitor.stats = MonitorStats(
            total_execs=100,
            total_crashes=2,
            total_hangs=1,
            saved_crashes=2,
            saved_hangs=1,
            interesting_inputs=10,
            start_time=datetime.now().isoformat(),
            total_coverage_bits=42
        )
        self.monitor.virgin_bits = bytearray([0xFF] * 100 + [0xFE] * 100)
        self.monitor.virgin_crash = bytearray([0xFF] * 200)
        self.monitor.virgin_tmout = bytearray([0xFF] * 200)

        # Mock scheduler
        self.scheduler = MagicMock()
        self.scheduler.strategy = 'energy'
        self.scheduler.total_exec_time = 50.0
        self.scheduler.total_coverage = 42
        self.scheduler.total_memory = 1024
        self.scheduler.fifo_index = 0
        self.scheduler.seeds = [
            Seed(data=b'seed1', exec_count=10, coverage_bits=20, exec_time=0.1, energy=5.0),
            Seed(data=b'seed2', exec_count=5, coverage_bits=15, exec_time=0.2, energy=3.0),
        ]


class TestCheckpointBasic(unittest.TestCase):
    """测试检查点基本功能"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_dir = Path(self.temp_dir) / 'checkpoints'
        self.fuzzer = MockFuzzer()

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_save_checkpoint(self):
        """测试保存检查点"""
        CheckpointManager.save(self.checkpoint_dir, self.fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        self.assertTrue(checkpoint_file.exists())

        # 验证 JSON 可以解析
        with open(checkpoint_file) as f:
            state = json.load(f)

        self.assertEqual(state['version'], CHECKPOINT_VERSION)
        self.assertEqual(state['target_id'], 'test_target')
        self.assertEqual(state['target_path'], '/bin/echo')
        self.assertIn('monitor', state)
        self.assertIn('scheduler', state)
        self.assertIn('runtime', state)

    def test_checkpoint_monitor_stats(self):
        """测试检查点包含正确的监控器统计"""
        CheckpointManager.save(self.checkpoint_dir, self.fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        with open(checkpoint_file) as f:
            state = json.load(f)

        stats = state['monitor']['stats']
        self.assertEqual(stats['total_execs'], 100)
        self.assertEqual(stats['total_crashes'], 2)
        self.assertEqual(stats['total_hangs'], 1)
        self.assertEqual(stats['saved_crashes'], 2)
        self.assertEqual(stats['saved_hangs'], 1)
        self.assertEqual(stats['interesting_inputs'], 10)

    def test_checkpoint_bitmaps(self):
        """测试检查点包含覆盖率位图"""
        CheckpointManager.save(self.checkpoint_dir, self.fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        with open(checkpoint_file) as f:
            state = json.load(f)

        monitor = state['monitor']
        self.assertIn('virgin_bits', monitor)
        self.assertIn('virgin_crash', monitor)
        self.assertIn('virgin_tmout', monitor)

        # 验证位图可以解码
        virgin_bits = base64.b64decode(monitor['virgin_bits'])
        self.assertEqual(len(virgin_bits), 200)

    def test_checkpoint_seeds(self):
        """测试检查点包含种子队列"""
        CheckpointManager.save(self.checkpoint_dir, self.fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        with open(checkpoint_file) as f:
            state = json.load(f)

        seeds = state['scheduler']['seeds']
        self.assertEqual(len(seeds), 2)

        # 验证种子数据
        seed1 = seeds[0]
        self.assertIn('data', seed1)
        self.assertIn('exec_count', seed1)
        self.assertIn('coverage_bits', seed1)

        # 解码种子数据
        data = base64.b64decode(seed1['data'])
        self.assertIn(data, [b'seed1', b'seed2'])

    def test_checkpoint_runtime(self):
        """测试检查点包含运行时状态"""
        CheckpointManager.save(self.checkpoint_dir, self.fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        with open(checkpoint_file) as f:
            state = json.load(f)

        runtime = state['runtime']
        self.assertEqual(runtime['start_time'], 1000.0)
        self.assertEqual(runtime['last_snapshot_time'], 1100.0)
        self.assertEqual(runtime['last_coverage'], 42)
        self.assertEqual(runtime['last_execs'], 100)


class TestCheckpointLoad(unittest.TestCase):
    """测试检查点加载功能"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_dir = Path(self.temp_dir) / 'checkpoints'

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_nonexistent_checkpoint(self):
        """测试加载不存在的检查点"""
        fuzzer = MockFuzzer()
        checkpoint_file = self.checkpoint_dir / 'nonexistent.json'

        result = CheckpointManager.load(checkpoint_file, fuzzer)
        self.assertFalse(result)

    def test_save_and_load_roundtrip(self):
        """测试保存和加载往返"""
        # 保存
        fuzzer1 = MockFuzzer()
        CheckpointManager.save(self.checkpoint_dir, fuzzer1)

        # 加载到新的 fuzzer
        fuzzer2 = MockFuzzer()
        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'

        result = CheckpointManager.load(checkpoint_file, fuzzer2)
        self.assertTrue(result)

        # 验证监控器统计被恢复
        self.assertEqual(fuzzer2.monitor.stats.total_execs, 100)
        self.assertEqual(fuzzer2.monitor.stats.total_crashes, 2)
        self.assertEqual(fuzzer2.monitor.stats.saved_crashes, 2)

        # 验证调度器状态被恢复
        self.assertEqual(len(fuzzer2.scheduler.seeds), 2)
        self.assertEqual(fuzzer2.scheduler.strategy, 'energy')

    def test_load_restores_bitmaps(self):
        """测试加载恢复覆盖率位图"""
        fuzzer1 = MockFuzzer()
        original_virgin_bits = bytes(fuzzer1.monitor.virgin_bits)

        CheckpointManager.save(self.checkpoint_dir, fuzzer1)

        fuzzer2 = MockFuzzer()
        fuzzer2.monitor.virgin_bits = bytearray([0xFF] * 200)  # 重置

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        CheckpointManager.load(checkpoint_file, fuzzer2)

        # 验证位图被恢复
        self.assertEqual(bytes(fuzzer2.monitor.virgin_bits), original_virgin_bits)

    def test_load_without_coverage(self):
        """测试加载不使用覆盖率的检查点"""
        fuzzer1 = MockFuzzer()
        fuzzer1.monitor.use_coverage = False

        CheckpointManager.save(self.checkpoint_dir, fuzzer1)

        fuzzer2 = MockFuzzer()
        fuzzer2.monitor.use_coverage = False

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        result = CheckpointManager.load(checkpoint_file, fuzzer2)

        self.assertTrue(result)


class TestCheckpointValidation(unittest.TestCase):
    """测试检查点验证功能"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_dir = Path(self.checkpoint_dir) / 'checkpoints' if hasattr(self, 'checkpoint_dir') else Path(self.temp_dir) / 'checkpoints'

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_validate_fields_runs_without_error(self):
        """测试字段验证可以正常运行"""
        from checkpoint import validate_fields
        # 如果字段不一致，会在模块导入时抛出断言错误
        # 这个测试确保 validate_fields 可以被调用
        validate_fields()  # 应该不抛出异常


class TestCheckpointVersioning(unittest.TestCase):
    """测试检查点版本兼容性"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.checkpoint_dir = Path(self.temp_dir) / 'checkpoints'
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_current_version_checkpoint(self):
        """测试当前版本的检查点"""
        fuzzer = MockFuzzer()
        CheckpointManager.save(self.checkpoint_dir, fuzzer)

        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'
        with open(checkpoint_file) as f:
            state = json.load(f)

        self.assertEqual(state['version'], CHECKPOINT_VERSION)

    def test_unsupported_version(self):
        """测试不支持的检查点版本"""
        checkpoint_file = self.checkpoint_dir / 'checkpoint.json'

        # 创建一个版本号过高的检查点
        invalid_state = {
            'version': 9999,
            'monitor': {'stats': {}},
            'scheduler': {'seeds': []},
            'runtime': {}
        }

        with open(checkpoint_file, 'w') as f:
            json.dump(invalid_state, f)

        fuzzer = MockFuzzer()
        result = CheckpointManager.load(checkpoint_file, fuzzer)

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
