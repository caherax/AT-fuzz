#!/bin/bash
# 统一的测试目标运行脚本
# 用法: run_target.sh T01
# 支持 Docker 容器和本地环境自动适配

set -e

# 自动检测运行环境
if [ -d "/fuzzer" ]; then
    # Docker 容器环境
    PROJECT_ROOT="/fuzzer"
    EXAMPLES_DIR="/fuzzer/examples"
else
    # 本地环境 - 使用脚本所在目录
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    EXAMPLES_DIR="$SCRIPT_DIR"
fi

# 设置 AFL++ 编译器
export CC="${AFLPP:-/usr/bin}/afl-cc"
export CXX="${AFLPP:-/usr/bin}/afl-c++"

# 修复 Docker 环境中可能的错误环境变量配置
unset AFL_CC
unset AFL_CXX

TARGET_ID=$1
FORCE_REBUILD=$2
WORK_DIR="/tmp/fuzz_work"

# 根据 TARGET_ID 决定使用哪个目录
case $TARGET_ID in
    T01|T02|T03|T04)
        # binutils 系列（T01-T04）使用共享目录，避免重复构建
        BUILD_DIR="$WORK_DIR/build/binutils-2.28"
        INSTALL_DIR="$WORK_DIR/install/binutils-2.28"
        ;;
    *)
        # 其他目标使用独立目录
        BUILD_DIR="$WORK_DIR/build/$TARGET_ID"
        INSTALL_DIR="$WORK_DIR/install/$TARGET_ID"
        ;;
esac

# 检查是否强制重新构建（仅清理当前目标对应的目录）
if [ "$FORCE_REBUILD" = "clean" ]; then
    echo "[!] 强制清理（clean）: 移除 $BUILD_DIR 和 $INSTALL_DIR"
    rm -rf "$BUILD_DIR" "$INSTALL_DIR"
    echo "[+] 清理完成"
    exit 0
fi
if [ "$FORCE_REBUILD" == "rebuild" ]; then
    echo "[!] 强制重新构建 $TARGET_ID: 清理 $BUILD_DIR 和 $INSTALL_DIR"
    rm -rf "$BUILD_DIR" "$INSTALL_DIR"
fi

# 构建 binutils 的通用函数（T01-T04 共享）
build_binutils() {
    echo "构建 binutils（共享构建，供 T01-T04 使用）..."
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"
    
    # 只在未解压时解压
    if [ ! -d "binutils-2.28" ]; then
        tar -xzf "$EXAMPLES_DIR/sources/binutils-2.28.tar.gz"
    fi
    
    cd binutils-2.28

    ./configure --disable-shared --prefix="$INSTALL_DIR"

    make -j$(nproc)
    make install
    
    echo "[+] binutils 构建完成，所有工具安装在 $INSTALL_DIR/bin/"
}

# 目标特定的 fuzzer 参数（默认空；各 target 在 case 中覆盖）
EXTRA_PARAMS=""

