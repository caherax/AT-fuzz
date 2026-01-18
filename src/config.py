"""
全局配置文件

注意：添加新配置项时,只需更新：
1. 本文件中的 CONFIG_SCHEMA（元数据）
2. 本文件中的 CONFIG（默认值）
3. README.md 中的配置说明（如需要）

命令行参数会自动从 CONFIG_SCHEMA 生成。
"""

from pathlib import Path
from typing import Any, Callable, NamedTuple


# ========== 配置项元数据定义 ==========
class ConfigMeta(NamedTuple):
    """配置项元数据"""
    type: type                           # 数据类型
    validator: Callable[[Any], bool]     # 验证函数
    description: str                     # 描述文本
    cli_name: str                        # 命令行参数名（自动转换：timeout -> --timeout）
    cli_help: str                        # 命令行帮助文本
    cli_choices: list | None = None      # 命令行可选值（仅 str 类型）


# 配置项 Schema：定义所有配置项的元数据
CONFIG_SCHEMA: dict[str, ConfigMeta] = {
    # 核心路径参数（命令行必需，但可通过 config 提供默认值）
    'target': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str) and len(x) > 0,
        description='目标程序路径',
        cli_name='--target',
        cli_help='Target program path'
    ),
    'args': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str),
        description='目标程序参数',
        cli_name='--args',
        cli_help='Target program arguments (use @@ for input file)'
    ),
    'seeds': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str) and len(x) > 0,
        description='种子文件目录',
        cli_name='--seeds',
        cli_help='Seed directory'
    ),
    'output': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str) and len(x) > 0,
        description='输出目录',
        cli_name='--output',
        cli_help='Output directory'
    ),
    'target_id': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str),
        description='目标程序标识符',
        cli_name='--target-id',
        cli_help='Target ID for naming'
    ),
    'checkpoint_path': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str),
        description='检查点保存目录或文件路径',
        cli_name='--checkpoint-path',
        cli_help='Directory to save checkpoints or path to checkpoint file'
    ),
    'resume_from': ConfigMeta(
        type=str,
        validator=lambda x: isinstance(x, str),
        description='从检查点恢复的路径',
        cli_name='--resume-from',
        cli_help='Path to checkpoint.json to resume from'
    ),
    'duration': ConfigMeta(
        type=int,
        validator=lambda x: x > 0,
        description='模糊测试持续时间（秒）',
        cli_name='--duration',
        cli_help='Fuzzing duration (seconds)'
    ),

    # 执行控制
    'timeout': ConfigMeta(
        type=float,
        validator=lambda x: 0.0 < x,
        description='单次执行超时（秒）',
        cli_name='--timeout',
        cli_help='Execution timeout per input (seconds)'
    ),
    'mem_limit': ConfigMeta(
        type=int,
        validator=lambda x: 0 < x,
        description='内存限制（MB）',
        cli_name='--mem-limit',
        cli_help='Memory limit for target process (MB)'
    ),
    'use_sandbox': ConfigMeta(
        type=bool,
        validator=lambda x: isinstance(x, bool),
        description='是否使用沙箱隔离环境（bubblewrap）',
        cli_name='--use-sandbox',
        cli_help='Enable sandbox isolation (bubblewrap)'
    ),

    # 覆盖率相关
    'bitmap_size': ConfigMeta(
        type=int,
        validator=lambda x: 0 <= x,
        description='AFL++ 共享内存 bitmap 大小（byte）',
        cli_name='--bitmap-size',
        cli_help='Coverage bitmap size (bytes)'
    ),

    # 变异策略
    'max_seed_size': ConfigMeta(
        type=int,
        validator=lambda x: 1 <= x,
        description='最大种子大小（byte）',
        cli_name='--max-seed-size',
        cli_help='Maximum seed size (bytes) for initial and mutated seeds'
    ),
    'havoc_iterations': ConfigMeta(
        type=int,
        validator=lambda x: 0 <= x,
        description='Havoc 变异迭代次数',
        cli_name='--havoc-iterations',
        cli_help='Number of havoc mutation iterations (higher = more mutations)'
    ),

    # 调度器参数
    'seed_sort_strategy': ConfigMeta(
        type=str,
        validator=lambda x: x in {'energy', 'fifo'},
        description='种子排序策略: energy/fifo',
        cli_name='--seed-sort-strategy',
        cli_help='Seed scheduling strategy',
        cli_choices=['energy', 'fifo']
    ),
    'max_seeds': ConfigMeta(
        type=int,
        validator=lambda x: 1 <= x,
        description='种子队列最大数量',
        cli_name='--max-seeds',
        cli_help='Maximum number of seeds in queue'
    ),
    'max_seeds_memory': ConfigMeta(
        type=int,
        validator=lambda x: 0 < x,
        description='种子队列最大内存（MB）',
        cli_name='--max-seeds-memory',
        cli_help='Maximum seed queue memory usage (MB)'
    ),

    # 日志与监控
    'log_interval': ConfigMeta(
        type=float,
        validator=lambda x: 0 < x,
        description='状态/日志更新频率（秒）',
        cli_name='--log-interval',
        cli_help='Status log update interval (seconds)'
    ),
    'stderr_max_len': ConfigMeta(
        type=int,
        validator=lambda x: 0 <= x,
        description='stderr 输出最大长度（byte）',
        cli_name='--stderr-max-len',
        cli_help='Maximum stderr output length (bytes)'
    ),
    'crash_info_max_len': ConfigMeta(
        type=int,
        validator=lambda x: 0 <= x,
        description='崩溃信息中 stderr 的最大长度（byte）',
        cli_name='--crash-info-max-len',
        cli_help='Maximum stderr length in crash info (bytes)'
    ),
}

