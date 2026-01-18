"""
评估器组件 (Component 6/6)
职责：收集运行时数据并生成可视化报告

功能：
- CSV 时间序列数据记录
- 生成执行数、速度、崩溃、覆盖率等统计图表
- 输出最终 JSON 报告

类型安全设计：
- 使用 TimelineRecord (NamedTuple) 定义记录结构
- CSV_COLUMNS 自动从 NamedTuple._fields 提取
- 构造时自动验证参数数量和顺序

详见：docs/DESIGN.md（“字段一致性与类型安全”）
"""

import csv
import json
from pathlib import Path
from datetime import datetime
from typing import NamedTuple

try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[Warning] matplotlib not available, visualization disabled")


# ========== CSV 数据结构定义 ==========
# 使用 NamedTuple 确保字段一致性，自动验证参数
class TimelineRecord(NamedTuple):
    """时间序列记录数据结构"""
    timestamp: str
    elapsed_sec: float
    total_execs: int
    exec_rate: float
    total_crashes: int
    saved_crashes: int
    total_hangs: int
    saved_hangs: int
    coverage: int

# 从 NamedTuple 自动提取列名（兼容旧代码）
CSV_COLUMNS = TimelineRecord._fields


class Evaluator:
    """
    评估器

    工作流程：
    1. 定期记录运行时状态快照
    2. 输出为 CSV 文件供后续分析
    """

    def __init__(self, output_dir: str):
        """
        初始化评估器

        Args:
            output_dir: 输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.csv_file = self.output_dir / 'timeline.csv'
        self.start_time = None

        # 初始化 CSV
        self._init_csv()

    def _init_csv(self):
        """初始化 CSV 文件头

        尝试删除旧的 timeline.csv 文件，如果失败则使用备份文件
        确保每次运行都有干净的 CSV 文件头
        """
        try:
            # 尝试删除旧文件（如果存在且有权限问题）
            if self.csv_file.exists():
                self.csv_file.unlink()
        except PermissionError:
            # 权限不足，尝试备份并创建新文件
            backup_file = self.csv_file.with_suffix('.csv.bak')
            print(f"[!] Cannot overwrite {self.csv_file}, using backup: {backup_file}")
            self.csv_file = backup_file

        # 写入 CSV 文件头（列名）
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)

    def record(self, total_execs: int, exec_rate: float, total_crashes: int,
               saved_crashes: int, total_hangs: int, saved_hangs: int, coverage: int = 0):
        """
        记录一个时间快照

        Args:
            total_execs: 总执行数
            exec_rate: 每秒执行数
            total_crashes: 总崩溃数（可能包含重复）
            saved_crashes: 保存的唯一崩溃数（去重后）
            total_hangs: 总超时数（可能包含重复）
            saved_hangs: 保存的唯一超时数（去重后）
            coverage: 当前覆盖率（边数）
        """
        now = datetime.now()

        # 计算从开始到现在的经过时间
        if self.start_time is None:
            self.start_time = now
            elapsed = 0.0
        else:
            elapsed = (now - self.start_time).total_seconds()

        # 使用 NamedTuple 构造记录（自动验证字段数量和类型）
        # TimelineRecord 会自动验证参数数量和顺序，确保数据一致性
        record = TimelineRecord(
            timestamp=now.isoformat(),
            elapsed_sec=elapsed,
            total_execs=total_execs,
            exec_rate=exec_rate,
            total_crashes=total_crashes,
            saved_crashes=saved_crashes,
            total_hangs=total_hangs,
            saved_hangs=saved_hangs,
            coverage=coverage
        )

        # 写入 CSV（NamedTuple 可直接迭代，自动转换为元组）
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(record)

    def save_final_report(self, stats: dict):
        """
        保存最终报告

        Args:
            stats: 统计数据字典，包含最终的统计信息
        """
        report_file = self.output_dir / 'final_report.json'

        # 使用 JSON 格式保存，便于后续分析和可视化
        with open(report_file, 'w') as f:
            json.dump(stats, f, indent=2)

        print(f"[Evaluator] Final report saved to {report_file}")

    def generate_plots(self):
        """
        生成所有统计图表

        从 CSV 文件读取时间序列数据，并生成以下图表：
        1. 执行数增长曲线
        2. 执行速度曲线
        3. 崩溃发现曲线（包含总崩溃数和保存的唯一崩溃数）
        4. 挂起发现曲线（包含总挂起数和保存的唯一挂起数）
        5. 覆盖率增长曲线
        """
        if not MATPLOTLIB_AVAILABLE:
            print("[Evaluator] Skipping plots - matplotlib not available")
            return

        # 读取时间序列数据
        if not self.csv_file.exists():
            print("[Evaluator] No timeline data to plot")
            return

        # 初始化数据字典，用于存储从 CSV 读取的数据
        data = {'timestamps': [], 'elapsed': [], 'execs': [], 'rate': [], 'coverage': [],
                'total_crashes': [], 'saved_crashes': [], 'total_hangs': [], 'saved_hangs': []}

        # 从 CSV 文件读取数据并转换为适当的类型
        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data['timestamps'].append(row['timestamp'])
                data['elapsed'].append(float(row['elapsed_sec']))
                data['execs'].append(int(row['total_execs']))
                data['rate'].append(float(row['exec_rate']))
                data['total_crashes'].append(int(row['total_crashes']))
                data['saved_crashes'].append(int(row['saved_crashes']))
                data['total_hangs'].append(int(row['total_hangs']))
                data['saved_hangs'].append(int(row['saved_hangs']))
                data['coverage'].append(int(row.get('coverage', 0)))

        # 检查是否有数据点可供绘图
        if len(data['elapsed']) == 0:
            print("[Evaluator] No data points to plot")
            return

        # 生成所有图表
        self._plot_execution_growth(data)
        self._plot_exec_rate(data)
        self._plot_crashes(data)
        self._plot_hangs(data)
        self._plot_coverage(data)

        print(f"[Evaluator] Plots saved to {self.output_dir}")

    def _plot_execution_growth(self, data: dict[str, list]):
        """绘制执行数增长曲线

        显示总执行数随时间的变化趋势
        蓝色实线表示执行数的增长情况
        """
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['execs'], 'b-', linewidth=2)
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Total Executions', fontsize=12)
        plt.title('Execution Growth Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_executions.png', dpi=150)
        plt.close()

    def _plot_exec_rate(self, data: dict[str, list]):
        """绘制执行速度曲线

        显示每秒执行数随时间的变化趋势
        绿色实线表示执行速度的变化情况
        """
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['rate'], 'g-', linewidth=2)
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Execution Rate (exec/s)', fontsize=12)
        plt.title('Execution Rate Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_exec_rate.png', dpi=150)
        plt.close()

    def _plot_crashes(self, data: dict[str, list]):
        """绘制崩溃发现曲线

        显示总崩溃数和保存的唯一崩溃数随时间的变化趋势
        - 虚线表示总崩溃数（可能包含重复）
        - 实线表示保存的唯一崩溃数（去重后）
        """
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['total_crashes'], 'b--', label='Total crashes')
        plt.plot(data['elapsed'], data['saved_crashes'], 'r-', linewidth=2, marker='o', label='Saved crashes')
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Crashes', fontsize=12)
        plt.title('Crash Discovery Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend()  # 显示图例
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_crashes.png', dpi=150)
        plt.close()

    def _plot_hangs(self, data: dict[str, list]):
        """绘制挂起发现曲线

        显示总挂起数和保存的唯一挂起数随时间的变化趋势
        - 虚线表示总挂起数（可能包含重复）
        - 实线表示保存的唯一挂起数（去重后）
        """
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['total_hangs'], 'b--', label='Total hangs')
        plt.plot(data['elapsed'], data['saved_hangs'], 'r-', linewidth=2, marker='o', label='Saved hangs')
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Hangs', fontsize=12)
        plt.title('Hang Discovery Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend()  # 显示图例
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_hangs.png', dpi=150)
        plt.close()

    def _plot_coverage(self, data: dict[str, list]):
        """绘制覆盖率增长曲线

        显示代码覆盖率（边数）随时间的变化趋势
        紫色实线表示覆盖率的增长情况
        """
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['coverage'], 'm-', linewidth=2)
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Coverage (edges)', fontsize=12)
        plt.title('Coverage Growth Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_coverage.png', dpi=150)
        plt.close()


# 测试代码
if __name__ == '__main__':
    import time
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        evaluator = Evaluator(tmpdir)

        # 模拟记录
        for i in range(5):
            evaluator.record(
                total_execs=i * 100,
                exec_rate=100.0,
                total_crashes=i,
                saved_crashes=i,
                total_hangs=0,
                saved_hangs=0
            )
            time.sleep(0.5)

        # 保存最终报告
        evaluator.save_final_report({
            'total_execs': 400,
            'total_crashes': 4,
            'duration': 2.0
        })

        # 显示 CSV 内容
        csv_path = Path(tmpdir) / 'timeline.csv'
        print(f"\n=== CSV Content ===")
        print(csv_path.read_text())

        print(f"\n=== Final Report ===")
        report_path = Path(tmpdir) / 'final_report.json'
        print(report_path.read_text())