# 测试目标配置
case $TARGET_ID in
    T01)
        TARGET_NAME="cxxfilt"
        PROJECT="binutils-2.28"
        BINARY="$INSTALL_DIR/bin/c++filt"
        ARGS="$BINARY"
        # 名称解析/解混淆：输入通常非常短，限制 seed 规模避免无意义膨胀
        EXTRA_PARAMS="--timeout 0.5 --havoc-iterations 10 --max-seed-size 1024"

        # 构建（T01-T04 共享一次 binutils 构建）
        if [ ! -f "$BINARY" ]; then
            build_binutils
        fi

        # 种子目录（直接使用原始路径，无需复制）
        if [ -d "$EXAMPLES_DIR/seeds/T01" ]; then
            SEEDS_DIR="$EXAMPLES_DIR/seeds/T01"
        else
            echo "[!] Warning: Seeds directory not found, using empty seed"
            SEEDS_DIR="/tmp/empty_seeds"
            mkdir -p "$SEEDS_DIR"
        fi
        ;;

    T02)
        TARGET_NAME="readelf"
        PROJECT="binutils-2.28"
        BINARY="$INSTALL_DIR/bin/readelf"
        ARGS="$BINARY -a @@"
        # ELF 分析：常见为二进制文件（KB~MB），适当放宽超时与 seed 上限
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 16 --max-seed-size $((512 * 1024))"

        # 构建（共享 binutils，已由 T01 构建则跳过）
        if [ ! -f "$BINARY" ]; then
            build_binutils
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T02" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T02" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T03)
        TARGET_NAME="nm"
        PROJECT="binutils-2.28"
        BINARY="$INSTALL_DIR/bin/nm"
        ARGS="$BINARY @@"
        # 符号表工具：一般比 objdump 快，但仍可能吃较大对象文件
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 14 --max-seed-size $((512 * 1024))"

        # 构建（共享 binutils，已由 T01 构建则跳过）
        if [ ! -f "$BINARY" ]; then
            build_binutils
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T03" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T03" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T04)
        TARGET_NAME="objdump"
        PROJECT="binutils-2.28"
        BINARY="$INSTALL_DIR/bin/objdump"
        ARGS="$BINARY -d @@"
        # 反汇编：最慢/最重，超时需要更宽松
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 16 --max-seed-size $((512 * 1024))"

        # 构建（共享 binutils，已由 T01 构建则跳过）
        if [ ! -f "$BINARY" ]; then
            build_binutils
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T04" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T04" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T05)
        TARGET_NAME="djpeg"
        PROJECT="libjpeg-turbo-3.0.4"
        BINARY="$INSTALL_DIR/bin/djpeg"
        ARGS="$BINARY @@"
        # JPEG 解码：结构化输入，偏向更强变异但限制文件大小（避免巨图拖慢）
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 20 --max-seed-size $((512 * 1024))"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            echo "构建 libjpeg-turbo..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/libjpeg-turbo-3.0.4.tar.gz"
            cd libjpeg-turbo-3.0.4
            cmake -S . -B build -G "Unix Makefiles" \
                -DCMAKE_C_COMPILER="$CC" \
                -DCMAKE_CXX_COMPILER="$CXX" \
                -DCMAKE_INSTALL_PREFIX="$INSTALL_DIR"
            cd build
            make -j$(nproc)
            make install
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T05" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T05" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T06)
        TARGET_NAME="readpng"
        PROJECT="libpng-1.6.29"
        BINARY="$INSTALL_DIR/bin/readpng"
        ARGS="$BINARY"
        # PNG 解析：同样是结构化二进制，控制输入规模
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 20 --max-seed-size $((512 * 1024))"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            # 安装 libpng 构建依赖
            echo "Installing dependencies for libpng..."
            apt-get update -qq && apt-get install -y -qq zlib1g-dev >/dev/null 2>&1 || true

            echo "构建 libpng..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/libpng-1.6.29.tar.gz"
            cd libpng-1.6.29

            # 使用普通编译器构建 libpng 库（不插桩）
            CC=gcc CXX=g++ ./configure --disable-shared
            make clean
            make -j$(nproc)

            # 只对 readpng.c 插桩，直接链接静态库
            echo "Compiling readpng with $CC..."
            $CC -o readpng ./contrib/libtests/readpng.c ./.libs/libpng16.a -lz -lm

            cp readpng "$INSTALL_DIR/bin/"
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T06" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T06" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T07)
        TARGET_NAME="xmllint"
        PROJECT="libxml2-2.13.4"
        BINARY="$INSTALL_DIR/bin/xmllint"
        ARGS="$BINARY @@"
        # XML：文本格式，过强的插入/删除会迅速破坏结构；适中变异 + 中等输入上限
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 14 --max-seed-size $((512 * 1024))"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            echo "构建 libxml2..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/libxml2-2.13.4.tar.gz"
            cd libxml2-2.13.4

            # 检查是否需要运行 autogen.sh
            if [ ! -f configure ]; then
                echo "Running autogen.sh..."
                ./autogen.sh --disable-shared --prefix="$INSTALL_DIR"
            fi

            ./configure --disable-shared --prefix="$INSTALL_DIR"

            make -j$(nproc)
            make install
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T07" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T07" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T08)
        TARGET_NAME="lua"
        PROJECT="lua-5.4.7"
        BINARY="$INSTALL_DIR/bin/lua"
        ARGS="$BINARY @@"
        # Lua：脚本通常较小，降低变异强度避免完全失去语法形态
        # 注意：Lua 测试/种子可能包含 os.execute/io.popen 等，建议默认启用沙箱隔离副作用
        EXTRA_PARAMS="--timeout 3.0 --havoc-iterations 10 --max-seed-size $((64 * 1024)) --use-sandbox"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            echo "构建 lua..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/lua-5.4.7.tar.gz"
            cd lua-5.4.7
            make linux CC="$CC" -j$(nproc)
            make install INSTALL_TOP="$INSTALL_DIR"
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T08" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T08" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T09)
        TARGET_NAME="mjs"
        PROJECT="mjs-2.20.0"
        BINARY="$INSTALL_DIR/bin/mjs"
        ARGS="$BINARY -f @@"
        # mJS：同 Lua，脚本输入不应太大
        EXTRA_PARAMS="--timeout 2.0 --havoc-iterations 10 --max-seed-size $((4 * 1024))"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            echo "构建 mjs..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/mjs-2.20.0.tar.gz"
            cd mjs-2.20.0

            # 使用 amalgamated file 直接编译（更简单可靠）
            echo "Compiling mjs.c with $CC..."
            $CC -DMJS_MAIN mjs.c -ldl -g -o mjs

            cp mjs "$INSTALL_DIR/bin/"
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T09" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T09" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    T10)
        TARGET_NAME="tcpdump"
        PROJECT="tcpdump-tcpdump-4.99.5"
        BINARY="$INSTALL_DIR/bin/tcpdump"
        ARGS="$BINARY -nr @@"
        # PCAP：协议结构复杂，适当增加变异；输入可能较大
        EXTRA_PARAMS="--timeout 3.0 --havoc-iterations 18 --max-seed-size $((512 * 1024))"

        # 构建（独立项目）
        mkdir -p "$BUILD_DIR" "$INSTALL_DIR/bin"
        if [ ! -f "$BINARY" ]; then
            # 安装 tcpdump 构建依赖
            echo "Installing dependencies for tcpdump..."
            apt-get update -qq && apt-get install -y -qq libpcap-dev >/dev/null 2>&1 || true

            echo "构建 tcpdump..."
            cd "$BUILD_DIR"
            tar -xzf "$EXAMPLES_DIR/sources/tcpdump-tcpdump-4.99.5.tar.gz"
            cd tcpdump-tcpdump-4.99.5
            if [ ! -f configure ]; then
                echo "Running autogen.sh..."
                ./autogen.sh --disable-shared --prefix="$INSTALL_DIR"
            fi
            ./configure --disable-shared --prefix="$INSTALL_DIR"
            make -j$(nproc)
            make install
        fi

        # 种子目录
        [ -d "$EXAMPLES_DIR/seeds/T10" ] && SEEDS_DIR="$EXAMPLES_DIR/seeds/T10" || SEEDS_DIR="/tmp/empty_seeds"
        ;;

    *)
        echo "错误: 未知的目标 ID: $TARGET_ID"
        exit 1
        ;;
