"""
集成测试
测试多个组件协同工作
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from components.executor import TestExecutor
from components.mutator import Mutator
from utils import CoverageTracker


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
        
        # 清理
        executor.cleanup()


if __name__ == '__main__':
    unittest.main()
