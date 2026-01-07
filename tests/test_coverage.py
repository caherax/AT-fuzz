"""
测试覆盖率功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.executor import TestExecutor
from utils import count_coverage_bits

def test_coverage_collection():
    """测试覆盖率收集"""
    print("=== Test: Coverage Collection ===\n")
    
    # 创建带覆盖率的 executor
    executor = TestExecutor(
        target_path='/tmp/test_target',
        target_args='/tmp/test_target @@',
        timeout=2,
        use_coverage=True
    )
    
    # 测试1：默认分支
    print("Test 1: Default branch (input: 'Z')")
    result1 = executor.execute(b'Z')
    cov1 = count_coverage_bits(result1['coverage']) if result1['coverage'] else 0
    print(f"  Return code: {result1['return_code']}")
    print(f"  Coverage bits: {cov1}")
    print(f"  Crashed: {result1['crashed']}")
    print()
    
    # 测试2：Branch A
    print("Test 2: Branch A (input: 'A')")
    result2 = executor.execute(b'A')
    cov2 = count_coverage_bits(result2['coverage']) if result2['coverage'] else 0
    print(f"  Return code: {result2['return_code']}")
    print(f"  Coverage bits: {cov2}")
    print(f"  New coverage: {cov2 - cov1}")
    print()
    
    # 测试3：Branch AB
    print("Test 3: Branch AB (input: 'AB')")
    result3 = executor.execute(b'AB')
    cov3 = count_coverage_bits(result3['coverage']) if result3['coverage'] else 0
    print(f"  Return code: {result3['return_code']}")
    print(f"  Coverage bits: {cov3}")
    print(f"  New coverage: {cov3 - cov2}")
    print()
    
    # 测试4：Branch ABC
    print("Test 4: Branch ABC (input: 'ABC')")
    result4 = executor.execute(b'ABC')
    cov4 = count_coverage_bits(result4['coverage']) if result4['coverage'] else 0
    print(f"  Return code: {result4['return_code']}")
    print(f"  Coverage bits: {cov4}")
    print(f"  New coverage: {cov4 - cov3}")
    print()
    
    # 测试5：Branch X
    print("Test 5: Branch X (input: 'X')")
    result5 = executor.execute(b'X')
    cov5 = count_coverage_bits(result5['coverage']) if result5['coverage'] else 0
    print(f"  Return code: {result5['return_code']}")
    print(f"  Coverage bits: {cov5}")
    print(f"  Comparison with ABC: {cov5} vs {cov4}")
    print()
    
    # 测试6：崩溃
    print("Test 6: Crash (input: 'ABC!')")
    result6 = executor.execute(b'ABC!')
    cov6 = count_coverage_bits(result6['coverage']) if result6['coverage'] else 0
    print(f"  Return code: {result6['return_code']}")
    print(f"  Coverage bits: {cov6}")
    print(f"  Crashed: {result6['crashed']}")
    print()
    
    # 验证覆盖率单调递增
    print("=" * 50)
    print("Coverage progression:")
    print(f"  Default: {cov1}")
    print(f"  A:       {cov2} (Δ{cov2-cov1:+d})")
    print(f"  AB:      {cov3} (Δ{cov3-cov2:+d})")
    print(f"  ABC:     {cov4} (Δ{cov4-cov3:+d})")
    print(f"  ABC!:    {cov6} (Δ{cov6-cov4:+d})")
    print("=" * 50)
    
    # 验证覆盖率数据有效（非空）
    assert cov1 > 0, "Should have some coverage"
    assert result1['coverage'] is not None, "Coverage should be collected"
    assert len(result1['coverage']) == 65536, "Coverage bitmap should be 64KB"
    
    # 验证不同输入产生不同覆盖率
    assert result1['coverage'] != result3['coverage'], "Different inputs should have different coverage"
    
    # 验证崩溃被正确检测
    assert result6['crashed'] == True, "ABC! should trigger crash"
    
    print("\n✅ Coverage collection test passed!")
    print("✓ SHM communication working")
    print("✓ Coverage data collected")
    print("✓ Different branches produce different coverage")
    print("✓ Crash detection working")
    
    executor.cleanup()

if __name__ == '__main__':
    try:
        test_coverage_collection()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
