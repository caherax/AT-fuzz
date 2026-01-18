"""
测试 SHM 功能（已合并到 test_utils.py）
保留此文件用于兼容性
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import AFLSHM


class TestSHMBasic(unittest.TestCase):
    """测试基本的 SHM 功能"""

    def test_shm_creation_and_cleanup(self):
        """测试 SHM 创建和清理"""
        shm = AFLSHM(bitmap_size=1024)

        # 验证创建
        shm_id = shm.get_shm_id()
        self.assertGreater(shm_id, 0)

        # 读取初始 bitmap（应该全是0）
        bitmap = shm.read_bitmap()
        self.assertEqual(len(bitmap), 1024)
        self.assertEqual(bitmap, b'\x00' * 1024)

        # 清理
        shm.cleanup()
        self.assertEqual(shm.shm_id, -1)

    def test_shm_env_passing(self):
        """测试通过环境变量传递 SHM ID"""
        shm = AFLSHM(bitmap_size=2048)
        shm_id = shm.get_shm_id()

        # 设置环境变量
        os.environ['__AFL_SHM_ID'] = str(shm_id)

        # 验证可以读取
        read_id = int(os.environ.get('__AFL_SHM_ID', '-1'))
        self.assertEqual(read_id, shm_id)

        shm.cleanup()
        del os.environ['__AFL_SHM_ID']

    def test_multiple_shm(self):
        """测试创建多个 SHM"""
        shm1 = AFLSHM(bitmap_size=512)
        shm2 = AFLSHM(bitmap_size=512)

        id1 = shm1.get_shm_id()
        id2 = shm2.get_shm_id()

        self.assertNotEqual(id1, id2)

        shm1.cleanup()
        shm2.cleanup()


if __name__ == '__main__':
    unittest.main(verbosity=2)

