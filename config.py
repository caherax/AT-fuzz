"""
全局配置文件
"""

# ========== Fuzzer 核心配置 ==========
CONFIG = {
    # --- 执行控制 ---
    'timeout': 1.0,                  # 单次执行超时（秒）
    'mem_limit': 256,                # 内存限制（MB）

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
