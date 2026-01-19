# 覆盖率引导的变异式模糊测试工具 (AT-Fuzz)

本项目实现了一个基于 Python 的**覆盖率引导的变异式模糊测试工具**，参考了 AFL++ 的核心设计理念，实现了完整的模糊测试循环。

---

## ⚡ 快速使用

```bash
# 1. 使用 AFL++ 编译目标程序
afl-cc -o target target.c

# 2. 准备种子
mkdir seeds && echo "test" > seeds/input.txt

# 3. 运行模糊测试（1小时）
python3 -m src.fuzzer \
    --target ./target \
    --args "@@" \
    --seeds ./seeds \
    --output ./output \
    --duration 3600

# 4. 查看结果
cat output/stats.json
ls output/crashes/
ls output/plot_*.png
```

**恢复检查点**：
```bash
python3 -m src.fuzzer \
    --target ./target \
    --args "@@" \
    --seeds ./seeds \
    --output ./output \
    --duration 7200 \
    --resume-from output/checkpoints/checkpoint.json
```

---

## 📋 功能特性

- **覆盖率引导**：通过 System V Shared Memory 与 AFL++ 插装程序通信，实时获取边覆盖率。
- **智能调度**：基于大根堆的能量优先调度 (O(log n))，参考 AFL++ 的评分策略。
- **变异策略**：实现了 BitFlip, ByteFlip, Arithmetic, Interesting Values, Havoc, Splice 等多种变异算子。
- **崩溃检测**：支持信号检测 (SIGSEGV, SIGABRT) 和 ASan (AddressSanitizer) 集成。
- **可视化评估**：自动生成覆盖率增长、执行速度和崩溃发现的统计图表。
- **灵活输入**：支持文件参数 (`@@`) 和标准输入 (stdin) 两种模式。
- **可选沙箱隔离**：支持使用 bubblewrap (`bwrap`) 在受限环境中运行目标程序（缺失时自动回退）。
- **检查点恢复**：支持暂停保存状态并在下次继续运行。

---

## 🏗️ 系统架构

系统由多个核心组件构成：

1. **测试执行组件** (`src/components/executor.py`)
   负责启动子进程，管理环境变量 (`__AFL_SHM_ID`, `AFL_NO_FORKSRV`)，处理超时和崩溃检测。

2. **执行结果监控组件** (`src/components/monitor.py`)
   解析执行结果，追踪全局覆盖率，保存崩溃样本。

3. **变异组件** (`src/components/mutator.py`)
   提供多种变异算子，支持堆叠变异 (Havoc)。

4. **种子调度组件** (`src/components/scheduler.py`)
   维护种子优先队列（大根堆），根据能量评分选择种子 (O(log n))。

5. **评估组件** (`src/components/evaluator.py`)
   记录运行时数据，生成 CSV 报告和 Matplotlib 图表。

**辅助模块**：
- **检查点管理** (`src/checkpoint.py`) - 用于保存和恢复模糊测试状态
- **工具函数** (`src/utils.py`) - 包含共享内存操作、覆盖率计算等工具函数
- **配置管理** (`src/config.py`) - 全局配置管理
- **日志系统** (`src/logger.py`) - 统一日志输出

---

## 🚀 快速开始

### 1. 环境准备

**推荐方法一：使用 Docker Compose（最简单）**

```bash
# 1. 构建并启动容器
docker-compose up -d fuzzer

# 2. 进入容器
docker-compose exec fuzzer bash

# 在容器内工作...

# 3. 退出并停止容器
exit
docker-compose down
```

**推荐方法二：使用 Docker**

```bash
docker build -t at-fuzz .

# 运行容器（交互模式）
docker run -it --privileged \
    -v $(pwd):/fuzzer \
    at-fuzz
```

> **注意**：如果不使用沙箱功能 (`--use-sandbox`)，可以移除 `--privileged` 参数。但通过 bubblewrap 进行隔离需要该权限。

**方法三：本地环境 (Ubuntu 22.04+)**

```bash
# 安装 AFL++ 和系统依赖
sudo apt-get update
sudo apt-get install -y build-essential python3 python3-pip python3-venv afl++ bubblewrap

# 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装 Python 依赖
pip install --upgrade pip
pip install matplotlib
```

---

### 2. 准备测试目标

使用 `afl-cc` 编译你的目标程序：

```bash
# 设置 AFL++ 编译器
export CC=afl-cc
export CXX=afl-c++

# 编译目标程序
./configure --disable-shared
make
```

---

### 3. 运行模糊测试

**基本用法**：

```bash
python3 -m src.fuzzer \
    --target /path/to/target_binary \
    --args "@@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 3600
```

