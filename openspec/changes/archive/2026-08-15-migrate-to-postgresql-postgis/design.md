## Context

当前 `framework/config.py` 中 `Config` 基类使用 `mysql+pymysql` 拼接 `SQLALCHEMY_DATABASE_URI`，默认端口 `3306`；`DevelopmentConfig` 与 `ProductionConfig` 又分别退化为 `sqlite:///./development.db` 与 `sqlite:///instance/production.db`，导致生产路径既无 MySQL 也无 PostgreSQL 实际连接能力。`init_db.py` 仅执行 `db.drop_all()` + `db.create_all()`，未处理任何扩展初始化。`pyproject.toml` 的 `[project].dependencies` 当前包含 `pymysql`，但缺少 PostgreSQL 驱动与 PostGIS ORM 集成所需的依赖。详细动机见 `proposal.md - Why`。

## Goals / Non-Goals

**Goals:**
- 让 `Config` 基类默认产出可用的 PostgreSQL + PostGIS 连接串，并支持 `DB_*` 环境变量覆盖
- 让 `init_db.py` 在 PostgreSQL 下幂等初始化 PostGIS 扩展，在 SQLite 下降级跳过
- 在 `pyproject.toml` 中声明 `psycopg2-binary` 与 `geoalchemy2` 依赖，使后续业务表 ORM 可直接使用 `Geometry` 列类型
- 保留 `SQLiteConfig` 作为开发降级路径，避免阻塞无 PostgreSQL 环境的本地开发

**Non-Goals:**
- 不部署 PostgreSQL/PostGIS 实例，不编写 Docker/Compose 编排（代码先行）
- 不新建业务表 ORM，不改动 `framework/models/` 下现有 8 张土壤数据模型的字段定义
- 不迁移旧 MySQL/SQLite 表数据
- 不删除 `pymysql` 依赖（保留过渡兼容，避免破坏未迁移的历史连接串）

## Decisions

### Decision 1: 双数据库支持（PostgreSQL 主 + SQLite 降级）

**选择**：`Config` 基类默认构造 PostgreSQL URI；`SQLiteConfig` 单独保留 SQLite URI，并通过 `config_map['sqlite']` 暴露。

**理由**：
- 业务目标要求生产路径具备 PostGIS 能力，必须由 PostgreSQL 承载
- 仍有开发场景（CI、本地快速调试）依赖 SQLite 零配置启动，强制 PostgreSQL 会拖慢开发循环
- 通过显式的 `SQLiteConfig` 类，让降级路径可被运行时识别（用于 `init_db.py` 分支判断），而不是依赖字符串解析

**备选方案**：
- 仅保留 PostgreSQL，删除所有 SQLite 配置：被否，会破坏现有 `config_map['sqlite']` 调用方，且与「保留 SQLite 作为开发环境降级选项」的非目标冲突
- 在 `Config` 基类中根据 `FLASK_ENV` 自动切换：被否，隐式分支难以在 `init_db.py` 中可靠判定是否应执行 PostGIS 初始化

### Decision 2: 配置类层级（Config 基类 + 子类覆盖 URI）

**选择**：保持现有 `Config` → `DevelopmentConfig` / `ProductionConfig` / `SQLiteConfig` 继承结构。`Config` 基类负责从 `DB_*` 拼接 PostgreSQL URI；`SQLiteConfig` 覆盖为 SQLite URI；`DevelopmentConfig`/`ProductionConfig` 不再硬编码 SQLite，直接继承基类的 PostgreSQL URI。

**理由**：
- 最小改动现有结构，不引入新基类
- `init_db.py` 可通过检查 `app.config['SQLALCHEMY_DATABASE_URI']` 是否以 `postgresql` 开头判定是否执行 PostGIS 扩展初始化
- 环境差异（DEBUG 等）仍由子类控制，符合现有 `config_map` 选择模式

**备选方案**：
- 引入 `PostgresConfig` 中间基类：被否，与现有 `Config` 职责重复，无额外收益
- 改用 `SQLALCHEMY_DATABASE_URI` 环境变量直接覆盖：被否，无法在代码侧固化 PostgreSQL 默认值，且失去对 `DB_*` 拼接的集中管理

### Decision 3: URI scheme 选择 `postgresql+psycopg2`

**选择**：使用 `postgresql+psycopg2://` 而非 `postgresql+psycopg://` 或 `postgresql://`。

**理由**：
- brief 明确要求 `postgresql+psycopg2`
- `psycopg2-binary` 是最稳定的 PostgreSQL 驱动，与 SQLAlchemy 2.0 兼容良好
- 显式 scheme 避免 SQLAlchemy 默认驱动歧义

**备选方案**：
- `postgresql+psycopg://`（psycopg3）：被否，brief 明确要求 psycopg2，且 psycopg3 在 Windows + GeoAlchemy2 组合下兼容性尚未验证
- `postgresql://`（让 SQLAlchemy 选择默认驱动）：被否，隐式驱动会导致 `pip install` 时难以确定必须安装哪个驱动包

