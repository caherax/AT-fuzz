"""
utils.py 的单元测试
测试覆盖率计算、格式化等工具函数
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.utils import (
    count_coverage_bits,
    get_coverage_delta,
    has_new_coverage,
    format_time,
    format_size,
    CoverageTracker,
    AFLSHM
)


class TestCoverageBits(unittest.TestCase):
    """测试覆盖率位计算"""

    def test_count_empty_bitmap(self):
        """测试空 bitmap"""
        bitmap = b'\x00\x00\x00\x00'
        self.assertEqual(count_coverage_bits(bitmap), 0)

    def test_count_single_bit(self):
        """测试单个位"""
        bitmap = b'\x01'  # 00000001
        self.assertEqual(count_coverage_bits(bitmap), 1)

    def test_count_multiple_bits(self):
        """测试多个位"""
        bitmap = b'\xFF'  # 11111111
        self.assertEqual(count_coverage_bits(bitmap), 8)

        bitmap = b'\x0F\xF0'  # 00001111 11110000
        self.assertEqual(count_coverage_bits(bitmap), 8)

    def test_count_mixed_bytes(self):
        """测试混合字节"""
        bitmap = b'\x01\x02\x04\x08'  # 每个字节一个位
        self.assertEqual(count_coverage_bits(bitmap), 4)


class TestCoverageDelta(unittest.TestCase):
    """测试覆盖率增量计算"""

    def test_no_change(self):
        """测试无变化"""
        old = b'\xFF\x00'
        new = b'\xFF\x00'
        self.assertEqual(get_coverage_delta(new, old), 0)

    def test_new_coverage(self):
        """测试新覆盖"""
        old = b'\x00\x00'
        new = b'\xFF\x00'
        self.assertEqual(get_coverage_delta(new, old), 8)

    def test_partial_new_coverage(self):
        """测试部分新覆盖"""
        old = b'\x0F'  # 00001111
        new = b'\xFF'  # 11111111
        self.assertEqual(get_coverage_delta(new, old), 4)  # 高 4 位是新的

    def test_size_mismatch(self):
        """测试大小不匹配"""
        old = b'\x00\x00'
        new = b'\x00'
        self.assertEqual(get_coverage_delta(new, old), 0)

    def test_has_new_coverage(self):
        """测试是否有新覆盖的辅助函数"""
        old = b'\x00'
        new = b'\x01'
        self.assertTrue(has_new_coverage(new, old))

        old = b'\xFF'
        new = b'\xFF'
        self.assertFalse(has_new_coverage(new, old))


class TestFormatters(unittest.TestCase):
    """测试格式化函数"""

    def test_format_time(self):
        """测试时间格式化"""
        self.assertEqual(format_time(30), "30.0s")
        self.assertEqual(format_time(90), "1.5m")
        self.assertEqual(format_time(3600), "1.0h")
        self.assertEqual(format_time(7200), "2.0h")

    def test_format_size(self):
        """测试大小格式化"""
        self.assertEqual(format_size(100), "100.0B")
        self.assertEqual(format_size(1024), "1.0KB")
        self.assertEqual(format_size(1024 * 1024), "1.0MB")


class TestCoverageTracker(unittest.TestCase):
    """测试覆盖率追踪器"""

    def setUp(self):
        """设置测试环境"""
        self.tracker = CoverageTracker(bitmap_size=16)  # 小一点方便测试

    def test_initial_coverage(self):
        """测试初始覆盖率"""
        self.assertEqual(self.tracker.get_coverage_count(), 0)

    def test_update_coverage(self):
        """测试更新覆盖率"""
        bitmap1 = b'\xFF' + b'\x00' * 15
        delta, has_new = self.tracker.update(bitmap1)

        self.assertTrue(has_new)
        self.assertEqual(delta, 8)
        self.assertEqual(self.tracker.get_coverage_count(), 8)

    def test_incremental_coverage(self):
        """测试增量覆盖"""
        # 第一次更新
        bitmap1 = b'\x0F' + b'\x00' * 15  # 低 4 位
        delta1, has_new1 = self.tracker.update(bitmap1)
        self.assertTrue(has_new1)
        self.assertEqual(delta1, 4)

        # 第二次更新（新增高 4 位）
        bitmap2 = b'\xFF' + b'\x00' * 15  # 全 8 位
        delta2, has_new2 = self.tracker.update(bitmap2)
        self.assertTrue(has_new2)
        self.assertEqual(delta2, 4)  # 只有高 4 位是新的
        self.assertEqual(self.tracker.get_coverage_count(), 8)

        # 第三次更新（无新覆盖）
        bitmap3 = b'\xFF' + b'\x00' * 15
        delta3, has_new3 = self.tracker.update(bitmap3)
        self.assertFalse(has_new3)
        self.assertEqual(delta3, 0)

    def test_record_snapshot(self):
        """测试快照记录"""
        self.tracker.record_snapshot("2026-01-01T12:00:00", 100)
        self.tracker.record_snapshot("2026-01-01T12:01:00", 150)

        self.assertEqual(len(self.tracker.coverage_history), 2)
        self.assertEqual(self.tracker.coverage_history[0]['coverage'], 100)
        self.assertEqual(self.tracker.coverage_history[1]['coverage'], 150)


class TestCoverageBitsEnhanced(unittest.TestCase):
    """增强的覆盖率位数计算测试（精简版）"""

    def test_count_coverage_bits_comprehensive(self):
        """综合测试覆盖率位数计算"""
        # None 输入
        self.assertEqual(count_coverage_bits(None), 0)

        # 空 bitmap
        self.assertEqual(count_coverage_bits(b'\x00' * 1024), 0)

        # 多字节覆盖
        bitmap = bytearray(1024)
        bitmap[0] = 0xFF  # 8 bits
        bitmap[1] = 0x0F  # 4 bits
        bitmap[10] = 0x01  # 1 bit
        self.assertEqual(count_coverage_bits(bytes(bitmap)), 13)


class TestCoverageTrackerEnhanced(unittest.TestCase):
    """增强的 CoverageTracker 测试（精简版）"""

    def test_coverage_tracker_lifecycle(self):
        """综合测试 CoverageTracker 生命周期"""
        tracker = CoverageTracker(bitmap_size=64)

        # 初始化测试
        self.assertEqual(len(tracker.global_bitmap), 64)
        self.assertEqual(tracker.get_coverage_count(), 0)

        # 第一次覆盖
        bitmap1 = bytearray(64)
        bitmap1[0] = 0xFF  # 8 bits
        delta1, has_new1 = tracker.update(bytes(bitmap1))
        self.assertTrue(has_new1)
        self.assertEqual(tracker.get_coverage_count(), 8)

        # 相同覆盖（去重）
        delta2, has_new2 = tracker.update(bytes(bitmap1))
        self.assertFalse(has_new2)

        # 新增覆盖
        bitmap2 = bytearray(64)
        bitmap2[0] = 0xFF
        bitmap2[1] = 0x0F  # 额外 4 bits
        delta3, has_new3 = tracker.update(bytes(bitmap2))
        self.assertTrue(has_new3)
        self.assertEqual(tracker.get_coverage_count(), 12)

        # 快照记录
        tracker.record_snapshot("2024-01-01T00:00:00", 12)
        self.assertEqual(len(tracker.coverage_history), 1)


class TestAFLSHM(unittest.TestCase):
    """测试 AFLSHM 共享内存类"""

    def test_aflshm_lifecycle(self):
        """测试 AFLSHM 完整生命周期"""
        shm = AFLSHM(bitmap_size=1024)

        # 创建验证
        self.assertGreater(shm.get_shm_id(), 0)
        self.assertIsNotNone(shm.shm_addr)

        # 读取验证
        bitmap = shm.read_bitmap()
        self.assertEqual(len(bitmap), 1024)
        self.assertTrue(all(b == 0 for b in bitmap))

        # 清空测试
        shm.clear()
        bitmap = shm.read_bitmap()
        self.assertTrue(all(b == 0 for b in bitmap))

        # 清理
        shm.cleanup()
        self.assertEqual(shm.shm_id, -1)


if __name__ == '__main__':
    unittest.main()
