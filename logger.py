"""
统一的日志配置模块

使用方法：
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("信息")
    logger.warning("警告")
    logger.error("错误")
"""

import logging
import sys
from typing import Optional


# 全局日志级别
LOG_LEVEL = logging.INFO


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    获取配置好的 logger

    Args:
        name: logger 名称（通常使用 __name__）
        level: 日志级别（默认使用全局 LOG_LEVEL）

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(level or LOG_LEVEL)

    # 创建控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level or LOG_LEVEL)

    # 设置格式（简洁格式，保持与原 print 风格一致）
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger


def set_global_log_level(level: int) -> None:
    """
    设置全局日志级别

    Args:
        level: logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR
    """
    global LOG_LEVEL
    LOG_LEVEL = level

    # 更新所有已存在的 logger
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
