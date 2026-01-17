# AT-Fuzz 设计文档

## 一、项目概述

### 1.1 项目背景

模糊测试（Fuzzing）通过持续向目标程序喂入大量输入并监控异常行为，来发现崩溃与潜在漏洞。相比纯随机的黑盒方式，覆盖率引导（灰盒）能够利用运行时反馈，把计算资源更多投入到“更可能走到新路径”的输入上。

AFL/AFL++ 是覆盖率引导模糊测试的经典实现。本项目（AT-Fuzz）参考 AFL++ 的核心思路，用 Python 实现一个可运行、可复现实验结果的灰盒变异式模糊测试框架。

### 1.2 项目目标

1. 实现一个可用的覆盖率引导模糊测试工具（完整主循环、崩溃保存、统计输出）
2. 跑通覆盖率反馈、种子调度、变异策略等关键机制
3. 掌握与 AFL++ 插桩程序通过共享内存交互的方法
4. 在多个真实目标上验证可用性

### 1.3 技术选型

- **开发语言**：Python 3（3.10+）
   - 优势：迭代快、代码可读性好，适合做完整流程验证
   - 代价：性能不如原生 C/C++ fuzzer，需要在实现上减少不必要的开销

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
   - 依赖 AFL++ 编译器对目标源代码进行插桩。
   - 确保生成的位置无关代码和共享内存通信接口正常工作。

2. **种子准备**
   - 从 AFL++ testcases 和项目自带样本中提取种子

3. **批量测试**
   - 支持对多个目标进行长时间（24小时）测试
   - 自动生成汇总报告

### 2.2 非功能性需求

1. **性能**
   - 执行速度目标：100+ execs/sec（Python 实现的合理水平）
   - 内存占用：控制在合理范围

2. **可靠性**
   - 支持长时间运行（24小时无异常）
   - 正确处理信号（SIGINT 触发保存检查点并退出；SIGTERM 做收尾并退出）
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

**职责**：把输入喂给目标程序并拿到一次执行的完整结果（退出码/信号、耗时、stdout/stderr，以及可选的覆盖率 bitmap）。

**主要接口**（对应实现：[components/executor.py](../components/executor.py)）：
```python
class TestExecutor:
   def __init__(
      self,
      target_path: str,
      target_args: str,
      timeout: float | None = None,
      use_coverage: bool = False,
   ) -> None: ...

   def execute(self, input_data: bytes) -> ExecutionResult: ...
   def cleanup(self) -> None: ...
```

说明：`ExecutionResult` 在实现中使用 `TypedDict` 描述字段结构；运行时依然是普通 `dict`，但字段集合由类型定义作为单一事实来源，避免“字段列表/校验函数/访问方”多处手工同步。

**实现要点**：
- execute 由多个私有步骤组成：清空 bitmap、写入输入、准备执行上下文、执行并收集结果
- 支持 `@@` 文件参数和 stdin 两种输入方式
- 通过 `__AFL_SHM_ID` 向目标进程传递共享内存 ID
- 使用超时限制避免 hang，并在返回码/信号上做崩溃判定（含 ASan exitcode）
- 可选使用 bubblewrap (`bwrap`) 沙箱隔离运行（通过 `config.py` 的 `use_sandbox` 开关控制；若缺失 `bwrap` 则自动回退）
- 统一日志输出使用 `logger.py` 提供的 logger

#### 组件2：执行监控器 (ExecutionMonitor)

**职责**：处理每次执行的结果：更新全局覆盖率、判断是否产生新路径、保存崩溃样本/新覆盖样本，并累计统计数据。

**主要接口**（对应实现：[components/monitor.py](../components/monitor.py)）：
```python
class ExecutionMonitor:
   def __init__(self, output_dir: str, use_coverage: bool = False) -> None: ...
   def process_execution(self, input_data: bytes, exec_result: ExecutionResult) -> bool: ...
   def save_stats_to_file(self) -> None: ...

   # 统计数据直接通过 stats 属性访问
   stats: MonitorStats  # dataclass，包含 total_execs/saved_crashes/total_coverage_bits 等
```

