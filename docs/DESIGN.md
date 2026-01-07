# AT-Fuzz 设计文档

## 一、项目概述

### 1.1 项目背景

模糊测试（Fuzzing）是一种自动化软件测试技术，通过向目标程序输入大量随机或半随机数据，监控程序行为以发现漏洞和崩溃。传统的随机模糊测试（黑盒模糊测试）效率较低，而覆盖率引导的模糊测试（灰盒模糊测试）通过实时获取代码覆盖率信息，能够智能地引导测试用例生成，显著提高了测试效率。

AFL（American Fuzzy Lop）及其后继者 AFL++ 是工业界和学术界广泛使用的覆盖率引导模糊测试工具，在漏洞挖掘领域取得了巨大成功。本项目（AT-Fuzz）基于 AFL++ 的核心设计理念，使用 Python 语言实现了一个完整的覆盖率引导模糊测试框架。

### 1.2 项目目标

1. 实现一个功能完整的覆盖率引导模糊测试工具
2. 理解模糊测试的核心算法和数据结构
3. 掌握与编译器插桩工具（AFL++）的集成方法
4. 验证工具在真实程序上的有效性（10个基准测试目标）

### 1.3 技术选型

- **开发语言**：Python 3.7+
  - 优势：开发效率高，代码可读性强，便于快速迭代
  - 劣势：执行速度相比 C/C++ 较慢（通过优化算法和数据结构弥补）

- **插桩工具**：AFL++ (afl-cc/afl-c++)
  - 提供编译时代码插桩
  - 生成覆盖率反馈的二进制程序

- **通信机制**：System V Shared Memory
  - 用于 Python 主进程与插桩子进程之间的高效数据传递
  - 避免管道或文件 I/O 的开销

- **可视化**：Matplotlib
  - 生成覆盖率增长曲线、崩溃发现图表等

---

## 二、需求分析

### 2.1 功能性需求

#### 核心功能

1. **测试执行**
   - 支持以子进程方式启动目标程序
   - 支持文件参数（`@@`）和标准输入（stdin）两种输入模式
   - 实现超时控制（防止程序hang）
   - 捕获崩溃信号（SIGSEGV, SIGABRT）和 ASan 错误

2. **覆盖率收集**
   - 通过共享内存与 AFL++ 插桩程序通信
   - 实时追踪全局代码边覆盖率
   - 检测新覆盖率的增量

3. **变异策略**
   - 实现多种基础变异算子（位翻转、字节翻转、算术、插入、删除）
   - 实现 Havoc 变异（随机堆叠多种变异）
   - 支持 Splice 变异（种子拼接）

4. **种子调度**
   - 维护种子队列
   - 基于覆盖率和执行时间计算种子优先级
   - 使用大根堆实现高效调度（O(log n)）

5. **崩溃检测与去重**
   - 检测程序崩溃（非零返回码、信号终止）
   - 基于 stderr 的哈希值对崩溃去重
   - 保存崩溃输入和元数据

6. **统计与评估**
   - 记录时间序列数据（执行数、覆盖率、崩溃数）
   - 生成 CSV 和 JSON 格式的报告
   - 自动绘制可视化图表

#### 辅助功能

1. **目标程序构建**
   - 提供批量构建脚本
   - 自动化处理特殊项目（mjs, readpng）

2. **种子准备**
   - 从 AFL++ testcases 和项目自带样本中提取种子

3. **批量测试**
   - 支持对多个目标进行长时间（24小时）测试
   - 自动生成汇总报告

### 2.2 非功能性需求

1. **性能**
   - 执行速度目标：50+ execs/sec（Python 实现的合理水平）
   - 内存占用：控制在合理范围（< 1GB）

2. **可靠性**
   - 支持长时间运行（24小时无异常）
   - 正确处理信号中断（SIGINT, SIGTERM）
   - 资源清理完整（共享内存、临时文件）

3. **可维护性**
   - 模块化设计，六个核心组件职责明确
   - 代码注释详细，符合 PEP 8 规范
   - 提供完整的文档和使用示例

4. **可扩展性**
   - 支持添加新的变异策略
   - 支持自定义调度算法
   - 与 AFL++ 插桩工具解耦，理论上可支持其他插桩方案

---

## 三、系统架构设计

### 3.1 总体架构

AT-Fuzz 采用模块化设计，将模糊测试流程分解为六个核心组件。这种设计使得每个组件职责单一，便于理解、测试和扩展。

