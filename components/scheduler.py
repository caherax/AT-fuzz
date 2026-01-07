"""
种子调度器 - 能量调度版本
职责：选择高价值种子进行变异

已实现：基于能量的大根堆优先队列调度 (O(log n))
"""

import random
import heapq
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass(order=True)
class Seed:
    """种子数据结构"""
    # 为了实现大根堆，我们让 energy 参与比较，且反转逻辑（heapq 是小根堆）
    sort_index: float = field(init=False)

    data: bytes = field(compare=False)
    exec_count: int = field(default=0, compare=False)
    coverage_bits: int = field(default=0, compare=False)
    exec_time: float = field(default=0.0, compare=False)
    energy: float = field(default=1.0, compare=False)

    def __post_init__(self):
        self.sort_index = -self.energy

    def update_energy(self, new_energy: float):
        self.energy = new_energy
        self.sort_index = -new_energy


class SeedScheduler:
    """
    种子调度器 - 能量优先调度版本 (基于大根堆)

    工作流程：
    1. 维护一个种子优先队列（大根堆）
    2. 每次选择能量最高的种子 (O(log n))
    3. 执行后降低其能量（防止其他种子饥饿），重新入堆
    """

    def __init__(self):
        """初始化调度器"""
        self.seeds: List[Seed] = []  # Heap
        self.total_exec_time = 0.0
        self.total_coverage = 0

    def add_seed(self, seed_data: bytes, coverage_bits: int = 0, exec_time: float = 0.0):
        """
        添加种子到队列

        Args:
            seed_data: 种子数据
            coverage_bits: 覆盖率位数
            exec_time: 执行时间
        """
        seed = Seed(
            data=seed_data,
            coverage_bits=coverage_bits,
            exec_time=exec_time
        )

        # 更新全局统计
        self.total_exec_time += exec_time
        self.total_coverage += coverage_bits

        self._calculate_energy(seed)
        heapq.heappush(self.seeds, seed)
        # print(f"[Scheduler] Added seed, total: {len(self.seeds)}")

    def _calculate_energy(self, seed: Seed):
        """
        计算种子能量（参考 AFL++ 的 calculate_score 函数）
        
        算法原理：
        该函数实现了基于质量的种子优先级评分机制，核心思想是优先测试
        "性价比高"的种子（覆盖率高且执行快），同时防止某些种子被过度测试。
        
        评分策略分为三个维度：
        1. 执行速度因子：相对于平均执行时间，越快的种子获得越高的分数
           - 原理：快速执行的种子可以在相同时间内产生更多变异，提高吞吐量
           - 分档：10倍慢->10分, 2倍慢->50分, 2倍快->150分, 4倍快->300分
           
        2. 覆盖率因子：相对于平均覆盖率，覆盖更广的种子获得更高权重
           - 原理：高覆盖率的种子更有可能通过变异发现新路径
           - 分档：30%平均->3倍, 50%平均->2倍, 低于平均->0.25-0.75倍
           
        3. 衰减机制：执行次数越多，能量越低（模拟 AFL++ 的 FAST 调度）
           - 原理：防止"饥饿"，确保所有种子都有机会被测试
           - 公式：score = score / (1 + 0.2 * exec_count)
        
        返回值：
            能量分数（1-10000），直接影响该种子在堆中的优先级
        """
        # 计算平均值
        num_seeds = len(self.seeds)
        if num_seeds == 0:
            # 队列为空（正在添加第一个种子），使用自身作为平均值
            avg_exec_us = seed.exec_time
            avg_bitmap_size = seed.coverage_bits
        else:
            # 注意：如果是 select_next 调用，seed 已经被 pop 出去了，所以 num_seeds 是剩余数量
            # 但 total_exec_time 包含所有。为了简单起见，我们使用当前的全局统计
            avg_exec_us = self.total_exec_time / (num_seeds + 1) # +1 近似包含当前种子
            avg_bitmap_size = self.total_coverage / (num_seeds + 1)

        perf_score = 100.0

        # 1. Adjust score based on execution speed
        # Fast inputs are less expensive to fuzz, so we're giving them more air time.
        if avg_exec_us > 0:
            if seed.exec_time * 0.1 > avg_exec_us:
                perf_score = 10
            elif seed.exec_time * 0.25 > avg_exec_us:
                perf_score = 25
            elif seed.exec_time * 0.5 > avg_exec_us:
                perf_score = 50
            elif seed.exec_time * 0.75 > avg_exec_us:
                perf_score = 75
            elif seed.exec_time * 4 < avg_exec_us:
                perf_score = 300
            elif seed.exec_time * 3 < avg_exec_us:
                perf_score = 200
            elif seed.exec_time * 2 < avg_exec_us:
                perf_score = 150

        # 2. Adjust score based on bitmap size (coverage)
        # The working theory is that better coverage translates to better targets.
        if avg_bitmap_size > 0:
            if seed.coverage_bits * 0.3 > avg_bitmap_size:
                perf_score *= 3
            elif seed.coverage_bits * 0.5 > avg_bitmap_size:
                perf_score *= 2
            elif seed.coverage_bits * 0.75 > avg_bitmap_size:
                perf_score *= 1.5
            elif seed.coverage_bits * 3 < avg_bitmap_size:
                perf_score *= 0.25
            elif seed.coverage_bits * 2 < avg_bitmap_size:
                perf_score *= 0.5
            elif seed.coverage_bits * 1.5 < avg_bitmap_size:
                perf_score *= 0.75

        # 3. Adjust score based on handicap / fuzz count (Simulating FAST schedule)
        # AFL++ uses complex schedule logic. Here we use a simplified decay.
        # The more often it has been fuzzed, the lower the score.
        if seed.exec_count > 0:
            # 使用非线性衰减，避免分数过快降为0
            # 类似于 AFL++ FAST schedule 的 log2 因子
            perf_score /= 1.0 + 0.2 * seed.exec_count

        # 限制上限，防止溢出或过度倾斜
        perf_score = min(perf_score, 10000.0)

        seed.update_energy(perf_score)

    def select_next(self) -> Optional[Seed]:
        """
        选择下一个种子（取堆顶，即能量最高）

        Returns:
            选中的种子，如果队列为空返回 None
        """
        if not self.seeds:
            return None

        # 取出能量最高的种子 (O(log n))
        seed = heapq.heappop(self.seeds)

        seed.exec_count += 1

        # 重新计算能量（会因为 exec_count 增加而降低）
        self._calculate_energy(seed)

        # 放回堆中
        heapq.heappush(self.seeds, seed)

        return seed

    def get_stats(self):
        """获取统计信息"""
        return {
            'total_seeds': len(self.seeds),
            'avg_energy': sum(s.energy for s in self.seeds) / len(self.seeds) if self.seeds else 0
        }


# 测试代码
if __name__ == '__main__':
    scheduler = SeedScheduler()

    # 添加种子
    scheduler.add_seed(b'seed1')
    scheduler.add_seed(b'seed2')
    scheduler.add_seed(b'seed3')

    # 选择种子
    for i in range(10):
        seed = scheduler.select_next()
        if seed:
            print(f"Round {i}: Selected seed with {len(seed.data)} bytes, "
                  f"executed {seed.exec_count} times")

    # 统计信息
    print(f"\nStats: {scheduler.get_stats()}")