**参数说明**：

*   `--target`：目标程序的路径（绝对路径或相对路径）。
*   `--args`：命令行参数，`@@` 会被替换为输入文件路径；如果不包含 `@@`，则通过 stdin 传递输入。
*   `--seeds`：初始种子目录。
*   `--output`：输出目录，保存 crashes, queue, 统计数据等。
*   `--duration`：测试持续时间（秒）。
*   `--checkpoint-path`：检查点保存目录（默认：`<output>/checkpoints`）。
*   `--resume-from`：从指定的 `checkpoint.json` 恢复运行。

配置项（如 `--timeout` / `--mem-limit` / `--max-seed-size` / `--use-sandbox` 等）与 `src/config.py` 保持一致，并由配置元数据自动生成命令行参数；完整列表以 `python3 -m src.fuzzer --help` 为准。

**示例：测试一个二进制程序**

```bash
# 文件参数模式
python3 -m src.fuzzer \
    --target /path/to/your_binary \
    --args "-a @@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 600

# 标准输入模式
python3 -m src.fuzzer \
    --target /path/to/your_binary \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 600
```

你也可以通过命令行覆盖 `config.py` 中的大多数参数，例如：

```bash
python3 -m src.fuzzer \
    --target /path/to/your_binary \
    --args "-a @@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 600 \
    --timeout 2.0 \
    --havoc-iterations 20 \
    --max-seed-size $((512 * 1024))
```

说明：`--max-seed-size` 的单位是 **字节**。

建议根据不同目标（例如是否 `@@` 文件输入、解析速度、典型输入规模）调整 `--timeout` / `--havoc-iterations` / `--max-seed-size`。

---

## ✅ 运行测试

本项目使用 `unittest`，可以一条命令跑完整测试集：

```bash
python3 -m unittest discover -s tests -v
```

说明：

- 覆盖核心组件：`executor` / `mutator` / `scheduler` / `evaluator` / `utils` / `checkpoint` / `monitor`。
- 如果系统安装了 `bwrap`，会额外跑 executor 的沙箱相关测试；未安装时会自动跳过或回退验证。

---

## 🛡️ 可选沙箱（bubblewrap）

当目标程序不可信或希望隔离文件系统副作用时，可以启用 `bwrap` 沙箱：

- 在 `src/config.py` 中设置 `use_sandbox=True`。
- 若系统缺少 `bwrap`，执行器会打印 warning 并自动回退为非沙箱运行（不影响基本功能）。

建议：对于脚本类/可能产生子进程或执行外部命令的目标，优先使用命令行开关 `--use-sandbox`。

---

## ⏸️ 暂停与恢复（检查点）

AT-Fuzz 支持在长时间运行中“暂停并保存状态”，并在下次从检查点继续。

- 暂停：向进程发送 `SIGINT`（最常用方式是直接按 Ctrl+C）。程序会在主循环中保存检查点并退出，同时输出检查点大小拆分与最终 JSON 大小。
- 恢复：使用 `--resume-from /path/to/checkpoint.json`。
- 重要限制：检查点保存发生在主 fuzz 循环中；加载初始种子阶段不会保存检查点。并且从检查点恢复时会跳过初始种子加载。

示例：

```bash
# 运行并指定检查点目录
python3 -m src.fuzzer \
    --target /path/to/your_binary \
    --args "your_binary -a @@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 3600 \
    --checkpoint-path output/test_run/checkpoints

# 从检查点恢复
python3 -m src.fuzzer \
    --target /path/to/your_binary \
    --args "your_binary -a @@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 3600 \
    --resume-from output/test_run/checkpoints/checkpoint.json
```

---

## 📊 输出结果

测试完成后，结果保存在指定的 `--output` 目录下：

```
output/
└── <test_name>/
    ├── crashes/               # 发现的崩溃样本 (唯一哈希)
    ├── hangs/                 # 发现的超时样本 (唯一哈希)
    ├── queue/                 # 触发新覆盖率的种子
    ├── timeline.csv           # 时间序列数据
    ├── stats.json             # 统计摘要
    ├── final_report.json      # 最终报告
    ├── plot_coverage.png      # 覆盖率增长曲线
    ├── plot_crashes.png       # 崩溃发现曲线
    ├── plot_executions.png    # 执行数增长曲线
    └── plot_exec_rate.png     # 执行速度曲线
```

---

## 📂 项目结构