### Decision 4: PostGIS 扩展初始化放在 `init_db.py`，且使用 `CREATE EXTENSION IF NOT EXISTS`

**选择**：在 `init_db.py` 的 `app.app_context()` 内、`db.create_all()` 之前，通过 `db.session.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))` 执行扩展初始化，并根据 URI scheme 守卫。

**理由**：
- `IF NOT EXISTS` 保证幂等，多次运行 `init_db.py` 不会因扩展已存在而失败
- 放在 `db.create_all()` 之前，确保任何依赖 PostGIS 类型的表能成功创建
- 通过 URI scheme 守卫，避免在 SQLite 下执行导致语法错误

**备选方案**：
- 在 Flask 应用工厂 `create_app()` 中初始化：被否，应用启动不应承担 DDL 职责，且每次启动都执行扩展检查会拖慢冷启动
- 通过 Alembic 迁移脚本管理：被否，项目当前未启用 Alembic，引入迁移框架超出本次范围
- 在 `Config` 类中通过 `SQLAlchemy` 事件监听器初始化：被否，隐式副作用，调试困难

### Decision 5: 依赖写入 `pyproject.toml` 而非 `requirements.txt`

**选择**：将 `psycopg2-binary` 与 `geoalchemy2` 写入 `pyproject.toml` 的 `[project].dependencies`。

**理由**：
- 项目实际使用 `pyproject.toml` 作为依赖管理入口，根目录无 `requirements.txt`
- brief 中提到的 `requirements.txt` 是泛指依赖文件，按项目现状落到 `pyproject.toml` 才能被 `pip install -e .` 正确解析

**备选方案**：
- 新建 `requirements.txt` 并写入：被否，会引入与 `pyproject.toml` 重复的依赖源，导致不一致
- 同时更新 `pyproject.toml` 和新建 `requirements.txt`：被否，违反单一事实源原则

### Decision 6: `SQLALCHEMY_ENGINE_OPTIONS` 去除 MySQL 专属参数

**选择**：保留 `pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle` 四个通用连接池参数；移除 `charset=utf8mb4`（原本通过 URI query 传递，不在 ENGINE_OPTIONS 中，但需在 URI 构造中确认不再拼接）。

**理由**：
- 这四个参数对 PostgreSQL 与 SQLite 的 SQLAlchemy QueuePool 均生效
- `charset` 是 MySQL 专属概念，PostgreSQL 默认 UTF-8，无需在 URI 中拼接

## Risks / Trade-offs

- **[风险] `psycopg2-binary` 在 Windows 编译环境异常** → 在 `pyproject.toml` 中使用 `psycopg2-binary`（预编译 wheel），避免源码编译；如遇平台问题，文档提示可临时替换为 `psycopg2`（需 PG client lib）
- **[风险] PostGIS 扩展未在目标 PG 实例中预装** → `CREATE EXTENSION IF NOT EXISTS postgis` 仍会因 `postgis.control` 文件缺失而失败；在 `init_db.py` 中捕获 `ProgrammingError` 并输出明确错误提示，引导运维在 PG 侧安装 `postgis-3.4` 包
- **[风险] `db.drop_all()` 在生产被误执行** → 这是既有行为，本次不引入改动；`init_db.py` 仅用于初始化与开发，生产部署不应运行该脚本
- **[权衡] 保留 `pymysql` 依赖** → 暂不删除以兼容历史连接串过渡，但会在文档中标注为待移除；后续清理 change 可统一删除
- **[权衡] `DevelopmentConfig` 不再使用 SQLite** → 开发者需自备 PostgreSQL 实例，或显式选择 `config_map['sqlite']`；通过 `README` 与 `init_db.py` 输出提示降低使用摩擦

## Migration Plan

1. 在 `pyproject.toml` 的 `[project].dependencies` 中追加 `psycopg2-binary` 与 `geoalchemy2`
2. 修改 `framework/config.py`：`Config.DB_PORT` 默认值改为 `5432`；`SQLALCHEMY_DATABASE_URI` 拼接改为 `postgresql+psycopg2://...`；移除 `?charset=utf8mb4` 查询参数；`DevelopmentConfig`/`ProductionConfig` 删除硬编码 SQLite URI，继承基类 PostgreSQL URI
3. 修改 `init_db.py`：在 `db.create_all()` 之前增加 URI scheme 守卫与 `CREATE EXTENSION IF NOT EXISTS postgis` 执行；SQLite 路径跳过
4. 验证：在 PostgreSQL 16 + PostGIS 3.4 实例上运行 `python init_db.py`，确认 8 张表创建成功；在 SQLite 配置下运行，确认跳过 PostGIS 初始化且建表成功

**回滚策略**：若 PG 实例不可用，将 `FLASK_CONFIG=sqlite`（或对应 `config_map` key）切换至 `SQLiteConfig`，恢复 SQLite 路径；`pyproject.toml` 中新增依赖不影响 SQLite 运行时。

## Open Questions

- 是否需要在 `init_db.py` 输出 PostGIS 版本号以便运维核对？暂定为不需要，保持脚本输出简洁；如后续验证阶段发现需要，再行补充。
