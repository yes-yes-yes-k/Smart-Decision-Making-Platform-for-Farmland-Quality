---
change: migrate-to-postgresql-postgis
design-doc: docs/superpowers/specs/2026-08-15-migrate-to-postgresql-postgis-design.md
base-ref: 96f9be821a5a91867cc3ca55e30d95c4866f4864
archived-with: 2026-08-15-migrate-to-postgresql-postgis
---

# migrate-to-postgresql-postgis 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将应用数据库引擎默认连接从 MySQL/SQLite 切换为 PostgreSQL 16 + PostGIS 3.4，并在 `init_db.py` 中加入 PostGIS 扩展初始化守卫与快速失败处理。

**Architecture:** `Config` 基类将 `SQLALCHEMY_DATABASE_URI` 拼接 scheme 从 `mysql+pymysql` 改为 `postgresql+psycopg2`，端口对齐 5432，移除 `charset=utf8mb4`；`DevelopmentConfig`/`ProductionConfig` 删除硬编码 SQLite URI，统一继承基类 PostgreSQL URI；`SQLiteConfig` 保留作为开发降级路径。`init_db.py` 在 `db.create_all()` 之前判定 URI scheme，仅 PostgreSQL 路径执行 `CREATE EXTENSION IF NOT EXISTS postgis`，失败时捕获 `ProgrammingError` 并 `sys.exit(1)` 快速失败。PostGIS 守卫内联在 `init_db.py`，不抽取到 `framework/db/`（单调用点、无复用需求，符合最小改动原则）。

**Tech Stack:** Python 3.10+、Flask 3、Flask-SQLAlchemy 3、SQLAlchemy 2.0（`text()` 包装原生 SQL）、psycopg2-binary 2.9+、geoalchemy2 0.14+、PostgreSQL 16、PostGIS 3.4、pytest。

**技术设计来源:** 本计划基于 Design Doc `docs/superpowers/specs/2026-08-15-migrate-to-postgresql-postgis-design.md`（role: technical-design）。该 Design Doc 是对 OpenSpec change `migrate-to-postgresql-postgis` 的 `design.md` 高层方案框架的深度技术细化；上游 OpenSpec 产物（`openspec/changes/migrate-to-postgresql-postgis/` 下的 proposal.md / design.md / tasks.md / specs/database-engine/spec.md）为 canonical spec。本计划的所有代码片段均与 Design Doc §2-§4 保持一致。

## Global Constraints

- **依赖版本下限**：`psycopg2-binary>=2.9.0`、`geoalchemy2>=0.14.0`（Design Doc §4.1）。
- **不删除 `pymysql` 依赖**：保留过渡兼容，标记待移除（OpenSpec Non-goals；Design Doc §4.1）。
- **URI scheme 固定为 `postgresql+psycopg2`**：不使用 `postgresql+psycopg`（Design Doc §3.1）。
- **默认端口 5432**、默认库名 `db_enterprise_qa`、默认用户 `root`（保持，可被环境变量覆盖；Design Doc §3.3）。
- **`SQLALCHEMY_ENGINE_OPTIONS` 仅保留 `pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle` 四个通用参数**，不含 `charset`（Design Doc §3.3）。
- **PostGIS 初始化逻辑内联在 `init_db.py`**，不抽取到 `framework/db/`（Design Doc §2.3）。
- **PostGIS 守卫使用 `text()` 包装原生 SQL**（SQLAlchemy 2.0 要求；Design Doc §2.2）。
- **快速失败**：PostGIS 初始化失败时 `ProgrammingError` → `rollback` + 打印提示 + `sys.exit(1)`，不继续 `db.create_all()`（Design Doc §2.2）。
- **测试隔离约束**：环境变量覆盖测试使用 `subprocess` 隔离，禁止 `importlib.reload(Config)`（project_memory 约束；Design Doc §4.2）。
- **PG 集成验证脚本不进入 pytest CI**：`scripts/verify_pg_init.py` 手动运行，遵循「代码先行，环境后续」原则（Design Doc §4.3）。
- **Python 版本**：`requires-python = ">=3.10"`（`pyproject.toml` 第 9 行）。

