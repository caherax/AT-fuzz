#!/bin/bash
# 运行所有测试的脚本

set -e

cd "$(dirname "$0")/.."

echo "========================================="
echo "  Running AT-Fuzz Test Suite"
echo "========================================="
echo ""

# 设置 Python 路径
export PYTHONPATH="$(pwd):$PYTHONPATH"

# 运行各个测试模块
echo "[1/4] Testing utils.py..."
python3 tests/test_utils.py -v

echo ""
echo "[2/4] Testing executor.py..."
python3 tests/test_executor.py -v

echo ""
echo "[3/4] Testing mutator.py..."
python3 tests/test_mutator.py -v

echo ""
echo "[4/4] Running integration tests..."
python3 tests/test_integration.py -v

echo ""
echo "========================================="
echo "  All Tests Passed!"
echo "========================================="
