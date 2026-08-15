## 1. 依赖声明

- [x] 1.1 在 `pyproject.toml` 的 `[project].dependencies` 中新增 `psycopg2-binary` 依赖项
- [x] 1.2 在 `pyproject.toml` 的 `[project].dependencies` 中新增 `geoalchemy2` 依赖项
- [x] 1.3 运行 `pip install -e .` 验证新依赖可被正确解析并安装

## 2. 配置类改造（framework/config.py）

- [x] 2.1 将 `Config.DB_PORT` 默认值从 `3306` 改为 `5432`
- [x] 2.2 将 `Config.SQLALCHEMY_DATABASE_URI` 拼接 scheme 从 `mysql+pymysql://` 改为 `postgresql+psycopg2://`，并移除 `?charset=utf8mb4` 查询参数
- [x] 2.3 确认 `SQLALCHEMY_ENGINE_OPTIONS` 仅保留 `pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle` 四个通用参数，无 MySQL 专属键
- [x] 2.4 删除 `DevelopmentConfig` 中硬编码的 `SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'`，使其继承基类 PostgreSQL URI
- [x] 2.5 删除 `ProductionConfig` 中硬编码的 `SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/production.db'`，使其继承基类 PostgreSQL URI
- [x] 2.6 保留 `SQLiteConfig` 类及其 `SQLALCHEMY_DATABASE_URI = 'sqlite:///./development.db'`，确认 `config_map['sqlite']` 仍指向该类

## 3. init_db.py 改造（init_db.py）

- [x] 3.1 在 `init_db.py` 顶部导入 `sqlalchemy.text`（或等价工具）用于执行原生 SQL
- [x] 3.2 在 `app.app_context()` 内、`db.create_all()` 之前，读取 `app.config['SQLALCHEMY_DATABASE_URI']` 并判定 scheme 是否以 `postgresql` 开头
- [x] 3.3 当且仅当 scheme 为 PostgreSQL 时，执行 `db.session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))` 并 `db.session.commit()`
- [x] 3.4 当 scheme 为 `sqlite` 时，跳过 PostGIS 初始化，直接进入 `db.create_all()`
- [x] 3.5 在 PostGIS 初始化失败时（如 `ProgrammingError`）输出明确的错误提示，引导运维检查 PostGIS 是否在 PG 实例侧安装

## 4. 验证测试

- [x] 4.1 编写或补充单元测试，验证 `Config` 基类默认 `SQLALCHEMY_DATABASE_URI` 以 `postgresql+psycopg2://` 开头且不含 `mysql+pymysql` 或 `charset=utf8mb4`
- [x] 4.2 编写或补充单元测试，验证设置 `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME` 环境变量后 URI 拼接正确
- [x] 4.3 编写或补充单元测试，验证 `SQLiteConfig.SQLALCHEMY_DATABASE_URI` 以 `sqlite:///` 开头
- [x] 4.4 编写或补充单元测试，验证 `SQLALCHEMY_ENGINE_OPTIONS` 包含四个通用连接池参数且不包含 `charset` 键
- [ ] 4.5 在 PostgreSQL 16 + PostGIS 3.4 实例上运行 `python init_db.py`，确认 8 张土壤数据表（`third_survey_topsoils` 等）创建成功且进程退出码为 0
- [x] 4.6 在 SQLite 配置（`config_map['sqlite']`）下运行 `python init_db.py`，确认跳过 PostGIS 初始化且建表成功
- [ ] 4.7 重复运行 `python init_db.py`（PostgreSQL 路径）两次，确认 `CREATE EXTENSION IF NOT EXISTS postgis` 幂等，第二次运行不报错

> **延后验证说明（4.5 / 4.7）**：遵循 Design Doc §4.3「代码先行，环境后续」原则，当前无 PostgreSQL 16 + PostGIS 3.4 实例，故 4.5 与 4.7 暂不勾选。Plan Task 5 显式声明「若当前无 PG 实例，本任务可跳过，不阻塞 change 收尾」。已提供 `scripts/verify_pg_init.py` 脚本，待具备 PG 环境时手动补跑。
