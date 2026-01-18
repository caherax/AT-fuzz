"""
测试覆盖率功能（转换为 unittest）
"""

import sys
import os
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.components.executor import TestExecutor
from src.components.monitor import ExecutionMonitor
from src.components.mutator import Mutator
from src.utils import count_coverage_bits


class TestCoverageCollection(unittest.TestCase):
    """测试覆盖率收集功能"""

    @unittest.skipUnless(os.path.exists('/tmp/test_target'),
                        "Requires /tmp/test_target binary")
    def test_coverage_basic(self):
        """测试基本覆盖率收集"""
        executor = TestExecutor(
            target_path='/tmp/test_target',
            target_args='/tmp/test_target @@',
            timeout=2,
            use_coverage=True
        )

        # 测试默认分支
        result1 = executor.execute(b'Z')
        self.assertIsNotNone(result1['coverage'])
        self.assertEqual(len(result1['coverage']), 65536)

        cov1 = count_coverage_bits(result1['coverage'])
        self.assertGreater(cov1, 0)

        # 测试不同分支
        result2 = executor.execute(b'A')
        cov2 = count_coverage_bits(result2['coverage'])

        # 不同输入应该产生不同覆盖率
        self.assertNotEqual(result1['coverage'], result2['coverage'])

        executor.cleanup()

    @unittest.skipUnless(os.path.exists('/tmp/test_target'),
                        "Requires /tmp/test_target binary")
    def test_coverage_progression(self):
        """测试覆盖率递进"""
        executor = TestExecutor(
            target_path='/tmp/test_target',
            target_args='/tmp/test_target @@',
            timeout=2,
            use_coverage=True
        )

        # 测试覆盖率递增
        inputs = [b'Z', b'A', b'AB', b'ABC']
        coverages = []

        for inp in inputs:
            result = executor.execute(inp)
            cov = count_coverage_bits(result['coverage']) if result['coverage'] else 0
            coverages.append(cov)

        # 验证覆盖率通常会增加（更长的输入探索更多路径）
        self.assertGreater(coverages[2], 0)  # AB 应该有覆盖率

        executor.cleanup()

    @unittest.skipUnless(os.path.exists('/tmp/test_target'),
                        "Requires /tmp/test_target binary")
    def test_crash_detection(self):
        """测试崩溃检测"""
        executor = TestExecutor(
            target_path='/tmp/test_target',
            target_args='/tmp/test_target @@',
            timeout=2,
            use_coverage=True
        )

        # 测试崩溃输入
        result = executor.execute(b'ABC!')
        self.assertTrue(result['crashed'])

        executor.cleanup()


class TestCoverageGuidedFuzzing(unittest.TestCase):
    """测试覆盖率引导的模糊测试流程"""

    @unittest.skipUnless(os.path.exists('/tmp/test_target'),
                        "Requires /tmp/test_target binary")
    def test_coverage_guided_basic(self):
        """测试基本覆盖率引导流程"""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = TestExecutor(
                target_path='/tmp/test_target',
                target_args='/tmp/test_target @@',
                timeout=2,
                use_coverage=True
            )

            monitor = ExecutionMonitor(tmpdir, use_coverage=True)
            mutator = Mutator()

            # 初始种子
            seed = b'A'

            # 测试几轮
            for _ in range(5):
                # 执行
                result = executor.execute(seed)

                # 监控
                is_interesting = monitor.process_execution(seed, result)

                # 如果有趣，使用它作为新种子
                if is_interesting and not result['crashed']:
                    seed = mutator.mutate(seed)

            # 验证执行了测试
            self.assertGreater(monitor.stats.total_execs, 0)

            executor.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)

