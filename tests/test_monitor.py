"""
Monitor 组件单元测试
重点测试覆盖率检测和崩溃处理的核心功能
"""

import os
import tempfile
import shutil
import unittest
from pathlib import Path

# 添加父目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from components.monitor import ExecutionMonitor
from components.executor import ExecutionResult


class TestMonitorCoverage(unittest.TestCase):
    """测试覆盖率检测功能"""

    def setUp(self):
        """创建临时目录和 Monitor 实例"""
        self.temp_dir = tempfile.mkdtemp(prefix='test_monitor_')
        self.monitor = ExecutionMonitor(self.temp_dir, use_coverage=True)

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_has_new_bits_first_coverage(self):
        """测试第一次覆盖率应该被识别为新覆盖"""
        # 创建一个简单的覆盖率 bitmap（64KB）
        coverage = bytearray(65536)
        coverage[0] = 0xFF  # 设置第一个字节
        coverage[100] = 0x0F  # 设置第100个字节

        # 第一次应该有新覆盖（virgin bitmap 是 monitor.virgin_bits）
        has_new = self.monitor._has_new_bits(bytes(coverage), self.monitor.virgin_bits)
        self.assertTrue(has_new, "First coverage should be recognized as new")

    def test_has_new_bits_no_change(self):
        """测试相同覆盖率不应该被识别为新覆盖"""
        coverage = bytearray(65536)
        coverage[0] = 0xFF
        coverage_bytes = bytes(coverage)

        # 第一次
        self.monitor._has_new_bits(coverage_bytes, self.monitor.virgin_bits)

        # 第二次相同覆盖（virgin bitmap 已经更新）
        has_new = self.monitor._has_new_bits(coverage_bytes, self.monitor.virgin_bits)
        self.assertFalse(has_new, "Same coverage should not be new")

    def test_has_new_bits_additional_coverage(self):
        """测试新增覆盖率应该被识别"""
        # 第一次覆盖
        coverage1 = bytearray(65536)
        coverage1[0] = 0x0F  # 低4位
        self.monitor._has_new_bits(bytes(coverage1), self.monitor.virgin_bits)

        # 第二次覆盖（增加新位）
        coverage2 = bytearray(65536)
        coverage2[0] = 0xFF  # 所有位（包含之前的低4位 + 新的高4位）
        has_new = self.monitor._has_new_bits(bytes(coverage2), self.monitor.virgin_bits)
        self.assertTrue(has_new, "Additional coverage should be recognized as new")

    def test_has_new_bits_new_bytes(self):
        """测试新字节的覆盖率应该被识别"""
        # 第一次覆盖
        coverage1 = bytearray(65536)
        coverage1[0] = 0xFF
        self.monitor._has_new_bits(bytes(coverage1), self.monitor.virgin_bits)

        # 第二次覆盖（新位置）
        coverage2 = bytearray(65536)
        coverage2[0] = 0xFF  # 旧位置
        coverage2[100] = 0x01  # 新位置
        has_new = self.monitor._has_new_bits(bytes(coverage2), self.monitor.virgin_bits)
        self.assertTrue(has_new, "New byte coverage should be recognized as new")

    def test_has_new_bits_subset_coverage(self):
        """测试覆盖率子集不应该被识别为新覆盖"""
        # 第一次覆盖（完整）
        coverage1 = bytearray(65536)
        coverage1[0] = 0xFF
        coverage1[1] = 0xFF
        self.monitor._has_new_bits(bytes(coverage1), self.monitor.virgin_bits)

        # 第二次覆盖（子集）
        coverage2 = bytearray(65536)
        coverage2[0] = 0x0F  # 仅部分位
        has_new = self.monitor._has_new_bits(bytes(coverage2), self.monitor.virgin_bits)
        self.assertFalse(has_new, "Subset coverage should not be new")


