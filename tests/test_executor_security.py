import unittest
import os
import time
import subprocess
from components.executor import TestExecutor

class TestExecutorSecurity(unittest.TestCase):
    def setUp(self):
        self.test_scripts = []

    def tearDown(self):
        for script in self.test_scripts:
            if os.path.exists(script):
                os.remove(script)

    def create_script(self, content):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.sh') as f:
            f.write(content)
            script_path = f.name
        os.chmod(script_path, 0o755)
        self.test_scripts.append(script_path)
        return script_path

    def test_process_leakage(self):
        """测试子进程是否被正确清理（防止孤儿进程）"""
        # 创建一个会生成后台进程的脚本 (模拟 T08 行为)
        # sleep 5 in background
        script_content = b"""#!/bin/sh
sleep 5 &
echo "Parent done"
"""
        script_path = self.create_script(script_content)

        # 启动执行器 (非沙箱模式便于更容易检测，或者沙箱模式下 bwrap --unshare-pid 应该也能清理)
        # 无论是否沙箱，目标是确保 execute 返回后没有残留
        # 为了测试 executor.py 的 finally 块逻辑，我们先测试无沙箱模式（因为 bwrap 会隔离 pid，使得 pgrep 查不到）
        # 但是如果启用了沙箱，我们也希望沙箱内清理干净。
        # 这里主要测试 executor.py Python 层的清理逻辑。

        # 强制禁用沙箱进行本测试，以验证 os.killpg 逻辑
        # (如果开启沙箱，进程在 namespace 里，pgrep 可能看不到，或者 killpg 杀的是 bwrap)

        # 保存原配置
        from config import CONFIG
        original_sandbox = CONFIG.get('use_sandbox')
        CONFIG['use_sandbox'] = False

        try:
            executor = TestExecutor(script_path, script_path, timeout=1)

            # 记录当前系统中的 sleep 进程数量
            try:
                initial_sleeps = int(subprocess.check_output("pgrep -c sleep || true", shell=True).strip() or 0)
            except:
                initial_sleeps = 0

            # 执行
            executor.execute(b"")

            # 稍作等待确保信号专递
            time.sleep(0.5)

            # 检查是否有新的 sleep 进程残留
            try:
                current_sleeps = int(subprocess.check_output("pgrep -c sleep || true", shell=True).strip() or 0)
            except:
                current_sleeps = 0

            # 恢复配置
            CONFIG['use_sandbox'] = original_sandbox

            print(f"[Test] Initial sleeps: {initial_sleeps}, Current sleeps: {current_sleeps}")
            self.assertLessEqual(current_sleeps, initial_sleeps, "Found leaked background processes (sleep)!")

        finally:
            CONFIG['use_sandbox'] = original_sandbox
            if 'executor' in locals():
                executor.cleanup()

    def test_infinite_loop_timeout(self):
        """测试无限循环是否能被 Timeout 正确终止"""
        script_content = b"""#!/bin/sh
while true; do
    echo "looping"
    sleep 0.1
done
"""
        script_path = self.create_script(script_content)

        try:
            executor = TestExecutor(script_path, script_path, timeout=1) # 1秒超时
            start = time.time()
            result = executor.execute(b"")
            duration = time.time() - start

            self.assertTrue(result['timeout'], "Should have timed out")
            self.assertAlmostEqual(duration, 1.0, delta=1.5, msg="Execution time should be close to timeout")

        finally:
             if 'executor' in locals():
                executor.cleanup()

if __name__ == '__main__':
    unittest.main()
