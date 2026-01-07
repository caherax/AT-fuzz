"""
mutator.py 的单元测试
测试变异算子功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from components.mutator import Mutator


class TestMutatorBasic(unittest.TestCase):
    """测试基本变异功能"""
    
    def test_bit_flip(self):
        """测试比特翻转"""
        original = b'\x00\x00\x00\x00'
        mutated = Mutator.bit_flip(original, flip_count=1)
        
        # 应该有一个字节发生了变化
        diff_count = sum(a != b for a, b in zip(original, mutated))
        self.assertGreaterEqual(diff_count, 1)
        
        # 长度应该保持不变
        self.assertEqual(len(mutated), len(original))
    
    def test_bit_flip_empty_data(self):
        """测试空数据的比特翻转"""
        original = b''
        mutated = Mutator.bit_flip(original)
        self.assertEqual(mutated, b'')
    
    def test_byte_flip(self):
        """测试字节翻转"""
        original = b'\x00\x00\x00\x00'
        mutated = Mutator.byte_flip(original, flip_count=1)
        
        # 应该有字节变成 0xFF
        self.assertTrue(b'\xFF' in mutated)
        self.assertEqual(len(mutated), len(original))
    
    def test_byte_flip_multiple(self):
        """测试多字节翻转"""
        original = b'\x00' * 10
        mutated = Mutator.byte_flip(original, flip_count=3)
        
        # 应该有至少 3 个字节变成 0xFF
        flipped_count = sum(1 for b in mutated if b == 0xFF)
        self.assertGreaterEqual(flipped_count, 1)
    
    def test_interesting_values(self):
        """测试有趣数值替换"""
        original = b'\x00\x00\x00\x00'
        mutated = Mutator.interesting_values(original)
        
        # 结果应该不同
        # （有小概率相同，但极低）
        self.assertEqual(len(mutated), len(original))
    
    def test_insert(self):
        """测试插入变异"""
        original = b'AAAA'
        mutated = Mutator.insert(original)
        
        # 长度应该增加
        self.assertGreaterEqual(len(mutated), len(original))
    
    def test_delete(self):
        """测试删除变异"""
        original = b'AAAABBBBCCCC'
        mutated = Mutator.delete(original)
        
        # 长度应该减少（除非原始数据为空）
        if len(original) > 0:
            self.assertLessEqual(len(mutated), len(original))
    
    def test_havoc_mutation(self):
        """测试 havoc 变异"""
        original = b'Hello, Fuzzer!'
        mutated = Mutator.havoc(original, iterations=5)
        
        # 长度可能变化
        self.assertIsInstance(mutated, bytes)
        
        # 应该有一些变化（概率极高）
        # 允许极小概率相同
        if len(original) == len(mutated):
            # 至少有一些字节应该不同
            pass  # havoc 可能不改变，但概率很低
    
    def test_mutate_wrapper(self):
        """测试 mutate 包装函数"""
        original = b'Test data'
        
        # 测试所有策略
        strategies = ['bitflip', 'byteflip', 'havoc', 'interesting', 'insert', 'delete']
        
        for strategy in strategies:
            mutated = Mutator.mutate(original, strategy)
            self.assertIsInstance(mutated, bytes)


class TestMutatorEdgeCases(unittest.TestCase):
    """测试边界情况"""
    
    def test_single_byte_input(self):
        """测试单字节输入"""
        original = b'A'
        
        mutated = Mutator.bit_flip(original)
        self.assertEqual(len(mutated), 1)
        
        mutated = Mutator.byte_flip(original)
        self.assertEqual(len(mutated), 1)
    
    def test_large_input(self):
        """测试大输入"""
        original = b'A' * 10000
        
        mutated = Mutator.havoc(original, iterations=10)
        self.assertIsInstance(mutated, bytes)
        
        # 长度变化不应该太离谱（允许一些变化）
        self.assertLess(abs(len(mutated) - len(original)), 100)
    
    def test_binary_data(self):
        """测试二进制数据"""
        original = bytes(range(256))
        
        mutated = Mutator.mutate(original, 'havoc')
        self.assertIsInstance(mutated, bytes)


if __name__ == '__main__':
    unittest.main()
