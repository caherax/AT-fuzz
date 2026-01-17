"""
logger 模块测试
专门测试 logger.py 中未覆盖的代码路径
"""

import unittest
import logging
import sys
from io import StringIO

# 添加父目录到路径
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from logger import get_logger, set_global_log_level, LOG_LEVEL


class TestLogger(unittest.TestCase):
    """测试 logger 模块"""

    def setUp(self):
        """每个测试前清理 logger"""
        # 清理所有 logger
        for logger_name in list(logging.Logger.manager.loggerDict.keys()):
            logger = logging.getLogger(logger_name)
            logger.handlers.clear()
            logger.setLevel(logging.NOTSET)

    def test_get_logger_basic(self):
        """测试基本 logger 获取"""
        logger = get_logger("test.basic")
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "test.basic")
        self.assertTrue(len(logger.handlers) > 0)

    def test_get_logger_with_custom_level(self):
        """测试自定义日志级别"""
        logger = get_logger("test.custom", level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)

    def test_get_logger_reuse_existing(self):
        """测试重用已存在的 logger（line 36）"""
        # 第一次创建
        logger1 = get_logger("test.reuse")
        handler_count1 = len(logger1.handlers)

        # 第二次获取同一个 logger（应该重用，不添加新 handler）
        logger2 = get_logger("test.reuse")
        handler_count2 = len(logger2.handlers)

        self.assertIs(logger1, logger2)
        self.assertEqual(handler_count1, handler_count2, "Should not add duplicate handlers")

    def test_set_global_log_level(self):
        """测试设置全局日志级别（lines 61-68）"""
        # 创建多个 logger
        logger1 = get_logger("test.global1")
        logger2 = get_logger("test.global2")

        # 设置全局日志级别为 WARNING
        set_global_log_level(logging.WARNING)

        # 验证所有 logger 都被更新
        self.assertEqual(logger1.level, logging.WARNING)
        self.assertEqual(logger2.level, logging.WARNING)

        # 验证 handler 级别也被更新
        for handler in logger1.handlers:
            self.assertEqual(handler.level, logging.WARNING)

    def test_logger_output_format(self):
        """测试 logger 输出格式"""
        # 捕获输出
        stream = StringIO()
        logger = get_logger("test.format")

        # 替换 handler 以捕获输出
        logger.handlers.clear()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # 记录日志
        logger.info("Test message")

        # 验证格式
        output = stream.getvalue()
        self.assertIn("[INFO]", output)
        self.assertIn("Test message", output)

    def test_logger_level_filtering(self):
        """测试日志级别过滤"""
        stream = StringIO()
        logger = get_logger("test.filter", level=logging.WARNING)

        logger.handlers.clear()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        logger.addHandler(handler)

        # INFO 应该被过滤
        logger.info("Should be filtered")
        # WARNING 应该显示
        logger.warning("Should appear")

        output = stream.getvalue()
        self.assertNotIn("Should be filtered", output)
        self.assertIn("Should appear", output)


class TestLoggerIntegration(unittest.TestCase):
    """测试 logger 集成场景"""

    def test_multiple_loggers_independent(self):
        """测试多个 logger 独立工作"""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        self.assertIsNot(logger1, logger2)
        self.assertEqual(logger1.name, "module1")
        self.assertEqual(logger2.name, "module2")

    def test_logger_hierarchy(self):
        """测试 logger 层次结构"""
        parent = get_logger("parent")
        child = get_logger("parent.child")

        # Python logging 自动建立父子关系
        self.assertEqual(child.parent.name, "parent")


if __name__ == '__main__':
    unittest.main(verbosity=2)