esac

# 验证构建
if [ ! -f "$BINARY" ]; then
    echo "错误: 构建失败，找不到 $BINARY"
    exit 1
fi

echo "目标: $TARGET_NAME"
echo "二进制: $BINARY"
echo "参数: $ARGS"
echo "种子: $SEEDS_DIR"

# 生成带时间戳和序号的输出目录
DATE=$(date +%Y%m%d)
OUTPUT_BASE="$PROJECT_ROOT/output/${TARGET_ID}_${TARGET_NAME}_${DATE}"
OUTPUT_DIR="${OUTPUT_BASE}_1"
COUNTER=1

# 如果目录已存在，递增序号
while [ -d "$OUTPUT_DIR" ]; do
    COUNTER=$((COUNTER + 1))
    OUTPUT_DIR="${OUTPUT_BASE}_${COUNTER}"
done

echo "输出目录: $OUTPUT_DIR"

# 设置运行时间（默认 24 小时，可通过环境变量 FUZZ_DURATION 覆盖）
DURATION=${FUZZ_DURATION:-86400}

# 可选：外部提供检查点目录或恢复文件
CHECKPOINT_PATH=${CHECKPOINT_PATH:-}
RESUME_FROM=${RESUME_FROM:-}

# 运行模糊测试
cd "$PROJECT_ROOT"
CMD=(python3 -u fuzzer.py
    --target "$BINARY"
    --args "$ARGS"
    --seeds "$SEEDS_DIR"
    --output "$OUTPUT_DIR"
    --target-id "$TARGET_ID"
    --duration "$DURATION"
)

# 附加 checkpoint 参数（如有）
if [ -n "$CHECKPOINT_PATH" ]; then
    CMD+=(--checkpoint-path "$CHECKPOINT_PATH")
fi
if [ -n "$RESUME_FROM" ]; then
    CMD+=(--resume-from "$RESUME_FROM")
fi

# 追加目标特定参数
if [ -n "$EXTRA_PARAMS" ]; then
    EXTRA_ARR=($EXTRA_PARAMS)
    CMD+=("${EXTRA_ARR[@]}")
fi

echo "Running: ${CMD[*]}"
"${CMD[@]}"
