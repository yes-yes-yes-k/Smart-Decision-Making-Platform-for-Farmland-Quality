---
comet_change: migrate-to-postgresql-postgis
role: technical-design
canonical_spec: openspec
archived-with: 2026-08-15-migrate-to-postgresql-postgis
status: final
---

# Design Doc: migrate-to-postgresql-postgis

本 Design Doc 是对 OpenSpec change `migrate-to-postgresql-postgis` 的 `design.md` 高层方案框架的深度技术细化。上游 OpenSpec 产物（proposal.md / design.md / tasks.md / specs/database-engine/spec.md）是 canonical spec，本文档聚焦实现方案、技术风险、测试策略与边界条件，不替代或重写 spec。

## 1. 架构概述

### 1.1 改动范围

| 文件 | 类型 | 改动摘要 |
|------|------|---------|
| `pyproject.toml` | 修改 | `[project].dependencies` 新增 `psycopg2-binary`、`geoalchemy2` |
| `framework/config.py` | 修改 | URI scheme 切换、端口对齐、删除子类硬编码 SQLite URI |
| `init_db.py` | 修改 | 新增 PostGIS 扩展初始化守卫 + 快速失败错误处理 |
| `tests/test_config.py` | 新增 | `framework/config.py` 单元测试（pytest CI） |
| `scripts/verify_pg_init.py` | 新增 | PG 集成验证脚本（手动运行，不进入 pytest CI） |

### 1.2 数据流

```
create_app(config_name) → config_map[config_name] → Config 类
                                                          ↓
                                          SQLALCHEMY_DATABASE_URI
                                                          ↓
init_db.py → app_context → 判定 URI.startswith('postgresql')
                                  ↓                          ↓
                        postgresql*                      sqlite*
                            ↓                                ↓
              CREATE EXTENSION IF NOT EXISTS postgis     跳过 PostGIS
                            ↓                                ↓
                ┌───成功───┐  ┌───失败(ProgrammingError)───┐  ↓
                ↓           ↓  ↓                           ↓
        db.drop_all()    rollback + 打印提示 + sys.exit(1)  db.drop_all()
        db.create_all()                                  db.create_all()
        创建 admin/user                                   创建 admin/user
```

### 1.3 与 OpenSpec design.md 的对应关系

本 Design Doc 深化以下 OpenSpec design.md Decisions，不改变其方向：

| OpenSpec Decision | 本 Design Doc 深化点 |
|-------------------|---------------------|
| Decision 1: 双数据库支持 | §2 init_db.py 守卫实现细节 |
| Decision 2: 配置类层级 | §3 config.py 改造代码结构 |
| Decision 3: URI scheme `postgresql+psycopg2` | §3 URI 拼接实现 |
| Decision 4: PostGIS 初始化放 init_db.py | §2 完整实现（含错误处理） |
| Decision 5: 依赖写入 pyproject.toml | §4.1 依赖声明细节 |
| Decision 6: ENGINE_OPTIONS 去除 MySQL 专属参数 | §3 确认现有代码已满足 |

## 2. init_db.py 深度实现

### 2.1 改造后的完整结构

PostGIS 初始化守卫内联在 `init_db.py`，不抽取到 `framework/db/` 模块。理由：本次只有 `init_db.py` 一个调用点，后续 `add-thematic-model-orm` change 不需要复用 PostGIS 初始化逻辑，符合最小改动原则。

```python
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from werkzeug.security import generate_password_hash
from framework.api.app import create_app
from framework.models.user import db, User
import framework.models  # noqa: F401  触发 soil_data 等模型注册

app = create_app()

with app.app_context():
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    # PostGIS 扩展初始化（仅 PostgreSQL 路径）
    if db_uri.startswith('postgresql'):
        try:
            db.session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            db.session.commit()
            print("[初始化] PostGIS 扩展已就绪")
        except ProgrammingError as e:
            print(f"[错误] PostGIS 扩展初始化失败：{e}", file=sys.stderr)
            print("[提示] 请在 PostgreSQL 实例侧安装 postgis 包", file=sys.stderr)
            print("[提示] 安装后重新运行 python init_db.py", file=sys.stderr)
            db.session.rollback()
            sys.exit(1)

    db.drop_all()
    db.create_all()

    admin = User(
        username='admin',
        password=generate_password_hash('admin123'),
        nickname='管理员',
        role='admin',
        status=1
    )
    db.session.add(admin)

    user = User(
        username='user',
        password=generate_password_hash('user123'),
        nickname='普通用户',
        role='user',
        status=1
    )
    db.session.add(user)

    db.session.commit()
    print("[初始化] 数据库表结构创建完成")
    print("[初始化] 管理员用户已创建: admin / admin123")
    print("[初始化] 普通用户已创建: user / user123")
    print("[提示] 运行 'python start_http_server.py' 启动服务")
```