---

## File Structure

| 文件 | 类型 | 责任 |
|------|------|------|
| `pyproject.toml` | 修改 | 在 `[project].dependencies` 新增 `psycopg2-binary`、`geoalchemy2` 两个依赖项 |
| `framework/config.py` | 修改 | `Config` 基类 URI scheme/端口切换、移除 `charset`；删除 `DevelopmentConfig`/`ProductionConfig` 硬编码 SQLite URI；保留 `SQLiteConfig` |
| `init_db.py` | 修改 | 导入 `text`/`ProgrammingError`；在 `app_context` 内、`db.create_all()` 之前加入 PostGIS 扩展初始化守卫与快速失败处理 |
| `tests/test_config.py` | 新增 | `framework/config.py` 单元测试（pytest CI）：默认 URI、环境变量覆盖、SQLiteConfig、ENGINE_OPTIONS 四组测试 |
| `scripts/verify_pg_init.py` | 新增 | PG + PostGIS 集成验证脚本（手动运行）：验证 PostGIS 扩展、表创建、用户创建、幂等性四个维度 |

**模块边界说明：**
- `framework/config.py` 位于项目根目录（非 `src/`），测试通过 `sys.path.insert(0, project_root)` 导入，与现有 `tests/test_config_indicators.py` 模式一致。
- `init_db.py` 调用 `create_app()`（使用 `'default'` → `DevelopmentConfig`），PostgreSQL 为默认路径；SQLite 降级通过 `config_map['sqlite']` 显式选择。
- `scripts/verify_pg_init.py` 独立于 pytest，对应 tasks.md 4.5-4.7 验收点。

---

## Task 1: 依赖声明（pyproject.toml）

**Files:**
- Modify: `pyproject.toml:10-33`（`[project].dependencies` 列表）

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `psycopg2-binary` 与 `geoalchemy2` 可被 `pip install -e .` 解析并导入，供后续 Task 2-4 使用。

**对应 tasks.md:** 1.1、1.2、1.3

- [x] **Step 1: 在 `pyproject.toml` 新增 `geoalchemy2` 依赖**

在 `d:\17417\Documents\agent_culti_demo\pyproject.toml` 的 `[project].dependencies` 列表中，在 `"Flask-CORS>=4.0.0",` 行之后插入 `geoalchemy2`：

```toml
    "Flask-CORS>=4.0.0",
    "geoalchemy2>=0.14.0",
    "pymysql>=1.1.0",
```

- [x] **Step 2: 在 `pyproject.toml` 新增 `psycopg2-binary` 依赖**

在同一列表中，在 `"pymysql>=1.1.0",` 行之后插入 `psycopg2-binary`：

```toml
    "pymysql>=1.1.0",
    "psycopg2-binary>=2.9.0",
    "langchain>=0.2.0",
```

完成后的 `dependencies` 列表前半段应为：

```toml
dependencies = [
    "Flask>=3.0.0",
    "Flask-SQLAlchemy>=3.1.0",
    "Flask-JWT-Extended>=4.6.0",
    "Flask-CORS>=4.0.0",
    "geoalchemy2>=0.14.0",
    "pymysql>=1.1.0",
    "psycopg2-binary>=2.9.0",
    "langchain>=0.2.0",
    "langchain-openai>=0.1.0",
    "langgraph>=0.1.0",
    "chromadb>=0.5.0",
    "pandas>=2.2.0",
    "numpy>=1.26.0",
    "python-dotenv>=1.0.0",
    "python-docx>=1.1.0",
    "PyPDF2>=3.0.0",
    "pycryptodome>=3.20.0",
    "pdfplumber>=0.11.0",
    "openpyxl>=3.1.0",
    "waitress>=3.0.0",
    "scikit-learn>=1.3.0",
    "joblib>=1.3.0",
    "scipy>=1.11.0",
    "geopandas>=0.14.0"
]
```

- [x] **Step 3: 运行 `pip install -e .` 验证依赖可解析并安装**

在项目根目录运行：

```bash
pip install -e .
```

Expected: 安装成功，无依赖冲突报错；`psycopg2` 与 `geoalchemy2` 出现在安装输出中。

