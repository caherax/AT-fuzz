"""
executor.py 的单元测试
测试目标程序执行功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
from components.executor import TestExecutor


class TestExecutorBasic(unittest.TestCase):
    """测试执行器基本功能"""

    def setUp(self):
        """设置测试环境"""
        # 使用系统自带的 cat 命令作为测试目标
        self.test_program = '/bin/cat'
        self.test_args = 'cat @@'

    def test_executor_initialization(self):
        """测试执行器初始化"""
        executor = TestExecutor(self.test_program, self.test_args, timeout=5)

        self.assertEqual(executor.target_path, self.test_program)
        self.assertEqual(executor.timeout, 5)
        self.assertTrue(os.path.exists(executor.temp_dir))

        executor.cleanup()

    def test_invalid_program(self):
        """测试无效程序路径"""
        with self.assertRaises(FileNotFoundError):
            TestExecutor('/nonexistent/program', 'program @@')

    def test_simple_execution(self):
        """测试简单执行"""
        executor = TestExecutor(self.test_program, self.test_args, timeout=5)

        test_input = b'Hello, World!\n'
        result = executor.execute(test_input)

        self.assertEqual(result['return_code'], 0)
        self.assertFalse(result['crashed'])
        self.assertFalse(result['timeout'])
        self.assertGreater(result['exec_time'], 0)

        executor.cleanup()

    def test_execution_with_empty_input(self):
        """测试空输入"""
        executor = TestExecutor(self.test_program, self.test_args, timeout=5)

        result = executor.execute(b'')

        self.assertEqual(result['return_code'], 0)
        self.assertFalse(result['crashed'])

        executor.cleanup()

    def test_execution_with_binary_input(self):
        """测试二进制输入"""
        executor = TestExecutor(self.test_program, self.test_args, timeout=5)

        # 测试包含空字节的二进制数据
        test_input = b'\x00\x01\x02\x03\xFF\xFE\xFD'
        result = executor.execute(test_input)

        self.assertEqual(result['return_code'], 0)
        self.assertFalse(result['crashed'])

        executor.cleanup()

    def test_execution_timeout(self):
        """测试执行超时"""
        # 使用 sleep 命令测试超时
        if os.path.exists('/bin/sleep'):
            executor = TestExecutor('/bin/sleep', 'sleep 10', timeout=1)

            result = executor.execute(b'')

            self.assertTrue(result['timeout'])
            self.assertLessEqual(result['exec_time'], 2)  # 应该在超时后不久返回

            executor.cleanup()

    def test_cleanup(self):
        """测试清理功能"""
        executor = TestExecutor(self.test_program, self.test_args, timeout=5)
        temp_dir = executor.temp_dir

        executor.cleanup()

        # 清理后临时目录应该不存在
        self.assertFalse(os.path.exists(temp_dir))


class TestExecutorEdgeCases(unittest.TestCase):
    """测试边界情况"""

    def test_large_input(self):
        """测试大输入"""
        executor = TestExecutor('/bin/cat', 'cat @@', timeout=10)

        # 1MB 的输入
        large_input = b'A' * (1024 * 1024)
        result = executor.execute(large_input)

        self.assertEqual(result['return_code'], 0)
        self.assertFalse(result['crashed'])

        executor.cleanup()

    def test_special_characters_in_input(self):
        """测试特殊字符"""
        executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)

        # 包含各种特殊字符的输入
        special_input = b'\n\r\t\x00\xFF!@#$%^&*()'
        result = executor.execute(special_input)

        self.assertEqual(result['return_code'], 0)

        executor.cleanup()


class TestExecutorStdinMode(unittest.TestCase):
    """测试 stdin 输入模式（没有 @@ 的情况）"""

    def test_stdin_input(self):
        """测试通过 stdin 传递输入"""
        # 使用不带 @@ 的命令，输入通过 stdin
        executor = TestExecutor('/bin/cat', 'cat', timeout=5)

        test_input = b'Hello via stdin!\n'
        result = executor.execute(test_input)

        self.assertEqual(result['return_code'], 0)
        self.assertFalse(result['crashed'])

        executor.cleanup()

    def test_stdin_binary_input(self):
        """测试 stdin 模式下的二进制输入"""
        executor = TestExecutor('/bin/cat', 'cat', timeout=5)

        binary_input = bytes(range(256))
        result = executor.execute(binary_input)

        self.assertEqual(result['return_code'], 0)

        executor.cleanup()

    def test_stdin_empty_input(self):
        """测试 stdin 模式下的空输入"""
        executor = TestExecutor('/bin/cat', 'cat', timeout=5)

        result = executor.execute(b'')

        self.assertEqual(result['return_code'], 0)

        executor.cleanup()


class TestExecutorSandbox(unittest.TestCase):
    """测试沙箱功能（如果可用）"""

    def setUp(self):
        """检查 bwrap 是否可用"""
        import shutil
        self.bwrap_available = shutil.which('bwrap') is not None

    def test_sandbox_fallback(self):
        """测试沙箱不可用时的回退"""
        from config import CONFIG
        original_setting = CONFIG.get('use_sandbox', False)

        try:
            CONFIG['use_sandbox'] = True
            executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)

            # 无论 bwrap 是否可用，执行器都应该正常工作
            result = executor.execute(b'test')
            self.assertFalse(result['crashed'])

            executor.cleanup()
        finally:
            CONFIG['use_sandbox'] = original_setting

    def test_sandbox_isolation(self):
        """测试沙箱隔离（如果 bwrap 可用）"""
        if not self.bwrap_available:
            self.skipTest("bwrap not available")

        from config import CONFIG
        original_setting = CONFIG.get('use_sandbox', False)

        try:
            CONFIG['use_sandbox'] = True
            executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)

            self.assertTrue(executor.use_sandbox)

            result = executor.execute(b'sandbox test')
            self.assertEqual(result['return_code'], 0)

            executor.cleanup()
        finally:
            CONFIG['use_sandbox'] = original_setting


class TestExecutorConcurrency(unittest.TestCase):
    """测试并发执行"""

    def test_multiple_executors_no_conflict(self):
        """测试多个执行器同时运行不冲突"""
        executors = []

        # 创建多个执行器
        for i in range(3):
            executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)
            executors.append(executor)

        # 验证每个执行器有独立的临时目录
        temp_dirs = [e.temp_dir for e in executors]
        self.assertEqual(len(temp_dirs), len(set(temp_dirs)))  # 所有目录都不同

        # 并发执行
        results = []
        for i, executor in enumerate(executors):
            result = executor.execute(f'test input {i}'.encode())
            results.append(result)

        # 验证所有执行成功
        for result in results:
            self.assertEqual(result['return_code'], 0)

        # 清理
        for executor in executors:
            executor.cleanup()

    def test_temp_dir_cleanup(self):
        """测试临时目录正确清理"""
        executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)
        temp_dir = executor.temp_dir

        self.assertTrue(os.path.exists(temp_dir))

        executor.cleanup()

        self.assertFalse(os.path.exists(temp_dir))


class TestExecutorResultFields(unittest.TestCase):
    """测试执行结果字段完整性"""

    def test_result_contains_all_fields(self):
        """测试结果包含所有必需字段"""
        from components.executor import EXEC_RESULT_FIELDS

        executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)
        result = executor.execute(b'test')

        for field in EXEC_RESULT_FIELDS:
            self.assertIn(field, result, f"Missing field: {field}")

        executor.cleanup()

    def test_result_types(self):
        """测试结果字段类型正确"""
        executor = TestExecutor('/bin/cat', 'cat @@', timeout=5)
        result = executor.execute(b'test')

        self.assertIsInstance(result['return_code'], int)
        self.assertIsInstance(result['exec_time'], float)
        self.assertIsInstance(result['crashed'], bool)
        self.assertIsInstance(result['timeout'], bool)
        self.assertIsInstance(result['stderr'], bytes)
        # coverage 可以是 None 或 bytes
        self.assertTrue(result['coverage'] is None or isinstance(result['coverage'], bytes))

        executor.cleanup()


if __name__ == '__main__':
    unittest.main()