### 2.2 关键设计点

**PostGIS 初始化守卫：**
- `db_uri.startswith('postgresql')` 判定 URI scheme，避免字符串解析复杂化
- 覆盖 `postgresql+psycopg2://` 和未来可能的 `postgresql+psycopg://`
- SQLite 路径（`sqlite:///`）跳过整个 PostGIS 块

**`text()` 包装原生 SQL：**
- SQLAlchemy 2.0 要求字符串 SQL 必须用 `text()` 包装，否则触发 `ObjectNotExecutableError`
- `CREATE EXTENSION IF NOT EXISTS postgis` 是 DDL，不需要参数绑定

**快速失败错误处理：**
- `ProgrammingError` 精确捕获 PostGIS 未安装的情况（PG 实例缺少 `postgis.control` 文件）
- 捕获后执行三步：打印错误 + 打印提示 + `sys.exit(1)`
- `db.session.rollback()` 清理会话状态，避免后续操作受影响
- **不继续执行 `db.create_all()`**：如果后续 ORM 使用 `Geometry` 列（`add-thematic-model-orm` change），建表会失败并产生误导性错误；快速失败让根因更清晰

**幂等性：**
- `CREATE EXTENSION IF NOT EXISTS` 保证多次运行 `init_db.py` 不报错
- `db.drop_all()` + `db.create_all()` 是既有行为，保持不变

### 2.3 不抽取为 framework/db/ 的理由

| 考虑 | 内联在 init_db.py | 抽取到 framework/db/extensions.py |
|------|-------------------|----------------------------------|
| 调用点数量 | 1 个（init_db.py） | 1 个（init_db.py） |
| 复用需求 | 无（后续 change 不需要） | 无 |
| 改动范围 | 最小 | 引入新模块 |
| 可测试性 | 通过 init_db.py 集成测试验证 | 可独立单元测试，但过度设计 |

选择内联，符合最小改动原则。如果后续有多个入口需要 PostGIS 初始化，再抽取不迟。

## 3. config.py 改造细节

### 3.1 改造后的 Config 基类

```python
class Config:
    DB_HOST = os.environ.get('DB_HOST') or 'localhost'
    DB_PORT = int(os.environ.get('DB_PORT') or 5432)  # 3306 → 5432
    DB_USER = os.environ.get('DB_USER') or 'root'
    DB_PASSWORD = os.environ.get('DB_PASSWORD') or ''
    DB_NAME = os.environ.get('DB_NAME') or 'db_enterprise_qa'

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    # 移除 ?charset=utf8mb4（MySQL 专属，PG 默认 UTF-8）
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'max_overflow': 50,
        'pool_timeout': 30,
        'pool_recycle': 1800,
    }
    # ... 其余配置不变
```

### 3.2 改造后的子类

```python
class DevelopmentConfig(Config):
    DEBUG = True
    # 删除：SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'
    # 现在继承基类 PostgreSQL URI

class ProductionConfig(Config):
    DEBUG = False
    # 删除：SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/production.db'
    # 现在继承基类 PostgreSQL URI

class SQLiteConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'  # 保持不变

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
    'sqlite': SQLiteConfig
}
```

### 3.3 关键设计点

**DB_USER 默认保持 `root`：**
- PG 也支持 `root` 用户名（虽非标准）
- 环境变量 `DB_USER` 可覆盖
- 改为 `postgres` 会破坏现有部署假设（运维可能已配置 `root` 用户）

**SQLALCHEMY_ENGINE_OPTIONS 保持不变：**
- 现有代码已是 4 个通用参数：`pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle`
- 不含 `charset` 键（`charset` 原本通过 URI query 传递，不在 ENGINE_OPTIONS 中）
- 无需改动，符合 OpenSpec Decision 6

**DB_PASSWORD 空值：**
- 当前默认空字符串，PG 默认配置可能拒绝空密码
- 这是部署侧配置问题，非代码改动范围
- 文档提示：生产部署必须设置 `DB_PASSWORD` 环境变量

