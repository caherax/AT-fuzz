"""
fuzzer.py 的单元测试
测试模糊测试主程序功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

from src.fuzzer import Fuzzer
from src.config import CONFIG, apply_advanced_defaults


class TestFuzzerBase(unittest.TestCase):
    """Fuzzer 测试基类，提供通用的 setUp 和配置方法"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.seed_dir = Path(self.temp_dir) / 'seeds'
        self.seed_dir.mkdir()
        self.output_dir = Path(self.temp_dir) / 'output'

        # 创建测试种子
        (self.seed_dir / 'test.txt').write_bytes(b'test input')

        # 使用系统命令作为测试目标
        self.test_program = '/bin/cat'
        self.test_args = 'cat @@'

        # 保存原始 CONFIG
        self.original_config = CONFIG.copy()

    def tearDown(self):
        """清理测试环境"""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

        # 恢复原始 CONFIG
        CONFIG.clear()
        CONFIG.update(self.original_config)

    def _setup_config(self, **kwargs):
        """辅助方法：设置 CONFIG 并应用高级默认值"""
        CONFIG['target'] = kwargs.get('target_path', self.test_program)
        CONFIG['args'] = kwargs.get('target_args', self.test_args)
        CONFIG['seeds'] = kwargs.get('seed_dir', str(self.seed_dir))
        CONFIG['output'] = kwargs.get('output_dir', str(self.output_dir))
        CONFIG['target_id'] = kwargs.get('target_id', 'test')
        CONFIG['checkpoint_path'] = kwargs.get('checkpoint_path', None)
        CONFIG['resume_from'] = kwargs.get('resume_from', None)
        apply_advanced_defaults()


class TestFuzzerInitialization(TestFuzzerBase):
    """测试 Fuzzer 初始化"""

    def test_fuzzer_creation(self):
        """测试创建 Fuzzer 实例"""
        self._setup_config()
        fuzzer = Fuzzer()

        self.assertEqual(fuzzer.target_id, 'test')
        self.assertEqual(fuzzer.target_path, self.test_program)
        self.assertIsNotNone(fuzzer.executor)
        self.assertIsNotNone(fuzzer.monitor)
        self.assertIsNotNone(fuzzer.scheduler)
        self.assertIsNotNone(fuzzer.evaluator)

        fuzzer.cleanup()

    def test_fuzzer_checkpoint_dir_default(self):
        """测试检查点目录默认值"""
        self._setup_config()
        fuzzer = Fuzzer()

        expected_checkpoint_dir = Path(self.output_dir) / 'checkpoints'
        self.assertEqual(fuzzer.checkpoint_dir, expected_checkpoint_dir)
        self.assertTrue(fuzzer.checkpoint_dir.exists())

        fuzzer.cleanup()

    def test_fuzzer_checkpoint_dir_custom(self):
        """测试自定义检查点目录"""
        custom_checkpoint = Path(self.temp_dir) / 'custom_checkpoints'
        self._setup_config(checkpoint_path=str(custom_checkpoint))
        fuzzer = Fuzzer()

        self.assertEqual(fuzzer.checkpoint_dir, custom_checkpoint)
        self.assertTrue(fuzzer.checkpoint_dir.exists())

        fuzzer.cleanup()


class TestFuzzerSignalHandling(TestFuzzerBase):
    """测试信号处理"""

    def test_pause_handler(self):
        """测试暂停信号处理器"""
        self._setup_config()
        fuzzer = Fuzzer()

        self.assertFalse(fuzzer.pause_requested)

        # 模拟接收 SIGINT
        fuzzer._pause_handler(signal.SIGINT, None)

        self.assertTrue(fuzzer.pause_requested)

        fuzzer.cleanup()

    def test_signal_handler(self):
        """测试 SIGTERM 信号处理器"""
        self._setup_config()
        fuzzer = Fuzzer()

        self.assertFalse(fuzzer.force_exit)

        # 模拟接收 SIGTERM
        fuzzer._signal_handler(signal.SIGTERM, None)

        self.assertTrue(fuzzer.force_exit)

        fuzzer.cleanup()


