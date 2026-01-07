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


if __name__ == '__main__':
    unittest.main()
