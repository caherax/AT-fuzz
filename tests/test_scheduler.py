"""
scheduler.py 的单元测试
测试种子调度器功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.components.scheduler import Seed, SeedScheduler, SEED_FIELDS


class TestSeedDataclass(unittest.TestCase):
    """测试 Seed 数据类"""

    def test_seed_creation(self):
        """测试种子创建"""
        seed = Seed(data=b'test seed')

        self.assertEqual(seed.data, b'test seed')
        self.assertEqual(seed.exec_count, 0)
        self.assertEqual(seed.coverage_bits, 0)
        self.assertEqual(seed.exec_time, 0.0)
        self.assertEqual(seed.energy, 1.0)

    def test_seed_with_params(self):
        """测试带参数的种子创建"""
        seed = Seed(
            data=b'test',
            exec_count=5,
            coverage_bits=100,
            exec_time=0.5,
            energy=50.0
        )

        self.assertEqual(seed.exec_count, 5)
        self.assertEqual(seed.coverage_bits, 100)
        self.assertEqual(seed.exec_time, 0.5)
        self.assertEqual(seed.energy, 50.0)

    def test_seed_energy_update(self):
        """测试能量更新"""
        seed = Seed(data=b'test')
        self.assertEqual(seed.energy, 1.0)

        seed.update_energy(100.0)
        self.assertEqual(seed.energy, 100.0)
        # sort_index 应该是能量的负值（用于大根堆）
        self.assertEqual(seed.sort_index, -100.0)

    def test_seed_ordering(self):
        """测试种子排序（大根堆逻辑）"""
        seed1 = Seed(data=b'low', energy=10.0)
        seed2 = Seed(data=b'high', energy=100.0)

        # sort_index 是负值，所以高能量的 sort_index 更小
        self.assertLess(seed2.sort_index, seed1.sort_index)
        # 在 heapq 中，seed2 会排在前面
        self.assertLess(seed2, seed1)

    def test_seed_fields_consistency(self):
        """测试 SEED_FIELDS 与 Seed 字段一致"""
        seed = Seed(data=b'test')
        # 确保所有 SEED_FIELDS 中的字段都存在于 Seed 中
        for field_name in SEED_FIELDS:
            self.assertTrue(hasattr(seed, field_name), f"Missing field: {field_name}")


class TestSeedSchedulerBasic(unittest.TestCase):
    """测试调度器基本功能"""

    def setUp(self):
        """设置测试环境"""
        self.scheduler = SeedScheduler()

    def test_empty_scheduler(self):
        """测试空调度器"""
        self.assertEqual(len(self.scheduler.seeds), 0)
        self.assertIsNone(self.scheduler.select_next())

    def test_add_single_seed(self):
        """测试添加单个种子"""
        self.scheduler.add_seed(b'seed1', coverage_bits=10, exec_time=0.1)

        self.assertEqual(len(self.scheduler.seeds), 1)

    def test_add_multiple_seeds(self):
        """测试添加多个种子"""
        for i in range(5):
            self.scheduler.add_seed(f'seed{i}'.encode(), coverage_bits=i*10)

        self.assertEqual(len(self.scheduler.seeds), 5)

    def test_select_next(self):
        """测试选择下一个种子"""
        self.scheduler.add_seed(b'seed1')
        self.scheduler.add_seed(b'seed2')

        seed = self.scheduler.select_next()

        self.assertIsNotNone(seed)
        self.assertIsInstance(seed, Seed)
        self.assertEqual(seed.exec_count, 1)  # 执行次数应该增加

    def test_select_updates_exec_count(self):
        """测试选择后执行次数递增"""
        self.scheduler.add_seed(b'only_seed')

        for i in range(5):
            seed = self.scheduler.select_next()
            # 由于只有一个种子，每次都会选中它
            self.assertEqual(seed.exec_count, i + 1)

    def test_get_stats(self):
        """测试获取统计信息"""
        self.scheduler.add_seed(b'seed1', coverage_bits=10)
        self.scheduler.add_seed(b'seed2', coverage_bits=20)

        stats = self.scheduler.get_stats()

        self.assertIn('total_seeds', stats)
        self.assertIn('avg_energy', stats)
        self.assertEqual(stats['total_seeds'], 2)


class TestSeedSchedulerEnergy(unittest.TestCase):
    """测试能量调度策略"""

    def setUp(self):
        """设置测试环境 - 强制使用 energy 策略"""
        # 确保使用 energy 策略
        from src.config import CONFIG
        CONFIG['seed_sort_strategy'] = 'energy'
        self.scheduler = SeedScheduler()

    def test_high_coverage_prioritized(self):
        """测试高覆盖率种子优先"""
        # 添加低覆盖率种子
        self.scheduler.add_seed(b'low_cov', coverage_bits=1, exec_time=0.1)
        # 添加高覆盖率种子
        self.scheduler.add_seed(b'high_cov', coverage_bits=100, exec_time=0.1)

        # 应该优先选择高覆盖率的种子
        seed = self.scheduler.select_next()
        self.assertEqual(seed.data, b'high_cov')

    def test_fast_execution_prioritized(self):
        """测试快速执行种子优先"""
        # 添加慢种子
        self.scheduler.add_seed(b'slow', coverage_bits=10, exec_time=1.0)
        # 添加快种子
        self.scheduler.add_seed(b'fast', coverage_bits=10, exec_time=0.001)

        # 应该优先选择快速执行的种子
        seed = self.scheduler.select_next()
        self.assertEqual(seed.data, b'fast')

    def test_energy_decay_with_exec_count(self):
        """测试执行次数增加导致能量衰减"""
        self.scheduler.add_seed(b'seed1', coverage_bits=50, exec_time=0.1)

        initial_seed = self.scheduler.select_next()
        initial_energy = initial_seed.energy

        # 多次执行后能量应该降低
        for _ in range(10):
            self.scheduler.select_next()

        final_seed = self.scheduler.select_next()
        self.assertLess(final_seed.energy, initial_energy)


class TestSeedSchedulerFIFO(unittest.TestCase):
    """测试 FIFO 调度策略"""

    def setUp(self):
        """设置测试环境 - 使用 FIFO 策略"""
        from src.config import CONFIG
        CONFIG['seed_sort_strategy'] = 'fifo'
        self.scheduler = SeedScheduler()

    def tearDown(self):
        """恢复默认策略"""
        from src.config import CONFIG
        CONFIG['seed_sort_strategy'] = 'energy'

    def test_fifo_order(self):
        """测试 FIFO 顺序"""
        self.scheduler.add_seed(b'first')
        self.scheduler.add_seed(b'second')
        self.scheduler.add_seed(b'third')

        # 应该按添加顺序选择
        self.assertEqual(self.scheduler.select_next().data, b'first')
        self.assertEqual(self.scheduler.select_next().data, b'second')
        self.assertEqual(self.scheduler.select_next().data, b'third')

    def test_fifo_cycles(self):
        """测试 FIFO 循环"""
        self.scheduler.add_seed(b'a')
        self.scheduler.add_seed(b'b')

        # 循环选择
        self.assertEqual(self.scheduler.select_next().data, b'a')
        self.assertEqual(self.scheduler.select_next().data, b'b')
        self.assertEqual(self.scheduler.select_next().data, b'a')  # 回到开始
        self.assertEqual(self.scheduler.select_next().data, b'b')


class TestSeedSchedulerLimits(unittest.TestCase):
    """测试调度器容量限制"""

    def setUp(self):
        """设置测试环境"""
        from src.config import CONFIG
        # 设置较小的限制以便测试
        CONFIG['max_queue_size'] = 10
        CONFIG['max_seeds_memory'] = 1  # 1 MB
        CONFIG['seed_sort_strategy'] = 'energy'
        self.scheduler = SeedScheduler()

    def tearDown(self):
        """恢复默认设置"""
        from src.config import CONFIG
        CONFIG['max_queue_size'] = 10000
        CONFIG['max_seeds_memory'] = 256

    def test_queue_size_limit(self):
        """测试队列大小限制"""
        # 添加超过限制的种子
        for i in range(20):
            self.scheduler.add_seed(f'seed{i}'.encode())

        # 应该被限制在 max_queue_size
        self.assertLessEqual(len(self.scheduler.seeds), 10)

    def test_memory_tracking(self):
        """测试内存追踪"""
        data = b'A' * 1000  # 1KB
        self.scheduler.add_seed(data)

        self.assertGreaterEqual(self.scheduler.total_memory, 1000)


if __name__ == '__main__':
    unittest.main()