# ========== Fuzzer 默认配置 ==========
CONFIG = {
    # --- 核心参数 ---
    'target': None,                 # 目标程序路径
    'args': None,                   # 目标程序参数
    'seeds': None,                  # 种子文件目录
    'output': None,                 # 输出目录
    'target_id': 'unknown',         # 目标 ID
    'duration': 3600,               # 默认运行 1 小时

    'checkpoint_path': None,        # 检查点目录或文件路径
    'resume_from': '',              # 从指定检查点恢复的路径

    # --- 执行控制 ---
    'timeout': 1.0,                 # 单次执行超时（秒）
    'mem_limit': 256,               # 内存限制（MB）
    'use_sandbox': False,           # 是否使用沙箱 (Linux bwrap)

    # --- 覆盖率相关 ---
    'bitmap_size': 65536,           # AFL++ 共享内存 bitmap 大小（byte）

    # --- 变异策略 ---
    'max_seed_size': 1024 * 500,    # 最大种子大小 (500KB)，限制初始种子和变异后的种子
    'havoc_iterations': 16,         # Havoc 变异迭代次数，控制变异强度（越大变异越多）

    # --- 调度器参数 ---
    'seed_sort_strategy': 'energy', # 种子排序策略: 'energy'(能量优先), 'fifo'(入队顺序)
    'max_seeds': 10000,             # 种子队列最大数量
    'max_seeds_memory': 256,        # 种子队列最大内存（MB）

    # --- 日志与监控 ---
    'log_interval': 10.0,           # 状态/日志更新频率（秒）
    'stderr_max_len': 1000,         # stderr 输出最大长度（byte）
    'crash_info_max_len': 500,      # 崩溃信息中 stderr 的最大长度（byte）
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

        meta = CONFIG_SCHEMA[key]

        # 类型检查
        if not isinstance(value, meta.type):
            errors.append(f"Config '{key}' should be {meta.type.__name__}, got {type(value).__name__}")
            continue

        # 使用 lambda 验证函数检查值的有效性
        try:
            if not meta.validator(value):
                errors.append(f"Config '{key}' = {value} failed validation: {meta.description}")
        except Exception as e:
            errors.append(f"Config '{key}' validation error: {e}")

    return errors


def apply_cli_args_to_config(args) -> None:
    """
    将命令行参数应用到全局 CONFIG

    Args:
        args: argparse.Namespace 对象
    """
    for config_key, meta in CONFIG_SCHEMA.items():
        # 将 config_key 转换为命令行参数名（timeout -> timeout, mem_limit -> mem_limit）
        # argparse 会自动将 --mem-limit 转换为 args.mem_limit
        arg_name = config_key  # argparse 会将 - 转换为 _

        # 获取命令行参数值
        arg_value = getattr(args, arg_name, None)

        if arg_value is not None:
            CONFIG[config_key] = arg_value


def apply_advanced_defaults() -> None:
    """
    设置高级默认值（依赖其他配置项的默认值）
    必须在 apply_cli_args_to_config 之后、validate_config 之前调用
    """
    # checkpoint_path: 如果未设置，默认为 <output>/checkpoints
    if CONFIG.get('checkpoint_path') is None and CONFIG.get('output') is not None:
        CONFIG['checkpoint_path'] = str(Path(CONFIG['output']) / 'checkpoints')

    # 可在此添加其他默认值
