"""
变异组件 (Component 3/6)
职责：生成新的测试用例，包含多种变异算子

参考 AFL++ 实现:
- afl-fuzz-one.c: fuzz_one_original, havoc_stage
- afl-mutations.h: 变异算子定义
"""

import random
import struct

# 这些值经常出现在边界条件和魔数中

INTERESTING_8 = [
    -128,                   # Overflow boundary
    -1,                     # 0xFF
    0,                      # Zero
    1,                      # One
    16,                     # One-off with common buffer size
    32,                     # Common buffer size / ASCII space
    64,                     # One-off with common buffer size
    100,                    # One-off with common buffer size
    127,                    # Signed int8 max
]

INTERESTING_16 = [
    -32768,                 # Overflow boundary
    -129,                   # Overflow boundary
    128,                    # Overflow boundary
    255,                    # Overflow boundary
    256,                    # Overflow boundary
    512,                    # Common buffer size
    1000,                   # Common size
    1024,                   # Common buffer size
    4096,                   # Common buffer size
    32767,                  # Signed int16 max
]

INTERESTING_32 = [
    -2147483648,            # Overflow boundary
    -100663046,             # Large negative
    -32769,                 # Overflow boundary
    32768,                  # Overflow boundary
    65535,                  # Overflow boundary
    65536,                  # Overflow boundary
    100663045,              # Large positive
    2147483647,             # Signed int32 max
]


