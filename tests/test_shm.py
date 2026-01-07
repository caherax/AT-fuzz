"""
测试 SHM 功能
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import AFLSHM

def test_shm_basic():
    """测试基本的 SHM 创建和读写"""
    print("=== Test 1: Basic SHM Creation ===")
    
    shm = AFLSHM(bitmap_size=1024)
    print(f"✓ SHM created, ID: {shm.get_shm_id()}")
    
    # 读取初始 bitmap（应该全是0）
    bitmap = shm.read_bitmap()
    assert len(bitmap) == 1024, f"Expected 1024 bytes, got {len(bitmap)}"
    assert bitmap == b'\x00' * 1024, "Bitmap should be all zeros"
    print("✓ Bitmap initialized to zeros")
    
    # 清理
    shm.cleanup()
    print("✓ SHM cleaned up\n")


def test_shm_env_passing():
    """测试通过环境变量传递 SHM ID"""
    print("=== Test 2: Env Variable Passing ===")
    
    shm = AFLSHM(bitmap_size=2048)
    shm_id = shm.get_shm_id()
    
    # 设置环境变量
    os.environ['__AFL_SHM_ID'] = str(shm_id)
    print(f"✓ Set __AFL_SHM_ID={shm_id}")
    
    # 验证可以读取
    read_id = int(os.environ.get('__AFL_SHM_ID', '-1'))
    assert read_id == shm_id, f"ID mismatch: {read_id} != {shm_id}"
    print("✓ Environment variable passed correctly")
    
    shm.cleanup()
    print("✓ Cleaned up\n")


def test_multiple_shm():
    """测试创建多个 SHM"""
    print("=== Test 3: Multiple SHM Instances ===")
    
    shm1 = AFLSHM(bitmap_size=512)
    shm2 = AFLSHM(bitmap_size=512)
    
    id1 = shm1.get_shm_id()
    id2 = shm2.get_shm_id()
    
    assert id1 != id2, f"SHM IDs should be different: {id1} vs {id2}"
    print(f"✓ Created 2 SHMs with different IDs: {id1}, {id2}")
    
    shm1.cleanup()
    shm2.cleanup()
    print("✓ Both cleaned up\n")


if __name__ == '__main__':
    try:
        test_shm_basic()
        test_shm_env_passing()
        test_multiple_shm()
        
        print("=" * 50)
        print("✅ All SHM tests passed!")
        print("=" * 50)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