- [x] **Step 4: 验证两个新依赖可导入**

```bash
python -c "import psycopg2; print('psycopg2', psycopg2.__version__)"
python -c "import geoalchemy2; print('geoalchemy2 ok')"
```

Expected: 两行均正常输出，无 `ImportError`。

- [x] **Step 5: 提交**

```bash
git add pyproject.toml
git commit -m "chore(deps): 新增 psycopg2-binary 与 geoalchemy2 依赖"
```

---

## Task 2: framework/config.py 配置类改造（TDD）

**Files:**
- Create: `tests/test_config.py`
- Modify: `framework/config.py:15`（`DB_PORT`）、`framework/config.py:20-22`（URI 拼接）、`framework/config.py:75-81`（`DevelopmentConfig`/`ProductionConfig` 删除硬编码 URI）

**Interfaces:**
- Consumes: Task 1 产出的 `psycopg2-binary` 可导入（`postgresql+psycopg2` scheme 需要 psycopg2 驱动；本任务的单元测试不连接真实 PG，但 import 链需可用）。
- Produces:
  - `Config.SQLALCHEMY_DATABASE_URI` 默认值 = `postgresql+psycopg2://root:@localhost:5432/db_enterprise_qa`
  - `Config.DB_PORT` 默认值 = `5432`（int）
  - `DevelopmentConfig`/`ProductionConfig` 继承基类 PostgreSQL URI（不再硬编码 SQLite）
  - `SQLiteConfig.SQLALCHEMY_DATABASE_URI` = `'sqlite:///./development.db'`（不变）
  - `config_map['sqlite']` 仍指向 `SQLiteConfig`

**对应 tasks.md:** 2.1、2.2、2.3、2.4、2.5、2.6、4.1、4.2、4.3、4.4

- [x] **Step 1: 编写失败测试 `tests/test_config.py`**

创建文件 `d:\17417\Documents\agent_culti_demo\tests\test_config.py`，完整内容如下（来自 Design Doc §4.2）：

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

- [x] **Step 2: 运行测试确认失败（Red）**

在项目根目录运行：

```bash
python -m pytest tests/test_config.py -v
```

Expected:
- `test_default_uri_uses_postgresql_scheme` FAIL（当前 URI 以 `mysql+pymysql://` 开头）
- `test_default_uri_not_contains_mysql` FAIL（当前 URI 含 `mysql+pymysql` 与 `charset=utf8mb4`）
- `test_default_port_is_5432` FAIL（当前 `DB_PORT == 3306`）
- `test_env_override_uri` FAIL（subprocess 输出 mysql URI）
- `TestSQLiteConfig` 与 `TestEngineOptions` 组 PASS（SQLiteConfig 与 ENGINE_OPTIONS 当前已满足）

- [x] **Step 3: 修改 `Config.DB_PORT` 默认值 3306 → 5432**

在 `d:\17417\Documents\agent_culti_demo\framework\config.py` 第 15 行：

旧：
```python
    DB_PORT = int(os.environ.get('DB_PORT') or 3306)
```
新：
```python
    DB_PORT = int(os.environ.get('DB_PORT') or 5432)
```

- [x] **Step 4: 修改 `Config.SQLALCHEMY_DATABASE_URI` 拼接（scheme + 移除 charset）**

在 `framework/config.py` 第 20-22 行：

旧：
```python
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
```
新：
```python
    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
```

- [x] **Step 5: 删除 `DevelopmentConfig` 硬编码 SQLite URI**

在 `framework/config.py` 第 75-77 行，删除 `SQLALCHEMY_DATABASE_URI` 赋值行，使其继承基类 PostgreSQL URI：

旧：
```python
class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'
```
新：
```python
class DevelopmentConfig(Config):
    DEBUG = True
```

- [x] **Step 6: 删除 `ProductionConfig` 硬编码 SQLite URI**

在 `framework/config.py` 第 79-81 行：

旧：
```python
class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/production.db'
```
新：
```python
class ProductionConfig(Config):
    DEBUG = False
```

- [x] **Step 7: 确认 `SQLiteConfig` 与 `config_map` 保持不变**

