## Context

当前 `framework/models/soil_data.py` 使用 Flask-SQLAlchemy（`db = SQLAlchemy()` 定义于 `framework/models/user.py`）定义 8 张土壤数据表，通过 `framework/models/__init__.py` 导入触发模型注册，`init_db.py` 调用 `db.create_all()` 建表。数据库设计文档 V2.0 新增 15 张面向专题模型的表，使用 PostgreSQL/PostGIS 特性（JSONB、Geometry），与并行进行的 `migrate-to-postgresql-postgis` change 协同。`framework/agents/capabilities.py` 中 Model-6 当前为"占位模型"（`model_id=placeholder`），需升级为"耕地综合地力改良提升模型"元数据。详见 proposal.md - Why。

## Goals / Non-Goals

**Goals:**
- 在 `framework/models/thematic_model.py` 中定义 15 张 V2.0 设计表的 ORM 模型，复用现有 Flask-SQLAlchemy `db` 对象
- 字段命名严格遵循数据库设计文档 V2.0 的拼音缩写（`sjd`、`yjz`、`ytk`、`gdzldj`、`safe_abs` 等）
- 空间几何列使用 GeoAlchemy2 `Geometry` 类型，JSONB 列使用 SQLAlchemy `JSON` 类型
- 通过 `__init__.py` 导入使 `db.create_all()` 能一次性创建全部 15 张新表
- 将 Model-6 元数据升级为"耕地综合地力改良提升模型"，保持占位状态标记

**Non-Goals:**
- 不实现 Model-6 综合地力改良提升的业务逻辑（仅元数据和数据库结构就绪）
- 不修改旧的 8 张土壤数据表结构
- 不修改路由判定逻辑或排他规则执行逻辑
- 不实现数据迁移脚本（建表即可，数据填充由后续 change 处理）
- 不实现模型执行日志的写入逻辑（仅定义 ORM 结构）

## Decisions

### 决策 1：复用 Flask-SQLAlchemy `db` 对象

**选择**：新模型从 `framework.models.user` 导入 `db`，与 `soil_data.py` 完全一致的模式定义模型类（`db.Model` 基类、`db.Column` 列）。

**理由**：保持与现有 8 张表一致的 ORM 风格，避免引入第二套会话/引擎管理。`db.create_all()` 已在 `init_db.py` 中调用，新模型经 `__init__.py` 导入即可被发现。

**备选方案**：独立定义 SQLAlchemy `Base` 和 engine —— 拒绝，会破坏现有单一 `db` 会话管理，导致事务跨会话问题。

### 决策 2：空间几何列使用 GeoAlchemy2 `Geometry` 类型

**选择**：`geom`、`extent` 等几何列使用 `geoalchemy2.Geometry` 类型，并指定 SRID（默认 4326）。

**理由**：数据库设计文档 V2.0 明确使用 PostGIS `geometry` 类型；GeoAlchemy2 是 SQLAlchemy 与 PostGIS 的标准集成，支持空间查询和空间索引。

**备选方案**：使用 WKT/WKB 字符串存储 —— 拒绝，丢失空间索引和空间查询能力，与 V2.0 设计文档冲突。

### 决策 3：JSONB 列使用 SQLAlchemy `JSON` 类型

**选择**：所有 JSONB 列（`minimum_inputs`、`input_params`、`output_result`、`evidence`、`attribute_fields`、`properties`、`input_snapshot`、`indicators`、`obstacle_degree`、`improvement_plan`、`candidate_agents`、`hit_exclusive_rules`、`five_dim_context`、`rule_pair`、`dimension_conditions`、`soil_indicators`、`parameters`、`out_of_range_features`）使用 `db.JSON` 类型。

**理由**：Flask-SQLAlchemy 的 `db.JSON` 在 PostgreSQL 后端自动映射为 `JSONB`，跨数据库兼容；任务明确要求使用 SQLAlchemy 的 JSON 类型。

### 决策 4：字段命名遵循拼音缩写

**选择**：字段名直接采用数据库设计文档 V2.0 的拼音缩写（如 `sjd`=酸碱度、`yjz`=有机质、`ytk`=碳钾、`gdzldj`=耕地质量等级、`safe_abs`=等级边界安全度绝对值、`tybh`=地块统一编号）。