说明：监控统计使用 `MonitorStats`（`dataclass`）统一字段定义；序列化落盘时使用 `stats.to_dict()`，字段名列表（如 `STATS_FIELDS`）从 dataclass 字段动态导出，降低“改字段要同步改多处”的风险。

**实现要点**：
- 覆盖率用 virgin_bits bitmap 维护，参考 AFL++ 的 has_new_bits 判断"新覆盖"
- 崩溃/超时去重采用 AFL++ 风格的 virgin_crash/virgin_tmout bitmap
- 覆盖率位数统计通过 `_get_coverage_bits()` 做缓存，并附带 LRU 清理逻辑

#### 组件3：变异器 (Mutator)

**职责**：对输入做变异，生成候选测试用例。

**主要接口**（对应实现：[components/mutator.py](../components/mutator.py)）：
```python
class Mutator:
   @staticmethod
   def mutate(data: bytes, strategy: str = 'havoc', **kwargs) -> bytes: ...

   # 常用算子（示例）
   @staticmethod
   def havoc(data: bytes, iterations: int = 16) -> bytes: ...
   @staticmethod
   def bit_flip(data: bytes, flip_count: int = 1) -> bytes: ...
   @staticmethod
   def byte_flip(data: bytes, flip_count: int = 1) -> bytes: ...
   @staticmethod
   def arithmetic(data: bytes, max_val: int = 35) -> bytes: ...
   @staticmethod
   def interesting_values(data: bytes) -> bytes: ...
   @staticmethod
   def insert(data: bytes) -> bytes: ...
   @staticmethod
   def delete(data: bytes) -> bytes: ...
   @staticmethod
   def splice(data1: bytes, data2: bytes) -> bytes: ...
```

**实现要点**：
- 基础算子：bit/byte 翻转、算术变异、interesting values、插入/删除等
- Havoc：随机堆叠多种变异，提升多样性
- Splice：从两个种子中切片拼接，适合结构化输入的探索

#### 组件4&5：种子调度器 (SeedScheduler)

**职责**：管理种子队列，并决定下一次优先 fuzz 哪个种子。

**主要接口**（对应实现：[components/scheduler.py](../components/scheduler.py)）：
```python
@dataclass(order=True)
class Seed:
   data: bytes
   exec_count: int = 0
   coverage_bits: int = 0
   exec_time: float = 0.0
   energy: float = 1.0

class SeedScheduler:
   def __init__(self) -> None: ...
   def add_seed(self, seed_data: bytes, coverage_bits: int = 0, exec_time: float = 0.0) -> None: ...
   def select_next(self): ...
   def get_stats(self) -> dict: ...
```

**实现要点**：
- 以“能量/优先级”对种子排序（覆盖率贡献、执行速度、已执行次数等因素综合）
- 使用堆结构保证选择与更新都是 $O(\log n)$
- 引入衰减/公平性，避免少数种子长期霸占执行预算

#### 组件6：评估器 (Evaluator)

**职责**：把运行过程的指标记录下来，并在结束时输出可复盘的数据与图表。

**主要接口**（对应实现：[components/evaluator.py](../components/evaluator.py)）：
```python
class Evaluator:
   def __init__(self, output_dir: str) -> None: ...
   def record(
      self,
      total_execs: int,
      exec_rate: float,
      total_crashes: int,
      saved_crashes: int,
      total_hangs: int,
      saved_hangs: int,
      coverage: int = 0,
   ) -> None: ...
   def save_final_report(self, stats: dict) -> None: ...
   def generate_plots(self) -> None: ...
```

**输出**：时间序列（CSV）、汇总统计（JSON）、以及覆盖率/执行速率/崩溃数量等曲线图。

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

