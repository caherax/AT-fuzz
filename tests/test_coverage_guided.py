"""
测试覆盖率引导模糊测试流程
"""

import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.executor import TestExecutor
from components.monitor import ExecutionMonitor
from components.mutator import Mutator


def test_coverage_guided_fuzzing():
    """测试覆盖率引导的模糊测试流程"""
    print("=== Test: Coverage-Guided Fuzzing ===\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建带覆盖率的组件
        executor = TestExecutor(
            target_path='/tmp/test_target',
            target_args='/tmp/test_target @@',
            timeout=2,
            use_coverage=True
        )
        
        monitor = ExecutionMonitor(tmpdir, use_coverage=True)
        
        # 初始种子
        seeds = [b'Z']
        
        print("Starting fuzzing loop...\n")
        
        for i in range(20):
            # 选择种子
            seed = seeds[i % len(seeds)]
            
            # 变异
            mutated = Mutator.mutate(seed, strategy='havoc')
            
            # 执行
            result = executor.execute(mutated)
            
            # 监控
            is_interesting = monitor.process_execution(mutated, result)
            
            # 如果发现有趣的输入，添加到种子库
            if is_interesting and len(seeds) < 10:
                seeds.append(mutated)
                print(f"  Iteration {i}: Found interesting input! "
                      f"(seeds: {len(seeds)}, coverage: {monitor.stats['total_coverage_bits']})")
        
        # 最终统计
        print("\n" + "=" * 50)
        print("Final Statistics:")
        print(f"  Total executions:  {monitor.stats['total_execs']}")
        print(f"  Interesting inputs: {monitor.stats['interesting_inputs']}")
        print(f"  Total crashes:     {monitor.stats['total_crashes']}")
        print(f"  Total seeds:       {len(seeds)}")
        print(f"  Coverage bits:     {monitor.stats['total_coverage_bits']}")
        print("=" * 50)
        
        # 验证
        assert monitor.stats['total_execs'] == 20, "Should execute 20 times"
        assert monitor.stats['total_coverage_bits'] > 0, "Should have some coverage"
        assert len(seeds) > 1, "Should find some interesting inputs"
        
        print("\n✅ Coverage-guided fuzzing test passed!")
        print("✓ Coverage feedback working")
        print("✓ Interesting inputs discovered")
        print("✓ Seed queue growing")
        
        executor.cleanup()


if __name__ == '__main__':
    try:
        test_coverage_guided_fuzzing()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