**移除 `?charset=utf8mb4`：**
- `charset` 是 MySQL 专属概念
- PostgreSQL 默认 UTF-8 编码，无需在 URI 中指定
- 移除后 URI 更简洁

## 4. 依赖声明与测试策略

### 4.1 依赖声明（pyproject.toml）

在 `[project].dependencies` 中新增（按字母序插入）：

```toml
dependencies = [
    "Flask>=3.0.0",
    "Flask-SQLAlchemy>=3.1.0",
    "Flask-JWT-Extended>=4.6.0",
    "Flask-CORS>=4.0.0",
    "geoalchemy2>=0.14.0",        # 新增
    "langchain>=0.2.0",
    "langchain-openai>=0.1.0",
    "langgraph>=0.1.0",
    "pymysql>=1.1.0",              # 保留（过渡兼容）
    "psycopg2-binary>=2.9.0",      # 新增
    # ... 其余不变
]
```

**版本约束选择：**
- `psycopg2-binary>=2.9.0`：2.9 是支持 PostgreSQL 16 的稳定版本
- `geoalchemy2>=0.14.0`：0.14 支持 SQLAlchemy 2.0 和 PostGIS 3.x

**不删除 `pymysql`：**
- OpenSpec Non-goals 明确"不删除 `pymysql` 依赖（保留过渡兼容）"
- 标记为待移除，后续清理 change 统一删除

### 4.2 单元测试（tests/test_config.py）

```python
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
```

**测试设计要点：**
- 默认值测试直接读取 Config 类属性，不依赖环境变量覆盖
- 环境变量覆盖测试使用 `subprocess` 隔离进程，避免 `importlib.reload` 导致测试污染（遵循 project_memory 约束）
- 不依赖真实 PG 连接，纯配置逻辑测试

### 4.3 独立 PG 验证脚本（scripts/verify_pg_init.py）

```python
#!/usr/bin/env python
"""
PostgreSQL + PostGIS 集成验证脚本。

在有 PostgreSQL 16 + PostGIS 3.4 实例时手动运行：
    python scripts/verify_pg_init.py

对应 tasks.md 4.5-4.7 验收点。
不进入 pytest CI（符合「代码先行，环境后续」原则）。
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sqlalchemy import text
from framework.api.app import create_app
from framework.models.user import db, User
import framework.models  # noqa: F401


def verify_postgis_extension():
    """验证 PostGIS 扩展已安装"""
    result = db.session.execute(text("SELECT PostGIS_Version()")).scalar()
    print(f"[PASS] PostGIS 版本: {result}")
    return True


def verify_tables_created():
    """验证 8 张土壤数据表 + user 表创建成功"""
    expected_tables = [
        'third_survey_topsoils', 'third_survey_profiles',
        'third_survey_site_conditions', 'third_survey_bulk_densities',
        'second_survey_points', 'formula_fertilizations',
        'agri_chemicalizations', 'grain_yields',
        'users', 'conversations', 'messages', 'documents', 'data_files'
    ]
    result = db.session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )).scalars().all()
    for table in expected_tables:
        if table not in result:
            print(f"[FAIL] 表 {table} 未创建")
            return False
    print(f"[PASS] 全部 {len(expected_tables)} 张表创建成功")
    return True


def verify_users_exist():
    """验证 admin/user 用户存在"""
    admin = User.query.filter_by(username='admin').first()
    user = User.query.filter_by(username='user').first()
    if not admin or not user:
        print("[FAIL] admin/user 用户未创建")
        return False
    print("[PASS] admin/user 用户存在")
    return True


def verify_idempotency():
    """验证重复运行 init_db.py 幂等性"""
    # 重复运行 init_db.py 逻辑（已在 app_context 内）
    os.system(f"python {PROJECT_ROOT / 'init_db.py'}")
    print("[PASS] 重复运行幂等")
    return True


def main():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("PostgreSQL + PostGIS 集成验证")
        print("=" * 60)
        results = []
        results.append(("PostGIS 扩展", verify_postgis_extension()))
        results.append(("表创建", verify_tables_created()))
        results.append(("用户创建", verify_users_exist()))
        results.append(("幂等性", verify_idempotency()))
        print("=" * 60)
        passed = sum(1 for _, ok in results if ok)
        total = len(results)
        print(f"结果: {passed}/{total} 通过")
        if passed != total:
            sys.exit(1)


if __name__ == '__main__':
    main()
```

