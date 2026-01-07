"""
全局配置文件
"""

# ========== Fuzzer 核心配置 ==========
CONFIG = {
    # --- 执行控制 ---
    'timeout': 1.0,                   # 单次执行超时（秒）
    'mem_limit': 256,                 # 内存限制（MB）

    # --- 覆盖率相关 ---
    'bitmap_size': 65536,             # AFL++ 默认共享内存 bitmap 大小 (2^16)

    # --- 变异策略 ---
    'max_file_size': 1024 * 500,      # 最大输入文件大小 (500KB)
    'havoc_divider': 10,              # Havoc 阶段的变异强度因子 (值越小变异越多)
    'mutation_rate': 0.6,             # 一般变异概率

    # --- 调度器参数 ---
    'seed_sort_strategy': 'composite',# 种子排序策略: 'coverage', 'composite'
    'base_energy': 10,                # 基础能量（每个种子至少执行多少次变异）
    'max_energy': 300,                # 最大能量限制

    # --- 日志与监控 ---
    'verbose': True,                  # 是否输出详细调试日志
    'log_interval': 10,               # 状态/日志更新频率（秒）
}