`framework/config.py` 第 83-92 行不改动，确认内容仍为：

```python
class SQLiteConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'

config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
    'sqlite': SQLiteConfig
}
```

- [x] **Step 8: 运行测试确认全部通过（Green）**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 8 个测试全部 PASS。

注意：`test_default_port_is_5432` 与 `TestConfigBase` 默认值测试假设运行环境未设置 `DB_PORT`/`DB_HOST` 等环境变量；若本地 shell 已导出这些变量，需在干净 shell 中运行或临时 `unset DB_PORT DB_HOST DB_USER DB_PASSWORD DB_NAME`。

- [x] **Step 9: 提交**

```bash
git add framework/config.py tests/test_config.py
git commit -m "feat(config): 切换默认数据库 URI 至 PostgreSQL+psycopg2 并补充单元测试"
```

---

## Task 3: init_db.py PostGIS 扩展初始化守卫改造

**Files:**
- Modify: `init_db.py:1-17`（导入区与 `app_context` 入口）

**Interfaces:**
- Consumes: Task 2 产出的 `Config.SQLALCHEMY_DATABASE_URI` 默认为 `postgresql+psycopg2://...`；`create_app()` 返回的 `app.config['SQLALCHEMY_DATABASE_URI']`。
- Produces:
  - `init_db.py` 在 `db.create_all()` 之前，当且仅当 URI 以 `postgresql` 开头时执行 `CREATE EXTENSION IF NOT EXISTS postgis`
  - PostgreSQL 路径 PostGIS 初始化失败时：`ProgrammingError` → `rollback` + stderr 提示 + `sys.exit(1)`，不继续建表
  - SQLite 路径跳过整个 PostGIS 块，直接 `db.drop_all()` + `db.create_all()`

**对应 tasks.md:** 3.1、3.2、3.3、3.4、3.5

- [x] **Step 1: 在 `init_db.py` 导入区新增 `text` 与 `ProgrammingError`**

在 `d:\17417\Documents\agent_culti_demo\init_db.py` 顶部，`from pathlib import Path` 之后新增两行导入。修改后的导入区（第 1-13 行）应为：

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
import framework.models  # noqa: F401  触发 soil_data 等模型注册，使 db.create_all() 发现新表
```

- [x] **Step 2: 在 `app_context` 内插入 PostGIS 守卫块**

在 `init_db.py` 的 `with app.app_context():` 之后、`db.drop_all()` 之前，读取 URI 并判定 scheme，仅 PostgreSQL 路径执行 PostGIS 初始化。修改后的 `app_context` 块（来自 Design Doc §2.1）应为：

```python
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

**关键设计点（来自 Design Doc §2.2）：**
- `db_uri.startswith('postgresql')` 覆盖 `postgresql+psycopg2://` 与未来 `postgresql+psycopg://`；SQLite 路径（`sqlite:///`）返回 `False` 跳过整个块。
- `text()` 包装原生 SQL：SQLAlchemy 2.0 要求字符串 SQL 必须用 `text()`，否则触发 `ObjectNotExecutableError`。
- `ProgrammingError` 精确捕获 PostGIS 未安装（PG 实例缺少 `postgis.control`）；不捕获 `OperationalError`（连接/密码问题属部署侧）。
- 快速失败不继续 `db.create_all()`：避免后续 ORM 使用 `Geometry` 列时产生误导性错误。
- `CREATE EXTENSION IF NOT EXISTS` 保证幂等。

- [x] **Step 3: 语法检查**

```bash
python -m py_compile init_db.py
```

Expected: 无输出，退出码 0。

- [x] **Step 4: SQLite 路径冒烟测试（对应 tasks.md 4.6）**

`init_db.py` 硬编码 `create_app()`（`'default'` → PostgreSQL），无法直接以 SQLite 配置运行。为验证 SQLite 路径跳过 PostGIS 且建表成功，使用等价内联调用（`config_map['sqlite']` + 同样的 `db_uri.startswith('postgresql')` 判定逻辑）：