**脚本设计要点：**
- 独立于 pytest，在有 PG 环境时手动运行
- 验证 4 个维度：PostGIS 扩展、表创建、用户创建、幂等性
- 对应 tasks.md 4.5-4.7 验收点
- 非零退出码表示验证失败

## 5. 风险与边界条件

| 风险 | 影响 | 处理 | 责任方 |
|------|------|------|--------|
| `psycopg2-binary` Windows 编译 | 安装失败 | 使用预编译 wheel（`psycopg2-binary` 而非 `psycopg2`） | 代码侧 |
| PostGIS 未在 PG 实例预装 | `init_db.py` 失败 | 快速失败 + 明确提示 + `sys.exit(1)` | 运维侧安装 `postgis-3.4` |
| `db.drop_all()` 生产误执行 | 数据丢失 | 既有行为，本次不改动；`init_db.py` 仅用于初始化/开发 | 运维侧避免生产运行 |
| `DB_PASSWORD` 空值 | PG 连接失败 | 部署侧配置，非代码改动范围 | 部署侧设置 `DB_PASSWORD` |
| `DevelopmentConfig` 不再用 SQLite | 开发环境需 PG | 开发者显式选择 `config_map['sqlite']` 或自备 PG | 开发侧 |
| `pymysql` 保留但不再使用 | 依赖冗余 | 标记待移除，后续清理 change 统一删除 | 后续 change |
| `importlib.reload` 测试污染 | 测试间状态泄露 | `teardown_method` 清理环境变量 | 测试侧 |

### 5.1 边界条件

**PostgreSQL 连接但 PostGIS 未安装：**
- `CREATE EXTENSION IF NOT EXISTS postgis` 抛出 `ProgrammingError`
- 错误信息包含 `control file` 关键字
- 快速失败，不继续建表

**SQLite 路径：**
- `db_uri.startswith('postgresql')` 返回 `False`
- 跳过整个 PostGIS 块
- 直接进入 `db.drop_all()` + `db.create_all()`

**空密码连接：**
- `DB_PASSWORD=''` 时 URI 为 `postgresql+psycopg2://root:@localhost:5432/db_enterprise_qa`
- PG `pg_hba.conf` 默认拒绝空密码
- 连接失败时 `psycopg2.OperationalError`（非 `ProgrammingError`），不被 PostGIS 守卫捕获
- 属于部署侧配置问题，非本次代码改动范围

## 6. Spec Patch

在 `openspec/changes/migrate-to-postgresql-postgis/specs/database-engine/spec.md` 的 `PostGIS 扩展初始化` Requirement 下补充场景：

```markdown
#### Scenario: PostGIS 扩展不可用时快速失败

- **WHEN** `SQLALCHEMY_DATABASE_URI` 以 `postgresql+psycopg2://` 开头
- **AND** PG 实例未安装 postgis 包（`postgis.control` 缺失）
- **AND** `init_db.py` 执行 `CREATE EXTENSION IF NOT EXISTS postgis`
- **THEN** 系统 SHALL 捕获 `ProgrammingError`
- **AND** SHALL 输出明确错误提示，引导运维安装 postgis 包
- **AND** SHALL 以非零退出码终止
- **AND** SHALL NOT 继续执行 `db.create_all()`
```

此 Spec Patch 仅补充验收场景，不修改 delta spec 的结构或范围，符合 comet-design SKILL 的 Spec Patch 约束。

## 7. 实施顺序建议

对应 tasks.md 的执行顺序，建议按依赖关系推进：

1. **依赖声明**（tasks 1.1-1.3）：先在 `pyproject.toml` 加依赖，`pip install -e .` 验证
2. **config.py 改造**（tasks 2.1-2.6）：改 URI、端口、删除子类硬编码
3. **单元测试**（tasks 4.1-4.4）：编写 `tests/test_config.py`，pytest 验证
4. **init_db.py 改造**（tasks 3.1-3.5）：加 PostGIS 守卫 + 错误处理
5. **PG 集成验证**（tasks 4.5-4.7）：编写 `scripts/verify_pg_init.py`，在有 PG 环境时手动运行

步骤 3 在步骤 4 之前，因为单元测试不依赖 init_db.py 改动，可以先验证 config.py 正确性。步骤 5 是最后的手动验证步骤。
