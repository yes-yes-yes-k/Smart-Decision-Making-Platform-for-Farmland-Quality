## Why

当前 `framework/config.py` 中 `SQLALCHEMY_DATABASE_URI` 默认使用 `mysql+pymysql`，且 `ProductionConfig` 退化为 SQLite，整体无法承载 PostgreSQL + PostGIS 空间扩展。数据库设计 V2.0 需要在关系表中存储地块几何、空间索引与空间查询能力，MySQL 与 SQLite 均不能稳定提供等效的 PostGIS 能力。本次切换先行完成代码与依赖侧准备，使后续业务表 ORM 与空间数据管理能力具备落地基础。

## What Changes

- **BREAKING** `Config.SQLALCHEMY_DATABASE_URI` 从 `mysql+pymysql://...` 切换为 `postgresql+psycopg2://...`，默认端口由 `3306` 调整为 `5432`，默认库名保持 `db_enterprise_qa`
- **BREAKING** `Config.DB_PORT` 默认值由 `3306` 改为 `5432`，对齐 PostgreSQL 默认端口
- 新增依赖 `psycopg2-binary` 与 `geoalchemy2`（写入项目依赖管理文件；本项目使用 `pyproject.toml` 的 `[project].dependencies`，未单独维护 `requirements.txt`，按现状落到 `pyproject.toml`）
- `init_db.py` 在 `db.create_all()` 之前增加 `CREATE EXTENSION IF NOT EXISTS postgis` 初始化逻辑，仅在 PostgreSQL 连接下执行；SQLite 降级路径跳过该步骤
- 保留 `SQLiteConfig` 作为开发环境降级选项，`DevelopmentConfig`/`ProductionConfig` 默认指向 PostgreSQL 连接串
- 调整 `SQLALCHEMY_ENGINE_OPTIONS`，去除 MySQL 专属参数（如 `charset=utf8mb4`），保留连接池通用参数并对齐 PostgreSQL 行为

## Capabilities

### New Capabilities
- `database-engine`: 数据库引擎配置与管理，覆盖 PostgreSQL + PostGIS 连接、环境变量覆盖、PostGIS 扩展初始化以及 SQLite 开发降级路径

### Modified Capabilities
<!-- 本次变更不修改既有 spec 的 requirements。`database-models` capability 仍由 archived change 维护，ORM 模型本身不变；本次只切换引擎与初始化逻辑，不引入 spec 级别行为变更。 -->

## Impact

- **代码**：`framework/config.py`（URI、端口、引擎选项、配置类默认值）、`init_db.py`（PostGIS 扩展初始化、PostgreSQL/SQLite 分支）
- **依赖**：`pyproject.toml` 的 `[project].dependencies` 新增 `psycopg2-binary`、`geoalchemy2`；保留 `pymysql` 以兼容历史连接串过渡（不强制删除）
- **运行时**：部署侧需要可用的 PostgreSQL 16 + PostGIS 3.4 实例；开发侧可继续使用 SQLite 降级配置
- **非影响范围**：不新建业务表 ORM；不部署 PG 环境；不迁移旧表数据；不改动 `framework/models/*` 中的现有 8 张土壤数据模型定义
