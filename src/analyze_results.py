#!/usr/bin/env python3
"""
实验结果分析脚本
用于汇总多个测试结果，生成对比图表和统计报告

用法:
    python3 analyze_results.py [output_dir]
    
参数:
    output_dir: 测试结果输出目录，默认为 ./output
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')


def load_results(output_dir: Path) -> Dict:
    """
    加载所有测试目标的结果
    
    自动扫描 output_dir 下的所有子目录，读取 final_report.json
    """
    results = {}
    
    if not output_dir.exists():
        print(f"错误: 输出目录不存在: {output_dir}")
        return results
    
    for target_dir in output_dir.iterdir():
        if not target_dir.is_dir():
            continue
        
        # 读取 final_report.json
        report_file = target_dir / "final_report.json"
        if not report_file.exists():
            continue
        
        try:
            with open(report_file) as f:
                data = json.load(f)
                results[target_dir.name] = {
                    "name": target_dir.name,
                    "stats": data
                }
                print(f"  ✓ {target_dir.name}")
        except Exception as e:
            print(f"  ✗ {target_dir.name}: {e}")
    
    return results


def generate_summary_table(results: Dict, output_file: Path):
    """生成汇总表格（Markdown格式）"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# 实验结果汇总\n\n")
        
        f.write("## 结果统计\n\n")
        f.write("| Target | Executions | Crashes | Unique | Coverage | Exec/sec | Duration |\n")
        f.write("|--------|------------|---------|--------|----------|----------|----------|\n")
        
        for name in sorted(results.keys()):
            r = results[name]
            stats = r["stats"]
            
            total_execs = stats.get("total_executions", 0)
            total_crashes = stats.get("total_crashes", 0)
            # 兼容新旧字段名：优先使用 saved_crashes，回退到 unique_crashes
            saved_crashes = stats.get("saved_crashes", stats.get("unique_crashes", 0))
            coverage = stats.get("total_coverage_bits", 0)
            duration = stats.get("duration_seconds", 0)
            
            # 计算平均执行速度
            exec_rate = total_execs / duration if duration > 0 else 0
            duration_h = duration / 3600 if duration > 0 else 0
            
            f.write(f"| {name} | {total_execs:,} | {total_crashes:,} | "
                   f"{saved_crashes} | {coverage} | {exec_rate:.1f} | {duration_h:.1f}h |\n")
        
        f.write("\n## 指标说明\n\n")
        f.write("- **Executions**: 总执行次数\n")
        f.write("- **Crashes**: 总崩溃次数（包括重复）\n")
        f.write("- **Unique**: 唯一崩溃数（按 stderr 哈希去重）\n")
        f.write("- **Coverage**: 发现的代码边数量（bits）\n")
        f.write("- **Exec/sec**: 平均执行速度\n")
        f.write("- **Duration**: 实际测试时长\n")


def plot_coverage_comparison(results: Dict, output_file: Path):
    """绘制覆盖率对比图"""
    names = []
    coverages = []
    
    for name in sorted(results.keys()):
        r = results[name]
        names.append(name)
        coverages.append(r["stats"].get("total_coverage_bits", 0))
    
    plt.figure(figsize=(12, 6))
    plt.bar(names, coverages, color='steelblue')
    plt.xlabel('Target', fontsize=12)
    plt.ylabel('Coverage (bits)', fontsize=12)
    plt.title('Coverage Comparison Across Targets', fontsize=14)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"  ✓ {output_file.name}")


def plot_crash_comparison(results: Dict, output_file: Path):
    """绘制崩溃数对比图"""
    names = []
    saved_crashes = []
    total_crashes = []
    
    for name in sorted(results.keys()):
        r = results[name]
        names.append(name)
        # 兼容新旧字段名
        saved_crashes.append(r["stats"].get("saved_crashes", r["stats"].get("unique_crashes", 0)))
        total_crashes.append(r["stats"].get("total_crashes", 0))
    
    x = range(len(names))
    width = 0.35
    
    plt.figure(figsize=(12, 6))
    plt.bar([i - width/2 for i in x], total_crashes, width, 
            label='Total Crashes', color='orange', alpha=0.8)
    plt.bar([i + width/2 for i in x], saved_crashes, width, 
            label='Saved Crashes', color='red', alpha=0.8)
    
    plt.xlabel('Target', fontsize=12)
    plt.ylabel('Crash Count', fontsize=12)
    plt.title('Crash Discovery Comparison', fontsize=14)
    plt.xticks(x, names, rotation=45, ha='right')
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"  ✓ {output_file.name}")


def plot_execrate_comparison(results: Dict, output_file: Path):
    """绘制执行速度对比图"""
    names = []
    exec_rates = []
    
    for name in sorted(results.keys()):
        r = results[name]
        stats = r["stats"]
        total_execs = stats.get("total_executions", 0)
        duration = stats.get("duration_seconds", 1)
        exec_rate = total_execs / duration
        
        names.append(name)
        exec_rates.append(exec_rate)
    
    plt.figure(figsize=(12, 6))
    plt.bar(names, exec_rates, color='green', alpha=0.7)
    plt.xlabel('Target', fontsize=12)
    plt.ylabel('Executions per Second', fontsize=12)
    plt.title('Execution Speed Comparison', fontsize=14)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    print(f"  ✓ {output_file.name}")


def main():
    # 解析命令行参数
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = Path("output")
    
    if not output_dir.exists():
        print(f"错误: 输出目录不存在: {output_dir}")
        print(f"\n用法: {sys.argv[0]} [output_dir]")
        sys.exit(1)
    
    # 加载结果
    print("正在加载实验结果...")
    results = load_results(output_dir)
    
    if not results:
        print("错误: 没有找到任何测试结果")
        print(f"请确保 {output_dir} 目录下有包含 final_report.json 的子目录")
        sys.exit(1)
    
    print(f"\n已加载 {len(results)} 个测试目标的结果\n")
    
    # 创建分析输出目录
    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    
    # 生成汇总表格
    print("生成分析报告...")
    generate_summary_table(results, analysis_dir / "summary.md")
    print(f"  ✓ summary.md")
    
    # 生成对比图表
    print("\n生成对比图表...")
    plot_coverage_comparison(results, analysis_dir / "coverage_comparison.png")
    plot_crash_comparison(results, analysis_dir / "crash_comparison.png")
    plot_execrate_comparison(results, analysis_dir / "execrate_comparison.png")
    
    print(f"\n✅ 分析完成！结果保存在: {analysis_dir}")
    print(f"\n文件列表:")
    print(f"  - summary.md: 汇总表格")
    print(f"  - coverage_comparison.png: 覆盖率对比")
    print(f"  - crash_comparison.png: 崩溃数对比")
    print(f"  - execrate_comparison.png: 执行速度对比")


if __name__ == "__main__":
    main()