class TestFuzzerSeedProcessing(TestFuzzerBase):
    """测试种子处理"""

    def test_process_seed_success(self):
        """测试处理有效种子"""
        self._setup_config()
        fuzzer = Fuzzer()

        result = fuzzer._process_seed(b'test input', is_initial=True)
        self.assertTrue(result)

        # 初始种子应该被添加到调度器
        self.assertGreater(len(fuzzer.scheduler.seeds), 0)

        fuzzer.cleanup()

    def test_process_seed_oversized(self):
        """测试处理超大种子"""
        self._setup_config()
        fuzzer = Fuzzer()

        # 创建一个超过最大大小的种子
        oversized_seed = b'x' * (CONFIG['max_seed_size'] + 1)
        result = fuzzer._process_seed(oversized_seed, is_initial=True)

        self.assertFalse(result)

        fuzzer.cleanup()

    def test_process_seed_updates_coverage(self):
        """测试处理种子更新覆盖率"""
        self._setup_config()
        fuzzer = Fuzzer()

        initial_coverage = fuzzer.last_coverage
        fuzzer._process_seed(b'test input', is_initial=True)

        # 覆盖率可能更新（取决于执行结果）
        # 至少应该执行了一次
        self.assertGreater(fuzzer.monitor.stats.total_execs, 0)

        fuzzer.cleanup()


class TestFuzzerSeedLoading(TestFuzzerBase):
    """测试种子加载"""

    def test_load_seeds_from_directory(self):
        """测试从目录加载种子"""
        # 创建多个种子文件
        (self.seed_dir / 'seed1.txt').write_bytes(b'seed1')
        (self.seed_dir / 'seed2.txt').write_bytes(b'seed2')
        (self.seed_dir / 'seed3.txt').write_bytes(b'seed3')

        self._setup_config()
        fuzzer = Fuzzer()

        fuzzer.load_initial_seeds()

        # 应该加载了至少一些种子
        self.assertGreater(len(fuzzer.scheduler.seeds), 0)

        fuzzer.cleanup()

    def test_load_seeds_empty_directory(self):
        """测试从空目录加载种子"""
        self._setup_config()
        fuzzer = Fuzzer()

        fuzzer.load_initial_seeds()

        # 应该创建一个空种子
        self.assertEqual(len(fuzzer.scheduler.seeds), 1)

        fuzzer.cleanup()

    def test_load_seeds_nonexistent_directory(self):
        """测试从不存在的目录加载种子"""
        nonexistent_dir = Path(self.temp_dir) / 'nonexistent'
        self._setup_config(seed_dir=str(nonexistent_dir))
        fuzzer = Fuzzer()

        fuzzer.load_initial_seeds()

        # 应该创建一个空种子
        self.assertEqual(len(fuzzer.scheduler.seeds), 1)

        fuzzer.cleanup()


class TestFuzzerMainLoop(TestFuzzerBase):
    """测试主循环功能"""

    def test_fuzz_loop_short_duration(self):
        """测试短时间运行模糊循环"""
        self._setup_config()
        fuzzer = Fuzzer()

        # 运行 1 秒
        fuzzer.fuzz_loop(duration_seconds=1)

        # 应该执行了一些测试
        self.assertGreater(fuzzer.monitor.stats.total_execs, 0)

        # 应该生成了报告
        self.assertTrue((Path(self.output_dir) / 'final_report.json').exists())

        fuzzer.cleanup()

    def test_fuzz_loop_with_pause(self):
        """测试带暂停的模糊循环"""
        self._setup_config()
        fuzzer = Fuzzer()

        # 加载种子
        fuzzer.load_initial_seeds()

        # 设置暂停标志
        fuzzer.pause_requested = True

        # 运行（应该很快退出）
        fuzzer.fuzz_loop(duration_seconds=60)

        # 应该生成了检查点
        checkpoint_file = fuzzer.checkpoint_dir / 'checkpoint.json'
        self.assertTrue(checkpoint_file.exists())

        fuzzer.cleanup()


class TestFuzzerStatistics(TestFuzzerBase):
    """测试统计功能"""

    def test_update_stats(self):
        """测试统计更新"""
        self._setup_config()
        fuzzer = Fuzzer()

        # 执行一些测试
        fuzzer._process_seed(b'test', is_initial=True)

        import time
        initial_time = fuzzer.last_snapshot_time
        time.sleep(0.1)  # 确保时间有差异

        # 更新统计
        fuzzer._update_stats()

        # 检查时间戳是否更新
        self.assertGreater(fuzzer.last_snapshot_time, initial_time)

        fuzzer.cleanup()


class TestFuzzerCleanup(TestFuzzerBase):
    """测试清理功能"""

    def test_cleanup(self):
        """测试清理资源"""
        self._setup_config()
        fuzzer = Fuzzer()

        # 清理应该不抛出异常
        fuzzer.cleanup()


if __name__ == '__main__':
    unittest.main()