```
AT-fuzz/
├── src/
│   ├── fuzzer.py               # 主程序入口
│   ├── config.py               # 全局配置
│   ├── utils.py                # 工具函数 (SHM, Bitmap)
│   ├── checkpoint.py           # 检查点管理
│   ├── logger.py               # 日志系统
│   └── components/             # 核心组件
│       ├── executor.py         # 测试执行组件
│       ├── monitor.py          # 执行结果监控组件
│       ├── mutator.py          # 变异组件
│       ├── scheduler.py        # 种子调度 + 能量调度组件
│       └── evaluator.py        # 评估组件
├── tests/                      # 单元测试
├── docs/                       # 文档
│   └── DESIGN.md               # 设计文档
├── examples/                   # 示例与实验资源
│   ├── sources/                # 测试目标源代码（含 tar.gz）
│   ├── seeds/                  # 各测试目标的初始种子库
│   ├── run_target.sh           # 统一的目标编译和运行脚本
│   └── docker-compose.yml      # 实验用 Docker Compose 配置
├── Dockerfile                  # 容器配置
├── docker-compose.yml          # Docker Compose 配置
└── README.md                   # 本文件
```

---

## 📝 文档与示例

- **[docs/DESIGN.md](docs/DESIGN.md)** - 系统设计文档（包含技术难点与实现方案）
- **[examples/](examples/)** - 实验资源与演示脚本
  - `run_target.sh` - 统一的测试目标编译与运行脚本
  - `sources/` - 测试目标源代码（tar.gz 格式）
  - `seeds/` - 各目标的初始种子库
  - `docker-compose.yml` - 批量实验的 Docker Compose 配置

---

## 🐳 Docker 使用

### 开发模式（推荐）

```bash
# 启动容器
docker-compose up -d fuzzer

# 进入容器
docker-compose exec fuzzer bash

# 在容器内运行测试
python3 -m src.fuzzer \
    --target /path/to/target \
    --args "target @@" \
    --seeds /path/to/seeds \
    --output output/test \
    --duration 300

# 退出
exit
docker-compose down
```

**或直接使用 Docker**：

```bash
# 构建镜像
docker build -t at-fuzz .

# 运行容器
docker run -it \
    -v $(pwd)/output:/fuzzer/output \
    -v $(pwd)/components:/fuzzer/components \
    at-fuzz
```

---

## 🛠️ 高级配置

编辑 `config.py` 可调整（以下为常用项；完整列表以 `python3 -m src.fuzzer --help` 与 `config.py` 为准）：

*   **`timeout`**：单次执行超时时间（秒）。
*   **`mem_limit`**：目标程序内存限制（MB）。
*   **`log_interval`**：状态栏/日志更新频率（秒）。
*   **`bitmap_size`**：覆盖率位图大小（默认 65536）。
*   **`max_seed_size`**：种子最大大小（字节），限制初始种子和变异后的种子大小。
*   **`havoc_iterations`**：Havoc 变异迭代次数，控制变异强度（默认 16，越大变异越多）。
*   **`seed_sort_strategy`**：种子调度策略（`energy` / `fifo`）。
*   **`max_seeds`**：种子队列最大数量。
*   **`max_seeds_memory`**：种子队列最大内存（MB）。
*   **`stderr_max_len`**：单次执行 stderr 保存上限（字节）。
*   **`crash_info_max_len`**：崩溃/超时样本记录中 stderr 保存上限（字节）。
*   **`use_sandbox`**：是否启用 bubblewrap 沙箱（需要系统已安装 `bwrap`）。

配置系统设计与“命令行参数自动生成”的实现细节见 [docs/DESIGN.md](docs/DESIGN.md)。

**注意**：配置项会自动从 `src/config.py` 的 `CONFIG_SCHEMA` 生成命令行参数，无需手动添加 argparse 参数。

---

## 📚 参考资源

*   **AFL++**：https://github.com/AFLplusplus/AFLplusplus
*   **AFL 论文**：*American Fuzzy Lop: A Security-Oriented Fuzzer* (Michał Zalewski, 2014)
*   **FairFuzz 论文**：*FairFuzz: A Targeted Mutation Strategy for Increasing Greybox Fuzz Testing Coverage* (ASE 2018)
*   **AFLGo 论文**：*Directed Greybox Fuzzing* (CCS 2017)

## 📝 使用建议

1. **目标程序编译**：使用 AFL++ 编译器（`afl-cc`/`afl-c++`）对目标程序进行插桩
2. **种子准备**：准备多样化的初始种子，有助于快速发现新路径
3. **参数调优**：根据目标程序特性调整 `timeout`、`havoc_iterations`、`max_seed_size` 等参数
4. **长时间运行**：使用检查点机制（`--resume-from`）支持长时间运行和中断恢复
5. **结果分析**：查看 `output/` 目录下的统计报告和可视化图表，分析模糊测试效果

---

## 📄 许可证

本项目仅供学习和研究使用。

---
