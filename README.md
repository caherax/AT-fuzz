# 覆盖率引导的变异式模糊测试工具 (AT-Fuzz)

本项目实现了一个基于 Python 的**覆盖率引导的变异式模糊测试工具**，参考了 AFL++ 的核心设计理念，实现了完整的模糊测试循环。

---

## 📋 功能特性

- **覆盖率引导**：通过 System V Shared Memory 与 AFL++ 插装程序通信，实时获取边覆盖率。
- **智能调度**：基于大根堆的能量优先调度 (O(log n))，参考 AFL++ 的评分策略。
- **变异策略**：实现了 BitFlip, ByteFlip, Arithmetic, Interesting Values, Havoc, Splice 等多种变异算子。
- **崩溃检测**：支持信号检测 (SIGSEGV, SIGABRT) 和 ASan (AddressSanitizer) 集成。
- **可视化评估**：自动生成覆盖率增长、执行速度和崩溃发现的统计图表。
- **灵活输入**：支持文件参数 (`@@`) 和标准输入 (stdin) 两种模式。

---

## 🏗️ 系统架构

系统由六个核心组件构成：

1. **测试执行组件** (`components/executor.py`)  
   负责启动子进程，管理环境变量 (`__AFL_SHM_ID`, `AFL_NO_FORKSRV`)，处理超时和崩溃检测。

2. **执行结果监控组件** (`components/monitor.py`)  
   解析执行结果，追踪全局覆盖率，保存崩溃样本。

3. **变异组件** (`components/mutator.py`)  
   提供多种变异算子，支持堆叠变异 (Havoc)。

4. **种子调度组件** (`components/scheduler.py`)  
   维护种子优先队列（大根堆），根据能量评分选择种子 (O(log n))。

5. **能量调度组件** (`components/scheduler.py`)  
   根据种子质量（覆盖率、执行时间、执行次数）动态计算能量，参考 AFL++ 的多调度策略。

6. **评估组件** (`components/evaluator.py`)  
   记录运行时数据，生成 CSV 报告和 Matplotlib 图表。

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
# 构建镜像
docker build -t at-fuzz .

# 运行容器（交互模式）
docker run -it \
    -v $(pwd)/output:/fuzzer/output \
    at-fuzz
```

**方法三：本地环境 (Ubuntu 22.04+)**

```bash
# 安装系统依赖
sudo apt-get install -y gcc g++ make python3 python3-pip zlib1g-dev

# 安装 AFL++ (用于插桩目标程序)
git clone https://github.com/AFLplusplus/AFLplusplus
cd AFLplusplus
make
sudo make install

# 安装 Python 依赖
pip3 install matplotlib
```

---

### 2. 准备测试目标

使用 `afl-cc` 编译你的目标程序：

```bash
# 设置 AFL++ 编译器
export CC=/path/to/afl-cc
export CXX=/path/to/afl-c++

# 编译目标程序
./configure --disable-shared
make
```

---

### 3. 运行模糊测试

**基本用法**：

```bash
python3 fuzzer.py \
    --target /path/to/target_binary \
    --args "target_binary @@" \
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

**示例：测试一个二进制程序**

```bash
# 文件参数模式
python3 fuzzer.py \
    --target /path/to/your_binary \
    --args "your_binary -a @@" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 600

# 标准输入模式
python3 fuzzer.py \
    --target /path/to/your_binary \
    --args "your_binary" \
    --seeds /path/to/seeds \
    --output output/test_run \
    --duration 600
```

---

## 📊 输出结果

测试完成后，结果保存在指定的 `--output` 目录下：

```
output/
└── <test_name>/
    ├── crashes/               # 发现的崩溃样本 (唯一哈希)
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
├── fuzzer.py               # 主程序入口
├── config.py               # 全局配置
├── utils.py                # 工具函数 (SHM, Bitmap)
├── components/             # 核心组件
│   ├── executor.py         # 测试执行组件
│   ├── monitor.py          # 执行结果监控组件
│   ├── mutator.py          # 变异组件
│   ├── scheduler.py        # 种子调度 + 能量调度组件
│   └── evaluator.py        # 评估组件
├── tests/                  # 单元测试
├── docs/                   # 文档
│   ├── DESIGN.md           # 设计文档
│   └── CODE_ANALYSIS.md    # 代码分析
├── Dockerfile              # 容器配置
├── docker-compose.yml      # Docker Compose 配置
└── README.md               # 本文件
```

---

## 📝 文档

- **[docs/DESIGN.md](docs/DESIGN.md)** - 系统设计文档（过程报告）
- **[docs/CODE_ANALYSIS.md](docs/CODE_ANALYSIS.md)** - 代码分析文档

---

## 🐳 Docker 使用

### 开发模式（推荐）

```bash
# 启动容器
docker-compose up -d fuzzer

# 进入容器
docker-compose exec fuzzer bash

# 在容器内运行测试
python3 fuzzer.py \
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

编辑 `config.py` 可调整：

*   **`timeout`**：单次执行超时时间（秒）。
*   **`bitmap_size`**：覆盖率位图大小（默认 65536）。
*   **`max_file_size`**：种子文件最大尺寸（字节）。
*   **`coverage_update_interval`**：统计更新间隔（执行次数）。

---

## 📚 参考资源

*   **AFL++**：https://github.com/AFLplusplus/AFLplusplus
*   **AFL 论文**：*American Fuzzy Lop: A Security-Oriented Fuzzer* (Michał Zalewski, 2014)
*   **FairFuzz 论文**：*FairFuzz: A Targeted Mutation Strategy for Increasing Greybox Fuzz Testing Coverage* (ASE 2018)
*   **AFLGo 论文**：*Directed Greybox Fuzzing* (CCS 2017)

---

## 📄 许可证

本项目仅供学习和研究使用。

---

## 👤 作者

南京大学软件学院/智软学院 - 软件测试课程大作业
