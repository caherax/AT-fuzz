"""
评估器组件 (Component 6/6)
职责：收集运行时数据并生成可视化报告

功能：
- CSV 时间序列数据记录
- 生成执行数、速度、崩溃、覆盖率等统计图表
- 输出最终 JSON 报告
"""

import csv
import json
from pathlib import Path
from datetime import datetime

try:
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[Warning] matplotlib not available, visualization disabled")


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
        """初始化 CSV 文件头"""
        try:
            # 尝试删除旧文件（如果存在且有权限问题）
            if self.csv_file.exists():
                self.csv_file.unlink()
        except PermissionError:
            # 权限不足，尝试备份并创建新文件
            backup_file = self.csv_file.with_suffix('.csv.bak')
            print(f"[!] Cannot overwrite {self.csv_file}, using backup: {backup_file}")
            self.csv_file = backup_file

        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'elapsed_sec', 'total_execs',
                           'exec_rate', 'total_crashes', 'saved_crashes', 
                           'total_hangs', 'saved_hangs', 'coverage'])

    def record(self, total_execs: int, exec_rate: float, total_crashes: int, 
               saved_crashes: int, total_hangs: int, saved_hangs: int, coverage: int = 0):
        """
        记录一个时间快照

        Args:
            total_execs: 总执行数
            exec_rate: 每秒执行数
            total_crashes: 总崩溃数
            saved_crashes: 保存的唯一崩溃数
            total_hangs: 总超时数
            saved_hangs: 保存的唯一超时数
            coverage: 当前覆盖率（边数）
        """
        now = datetime.now()

        if self.start_time is None:
            self.start_time = now
            elapsed = 0
        else:
            elapsed = (now - self.start_time).total_seconds()

        # 写入 CSV
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                now.isoformat(),
                f'{elapsed:.1f}',
                total_execs,
                f'{exec_rate:.1f}',
                total_crashes,
                saved_crashes,
                total_hangs,
                saved_hangs,
                coverage
            ])

    def save_final_report(self, stats: dict):
        """
        保存最终报告

        Args:
            stats: 统计数据字典
        """
        report_file = self.output_dir / 'final_report.json'

        with open(report_file, 'w') as f:
            json.dump(stats, f, indent=2)

        print(f"[Evaluator] Final report saved to {report_file}")

    def generate_plots(self):
        """
        生成所有统计图表
        """
        if not MATPLOTLIB_AVAILABLE:
            print("[Evaluator] Skipping plots - matplotlib not available")
            return

        # 读取时间序列数据
        if not self.csv_file.exists():
            print("[Evaluator] No timeline data to plot")
            return

        data = {'timestamps': [], 'elapsed': [], 'execs': [], 'rate': [], 'crashes': [], 'coverage': []}

        with open(self.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data['timestamps'].append(row['timestamp'])
                data['elapsed'].append(float(row['elapsed_sec']))
                data['execs'].append(int(row['total_execs']))
                data['rate'].append(float(row['exec_rate']))
                data['crashes'].append(int(row['total_crashes']))
                data['coverage'].append(int(row.get('coverage', 0)))

        if len(data['elapsed']) == 0:
            print("[Evaluator] No data points to plot")
            return

        # 生成图表
        self._plot_execution_growth(data)
        self._plot_exec_rate(data)
        self._plot_crashes(data)
        self._plot_coverage(data)

        print(f"[Evaluator] Plots saved to {self.output_dir}")

    def _plot_execution_growth(self, data: dict[str, list]):
        """绘制执行数增长曲线"""
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
        """绘制执行速度曲线"""
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
        """绘制崩溃发现曲线"""
        plt.figure(figsize=(10, 6))
        plt.plot(data['elapsed'], data['crashes'], 'r-', linewidth=2, marker='o')
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel('Total Crashes Found', fontsize=12)
        plt.title('Crash Discovery Over Time', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(self.output_dir / 'plot_crashes.png', dpi=150)
        plt.close()

    def _plot_coverage(self, data: dict[str, list]):
        """绘制覆盖率增长曲线"""
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