class TestMonitorCrashHandling(unittest.TestCase):
    """测试崩溃处理功能"""

    def setUp(self):
        """创建临时目录和 Monitor 实例"""
        self.temp_dir = tempfile.mkdtemp(prefix='test_monitor_crash_')
        self.monitor = ExecutionMonitor(self.temp_dir, use_coverage=False)

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_handle_crash_basic(self):
        """测试基本崩溃处理"""
        input_data = b"CRASH_INPUT"
        result: ExecutionResult = {
            'return_code': -11,  # SIGSEGV
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b'Segmentation fault',
            'coverage': None
        }

        # 处理崩溃
        self.monitor._handle_crash(input_data, result)

        # 验证崩溃文件已保存
        crashes_dir = Path(self.temp_dir) / 'crashes'
        self.assertTrue(crashes_dir.exists(), "Crashes directory should exist")

        crash_files = list(crashes_dir.glob('crash_*'))
        # 注意：可能有两个文件（crash 文件 + crash info 文件）
        self.assertGreaterEqual(len(crash_files), 1, "Should have at least one crash file")

        # 验证统计
        self.assertEqual(self.monitor.stats.saved_crashes, 1, "Should have 1 saved crash")
        # unique_crashes 不在 MonitorStats 中，只检查 saved_crashes

    def test_handle_crash_deduplication(self):
        """测试崩溃去重功能"""
        input1 = b"INPUT1"
        input2 = b"INPUT2"

        # 相同的崩溃特征（相同 stderr）
        result: ExecutionResult = {
            'return_code': -11,
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b'Segmentation fault at 0x12345',
            'coverage': None
        }

        # 第一次崩溃
        self.monitor._handle_crash(input1, result)
        first_count = self.monitor.stats.saved_crashes

        # 第二次相同崩溃（应该被去重）
        self.monitor._handle_crash(input2, result)
        # 由于去重，saved_crashes 不应该增加
        self.assertEqual(self.monitor.stats.saved_crashes, first_count,
                         "Same crash should not increase saved count due to deduplication")

    def test_handle_crash_different_crashes(self):
        """测试不同崩溃应该都被保存"""
        input1 = b"INPUT1"
        input2 = b"INPUT2"

        result1: ExecutionResult = {
            'return_code': -11,  # SIGSEGV
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b'Segmentation fault at 0x11111',
            'coverage': None
        }

        result2: ExecutionResult = {
            'return_code': -6,  # SIGABRT
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b'Assertion failed at line 42',
            'coverage': None
        }

        # 处理两个不同崩溃
        self.monitor._handle_crash(input1, result1)
        self.monitor._handle_crash(input2, result2)

        # 验证统计（两个不同崩溃都应该被保存）
        self.assertEqual(self.monitor.stats.saved_crashes, 2, "Should have 2 saved crashes")


class TestMonitorIntegration(unittest.TestCase):
    """测试 Monitor 集成功能"""

    def setUp(self):
        """创建临时目录和 Monitor 实例"""
        self.temp_dir = tempfile.mkdtemp(prefix='test_monitor_int_')
        self.monitor = ExecutionMonitor(self.temp_dir, use_coverage=True)

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_result_new_coverage(self):
        """测试 process_result 对新覆盖率的处理"""
        input_data = b"TEST_INPUT"
        coverage = bytearray(65536)
        coverage[42] = 0xFF

        result: ExecutionResult = {
            'return_code': 0,
            'exec_time': 0.05,
            'crashed': False,
            'timeout': False,
            'stderr': b'',
            'coverage': bytes(coverage)
        }

        # 处理结果
        has_new = self.monitor.process_execution(input_data, result)

        # 验证
        self.assertTrue(has_new, "New coverage should return True")
        self.assertEqual(self.monitor.stats.total_execs, 1, "Should have 1 execution")

    def test_process_result_crash(self):
        """测试 process_execution 对崩溃的处理"""
        input_data = b"CRASH_INPUT"

        result: ExecutionResult = {
            'return_code': -11,
            'exec_time': 0.05,
            'crashed': True,
            'timeout': False,
            'stderr': b'Segmentation fault',
            'coverage': None
        }

        # 处理结果
        has_new = self.monitor.process_execution(input_data, result)

        # 验证
        self.assertTrue(has_new, "Crash should return True (considered interesting)")
        self.assertEqual(self.monitor.stats.total_execs, 1, "Should have 1 execution")
        self.assertEqual(self.monitor.stats.saved_crashes, 1, "Should have 1 saved crash")


