## Purpose

定义应用程序数据库引擎的配置契约：默认使用 PostgreSQL 16 + PostGIS 3.4 作为生产与开发主引擎，同时保留 SQLite 作为开发降级路径，使空间数据管理能力具备可承载基础。

## ADDED Requirements

### Requirement: PostgreSQL + PostGIS 默认连接

系统 SHALL 在 `Config` 基类中将默认 `SQLALCHEMY_DATABASE_URI` 构造为 `postgresql+psycopg2` scheme，并使用环境变量 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME` 拼接连接串。默认端口 SHALL 为 `5432`，默认库名 SHALL 为 `db_enterprise_qa`。

#### Scenario: 默认 PostgreSQL 连接串构造

- **WHEN** 未设置任何 `DB_*` 环境变量且使用 `Config` 基类
- **THEN** `SQLALCHEMY_DATABASE_URI` SHALL 以 `postgresql+psycopg2://` 开头
- **AND** 连接串 SHALL 指向 `localhost:5432/db_enterprise_qa`

#### Scenario: 环境变量覆盖连接参数

- **WHEN** 设置环境变量 `DB_HOST=pg.example.com`、`DB_PORT=6543`、`DB_USER=app`、`DB_PASSWORD=secret`、`DB_NAME=prod_db`
- **THEN** `SQLALCHEMY_DATABASE_URI` SHALL 等于 `postgresql+psycopg2://app:secret@pg.example.com:6543/prod_db`

#### Scenario: 默认端口对齐 PostgreSQL

- **WHEN** 未设置 `DB_PORT` 环境变量
- **THEN** `Config.DB_PORT` SHALL 为 `5432`

### Requirement: MySQL 连接串移除

系统 SHALL 不再在 `Config` 基类中构造 `mysql+pymysql` 连接串，且默认 URI 中 SHALL 不携带 `charset=utf8mb4` 等 MySQL 专属查询参数。

#### Scenario: URI 不包含 MySQL scheme

- **WHEN** 检查 `Config.SQLALCHEMY_DATABASE_URI` 的默认值
- **THEN** 该值 SHALL NOT 以 `mysql+pymysql://` 开头
- **AND** 该值 SHALL NOT 包含 `charset=utf8mb4` 子串

### Requirement: 连接池通用配置

系统 SHALL 在 `SQLALCHEMY_ENGINE_OPTIONS` 中保留与数据库引擎无关的连接池参数（`pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle`），且 SHALL NOT 包含 MySQL 专属参数。

#### Scenario: 连接池参数存在

- **WHEN** 读取 `Config.SQLALCHEMY_ENGINE_OPTIONS`
- **THEN** 字典 SHALL 包含 `pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle` 四个键
- **AND** 字典 SHALL NOT 包含 `charset` 键

### Requirement: SQLite 开发降级路径

系统 SHALL 保留 `SQLiteConfig` 配置类，其 `SQLALCHEMY_DATABASE_URI` SHALL 使用 `sqlite:///./development.db`，用于在没有 PostgreSQL 实例的开发环境中运行。

#### Scenario: SQLiteConfig 提供 SQLite URI

- **WHEN** 使用 `config_map['sqlite']` 选择配置
- **THEN** 返回的配置类 SHALL 暴露 `SQLALCHEMY_DATABASE_URI` 且其值以 `sqlite:///` 开头

#### Scenario: SQLiteConfig 不触发 PostGIS 初始化

- **WHEN** `SQLiteConfig` 被激活且 `init_db.py` 运行
- **THEN** 系统 SHALL 跳过 `CREATE EXTENSION IF NOT EXISTS postgis` 语句
- **AND** 系统 SHALL 不抛出与 PostGIS 相关的错误

### Requirement: PostGIS 扩展初始化

系统 SHALL 在 `init_db.py` 创建数据库表之前，当且仅当当前 `SQLALCHEMY_DATABASE_URI` 指向 PostgreSQL 时，通过数据库连接执行 `CREATE EXTENSION IF NOT EXISTS postgis` 以确保 PostGIS 扩展可用。

#### Scenario: PostgreSQL 连接下初始化 PostGIS

- **WHEN** `SQLALCHEMY_DATABASE_URI` 以 `postgresql+psycopg2://` 开头
- **AND** `init_db.py` 在应用上下文中运行
- **THEN** 系统 SHALL 在 `db.create_all()` 之前执行 `CREATE EXTENSION IF NOT EXISTS postgis`
- **AND** 该语句 SHALL 幂等，多次运行不报错

#### Scenario: SQLite 连接下跳过 PostGIS 初始化

- **WHEN** `SQLALCHEMY_DATABASE_URI` 以 `sqlite:///` 开头
- **AND** `init_db.py` 在应用上下文中运行
- **THEN** 系统 SHALL 跳过 `CREATE EXTENSION IF NOT EXISTS postgis` 执行
- **AND** 系统 SHALL 继续完成 `db.create_all()`

#### Scenario: PostGIS 扩展不可用时快速失败

- **WHEN** `SQLALCHEMY_DATABASE_URI` 以 `postgresql+psycopg2://` 开头
- **AND** PG 实例未安装 postgis 包（`postgis.control` 缺失）
- **AND** `init_db.py` 执行 `CREATE EXTENSION IF NOT EXISTS postgis`
- **THEN** 系统 SHALL 捕获 `ProgrammingError`
- **AND** SHALL 输出明确错误提示，引导运维安装 postgis 包
- **AND** SHALL 以非零退出码终止
- **AND** SHALL NOT 继续执行 `db.create_all()`

### Requirement: 依赖声明

系统 SHALL 在项目依赖管理文件中声明 `psycopg2-binary` 与 `geoalchemy2` 两个 Python 依赖，使其可用于 PostgreSQL 驱动与 PostGIS ORM 集成。本项目使用 `pyproject.toml` 的 `[project].dependencies` 作为依赖管理入口。

#### Scenario: psycopg2-binary 依赖存在

- **WHEN** 检查 `pyproject.toml` 的 `[project].dependencies`
- **THEN** 列表 SHALL 包含 `psycopg2-binary` 条目

#### Scenario: geoalchemy2 依赖存在

- **WHEN** 检查 `pyproject.toml` 的 `[project].dependencies`
- **THEN** 列表 SHALL 包含 `geoalchemy2` 条目

### Requirement: 既有数据库表创建兼容

系统 SHALL 在 PostgreSQL + PostGIS 环境下运行 `init_db.py` 时成功创建当前 `framework/models/` 中已注册的全部 8 张土壤数据表，且不改变表名与字段定义。

#### Scenario: PostgreSQL 下创建 8 张土壤数据表

- **WHEN** 配置为 PostgreSQL + PostGIS 连接且 `init_db.py` 运行至 `db.create_all()`
- **THEN** 系统 SHALL 成功创建 `third_survey_topsoils`、`third_survey_profiles`、`third_survey_site_conditions`、`third_survey_bulk_densities`、`second_survey_points`、`formula_fertilizations`、`agri_chemicalizations`、`grain_yields` 8 张表
- **AND** 进程退出码 SHALL 为 0