```
┌──────────────────────────────────────────────────────────────┐
│                        主程序 (fuzzer.py)                      │
│  职责：初始化组件、编排主循环、处理信号、生成最终报告           │
└───────────────────────┬──────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
 │  Executor   │ │  Monitor    │ │  Scheduler   │
 │  组件1      │ │  组件2      │ │  组件4&5     │
 │  测试执行   │ │  结果监控   │ │  种子调度    │
 └──────┬──────┘ └──────┬──────┘ └──────┬───────┘
        │               │               │
        │               │               │
        ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌──────────────┐
 │  Mutator    │ │ Evaluator   │ │   Utils      │
 │  组件3      │ │  组件6      │ │  辅助模块    │
 │  输入变异   │ │  评估报告   │ │  SHM/工具    │
 └─────────────┘ └─────────────┘ └──────────────┘
```

### 3.2 组件详细设计

#### 组件1：测试执行器 (TestExecutor)

**职责**：
- 启动目标程序的子进程
- 管理输入输出（文件或 stdin）
- 设置环境变量（共享内存 ID）
- 超时控制和信号捕获

**关键接口**：
```python
class TestExecutor:
    def __init__(target_path, target_args, timeout, use_coverage)
    def execute(input_data: bytes) -> Dict
    def cleanup()
```

**核心逻辑**：
1. 将输入写入临时文件
2. 构建命令行（替换 `@@` 或使用 stdin）
3. 设置环境变量：`__AFL_SHM_ID`, `AFL_NO_FORKSRV`
4. 执行子进程，捕获返回码、执行时间、覆盖率
5. 判断崩溃（返回码 77/128+/负数）

**技术要点**：
- 使用 `/tmp` 作为临时目录（内存文件系统，加速 I/O）
- 配置 ASan 使用特殊退出码（77）区分崩溃和正常错误
- 通过 `subprocess.run()` 的 `timeout` 参数实现超时

#### 组件2：执行监控器 (ExecutionMonitor)

**职责**：
- 处理每次执行的结果
- 维护全局覆盖率 bitmap
- 检测和保存崩溃
- 记录统计数据

**关键接口**：
```python
class ExecutionMonitor:
    def __init__(output_dir, use_coverage)
    def process_execution(input_data, exec_result) -> bool
    def save_stats_to_file()
```

**核心逻辑**：
1. 判断是否为崩溃：检查 `crashed` 标志
2. 计算崩溃哈希：使用 stderr 的 MD5（去重）
3. 更新全局覆盖率：按位或合并新的 bitmap
4. 检测新覆盖：与全局 bitmap 比较
5. 保存有趣输入：崩溃、新覆盖、超时

**数据结构**：
```python
global_coverage: bytearray(65536)  # 全局覆盖率位图
unique_crashes: set                # 唯一崩溃哈希集合
stats: dict                        # 统计数据
```

#### 组件3：变异器 (Mutator)

**职责**：
- 实现多种变异算子
- 提供 Havoc 组合变异
- 支持 Splice 种子拼接

**关键接口**：
```python
class Mutator:
    @staticmethod
    def bit_flip(data, flip_count) -> bytes
    @staticmethod
    def havoc(data, iterations) -> bytes
    @staticmethod
    def splice(data1, data2) -> bytes
```

**变异算子**：
1. **Bit Flip**：随机翻转若干比特
2. **Byte Flip**：随机翻转若干字节
3. **Arithmetic**：对字节进行加减操作（±1 到 ±35）
4. **Interesting Values**：替换为特殊值（0, -1, 0x7F, 0xFF, 0x100）
5. **Insert**：随机插入字节
6. **Delete**：随机删除字节
7. **Havoc**：随机堆叠上述变异（默认16次）
8. **Splice**：从两个种子中各取一部分拼接

#### 组件4&5：种子调度器 (SeedScheduler)

**职责**：
- 维护种子队列（大根堆）
- 计算种子能量（优先级）
- 选择下一个测试种子

**关键接口**：
```python
class SeedScheduler:
    def __init__()
    def add_seed(seed_data, coverage_bits, exec_time)
    def select_next() -> Seed
```

**调度算法**（参考 AFL++ 的 calculate_score）：
```
perf_score = 100  # 基础分

# 1. 执行速度因子
if exec_time < avg * 0.25: perf_score = 300
elif exec_time < avg * 0.5: perf_score = 200
...

# 2. 覆盖率因子
if coverage > avg * 3: perf_score *= 3
elif coverage > avg * 2: perf_score *= 2
...

# 3. 衰减因子
perf_score /= 1 + 0.2 * exec_count
```

**数据结构**：
- 使用 Python 的 `heapq` 实现最小堆
- 通过 `sort_index = -energy` 转换为最大堆
- 每次 `select_next()` 复杂度：O(log n)

#### 组件6：评估器 (Evaluator)

