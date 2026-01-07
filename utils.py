"""
工具函数模块
包含覆盖率计算、SHM 通信、文件操作等辅助函数
"""

import os
import ctypes
from pathlib import Path
from typing import Tuple, Optional
from datetime import datetime


# ============== System V Shared Memory 支持 ==============

# 加载 C 标准库
try:
    libc = ctypes.CDLL("libc.so.6")
except OSError:
    # macOS 等其他系统
    libc = ctypes.CDLL(ctypes.util.find_library("c"))

# 定义常量（来自 sys/ipc.h 和 sys/shm.h）
IPC_PRIVATE = 0
IPC_CREAT = 0o1000
IPC_EXCL = 0o2000
IPC_RMID = 0

# 定义 C 函数签名
libc.shmget.argtypes = [ctypes.c_int, ctypes.c_size_t, ctypes.c_int]
libc.shmget.restype = ctypes.c_int

libc.shmat.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
libc.shmat.restype = ctypes.c_void_p

libc.shmdt.argtypes = [ctypes.c_void_p]
libc.shmdt.restype = ctypes.c_int

libc.shmctl.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
libc.shmctl.restype = ctypes.c_int


class AFLSHM:
    """
    AFL++ 共享内存包装类
    
    用于与 AFL++ 插装的程序通信，读取覆盖率 bitmap
    
    工作流程：
    1. 创建共享内存：shmget(IPC_PRIVATE, size, IPC_CREAT)
    2. 映射到进程地址空间：shmat(shm_id, NULL, 0)
    3. 将 SHM ID 通过环境变量传递给子进程：__AFL_SHM_ID
    4. 子进程（插装程序）写入覆盖率数据
    5. 父进程读取 bitmap
    6. 清理：shmdt() + shmctl(IPC_RMID)
    """
    
    def __init__(self, bitmap_size: int = 65536):
        """
        初始化 SHM
        
        Args:
            bitmap_size: bitmap 大小（默认 64KB）
        """
        self.bitmap_size = bitmap_size
        self.shm_id = -1
        self.shm_addr = None
        
        # 创建共享内存
        self.shm_id = libc.shmget(IPC_PRIVATE, bitmap_size, IPC_CREAT | 0o600)
        if self.shm_id < 0:
            raise OSError(f"Failed to create SHM: {ctypes.get_errno()}")
        
        # 映射到当前进程
        self.shm_addr = libc.shmat(self.shm_id, None, 0)
        if self.shm_addr == -1:
            raise OSError(f"Failed to attach SHM: {ctypes.get_errno()}")
        
        # 清零 bitmap
        self.clear()
        
        print(f"[SHM] Created SHM ID: {self.shm_id}, size: {bitmap_size}")
    
    def get_shm_id(self) -> int:
        """获取 SHM ID（用于传递给子进程）"""
        return self.shm_id
    
    def clear(self):
        """清空 bitmap"""
        if self.shm_addr:
            ctypes.memset(self.shm_addr, 0, self.bitmap_size)
    
    def read_bitmap(self) -> bytes:
        """
        读取 bitmap 数据
        
        Returns:
            bitmap 字节数组
        """
        if not self.shm_addr:
            return b'\x00' * self.bitmap_size
        
        # 从共享内存读取数据
        return ctypes.string_at(self.shm_addr, self.bitmap_size)
    
    def cleanup(self):
        """清理 SHM 资源"""
        if self.shm_addr:
            libc.shmdt(self.shm_addr)
            self.shm_addr = None
        
        if self.shm_id >= 0:
            libc.shmctl(self.shm_id, IPC_RMID, None)
            print(f"[SHM] Cleaned up SHM ID: {self.shm_id}")
            self.shm_id = -1
    
    def __del__(self):
        """析构函数，确保资源释放"""
        self.cleanup()


# ============== 覆盖率计算函数 ==============


def count_coverage_bits(bitmap: bytes) -> int:
    """
    计算 bitmap 中设置的位数（边覆盖数）
    
    Args:
        bitmap: 覆盖率位图
    
    Returns:
        设置位的总数
    """
    if not bitmap:
        return 0
    return sum(bin(b).count('1') for b in bitmap)


def get_coverage_delta(new_bitmap: bytes, old_bitmap: bytes) -> int:
    """
    计算两个 bitmap 之间的新覆盖
    
    Args:
        new_bitmap: 新的覆盖率位图
        old_bitmap: 旧的覆盖率位图
    
    Returns:
        新增覆盖的位数
    """
    if len(new_bitmap) != len(old_bitmap):
        return 0
    
    delta = bytes(a & ~b for a, b in zip(new_bitmap, old_bitmap))
    return count_coverage_bits(delta)


def has_new_coverage(new_bitmap: bytes, old_bitmap: bytes) -> bool:
    """检测是否有新覆盖"""
    return get_coverage_delta(new_bitmap, old_bitmap) > 0


def format_time(seconds: float) -> str:
    """格式化时间显示"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def format_size(bytes_size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f}{unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f}TB"


def get_current_timestamp() -> str:
    """获取当前时间戳（ISO格式）"""
    return datetime.now().isoformat()


class CoverageTracker:
    """
    覆盖率追踪器
    维护全局覆盖率 bitmap，检测新覆盖
    """
    
    def __init__(self, bitmap_size: int = 65536):
        """
        初始化追踪器
        
        Args:
            bitmap_size: bitmap 大小（默认 AFL++ 的 64KB）
        """
        self.bitmap_size = bitmap_size
        self.global_bitmap = bytearray(bitmap_size)
        self.coverage_history = []
    
    def update(self, new_bitmap: bytes) -> Tuple[int, bool]:
        """
        更新全局覆盖率
        
        Args:
            new_bitmap: 新的执行覆盖率
        
        Returns:
            (新增覆盖数, 是否有新覆盖)
        """
        if len(new_bitmap) != self.bitmap_size:
            return 0, False
        
        delta = 0
        has_new = False
        
        for i in range(self.bitmap_size):
            new_bits = new_bitmap[i] & ~self.global_bitmap[i]
            if new_bits:
                delta += bin(new_bits).count('1')
                has_new = True
                self.global_bitmap[i] |= new_bitmap[i]
        
        return delta, has_new
    
    def get_coverage_count(self) -> int:
        """获取当前总覆盖数"""
        return sum(bin(b).count('1') for b in self.global_bitmap)
    
    def record_snapshot(self, timestamp: str, coverage: int):
        """记录时间点的覆盖率"""
        self.coverage_history.append({
            'timestamp': timestamp,
            'coverage': coverage
        })
