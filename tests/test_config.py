import os
import sys
import pytest
import subprocess

# 确保导入项目根的 framework.config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigBase:
    """Config 基类默认值测试（不依赖环境变量覆盖）"""

    def test_default_uri_uses_postgresql_scheme(self):
        from framework.config import Config
        assert Config.SQLALCHEMY_DATABASE_URI.startswith('postgresql+psycopg2://')

    def test_default_uri_not_contains_mysql(self):
        from framework.config import Config
        uri = Config.SQLALCHEMY_DATABASE_URI
        assert 'mysql+pymysql' not in uri
        assert 'charset=utf8mb4' not in uri

    def test_default_port_is_5432(self):
        from framework.config import Config
        assert Config.DB_PORT == 5432

    def test_comprehensive_workflow_defaults_off(self):
        from framework.config import Config
        assert Config.COMPREHENSIVE_WORKFLOW_MODE == 'off'


class TestEnvironmentOverride:
    """DB_* 环境变量覆盖测试

    使用 subprocess 隔离环境变量，避免 importlib.reload 导致测试污染
    （遵循 project_memory 约束：避免 reload Config 模块）。
    """

    def test_env_override_uri(self):
        env = {
            **os.environ,
            'DB_HOST': 'pg.example.com',
            'DB_PORT': '6543',
            'DB_USER': 'app',
            'DB_PASSWORD': 'secret',
            'DB_NAME': 'prod_db',
        }
        result = subprocess.run(
            [sys.executable, '-c',
             'from framework.config import Config; '
             'print(Config.SQLALCHEMY_DATABASE_URI)'],
            env=env, capture_output=True, text=True, cwd=os.getcwd()
        )
        assert result.returncode == 0
        assert result.stdout.strip() == 'postgresql+psycopg2://app:secret@pg.example.com:6543/prod_db'


class TestSQLiteConfig:
    """SQLiteConfig 降级路径测试"""

    def test_sqlite_uri(self):
        from framework.config import SQLiteConfig
        assert SQLiteConfig.SQLALCHEMY_DATABASE_URI.startswith('sqlite:///')

    def test_config_map_sqlite(self):
        from framework.config import config_map, SQLiteConfig
        assert config_map['sqlite'] is SQLiteConfig


class TestEngineOptions:
    """SQLALCHEMY_ENGINE_OPTIONS 测试"""

    def test_engine_options_has_generic_params(self):
        from framework.config import Config
        opts = Config.SQLALCHEMY_ENGINE_OPTIONS
        assert 'pool_size' in opts
        assert 'max_overflow' in opts
        assert 'pool_timeout' in opts
        assert 'pool_recycle' in opts

    def test_engine_options_no_charset(self):
        from framework.config import Config
        assert 'charset' not in Config.SQLALCHEMY_ENGINE_OPTIONS