**职责**：
- 记录时间序列数据
- 生成 CSV 和 JSON 报告
- 绘制可视化图表

**关键接口**：
```python
class Evaluator:
    def __init__(output_dir)
    def record(total_execs, exec_rate, total_crashes, coverage)
    def save_final_report(stats)
    def generate_plots()
```

**输出文件**：
- `timeline.csv`：时间序列数据
- `final_report.json`：最终统计报告
- `plot_*.png`：可视化图表（覆盖率、执行速度、崩溃）

### 3.3 数据流图

```
[种子库] ─┐
          │
          ├──> [调度器选择] ──> [变异器] ──> [执行器]
          │                                      │
          │                                      ▼
          │                              [监控器分析]
          │                                      │
          │                                      ├─ 崩溃 ──> [保存崩溃]
          │                                      │
          │                                      └─ 新覆盖 ─┐
          │                                                 │
          └─────────────────────────────────────────────────┘
                                (有趣的输入加回种子库)
```

---

## 四、关键技术实现

### 4.1 共享内存通信

#### 4.1.1 技术背景

AFL++ 插桩的程序在运行时会将覆盖率信息写入共享内存（bitmap），模糊器需要读取这些数据来判断是否发现新路径。Python 没有原生的共享内存 API（Python 3.8+ 有 `multiprocessing.shared_memory`，但与 AFL++ 的 System V SHM 不兼容），因此需要通过 `ctypes` 调用 C 库函数。

#### 4.1.2 实现细节

1. **创建共享内存**：
```python
libc = ctypes.CDLL("libc.so.6")
shm_id = libc.shmget(IPC_PRIVATE, bitmap_size, IPC_CREAT | 0o600)
```

2. **映射到进程地址空间**：
```python
shm_addr = libc.shmat(shm_id, None, 0)
```

3. **传递给子进程**：
```python
env['__AFL_SHM_ID'] = str(shm_id)
env['AFL_NO_FORKSRV'] = '1'  # 关键：禁用 forkserver
```

4. **读取覆盖率**：
```python
bitmap = ctypes.string_at(shm_addr, bitmap_size)
```

5. **清理资源**：
```python
libc.shmdt(shm_addr)
libc.shmctl(shm_id, IPC_RMID, None)
```

#### 4.1.3 技术难点

**问题**：AFL++ 默认使用 forkserver 模式，这种模式下 Python 难以与其通信。

**解决方案**：通过环境变量 `AFL_NO_FORKSRV=1` 强制目标程序每次都重新执行（exec），虽然牺牲了一些性能，但大大简化了实现，且对 Python 实现的模糊器来说，这个开销在可接受范围内。

### 4.2 崩溃检测机制

#### 4.2.1 崩溃类型识别

并非所有非零返回码都是崩溃，需要精确识别真正的内存错误：

1. **ASan 崩溃**：返回码 = 77（通过 `ASAN_OPTIONS=exitcode=77` 配置）
2. **信号终止**：
   - 返回码 < 0（Python `subprocess` 表示被信号杀死）
   - 返回码 >= 128（Shell 惯例，如 SIGSEGV=139）

正常错误（如参数错误 `exit(1)`）不应被视为崩溃。

#### 4.2.2 去重策略

使用 stderr 的哈希值作为崩溃的唯一标识：
```python
crash_hash = hashlib.md5(stderr).hexdigest()[:8]
if crash_hash not in unique_crashes:
    unique_crashes.add(crash_hash)
    # 保存崩溃输入
```

这种方法能够有效过滤重复崩溃，但也有局限性（同一漏洞的不同触发路径可能产生不同 stderr）。

### 4.3 能量调度算法

#### 4.3.1 设计目标

1. 优先测试"高价值"种子（覆盖率高、执行快）
2. 防止饥饿（确保所有种子都有机会）
3. 高效实现（O(log n) 复杂度）

#### 4.3.2 算法实现

参考 AFL++ 的 `calculate_score` 函数，实现三维评分：

```python
def _calculate_energy(seed):
    perf_score = 100
    
    # 维度1：执行速度（快者优先）
    if seed.exec_time * 4 < avg_exec_us:
        perf_score = 300
    # ... 其他分档
    
    # 维度2：覆盖率（高者优先）
    if seed.coverage_bits * 0.3 > avg_bitmap_size:
        perf_score *= 3
    # ... 其他分档
    
    # 维度3：衰减（防止过度测试）
    perf_score /= (1 + 0.2 * seed.exec_count)
    
    return perf_score
```

#### 4.3.3 堆优化

使用 Python 的 `heapq` 模块（最小堆）：
- 通过 `sort_index = -energy` 实现最大堆
- `heappop()` 取出能量最高的种子
- 更新能量后 `heappush()` 重新入堆