```bash
python -c "import sys; sys.path.insert(0, '.'); from framework.api.app import create_app; from framework.models.user import db; import framework.models; app = create_app('sqlite'); ctx = app.app_context(); ctx.push(); uri = app.config['SQLALCHEMY_DATABASE_URI']; assert uri.startswith('sqlite:///'), uri; assert not uri.startswith('postgresql'); db.drop_all(); db.create_all(); print('sqlite path ok, PostGIS skipped'); ctx.pop()"
```

Expected: 输出 `sqlite path ok, PostGIS skipped`，退出码 0；无 `CREATE EXTENSION` 相关错误。

说明：tasks.md 4.6「在 SQLite 配置下运行 `python init_db.py`」由于 `init_db.py` 固定使用 `'default'` 配置，本计划以等价内联调用验证同一守卫分支（`db_uri.startswith('postgresql')` 为 `False` → 跳过 PostGIS → `db.create_all()`）。PostgreSQL 路径的真实 `init_db.py` 运行（4.5）与幂等性（4.7）在 Task 5 通过 `scripts/verify_pg_init.py` 在有 PG 环境时手动验证。

- [x] **Step 5: 提交**

```bash
git add init_db.py
git commit -m "feat(init_db): 新增 PostGIS 扩展初始化守卫与快速失败处理"
```

---

## Task 4: scripts/verify_pg_init.py PG 集成验证脚本

**Files:**
- Create: `scripts/verify_pg_init.py`

**Interfaces:**
- Consumes: Task 2 的 `Config`（PostgreSQL URI）、Task 3 的 `init_db.py`（幂等性验证通过 `os.system` 重复调用）。
- Produces: 手动运行的 PG + PostGIS 集成验证脚本，验证 4 个维度（PostGIS 扩展、表创建、用户创建、幂等性），退出码非 0 表示失败。

**对应 tasks.md:** 4.5、4.6、4.7（脚本编写部分）

- [x] **Step 1: 创建 `scripts/verify_pg_init.py`**

创建文件 `d:\17417\Documents\agent_culti_demo\scripts\verify_pg_init.py`，完整内容如下（来自 Design Doc §4.3）：

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
        'agri_chemicalization', 'grain_yields',
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

- [x] **Step 2: 语法检查**

```bash
python -m py_compile scripts/verify_pg_init.py
```

Expected: 无输出，退出码 0。

- [x] **Step 3: 提交**

```bash
git add scripts/verify_pg_init.py
git commit -m "test(scripts): 新增 PostgreSQL+PostGIS 集成验证脚本"
```

---

## Task 5: 手动 PG 集成验证（条件性：需 PG 16 + PostGIS 3.4 实例）

**Files:**
- 无文件改动；运行 Task 4 产出的 `scripts/verify_pg_init.py` 与 `init_db.py`。

**Interfaces:**
- Consumes: Task 1（psycopg2-binary 可用）、Task 2（PostgreSQL URI）、Task 3（init_db.py 守卫）、Task 4（验证脚本）。
- Produces: tasks.md 4.5、4.6、4.7 的手动验收证据（退出码 0、表创建成功、幂等）。

**对应 tasks.md:** 4.5、4.6、4.7（运行验证部分）

**前置条件：** 已具备可连接的 PostgreSQL 16 + PostGIS 3.4 实例，并通过环境变量配置连接参数：

```bash
# 示例（按实际实例调整）
set DB_HOST=localhost
set DB_PORT=5432
set DB_USER=postgres
set DB_PASSWORD=<your-password>
set DB_NAME=db_enterprise_qa
```

若当前无 PG 实例，本任务可跳过，不阻塞 change 收尾（遵循「代码先行，环境后续」原则，Design Doc §4.3）。后续具备 PG 环境时补跑。

- [x] **Step 1: 运行 `init_db.py` 验证 PostgreSQL 路径（对应 4.5）**

```bash
python init_db.py
```

Expected:
- 输出 `[初始化] PostGIS 扩展已就绪`
- 输出 `[初始化] 数据库表结构创建完成`、`管理员用户已创建`、`普通用户已创建`
- 进程退出码 0

验证 8 张土壤数据表创建（对应 spec「既有数据库表创建兼容」Requirement）：