**理由**：与数据库设计文档 V2.0 和数据字段标准化表保持一致，便于上下游数据对接和字段溯源。

**备选方案**：转为英文语义命名 —— 拒绝，会与 V2.0 设计文档脱节，增加字段映射维护成本。

### 决策 5：Model-6 元数据升级策略

**选择**：在 `framework/agents/capabilities.py` 中将 Model-6 的 `ProfessionalCapability` 更新为：
- `model_id`: `placeholder` → `comprehensive-fertility-improvement`
- `name`: `占位模型` → `耕地综合地力改良提升模型`
- `description`: 更新为综合地力评价与改良提升描述
- `domain`: `placeholder` → `fertility`
- `runtime_requirement`: 标注为占位状态（业务逻辑尚未实现）

**理由**：数据库结构（`comprehensive_fertility_result` 表）已就绪，元数据需同步升级以反映目标能力；但业务逻辑不实现，故 `runtime_requirement` 明确标注占位状态，避免被误认为可用。

**备选方案**：保持 `placeholder` 直到业务逻辑实现 —— 拒绝，元数据与已就绪的数据库结构脱节，不利于后续接入。

### 决策 6：新增 `geoalchemy2` 依赖

**选择**：在 `pyproject.toml` 的 `dependencies` 中新增 `geoalchemy2>=0.14.0`。

**理由**：空间几何列依赖 GeoAlchemy2，当前 `pyproject.toml` 未声明该依赖。已有 `geopandas` 依赖，GeoAlchemy2 与之兼容。

### 决策 7：主键与外键设计

**选择**：每张表使用自增整数主键 `id`（与现有 `soil_data.py` 一致）；`tybh`（地块统一编号）作为业务键但不设为联合主键；`execution_id`、`layer_id`、`trace_id` 等关联字段使用普通整数/字符串列，不强制外键约束（与 V2.0 设计文档一致，弱关联便于离线数据导入）。

**理由**：保持与现有模型一致的主键风格；V2.0 设计文档未定义严格外键约束，弱关联允许先导入数据后建立引用。

## Risks / Trade-offs

- **[风险] GeoAlchemy2 依赖 PostgreSQL/PostGIS 后端** → 若数据库仍为 MySQL，Geometry 类型建表会失败。缓解：本 change 与 `migrate-to-postgresql-postgis` change 协同，建表验证需在 PostgreSQL 环境进行；MySQL 环境下 `db.create_all()` 对 Geometry 列会报错，这是预期行为。
- **[风险] 障碍诊断表字段众多（36+ 字段）** → `obstacle_diagnosis_result` 表含 12 项障碍度原始值、12 项障碍度、12 项障碍等级字段，模型类较长。缓解：按 V2.0 设计文档完整定义，字段分组添加 comment 注释便于维护。
- **[权衡] 弱外键关联** → 不设严格外键约束，可能产生孤儿记录。权衡：便于离线数据导入和增量更新，与 V2.0 设计文档一致；数据完整性由应用层保障。
- **[风险] Model-6 升级后占位状态误用** → 元数据升级后可能被误认为可用能力。缓解：`runtime_requirement` 明确标注占位状态，路由层不应将 question_type=6 路由到实际执行。

## Migration Plan

1. 在 `pyproject.toml` 新增 `geoalchemy2>=0.14.0` 依赖并安装
2. 创建 `framework/models/thematic_model.py`，定义全部 15 个 ORM 模型类
3. 修改 `framework/models/__init__.py`，导入 `thematic_model` 模块中的全部模型类
4. 修改 `framework/agents/capabilities.py`，升级 Model-6 的 `ProfessionalCapability` 元数据
5. 在 PostgreSQL/PostGIS 环境运行 `python init_db.py` 验证 `db.create_all()` 创建全部 15 张表
6. 回滚策略：删除 `thematic_model.py`、还原 `__init__.py` 和 `capabilities.py` 修改、移除 `geoalchemy2` 依赖即可完全回滚（新表为新增，不影响旧表）

## Open Questions

无。所有设计决策已在 brief 和数据库设计文档 V2.0 中明确，无需用户进一步确认。