AT-Fuzz 通过 System V 共享内存读取 AFL++ 的覆盖率 bitmap。核心思路是：主进程创建并映射共享内存，把 `__AFL_SHM_ID` 传给子进程，执行结束后读取 bitmap 并与全局覆盖率做比较。

实现上有一个重要取舍：为了让 Python 侧逻辑更简单，本项目通过 `AFL_NO_FORKSRV=1` 禁用 forkserver。这样每次执行都走一次 exec，性能会有损失，但换来更直接、可控的执行模型。

### 4.2 崩溃检测机制

#### 4.2.1 崩溃类型识别

并非所有非零返回码都是崩溃，需要精确识别真正的内存错误：

1. **ASan 崩溃**：返回码 = 77（通过 `ASAN_OPTIONS=exitcode=77` 配置）
2. **信号终止**：
   - 返回码 < 0（Python `subprocess` 表示被信号杀死）
   - 返回码 >= 128（Shell 惯例，如 SIGSEGV=139）

正常错误（如参数错误 `exit(1)`）不应被视为崩溃。

#### 4.2.2 去重策略

崩溃去重采用“可实现、够用”的策略：例如对 stderr 做哈希，重复的崩溃不重复落盘。它能明显减少噪声，但不保证严格等价于“漏洞唯一”。

### 4.3 能量调度算法

#### 4.3.1 设计目标

1. 优先测试"高价值"种子（覆盖率高、执行快）
2. 防止饥饿（确保所有种子都有机会）
3. 高效实现（O(log n) 复杂度）

#### 4.3.2 算法实现

能量计算参考 AFL++ 的思路：更快的样本、更能带来覆盖增长的样本，会拿到更高的执行预算；同时对已经跑了很多次的样本做衰减。实现上用堆维护优先级，保证选择与更新的代价可控。

### 4.4 变异策略

#### 4.4.1 Havoc 变异

Havoc 通过随机堆叠多种算子生成更“野”的输入，用来快速扩大搜索空间；当一些确定性变异开始边际收益下降时，Havoc 往往更有效。

实现上，Havoc 的“堆叠次数”通过 `config.py` 的 `havoc_iterations` 控制，并支持用命令行参数 `--havoc-iterations` 覆盖。主循环在生成变异样本时，会把该配置值传递给 `Mutator.mutate(..., iterations=...)`，从而真正影响变异强度。

#### 4.4.2 Splice 变异

从两个不同的种子中各取一部分拼接，产生新的组合：

Splice 将两个种子切片后拼接，适合结构化输入（多个字段/块）的探索。

### 4.5 配置系统与命令行一致性

AT-Fuzz 将“默认配置、类型约束、验证规则、命令行参数”统一收敛到 [config.py](../config.py) 中，确保配置体系符合软件工程的单一事实来源（Single Source of Truth）原则。

核心机制：

1. `config.py` 定义两部分：
   - `CONFIG`：默认值（运行时读取）。
   - `CONFIG_SCHEMA`：配置元数据（类型、validator、命令行参数名/帮助、枚举 choices）。

2. `fuzzer.py` 通过遍历 `CONFIG_SCHEMA` 自动生成 argparse 参数，并将解析结果统一应用到 `CONFIG`，避免在多处重复维护参数列表。

3. 命令行覆盖规则：
   - 数值/字符串配置：通过 `--key value` 覆盖。
   - 枚举配置：通过 `choices` 限制可选值（例如 `--seed-sort-strategy energy|fifo`）。
   - 布尔开关：使用 flag 形式（例如 `--use-sandbox`），用于在需要隔离副作用的目标上启用 bubblewrap。

4. Fail-fast 校验：启动时会对默认配置做校验；运行时若通过命令行覆盖，类型转换由 argparse 保证，值域/约束由 `validator` 保证。

添加新配置项的步骤（最小化维护成本）：

