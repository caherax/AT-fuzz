"""
全局配置文件

注意：添加新配置项时，需要同时更新：
1. 本文件中的 CONFIG 字典
2. 本文件中的 CONFIG_SCHEMA（类型和约束）
3. fuzzer.py 中的命令行参数（如需要）
4. README.md 中的配置说明（如需要）
"""

from typing import Any, Callable


# ========== 配置项 Schema 定义 ==========
# 用于验证配置项的类型和约束
CONFIG_SCHEMA: dict[str, tuple[type, Callable[[Any], bool], str]] = {
    # (类型, 验证函数, 描述)
    'timeout': (float, lambda x: 0.0 < x, '单次执行超时（秒）'),
    'mem_limit': (int, lambda x: 0 < x, '内存限制（MB）'),
    'bitmap_size': (int, lambda x: 0 <= x, 'AFL++ 共享内存 bitmap 大小（byte）'),
    'max_seed_size': (int, lambda x: 1 <= x, '最大种子大小（byte）'),
    'havoc_iterations': (int, lambda x: 0 <= x, 'Havoc 变异迭代次数'),
    'seed_sort_strategy': (str, lambda x: x in {'energy', 'fifo'}, '种子排序策略: energy/fifo'),
    'max_seeds': (int, lambda x: 1 <= x, '种子队列最大数量'),
    'max_seeds_memory': (int, lambda x: 0 < x, '种子队列最大内存（MB）'),
    'log_interval': (float, lambda x: 0 < x, '状态/日志更新频率（秒）'),
    'stderr_max_len': (int, lambda x: 0 <= x, 'stderr 输出最大长度（byte）'),
    'crash_info_max_len': (int, lambda x: 0 <= x, '崩溃信息中 stderr 的最大长度（byte）'),
    'use_sandbox': (bool, lambda x: isinstance(x, bool), '是否使用沙箱隔离环境（bubblewrap）'),
}

# ========== Fuzzer 核心配置 ==========
CONFIG = {
    # --- 执行控制 ---
    'timeout': 1.0,                  # 单次执行超时（秒）
    'mem_limit': 256,                # 内存限制（MB）
    'use_sandbox': False,            # 是否使用沙箱 (Linux bwrap)

    # --- 覆盖率相关 ---
    'bitmap_size': 65536,            # AFL++ 共享内存 bitmap 大小（byte）

    # --- 变异策略 ---
    'max_seed_size': 1024 * 500,     # 最大种子大小 (500KB)，限制初始种子和变异后的种子
    'havoc_iterations': 16,          # Havoc 变异迭代次数，控制变异强度（越大变异越多）

    # --- 调度器参数 ---
    'seed_sort_strategy': 'energy',  # 种子排序策略: 'energy'(能量优先), 'fifo'(入队顺序)
    'max_seeds': 10000,              # 种子队列最大数量
    'max_seeds_memory': 256,         # 种子队列最大内存（MB）

    # --- 日志与监控 ---
    'log_interval': 10,              # 状态/日志更新频率（秒）
    'stderr_max_len': 1000,          # stderr 输出最大长度（byte）
    'crash_info_max_len': 500,       # 崩溃信息中 stderr 的最大长度（byte）
}


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    验证配置项的类型和约束

    Args:
        config: 要验证的配置字典

    Returns:
        错误消息列表（空列表表示验证通过）
    """
    errors = []

    for key, value in config.items():
        if key not in CONFIG_SCHEMA:
            # 未知配置项，跳过
            continue

        expected_type, validator, desc = CONFIG_SCHEMA[key]

        # 类型检查
        if not isinstance(value, expected_type):
            errors.append(f"Config '{key}' should be {expected_type.__name__}, got {type(value).__name__}")
            continue

        # 使用 lambda 验证函数检查值的有效性
        try:
            if not validator(value):
                errors.append(f"Config '{key}' = {value} failed validation: {desc}")
        except Exception as e:
            errors.append(f"Config '{key}' validation error: {e}")

    return errors


# 启动时验证默认配置
_config_errors = validate_config(CONFIG)