class Mutator:
    """
    变异引擎
    实现多种变异策略，参考 AFL++
    """

    @staticmethod
    def bit_flip(data: bytes, flip_count: int = 1) -> bytes:
        """
        比特翻转（Bit Flip）
        随机翻转 flip_count 个比特
        """
        if len(data) == 0:
            return data

        data = bytearray(data)
        for _ in range(flip_count):
            bit_pos = random.randint(0, len(data) * 8 - 1)
            byte_idx = bit_pos // 8
            bit_idx = bit_pos % 8
            data[byte_idx] ^= 1 << bit_idx
        return bytes(data)

    @staticmethod
    def byte_flip(data: bytes, flip_count: int = 1) -> bytes:
        """
        字节翻转（Byte Flip）
        随机翻转 flip_count 个完整字节
        """
        if len(data) == 0:
            return data

        data = bytearray(data)
        for _ in range(flip_count):
            idx = random.randint(0, len(data) - 1)
            data[idx] ^= 0xFF
        return bytes(data)

    @staticmethod
    def interesting_values(data: bytes) -> bytes:
        """
        有趣数值替换（Interesting Values）
        用 AFL++ 定义的特殊边界值替换字节
        """
        if len(data) == 0:
            return data

        data = bytearray(data)

        # 随机选择 8/16/32 位替换
        choice = random.randint(0, 2)

        if choice == 0 and len(data) >= 1:
            # 8-bit
            idx = random.randint(0, len(data) - 1)
            val = random.choice(INTERESTING_8)
            data[idx] = val & 0xFF
        elif choice == 1 and len(data) >= 2:
            # 16-bit
            idx = random.randint(0, len(data) - 2)
            val = random.choice(INTERESTING_8 + INTERESTING_16)
            data[idx:idx+2] = struct.pack('<h', val)
        elif len(data) >= 4:
            # 32-bit
            idx = random.randint(0, len(data) - 4)
            val = random.choice(INTERESTING_8 + INTERESTING_16 + INTERESTING_32)
            data[idx:idx+4] = struct.pack('<i', val)

        return bytes(data)

    @staticmethod
    def insert(data: bytes) -> bytes:
        """
        插入变异
        随机插入一个字节
        """
        if len(data) >= 1024 * 100:  # 防止过大
            return data

        data = bytearray(data)
        insert_pos = random.randint(0, len(data))
        insert_byte = random.randint(0, 255)
        data.insert(insert_pos, insert_byte)
        return bytes(data)

    @staticmethod
    def delete(data: bytes) -> bytes:
        """
        删除变异
        随机删除一个字节
        """
        if len(data) == 0:
            return data

        data = bytearray(data)
        del_pos = random.randint(0, len(data) - 1)
        del data[del_pos]
        return bytes(data)

    @staticmethod
    def arithmetic(data: bytes, max_val: int = 35) -> bytes:
        """
        算术变异
        随机选择一个字节进行加减操作
        """
        if len(data) == 0:
            return data

        data = bytearray(data)
        idx = random.randint(0, len(data) - 1)
        val = random.randint(1, max_val)

        if random.choice([True, False]):
            # Add
            data[idx] = (data[idx] + val) % 256
        else:
            # Sub
            data[idx] = (data[idx] - val) % 256

        return bytes(data)

    @staticmethod
    def havoc(data: bytes, iterations: int = 16) -> bytes:
        """
        Havoc 变异 - AFL++ 的核心变异策略

        算法原理：
        Havoc 是一种"暴风式"变异策略，通过随机堆叠多个不同的变异操作，
        产生高度多样化的测试输入。这种策略在传统确定性变异(如逐位翻转)
        效率降低后，能够快速探索输入空间的不同区域。

        实现细节：
        - 从6种基础变异中随机选择（位翻转、字节翻转、算术、插入、删除、特殊值）
        - 每次迭代应用一个随机变异，变异结果作为下一次迭代的输入
        - 迭代次数默认16次，确保足够的变异强度，但又不至于完全破坏输入结构

        Args:
            data: 原始输入数据
            iterations: 堆叠变异的次数，越多越激进

        Returns:
            经过多次变异后的数据
        """
        mutations = [
            Mutator.bit_flip,
            Mutator.byte_flip,
            Mutator.interesting_values,
            Mutator.insert,
            Mutator.delete,
            Mutator.arithmetic
        ]

        data = bytearray(data)
        for _ in range(iterations):
            mutation_func = random.choice(mutations)
            try:
                data = bytearray(mutation_func(bytes(data)))
            except:
                # 变异失败，跳过
                pass

        return bytes(data)

    @staticmethod
    def splice(data1: bytes, data2: bytes) -> bytes:
        """
        拼接变异（Splice）
        结合两个种子
        """
        if len(data1) == 0: return data2
        if len(data2) == 0: return data1

        # 随机选择拼接点
        split_point1 = random.randint(0, len(data1))
        split_point2 = random.randint(0, len(data2))

        return data1[:split_point1] + data2[split_point2:]

    @staticmethod
    def mutate(data: bytes, strategy: str = 'havoc',
               **kwargs) -> bytes:
        """
        统一变异接口

        Args:
            data: 输入数据
            strategy: 变异策略
                - 'havoc': 混合变异（推荐）
                - 'bitflip': 比特翻转
                - 'byteflip': 字节翻转
                - 'interesting': 有趣值替换
                - 'insert': 插入
                - 'delete': 删除
                - 'arithmetic': 算术变异
                - 'splice': 拼接（需要 kwargs['other_data']）

        Returns:
            变异后的数据
        """
        match strategy:
            case 'havoc':
                iterations = kwargs.get('iterations', 16)
                return Mutator.havoc(data, iterations=iterations)

            case 'bitflip':
                flip_count = kwargs.get('flip_count', 1)
                return Mutator.bit_flip(data, flip_count=flip_count)

            case 'byteflip':
                flip_count = kwargs.get('flip_count', 1)
                return Mutator.byte_flip(data, flip_count=flip_count)

            case 'interesting':
                return Mutator.interesting_values(data)

            case 'insert':
                return Mutator.insert(data)

            case 'delete':
                return Mutator.delete(data)

            case 'arithmetic':
                return Mutator.arithmetic(data)

            case 'splice':
                other_data = kwargs.get('other_data')
                return data if not other_data else Mutator.splice(data, other_data)

            case _:
                # 默认使用 havoc
                return Mutator.havoc(data)


# ========== 测试代码 ==========
if __name__ == '__main__':
    test_data = b'Hello, Fuzzer!'

    print("Original:", test_data)
    print("Bit Flip:", Mutator.bit_flip(test_data))
    print("Byte Flip:", Mutator.byte_flip(test_data))
    print("Havoc:", Mutator.havoc(test_data, iterations=3))