1. 在 `CONFIG_SCHEMA` 中新增元数据（包含类型与校验规则）。
2. 在 `CONFIG` 中新增默认值。
3.（可选）补充/更新单元测试与 README 的使用说明。

### 4.6 字段一致性与类型安全

项目中有若干“跨组件传递/持久化的结构化数据”（例如执行结果、监控统计、时间序列记录）。早期实现如果同时维护：字段名元组、构造逻辑、序列化逻辑、读取/访问逻辑，容易出现“改一处漏改另一处”的隐患。

为降低这类人工同步成本，当前实现采用“类型定义即字段单一事实来源”的方式：

1. 执行器返回值：使用 `ExecutionResult(TypedDict)` 定义字段集合与类型；测试可通过 `ExecutionResult.__annotations__` 反射字段名。
2. 监控统计：使用 `MonitorStats(dataclass)` 定义统计字段；`STATS_FIELDS` 通过 `dataclasses.fields(MonitorStats)` 动态导出；序列化使用 `asdict()`。
3. 评估时间序列：使用 `TimelineRecord(NamedTuple)` 定义 CSV 行结构；`CSV_COLUMNS` 通过 `TimelineRecord._fields` 自动导出；写入 CSV 直接 `writer.writerow(record)`。

这套做法的目标是：在不引入额外运行时开销的前提下，让字段结构在代码层面“可检查、可推断、可复用”，并把字段变更的影响面收敛到单一位置。

---

## 五、技术难点与解决方案

### 5.1 Python 性能优化

**问题**：Python 执行速度慢，模糊测试对性能敏感。

**解决方案**：
- 用 `/tmp` 作为临时目录（通常是 tmpfs），减少 I/O 开销
- 关键路径尽量用 `bytearray`，避免反复拷贝与对象创建
- 调度器用堆结构，避免线性扫描

### 5.2 stdin 输入支持

**问题**：AFL++ 默认使用文件参数（`@@`），但部分目标（如 `readpng`）只接受 stdin。

**解决方案**：参数含 `@@` 走文件模式；否则走 stdin 模式（把输入写入子进程 stdin）。

### 5.3 长时间运行稳定性

**问题**：24小时测试需要确保无内存泄漏、无资源耗尽。

**解决方案**：确保资源清理（共享内存/临时文件）、把关键统计按周期落盘，并提供检查点机制用于长跑过程中的暂停与恢复：

- SIGINT：请求暂停并保存检查点（随后退出）。
- SIGTERM：正常收尾（生成报告/图表）后退出。
- 限制：检查点保存发生在主 fuzz 循环中；加载初始种子阶段不会保存检查点；从检查点恢复时会跳过初始种子加载。

---

## 六、测试与验证

### 6.1 单元测试

为核心组件编写单元测试（`tests/` 目录），覆盖执行器、变异器、调度器、评估器、覆盖率更新与共享内存等关键逻辑。

推荐在开发/CI 中使用以下命令运行全部测试：

```bash
python3 -m unittest discover -s tests -v
```

说明：如果系统安装了 `bwrap`，会额外覆盖执行器的沙箱路径；未安装时相关测试会跳过或验证回退逻辑。

### 6.2 集成测试

使用一个可控的“必崩”小目标程序验证端到端流程（生成输入 → 执行 → 捕获崩溃 → 落盘去重 → 统计输出）。

### 6.3 基准测试

在多个真实目标上做长时间运行验证：稳定性（不中断）、有效性（覆盖率增长/崩溃样本）、以及资源占用。

---

## 七、总结与展望

### 7.1 项目成果

实现了一个可运行的 Python 灰盒 fuzzer：覆盖率反馈、变异主循环、崩溃处理与统计输出均可用。

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

本项目的重点收获是把“覆盖率反馈 + 调度 + 变异 + 执行 + 评估”的完整闭环跑通，并把工程取舍（如禁用 forkserver）写清楚。