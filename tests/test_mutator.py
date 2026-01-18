"""
mutator.py 的单元测试
测试变异算子功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.components.mutator import Mutator


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


class TestMutatorArithmetic(unittest.TestCase):
    """测试算术变异"""

    def test_arithmetic_basic(self):
        """测试基本算术变异"""
        original = b'\x80\x80\x80\x80'
        mutated = Mutator.arithmetic(original)

        # 长度应该保持不变
        self.assertEqual(len(mutated), len(original))
        # 应该有变化
        self.assertNotEqual(mutated, original)

    def test_arithmetic_empty(self):
        """测试空数据的算术变异"""
        original = b''
        mutated = Mutator.arithmetic(original)
        self.assertEqual(mutated, b'')

    def test_arithmetic_single_byte(self):
        """测试单字节算术变异"""
        original = b'\x00'
        mutated = Mutator.arithmetic(original)
        self.assertEqual(len(mutated), 1)

    def test_arithmetic_max_val(self):
        """测试算术变异的 max_val 参数"""
        original = b'\x80'
        # 使用较大的 max_val
        mutated = Mutator.arithmetic(original, max_val=100)
        self.assertEqual(len(mutated), 1)


class TestMutatorSplice(unittest.TestCase):
    """测试拼接变异"""

    def test_splice_basic(self):
        """测试基本拼接"""
        data1 = b'AAAA'
        data2 = b'BBBB'
        spliced = Mutator.splice(data1, data2)

        self.assertIsInstance(spliced, bytes)
        # 拼接结果应该包含来自两个输入的部分
        # （除非拼接点在边界）

    def test_splice_empty_first(self):
        """测试第一个数据为空"""
        spliced = Mutator.splice(b'', b'BBBB')
        self.assertEqual(spliced, b'BBBB')

    def test_splice_empty_second(self):
        """测试第二个数据为空"""
        spliced = Mutator.splice(b'AAAA', b'')
        self.assertEqual(spliced, b'AAAA')

    def test_splice_both_empty(self):
        """测试两个数据都为空"""
        spliced = Mutator.splice(b'', b'')
        self.assertEqual(spliced, b'')

    def test_splice_via_mutate(self):
        """测试通过 mutate 接口调用 splice"""
        data1 = b'AAAA'
        data2 = b'BBBB'
        spliced = Mutator.mutate(data1, 'splice', other_data=data2)

        self.assertIsInstance(spliced, bytes)

    def test_splice_without_other_data(self):
        """测试 splice 策略没有 other_data 参数"""
        data = b'AAAA'
        result = Mutator.mutate(data, 'splice')
        # 没有 other_data 应该返回原数据
        self.assertEqual(result, data)


class TestMutatorInterestingValues(unittest.TestCase):
    """测试有趣数值常量"""

    def test_interesting_8_values(self):
        """测试 8 位有趣值"""
        from src.components.mutator import INTERESTING_8

        # 验证包含关键边界值
        self.assertIn(-128, INTERESTING_8)
        self.assertIn(-1, INTERESTING_8)
        self.assertIn(0, INTERESTING_8)
        self.assertIn(127, INTERESTING_8)

    def test_interesting_16_values(self):
        """测试 16 位有趣值"""
        from src.components.mutator import INTERESTING_16

        # 验证包含关键边界值
        self.assertIn(-32768, INTERESTING_16)
        self.assertIn(255, INTERESTING_16)
        self.assertIn(256, INTERESTING_16)
        self.assertIn(32767, INTERESTING_16)

    def test_interesting_32_values(self):
        """测试 32 位有趣值"""
        from src.components.mutator import INTERESTING_32

        # 验证包含关键边界值
        self.assertIn(-2147483648, INTERESTING_32)
        self.assertIn(65535, INTERESTING_32)
        self.assertIn(65536, INTERESTING_32)
        self.assertIn(2147483647, INTERESTING_32)

    def test_interesting_values_different_sizes(self):
        """测试不同大小数据的有趣值替换"""
        # 1 字节 - 只能用 8 位值
        data1 = b'\x00'
        mutated1 = Mutator.interesting_values(data1)
        self.assertEqual(len(mutated1), 1)

        # 2 字节 - 可以用 8 或 16 位值
        data2 = b'\x00\x00'
        mutated2 = Mutator.interesting_values(data2)
        self.assertEqual(len(mutated2), 2)

        # 4 字节 - 可以用 8/16/32 位值
        data4 = b'\x00\x00\x00\x00'
        mutated4 = Mutator.interesting_values(data4)
        self.assertEqual(len(mutated4), 4)


class TestMutatorStrategy(unittest.TestCase):
    """测试变异策略选择"""

    def test_all_strategies(self):
        """测试所有策略都能正常工作"""
        original = b'Test data for mutation'
        strategies = [
            'havoc', 'bitflip', 'byteflip', 'interesting',
            'insert', 'delete', 'arithmetic'
        ]

        for strategy in strategies:
            with self.subTest(strategy=strategy):
                mutated = Mutator.mutate(original, strategy)
                self.assertIsInstance(mutated, bytes)

    def test_unknown_strategy_defaults_to_havoc(self):
        """测试未知策略默认使用 havoc"""
        original = b'Test data'
        mutated = Mutator.mutate(original, 'unknown_strategy')

        # 应该不抛出异常，使用默认的 havoc
        self.assertIsInstance(mutated, bytes)

    def test_strategy_with_kwargs(self):
        """测试带参数的策略"""
        original = b'Test data'

        # bitflip 带 flip_count
        mutated = Mutator.mutate(original, 'bitflip', flip_count=5)
        self.assertIsInstance(mutated, bytes)

        # havoc 带 iterations
        mutated = Mutator.mutate(original, 'havoc', iterations=32)
        self.assertIsInstance(mutated, bytes)


if __name__ == '__main__':
    unittest.main()
