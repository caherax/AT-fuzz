"""
evaluator.py 的单元测试
测试评估器功能（CSV 记录、报告生成等）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
import tempfile
import csv
import json
from pathlib import Path
from src.components.evaluator import Evaluator, CSV_COLUMNS


class TestEvaluatorInit(unittest.TestCase):
    """测试评估器初始化"""

    def test_create_output_dir(self):
        """测试自动创建输出目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'new_subdir', 'output')
            evaluator = Evaluator(output_path)

            self.assertTrue(os.path.exists(output_path))
            self.assertTrue(os.path.exists(evaluator.csv_file))

    def test_csv_header_created(self):
        """测试 CSV 文件头正确创建"""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = Evaluator(tmpdir)

            with open(evaluator.csv_file, 'r') as f:
                reader = csv.reader(f)
                header = next(reader)

            self.assertEqual(tuple(header), CSV_COLUMNS)

    def test_csv_columns_consistency(self):
        """测试 CSV_COLUMNS 定义正确"""
        expected_columns = (
            'timestamp',
            'elapsed_sec',
            'total_execs',
            'exec_rate',
            'total_crashes',
            'saved_crashes',
            'total_hangs',
            'saved_hangs',
            'coverage',
        )
        self.assertEqual(CSV_COLUMNS, expected_columns)


class TestEvaluatorRecord(unittest.TestCase):
    """测试记录功能"""

    def setUp(self):
        """设置测试环境"""
        self.tmpdir = tempfile.mkdtemp()
        self.evaluator = Evaluator(self.tmpdir)

    def tearDown(self):
        """清理"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_record_single_entry(self):
        """测试记录单条数据"""
        self.evaluator.record(
            total_execs=100,
            exec_rate=50.0,
            total_crashes=2,
            saved_crashes=1,
            total_hangs=0,
            saved_hangs=0,
            coverage=150
        )

        with open(self.evaluator.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]['total_execs']), 100)
        self.assertEqual(float(rows[0]['exec_rate']), 50.0)
        self.assertEqual(int(rows[0]['total_crashes']), 2)
        self.assertEqual(int(rows[0]['coverage']), 150)

    def test_record_multiple_entries(self):
        """测试记录多条数据"""
        for i in range(5):
            self.evaluator.record(
                total_execs=i * 100,
                exec_rate=100.0,
                total_crashes=i,
                saved_crashes=i,
                total_hangs=0,
                saved_hangs=0,
                coverage=i * 10
            )

        with open(self.evaluator.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 5)
        # 验证数据递增
        for i, row in enumerate(rows):
            self.assertEqual(int(row['total_execs']), i * 100)

    def test_elapsed_time_tracking(self):
        """测试经过时间追踪"""
        import time

        self.evaluator.record(
            total_execs=0, exec_rate=0,
            total_crashes=0, saved_crashes=0,
            total_hangs=0, saved_hangs=0
        )

        time.sleep(0.1)  # 等待 100ms

        self.evaluator.record(
            total_execs=10, exec_rate=100,
            total_crashes=0, saved_crashes=0,
            total_hangs=0, saved_hangs=0
        )

        with open(self.evaluator.csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # 第一条记录的 elapsed 应该接近 0
        self.assertAlmostEqual(float(rows[0]['elapsed_sec']), 0, delta=0.01)
        # 第二条记录的 elapsed 应该 >= 0.1
        self.assertGreaterEqual(float(rows[1]['elapsed_sec']), 0.09)


class TestEvaluatorReport(unittest.TestCase):
    """测试报告生成"""

    def setUp(self):
        """设置测试环境"""
        self.tmpdir = tempfile.mkdtemp()
        self.evaluator = Evaluator(self.tmpdir)

    def tearDown(self):
        """清理"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_final_report(self):
        """测试保存最终报告"""
        stats = {
            'total_execs': 10000,
            'total_crashes': 5,
            'unique_crashes': 3,
            'duration_seconds': 3600,
            'coverage_edges': 1500
        }

        self.evaluator.save_final_report(stats)

        report_file = Path(self.tmpdir) / 'final_report.json'
        self.assertTrue(report_file.exists())

        with open(report_file, 'r') as f:
            loaded_stats = json.load(f)

        self.assertEqual(loaded_stats['total_execs'], 10000)
        self.assertEqual(loaded_stats['total_crashes'], 5)
        self.assertEqual(loaded_stats['coverage_edges'], 1500)

    def test_report_json_format(self):
        """测试报告 JSON 格式正确"""
        stats = {'key': 'value', 'number': 42}
        self.evaluator.save_final_report(stats)

        report_file = Path(self.tmpdir) / 'final_report.json'
        content = report_file.read_text()

        # 应该是格式化的 JSON（有缩进）
        self.assertIn('\n', content)
        self.assertIn('  ', content)


class TestEvaluatorPlots(unittest.TestCase):
    """测试图表生成"""

    def setUp(self):
        """设置测试环境"""
        self.tmpdir = tempfile.mkdtemp()
        self.evaluator = Evaluator(self.tmpdir)

    def tearDown(self):
        """清理"""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_generate_plots_with_data(self):
        """测试有数据时生成图表"""
        # 记录一些数据
        for i in range(10):
            self.evaluator.record(
                total_execs=i * 100,
                exec_rate=100.0 + i,
                total_crashes=i,
                saved_crashes=i,
                total_hangs=0,
                saved_hangs=0,
                coverage=i * 50
            )

        # 生成图表
        self.evaluator.generate_plots()

        # 检查是否生成了图表文件（如果 matplotlib 可用）
        try:
            import matplotlib
            plot_files = [
                'plot_executions.png',
                'plot_exec_rate.png',
                'plot_crashes.png',
                'plot_coverage.png'
            ]
            for plot_file in plot_files:
                plot_path = Path(self.tmpdir) / plot_file
                self.assertTrue(plot_path.exists(), f"Missing plot: {plot_file}")
        except ImportError:
            # matplotlib 不可用，跳过图表检查
            pass

    def test_generate_plots_empty_data(self):
        """测试空数据时生成图表不会崩溃"""
        # 不记录任何数据，直接尝试生成图表
        # 应该优雅地处理，不抛出异常
        try:
            self.evaluator.generate_plots()
        except Exception as e:
            self.fail(f"generate_plots() raised exception with empty data: {e}")


class TestEvaluatorEdgeCases(unittest.TestCase):
    """测试边界情况"""

    def test_zero_values(self):
        """测试零值"""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = Evaluator(tmpdir)

            evaluator.record(
                total_execs=0,
                exec_rate=0.0,
                total_crashes=0,
                saved_crashes=0,
                total_hangs=0,
                saved_hangs=0,
                coverage=0
            )

            with open(evaluator.csv_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(len(rows), 1)
            self.assertEqual(int(rows[0]['total_execs']), 0)

    def test_large_values(self):
        """测试大数值"""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = Evaluator(tmpdir)

            large_value = 10**9
            evaluator.record(
                total_execs=large_value,
                exec_rate=float(large_value),
                total_crashes=large_value,
                saved_crashes=large_value,
                total_hangs=large_value,
                saved_hangs=large_value,
                coverage=large_value
            )

            with open(evaluator.csv_file, 'r') as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            self.assertEqual(int(rows[0]['total_execs']), large_value)


if __name__ == '__main__':
    unittest.main()