### 4.4 变异策略

#### 4.4.1 Havoc 变异

Havoc 是 AFL++ 的核心变异策略，通过随机堆叠多种变异产生高度多样化的输入。

```python
def havoc(data, iterations=16):
    mutations = [bit_flip, byte_flip, arithmetic, insert, delete, ...]
    for _ in range(iterations):
        mutation_func = random.choice(mutations)
        data = mutation_func(data)
    return data
```

**优势**：
- 能够快速探索输入空间
- 不依赖对文件格式的先验知识
- 在确定性变异效率降低后仍然有效

#### 4.4.2 Splice 变异

从两个不同的种子中各取一部分拼接，产生新的组合：

```python
def splice(data1, data2):
    split1 = random.randint(0, len(data1))
    split2 = random.randint(0, len(data2))
    return data1[:split1] + data2[split2:]
```

**适用场景**：结构化输入（如包含多个字段的文件格式）

---

## 五、技术难点与解决方案

### 5.1 Python 性能优化

**问题**：Python 执行速度慢，模糊测试对性能敏感。

**解决方案**：
1. 使用 `/tmp` 作为临时目录（通常是 tmpfs，内存文件系统）
2. 优化数据结构（使用 `bytearray` 而非多次 `bytes` 转换）
3. 减少不必要的对象创建
4. 使用堆优化调度器（O(log n) vs O(n)）

**实测结果**：达到 50-70 execs/sec（相比原生 AFL++ 的 500+ execs/sec 仍有差距，但对 Python 实现来说已是合理水平）

### 5.2 非标准目标构建

**问题**：部分目标（mjs, readpng）没有标准的 `configure && make` 流程。

**解决方案**：
- mjs：手动添加 `-DMJS_MAIN` 编译选项
- readpng：手动链接静态库 `libpng16.a` 和 `zlib`
- 在 `build_targets.sh` 中添加特殊处理逻辑

### 5.3 stdin 输入支持

**问题**：AFL++ 默认使用文件参数（`@@`），但部分目标（如 `readpng`）只接受 stdin。

**解决方案**：
- 检测参数中是否包含 `@@`
- 如果不包含，使用 Shell 重定向：`cmd < input_file`
- 确保跨平台兼容性

### 5.4 长时间运行稳定性

**问题**：24小时测试需要确保无内存泄漏、无资源耗尽。

**解决方案**：
1. 使用 `__del__` 和 `finally` 确保资源清理
2. 信号处理：优雅地响应 SIGINT/SIGTERM
3. 定期保存快照，避免意外中断导致数据丢失

---

## 六、测试与验证

### 6.1 单元测试

为核心组件编写单元测试（`tests/` 目录）：
- `test_executor.py`：测试执行器的超时、崩溃检测
- `test_mutator.py`：测试变异算子的正确性
- `test_coverage.py`：测试覆盖率计算
- `test_shm.py`：测试共享内存通信

### 6.2 集成测试

使用简单的目标程序（如 `test_crash.c`）验证端到端流程：
```c
int main(int argc, char **argv) {
    if (argc > 1 && argv[1][0] == 'A') {
        int *p = NULL;
        *p = 42;  // 崩溃
    }
    return 0;
}
```

### 6.3 基准测试

在10个真实目标上运行24小时测试，验证：
- 稳定性（无异常退出）
- 有效性（发现崩溃、覆盖率增长）
- 性能（执行速度、内存占用）

---

## 七、总结与展望

### 7.1 项目成果

1. 实现了功能完整的覆盖率引导模糊测试工具
2. 成功集成 AFL++ 插桩和共享内存通信
3. 在多个真实目标上验证了有效性
4. 代码结构清晰，文档完善

### 7.2 不足与改进方向

1. **性能**：相比原生 AFL++，执行速度仍有差距
   - 改进方向：使用 Cython 优化热点代码，或改用 C++ 重写核心模块

2. **调度策略**：目前仅实现了类似 FAST 的调度
   - 改进方向：支持更多调度策略（COE, RARE, MMOPT）

3. **变异策略**：缺少结构感知变异
   - 改进方向：集成语法/协议规范，实现基于语法的变异

4. **并行化**：当前为单进程
   - 改进方向：支持多进程并行模糊测试

### 7.3 学习收获

通过本项目，深入理解了：
- 模糊测试的核心原理和工作流程
- 覆盖率引导的价值和实现方法
- 与底层系统（共享内存、信号）的交互
- 软件工程实践（模块化设计、测试、文档）

---

**文档版本**：v1.0  
**最后更新**：2026年1月3日  
**作者**：南京大学软件学院
