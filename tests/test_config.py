"""
测试配置系统的自动化功能
"""
import unittest
from config import CONFIG, CONFIG_SCHEMA, validate_config, apply_cli_args_to_config


class TestConfigSystem(unittest.TestCase):
    """测试配置系统"""

    def test_config_schema_completeness(self):
        """测试 CONFIG_SCHEMA 包含所有必要字段"""
        for key, meta in CONFIG_SCHEMA.items():
            self.assertIsNotNone(meta.type, f"{key} missing type")
            self.assertIsNotNone(meta.validator, f"{key} missing validator")
            self.assertIsNotNone(meta.description, f"{key} missing description")
            self.assertIsNotNone(meta.cli_name, f"{key} missing cli_name")
            self.assertIsNotNone(meta.cli_help, f"{key} missing cli_help")

            # CLI name 应该以 -- 开头
            self.assertTrue(meta.cli_name.startswith('--'),
                          f"{key} cli_name should start with --")


    def test_config_keys_consistency(self):
        """测试 CONFIG 和 CONFIG_SCHEMA 的键一致"""
        schema_keys = set(CONFIG_SCHEMA.keys())
        config_keys = set(CONFIG.keys())

        self.assertEqual(schema_keys, config_keys,
                        f"Mismatch between CONFIG_SCHEMA and CONFIG keys.\n"
                        f"Missing in CONFIG: {schema_keys - config_keys}\n"
                        f"Extra in CONFIG: {config_keys - schema_keys}")


    def test_validate_config_catches_type_errors(self):
        """测试验证函数能捕获类型错误"""
        bad_config = CONFIG.copy()
        bad_config['timeout'] = "not a float"  # 应该是 float

        errors = validate_config(bad_config)
        self.assertTrue(len(errors) > 0, "Should catch type error")
        self.assertTrue(any('timeout' in err for err in errors))

    def test_validate_config_catches_value_errors(self):
        """测试验证函数能捕获值错误"""
        bad_config = CONFIG.copy()
        bad_config['timeout'] = -1.0  # 应该 > 0

        errors = validate_config(bad_config)
        self.assertTrue(len(errors) > 0, "Should catch value validation error")
        self.assertTrue(any('timeout' in err for err in errors))

    def test_apply_cli_args_to_config(self):
        """测试命令行参数应用到 CONFIG"""
        from argparse import Namespace

        # 保存原始 CONFIG
        original_timeout = CONFIG['timeout']

        try:
            # 模拟命令行参数
            args = Namespace()
            args.timeout = 5.0
            args.mem_limit = None  # 未指定，不应覆盖

            # 为所有其他参数设置 None
            for key in CONFIG_SCHEMA.keys():
                if not hasattr(args, key):
                    setattr(args, key, None)

            # 应用
            apply_cli_args_to_config(args)

            # 验证
            self.assertEqual(CONFIG['timeout'], 5.0, "Should apply CLI arg")

        finally:
            # 恢复原始值
            CONFIG['timeout'] = original_timeout

    def test_cli_choices_for_enum_types(self):
        """测试枚举类型配置有 choices 定义"""
        # seed_sort_strategy 应该有 choices
        meta = CONFIG_SCHEMA['seed_sort_strategy']
        self.assertIsNotNone(meta.cli_choices,
                            "Enum config should have cli_choices")
        self.assertEqual(set(meta.cli_choices), {'energy', 'fifo'})

        # 验证当前值在 choices 中
        current_value = CONFIG['seed_sort_strategy']
        self.assertIn(current_value, meta.cli_choices)

    def test_bool_config_handling(self):
        """测试布尔类型配置"""
        meta = CONFIG_SCHEMA['use_sandbox']
        self.assertEqual(meta.type, bool)
        self.assertIsInstance(CONFIG['use_sandbox'], bool)


class TestConfigValidation(unittest.TestCase):
    """测试配置验证逻辑"""

    def test_numeric_range_validation(self):
        """测试数值范围验证"""
        # timeout 应该 > 0
        meta = CONFIG_SCHEMA['timeout']
        self.assertTrue(meta.validator(1.0))
        self.assertFalse(meta.validator(0.0))
        self.assertFalse(meta.validator(-1.0))

    def test_enum_validation(self):
        """测试枚举值验证"""
        meta = CONFIG_SCHEMA['seed_sort_strategy']
        self.assertTrue(meta.validator('energy'))
        self.assertTrue(meta.validator('fifo'))
        self.assertFalse(meta.validator('invalid'))


if __name__ == '__main__':
    unittest.main()