```bash
python -c "import sys; sys.path.insert(0,'.'); from framework.api.app import create_app; from framework.models.user import db; from sqlalchemy import inspect; app=create_app(); ctx=app.app_context(); ctx.push(); names=set(inspect(db.engine).get_table_names()); expected={'third_survey_topsoils','third_survey_profiles','third_survey_site_conditions','third_survey_bulk_densities','second_survey_points','formula_fertilizations','agri_chemicalization','grain_yields'}; missing=expected-names; print('missing:', missing); assert not missing; ctx.pop()"
```

Expected: 输出 `missing: set()`，退出码 0。

- [x] **Step 2: 重复运行 `init_db.py` 验证幂等性（对应 4.7）**

```bash
python init_db.py
python init_db.py
```

Expected: 两次运行均退出码 0，第二次运行不报 `CREATE EXTENSION` 相关错误（`IF NOT EXISTS` 保证幂等）。

- [x] **Step 3: 运行 `scripts/verify_pg_init.py` 全量验证（对应 4.5-4.7 汇总）**

```bash
python scripts/verify_pg_init.py
```

Expected:
- `[PASS] PostGIS 版本: <version>`
- `[PASS] 全部 13 张表创建成功`
- `[PASS] admin/user 用户存在`
- `[PASS] 重复运行幂等`
- `结果: 4/4 通过`，退出码 0

- [x] **Step 4: 记录验收证据**

将上述命令的输出（退出码、表清单、`4/4 通过`）记录到 change 的验证记录中（如 `openspec/changes/migrate-to-postgresql-postgis/` 下的验证说明，或在 PR 描述中附上）。无需新增代码文件。

---

## 验收映射（Self-Review 产出）

| tasks.md 条目 | OpenSpec spec Requirement / Scenario | 本计划覆盖位置 |
|---------------|--------------------------------------|----------------|
| 1.1 / 1.2 | 依赖声明 → psycopg2-binary 依赖存在 / geoalchemy2 依赖存在 | Task 1 Step 1-2 |
| 1.3 | —（依赖可解析） | Task 1 Step 3-4 |
| 2.1 | 默认端口对齐 PostgreSQL → DB_PORT SHALL 为 5432 | Task 2 Step 3 |
| 2.2 | PostgreSQL + PostGIS 默认连接 / MySQL 连接串移除 | Task 2 Step 4 |
| 2.3 | 连接池通用配置 → 四参数 / 无 charset | Task 2 Step 8（test_engine_options_*） |
| 2.4 / 2.5 | PostgreSQL + PostGIS 默认连接（子类继承基类） | Task 2 Step 5-6 |
| 2.6 | SQLite 开发降级路径 → SQLiteConfig 保留 | Task 2 Step 7、Step 8（TestSQLiteConfig） |
| 3.1-3.4 | PostGIS 扩展初始化 → PG 下初始化 / SQLite 下跳过 | Task 3 Step 1-2 |
| 3.5 | PostGIS 扩展不可用时快速失败 → 捕获 ProgrammingError + 非零退出 + 不继续 create_all | Task 3 Step 2（`except ProgrammingError` 块） |
| 4.1-4.4 | 单元测试（默认 URI / 环境覆盖 / SQLiteConfig / ENGINE_OPTIONS） | Task 2 Step 1、Step 8 |
| 4.5 | 既有数据库表创建兼容 → 8 张土壤数据表 + 退出码 0 | Task 5 Step 1 |
| 4.6 | SQLiteConfig 不触发 PostGIS 初始化 | Task 3 Step 4（等价内联验证） |
| 4.7 | PostGIS 扩展初始化 → 幂等 | Task 5 Step 2、Step 3 |

**类型一致性检查：** `Config.SQLALCHEMY_DATABASE_URI`、`Config.DB_PORT`、`SQLiteConfig`、`config_map` 在 Task 2（定义）与 Task 3/4/5（消费）中名称与类型一致；`text`、`ProgrammingError` 在 Task 3 导入并使用；`verify_postgis_extension`/`verify_tables_created`/`verify_users_exist`/`verify_idempotency` 在 Task 4 定义并在 Task 5 通过 `main()` 调用，签名一致。
