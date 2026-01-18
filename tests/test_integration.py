"""
集成测试
测试多个组件协同工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from src.components.executor import TestExecutor
from src.components.mutator import Mutator
from src.utils import CoverageTracker


class TestBasicFuzzingLoop(unittest.TestCase):
    """测试基本的模糊测试循环"""

    def setUp(self):
        """设置测试环境"""
        self.executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)
        self.tracker = CoverageTracker(bitmap_size=1024)

    def tearDown(self):
        """清理"""
        self.executor.cleanup()

    def test_execute_and_mutate_loop(self):
        """测试执行-变异循环"""
        # 初始种子
        seed = b'Initial seed data'

        # 模拟几次模糊测试迭代
        for i in range(10):
            # 变异
            mutated = Mutator.mutate(seed, 'havoc')

            # 执行
            result = self.executor.execute(mutated)

            # 验证执行成功
            self.assertIsNotNone(result)
            self.assertIn('return_code', result)
            self.assertIn('exec_time', result)

            # 如果没有崩溃，可能选择这个作为新种子
            if not result['crashed']:
                seed = mutated

    def test_crash_detection(self):
        """测试崩溃检测"""
        # 执行正常输入
        normal_result = self.executor.execute(b'normal input')
        self.assertFalse(normal_result['crashed'])
        self.assertEqual(normal_result['return_code'], 0)

    def test_multiple_mutations(self):
        """测试多种变异策略"""
        original = b'Test input'
        strategies = ['bit_flip', 'byte_flip', 'havoc', 'interesting']

        for strategy in strategies:
            mutated = Mutator.mutate(original, strategy)
            result = self.executor.execute(mutated)

            # 所有变异后的输入都应该能执行
            self.assertIsNotNone(result)
            self.assertIn('return_code', result)


class TestCoverageIntegration(unittest.TestCase):
    """测试覆盖率追踪集成"""

    def test_coverage_tracking_workflow(self):
        """测试覆盖率追踪工作流"""
        tracker = CoverageTracker(bitmap_size=64)

        # 模拟三次执行，每次增加覆盖率
        bitmaps = [
            b'\x0F' + b'\x00' * 63,  # 4 bits
            b'\xFF' + b'\x00' * 63,  # 8 bits (新增 4)
            b'\xFF\x0F' + b'\x00' * 62,  # 12 bits (新增 4)
        ]

        total_new = 0
        for i, bitmap in enumerate(bitmaps):
            delta, has_new = tracker.update(bitmap)

            if i == 0:
                self.assertTrue(has_new)
                self.assertEqual(delta, 4)
            elif i == 1:
                self.assertTrue(has_new)
                self.assertEqual(delta, 4)
            elif i == 2:
                self.assertTrue(has_new)
                self.assertEqual(delta, 4)

            total_new += delta

        # 最终覆盖率应该是 12
        self.assertEqual(tracker.get_coverage_count(), 12)


class TestEndToEndScenario(unittest.TestCase):
    """端到端场景测试"""

    def test_simple_fuzzing_campaign(self):
        """测试简单的模糊测试活动"""
        # 准备
        executor = TestExecutor('/bin/cat', 'cat @@', timeout=2)
        seeds = [b'seed1', b'seed2', b'seed3']

        total_execs = 0
        crashes = 0

        # 模拟短时间的模糊测试
        for seed in seeds:
            for _ in range(5):  # 每个种子变异 5 次
                mutated = Mutator.mutate(seed, 'havoc')
                result = executor.execute(mutated)

                total_execs += 1
                if result.get('crashed'):
                    crashes += 1

        # 验证
        self.assertEqual(total_execs, 15)  # 3 seeds * 5 mutations
        self.assertGreaterEqual(total_execs, 0)

        executor.cleanup()


class TestSchedulerIntegration(unittest.TestCase):
    """测试调度器与其他组件的集成"""

    def setUp(self):
        """设置测试环境"""
        from src.components.scheduler import SeedScheduler
        self.scheduler = SeedScheduler()
        self.executor = TestExecutor('/bin/cat', 'cat @@', timeout=2)

    def tearDown(self):
        """清理"""
        self.executor.cleanup()

    def test_scheduler_with_executor(self):
        """测试调度器与执行器协同"""
        # 添加初始种子
        initial_seeds = [b'seed_a', b'seed_b', b'seed_c']
        for seed in initial_seeds:
            self.scheduler.add_seed(seed, coverage_bits=10)

        # 模拟模糊测试循环
        for _ in range(10):
            # 从调度器选择种子
            seed = self.scheduler.select_next()
            self.assertIsNotNone(seed)

            # 变异
            mutated = Mutator.mutate(seed.data, 'havoc')

            # 执行
            result = self.executor.execute(mutated)

            # 如果发现新覆盖，添加到调度器
            if result['return_code'] == 0:
                self.scheduler.add_seed(
                    mutated,
                    coverage_bits=10,
                    exec_time=result['exec_time']
                )

        # 验证调度器状态
        stats = self.scheduler.get_stats()
        self.assertGreater(stats['total_seeds'], 0)

    def test_coverage_guided_seed_selection(self):
        """测试基于覆盖率的种子选择"""
        from src.components.scheduler import SeedScheduler
        from src.config import CONFIG

        # 强制使用 energy 策略
        CONFIG['seed_sort_strategy'] = 'energy'
        scheduler = SeedScheduler()

        # 添加不同覆盖率的种子
        scheduler.add_seed(b'low_cov', coverage_bits=10, exec_time=0.1)
        scheduler.add_seed(b'high_cov', coverage_bits=100, exec_time=0.1)

        # 高覆盖率种子应该被优先选择
        selected = scheduler.select_next()
        self.assertEqual(selected.data, b'high_cov')


class TestEvaluatorIntegration(unittest.TestCase):
    """测试评估器集成"""

    def test_evaluator_with_fuzzing_loop(self):
        """测试评估器在模糊测试循环中的使用"""
        import tempfile
        from src.components.evaluator import Evaluator

        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = Evaluator(tmpdir)
            executor = TestExecutor('/bin/cat', 'cat @@', timeout=2)

            total_execs = 0
            total_crashes = 0

            # 模拟模糊测试
            for i in range(5):
                seed = b'test seed'
                mutated = Mutator.mutate(seed, 'havoc')
                result = executor.execute(mutated)

                total_execs += 1
                if result['crashed']:
                    total_crashes += 1

                # 记录状态
                evaluator.record(
                    total_execs=total_execs,
                    exec_rate=10.0,
                    total_crashes=total_crashes,
                    saved_crashes=total_crashes,
                    total_hangs=0,
                    saved_hangs=0,
                    coverage=i * 10
                )

            # 保存报告
            evaluator.save_final_report({
                'total_execs': total_execs,
                'total_crashes': total_crashes
            })

            executor.cleanup()

            # 验证文件生成
            import os
            self.assertTrue(os.path.exists(os.path.join(tmpdir, 'timeline.csv')))
            self.assertTrue(os.path.exists(os.path.join(tmpdir, 'final_report.json')))


class TestFullPipelineIntegration(unittest.TestCase):
    """完整管道集成测试"""

    def test_complete_fuzzing_pipeline(self):
        """测试完整的模糊测试管道"""
        import tempfile
        from src.components.scheduler import SeedScheduler
        from src.components.evaluator import Evaluator

        with tempfile.TemporaryDirectory() as tmpdir:
            # 初始化所有组件
            scheduler = SeedScheduler()
            executor = TestExecutor('/bin/cat', 'cat @@', timeout=2)
            tracker = CoverageTracker(bitmap_size=1024)
            evaluator = Evaluator(tmpdir)

            # 添加初始种子
            scheduler.add_seed(b'initial seed')

            total_execs = 0

            # 运行模糊测试循环
            for iteration in range(20):
                # 1. 选择种子
                seed = scheduler.select_next()
                if seed is None:
                    break

                # 2. 变异
                mutated = Mutator.mutate(seed.data, 'havoc')

                # 3. 执行
                result = executor.execute(mutated)
                total_execs += 1

                # 4. 如果成功执行，可能添加为新种子
                if not result['crashed'] and not result['timeout']:
                    # 模拟发现新覆盖
                    if iteration % 3 == 0:
                        scheduler.add_seed(
                            mutated,
                            coverage_bits=10 + iteration,
                            exec_time=result['exec_time']
                        )

                # 5. 记录状态
                if iteration % 5 == 0:
                    evaluator.record(
                        total_execs=total_execs,
                        exec_rate=10.0,
                        total_crashes=0,
                        saved_crashes=0,
                        total_hangs=0,
                        saved_hangs=0,
                        coverage=tracker.get_coverage_count()
                    )

            # 清理
            executor.cleanup()

            # 验证
            self.assertGreater(total_execs, 0)
            self.assertGreater(scheduler.get_stats()['total_seeds'], 0)


if __name__ == '__main__':
    unittest.main()