class TestMonitorEnhanced(unittest.TestCase):
    """Monitor 增强功能综合测试（精简版）"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp(prefix='test_monitor_enh_')
        self.output_dir = Path(self.temp_dir) / "output"
        self.output_dir.mkdir(parents=True)

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_coverage_cache(self):
        """测试覆盖率计算缓存"""
        monitor = ExecutionMonitor(
            output_dir=str(self.output_dir),
            use_coverage=True
        )

        coverage = bytes([0xFF] * 1024)

        # 第一次计算
        bits1 = monitor._get_coverage_bits(coverage)
        # 第二次应该使用缓存
        bits2 = monitor._get_coverage_bits(coverage)
        self.assertEqual(bits1, bits2)

        # 填充超过 10000 个条目测试缓存清理
        for i in range(12000):
            monitor._get_coverage_bits(bytes([i % 256] * 1024))
        self.assertLess(len(monitor._coverage_cache), 10000)

    def test_crash_handling(self):
        """测试崩溃处理和去重"""
        monitor = ExecutionMonitor(
            output_dir=str(self.output_dir),
            use_coverage=True
        )

        # 第一次崩溃
        exec_result1: ExecutionResult = {
            'return_code': -11,
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b"Segmentation fault",
            'coverage': bytes([0xFF, 0xAA] + [0] * 65534)
        }
        result1 = monitor._handle_crash(b"crash1", exec_result1)
        self.assertTrue(result1)
        self.assertEqual(monitor.stats.saved_crashes, 1)

        # 相同覆盖率的崩溃（去重）
        result2 = monitor._handle_crash(b"crash2", exec_result1)
        self.assertFalse(result2)

        # 测试无覆盖率时的哈希去重
        monitor2 = ExecutionMonitor(
            output_dir=str(Path(self.output_dir) / "no_cov"),
            use_coverage=False
        )
        exec_result_no_cov: ExecutionResult = {
            'return_code': -6,
            'exec_time': 0.1,
            'crashed': True,
            'timeout': False,
            'stderr': b"SIGABRT",
            'coverage': None
        }
        result3 = monitor2._handle_crash(b"crash_hash", exec_result_no_cov)
        self.assertTrue(result3)
        result4 = monitor2._handle_crash(b"crash_hash", exec_result_no_cov)
        self.assertFalse(result4)

    def test_hang_handling(self):
        """测试挂起处理和去重"""
        monitor = ExecutionMonitor(
            output_dir=str(self.output_dir),
            use_coverage=True
        )

        exec_result: ExecutionResult = {
            'return_code': -15,
            'exec_time': 2.5,
            'crashed': False,
            'timeout': True,
            'stderr': b"",
            'coverage': bytes([0xAA, 0x55] + [0] * 65534)
        }

        # 第一次挂起
        result1 = monitor._handle_hang(b"hang1", exec_result)
        self.assertTrue(result1)
        self.assertEqual(monitor.stats.saved_hangs, 1)

        # 相同覆盖率的挂起（去重）
        result2 = monitor._handle_hang(b"hang2", exec_result)
        self.assertFalse(result2)

    def test_simplify_trace(self):
        """测试 simplify_trace"""
        # 测试基本转换
        trace = bytes([0, 1, 2, 100, 255])
        simplified = ExecutionMonitor._simplify_trace(trace)
        expected = bytearray([1, 128, 128, 128, 128])
        self.assertEqual(simplified, expected)

        # 测试空 trace
        trace_empty = bytes([0] * 100)
        simplified_empty = ExecutionMonitor._simplify_trace(trace_empty)
        self.assertTrue(all(b == 1 for b in simplified_empty))


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
