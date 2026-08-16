## Context

当前 `framework/models/soil_data.py` 使用 Flask-SQLAlchemy（`db = SQLAlchemy()` 定义于 `framework/models/user.py`）定义 8 张土壤数据表，通过 `framework/models/__init__.py` 导入触发模型注册，`init_db.py` 调用 `db.create_all()` 建表。**数据库设计文档 V3.0（2026-08-15）取代 V2.0**，新增 15 张面向专题模型的表，全面采用英文 snake_case 字段命名（取消 V2.0 拼音缩写 SJD/YJZ/YTK 等）；地块编号统一为 `parcel_id`（取消 tybh）；引入显式外键约束（取代 V2.0 弱关联）；新增 3 个查询视图。使用 PostgreSQL/PostGIS 特性（JSONB、Geometry），与并行进行的 `migrate-to-postgresql-postgis` change 协同。`framework/agents/capabilities.py` 中 Model-6 当前为"占位模型"（`model_id=placeholder`），需升级为"耕地综合地力改良提升模型"元数据。详见 proposal.md - Why。

**详细技术设计**：参见 Superpowers Design Doc `docs/superpowers/specs/2026-08-16-thematic-model-orm-v3-design.md`。

## Goals / Non-Goals

**Goals:**
- 在 `framework/models/thematic_model.py` 中定义 15 张 V3.0 设计表的 ORM 模型，复用现有 Flask-SQLAlchemy `db` 对象
- 字段命名严格遵循 V3.0 英文 snake_case（`soil_ph`、`organic_matter`、`available_potassium`、`exchangeable_hydrogen`、`parcel_id` 等），取消 V2.0 拼音缩写
- ORM 显式定义 V3.0 全部 10 个外键约束（取代 V2.0 弱关联）
- 每列通过 `comment=` 参数携带 V3.0 §8 COMMENT ON COLUMN 中文注释
- 索引名按表前缀化（PostgreSQL 全局唯一性约束）
- 空间几何列使用 GeoAlchemy2 `Geometry` 类型（POLYGON SRID=4326），创建 GIST 索引；JSONB 列使用 SQLAlchemy `JSON` 类型
- 通过 `__init__.py` 导入使 `db.create_all()` 能一次性创建全部 15 张新表
- 在 `scripts/v3_views.sql` 提供 V3.0 §5 的 3 个视图 DDL，由 `init_db.py` 在 `db.create_all()` 之后执行
- 在 `scripts/thematic_models_v3_ddl.sql` 提供 V3.0 §8 的完整 DDL 脚本作为权威参考
- 将 Model-6 元数据升级为"耕地综合地力改良提升模型"，保持占位状态标记

**Non-Goals:**
- 不实现 Model-6 综合地力改良提升的业务逻辑（仅元数据和数据库结构就绪）
- 不修改旧的 8 张土壤数据表结构
- 不修改路由判定逻辑或排他规则执行逻辑
- 不实现 V2.0→V3.0 数据迁移脚本（V2.0 表从未落地，无数据需迁移；如未来需要作为独立 change 处理）
- 不实现模型执行日志的写入逻辑（仅定义 ORM 结构）
- 不实现离线导入流程（FK 约束下的导入优化由后续变更处理）

## Decisions

### 决策 1：复用 Flask-SQLAlchemy `db` 对象

**选择**：新模型从 `framework.models.user` 导入 `db`，与 `soil_data.py` 完全一致的模式定义模型类（`db.Model` 基类、`db.Column` 列）。

**理由**：保持与现有 8 张表一致的 ORM 风格，避免引入第二套会话/引擎管理。`db.create_all()` 已在 `init_db.py` 中调用，新模型经 `__init__.py` 导入即可被发现。

**备选方案**：独立定义 SQLAlchemy `Base` 和 engine —— 拒绝，会破坏现有单一 `db` 会话管理，导致事务跨会话问题。

### 决策 2：空间几何列使用 GeoAlchemy2 `Geometry` 类型

**选择**：`geom`、`extent` 等几何列使用 `geoalchemy2.Geometry` 类型，指定 `geometry_type='POLYGON'`、`srid=4326`，并创建 GIST 索引。

**理由**：V3.0 §8 明确使用 PostGIS `geometry(Polygon,4326)` 类型；GeoAlchemy2 是 SQLAlchemy 与 PostGIS 的标准集成，支持空间查询和空间索引。

**备选方案**：使用 WKT/WKB 字符串存储 —— 拒绝，丢失空间索引和空间查询能力，与 V3.0 设计文档冲突。

### 决策 3：JSONB 列使用 SQLAlchemy `JSON` 类型

**选择**：所有 V3.0 JSONB 列（`minimum_inputs`、`input_params`、`output_result`、`evidence`、`attribute_fields`、`properties`、`input_snapshot`、`indicators`、`obstacle_degree`、`improvement_plan`、`candidate_agents`、`hit_exclusive_rules`、`five_dim_context`、`rule_pair`、`dimension_conditions`、`soil_indicators`、`parameters`、`out_of_range_features`）使用 `db.JSON` 类型。

**理由**：Flask-SQLAlchemy 的 `db.JSON` 在 PostgreSQL 后端自动映射为 `JSONB`，跨数据库兼容；任务明确要求使用 SQLAlchemy 的 JSON 类型。

### 决策 4：V3.0 英文 snake_case 字段命名（取代 V2.0 拼音缩写）

**选择**：字段名全面采用 V3.0 §8 的英文 snake_case 命名（如 `soil_ph`=酸碱度、`organic_matter`=有机质、`available_potassium`=速效钾、`exchangeable_hydrogen`=交换性氢、`parcel_id`=地块唯一编号、`grade_boundary_safety`=等级边界安全度等），取消 V2.0 拼音缩写（`sjd`/`yjz`/`ytk`/`tybh`/`gdzldj`/`safe_abs` 等）。

**理由**：V3.0 §1.1/§6.2 明确"全面取消拼音缩写字段命名，采用规范化的英文 snake_case 命名方式"；地块唯一编号 `parcel_id` 取消 TYBH/tybh 命名；项目记忆硬约束已同步更新为 V3.0。后缀规范遵循 V3.0 §6.2：`_membership`/`_weight`/`_obstacle_degree`/`_obstacle_grade`/`_abs`/`_rel`/`_content`/`_dosage`。

**备选方案**：保留 V2.0 拼音缩写 —— 拒绝，与 V3.0 设计文档脱节，违背项目记忆已更新的硬约束。

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

### 决策 7：V3.0 显式外键约束（取代 V2.0 弱关联）

**选择**：ORM 显式定义 V3.0 §8 DDL 中的全部 10 个外键约束，FK 约束名命名规则为 `fk_<table_name>_<column_name>`：
- `fk_model_execution_log_agent_id` → `thematic_model_registry.agent_id`
- `fk_model_execution_log_layer_id` → `spatial_data_layer.id`
- `fk_parcel_geometry_layer_id` → `spatial_data_layer.id`
- `fk_stability_risk_result_execution_id` → `model_execution_log.id`
- `fk_quality_grade_result_execution_id` → `model_execution_log.id`
- `fk_obstacle_diagnosis_result_execution_id` → `model_execution_log.id`
- `fk_acidification_remediation_result_execution_id` → `model_execution_log.id`
- `fk_organic_matter_result_execution_id` → `model_execution_log.id`
- `fk_comprehensive_fertility_result_execution_id` → `model_execution_log.id`
- `fk_model_version_history_agent_id` → `thematic_model_registry.agent_id`

**理由**：V3.0 §8 DDL 明确定义了 FK 约束，且用户已通过方案 A 确认完全跟随 V3.0；数据完整性由数据库强制保障。

**备选方案**：保留 V2.0 弱关联（不强制 FK）—— 拒绝，与 V3.0 DDL 不一致，违背用户已确认的方案 A。

**权衡**：FK 约束可能阻碍"先导入数据后建立引用"的离线导入流程；缓解：本变更仅定义 ORM 结构，不实现离线导入逻辑；如未来需要，可通过 `DEFERRABLE INITIALLY DEFERRED` 或临时禁用 FK 优化。

### 决策 8：V3.0 视图作为原始 SQL DDL 实现

**选择**：V3.0 §5 的 3 个视图（`v_model_execution_summary`、`v_parcel_stability_spatial`、`v_confusion_matrix_latest`）作为原始 SQL DDL 存放在 `scripts/v3_views.sql`，由 `init_db.py` 在 `db.create_all()` 之后通过 `db.session.execute(text(...))` 执行。ORM 不为视图定义模型类。

**理由**：SQLAlchemy ORM 不原生建模视图（视图是查询辅助，非数据存储）；通过原始 SQL DDL 实现最直接、最贴近 V3.0 §5 定义。`init_db.py` 固定调用顺序为 `db.create_all()` → 执行 `v3_views.sql`，使用 `CREATE OR REPLACE VIEW` 容错。

**备选方案**：(a) 定义只读 ORM 模型类查询视图 —— 拒绝，超出本变更范围，增加复杂度；(b) 跳过视图实现 —— 拒绝，与 V3.0 §5 不一致。

### 决策 9：COMMENT ON COLUMN 通过 `comment=` 参数实现

**选择**：ORM 每个字段通过 `comment=` 参数携带 V3.0 §8 `COMMENT ON COLUMN` 定义的中文注释，与现有 `soil_data.py` 风格一致。

**理由**：SQLAlchemy `Column(comment=...)` 在 PostgreSQL 后端自动生成 `COMMENT ON COLUMN` 语句；与 V3.0 §8 一一对应；与现有 `soil_data.py` 风格一致（该模块已使用 `comment=` 参数）。

### 决策 10：索引名按表前缀化（PostgreSQL 全局唯一性）

**选择**：所有索引名按表名前缀化，命名规则为 `<type>_<table_name>_<column>[_<suffix>]`，例如：
- `uk_thematic_model_registry_agent_id`、`uk_thematic_model_registry_model_id`、`idx_thematic_model_registry_question_type`
- `uk_parcel_geometry_parcel_id`、`uk_parcel_info_parcel_id`（避免跨表重名）
- `idx_parcel_geometry_geom`、`idx_parcel_info_geom`、`idx_stability_risk_result_geom`（GIST 索引也按表前缀化）

**理由**：PostgreSQL 索引名在 schema 内全局唯一，V3.0 §8 DDL 中跨表使用同名索引（如多个 `uk_parcel_id`、`idx_geom`、`idx_agent_id`）会触发 PostgreSQL 重名错误。按表前缀化避免冲突，DDL 脚本与 ORM `__table_args__` 同步前缀化。

**备选方案**：让 PostgreSQL 自动命名 —— 拒绝，丢失 V3.0 DDL 命名可读性，难以追踪。

### 决策 11：V2.0→V3.0 数据迁移不在本变更 scope

**选择**：本变更不实现 V3.0 §7.1 的 V2.0→V3.0 数据迁移脚本。

**理由**：V2.0 表从未落地（前一个变更 `migrate-to-postgresql-postgis` 仅升级数据库引擎和 ORM 基础，未实际创建 V2.0 拼音字段表），无 V2.0 数据需要迁移。本变更直接以 V3.0 设计为基线创建新表。

**备选方案**：实现 V3.0 §7.1 迁移脚本 —— 拒绝，无源数据可迁移，浪费工作量；如未来需要 V2.0 表存在场景的迁移，作为独立 change 处理。

## Risks / Trade-offs

- **[风险] GeoAlchemy2 依赖 PostgreSQL/PostGIS 后端** → 若数据库仍为 MySQL，Geometry 类型建表会失败。缓解：本 change 与 `migrate-to-postgresql-postgis` change 协同，建表验证需在 PostgreSQL 16 + PostGIS 3.4 环境进行；MySQL 环境下 `db.create_all()` 对 Geometry 列会报错，这是预期行为。
- **[风险] FK 约束阻碍离线导入** → V3.0 FK 可能阻碍"先导入数据后建立引用"的离线导入流程。缓解：本变更仅定义 ORM 结构，不实现离线导入逻辑；如未来需要，可通过 `DEFERRABLE INITIALLY DEFERRED`、`SET session_replication_role='replica'` 临时禁用触发器、或按依赖顺序导入。
- **[风险] PostgreSQL 索引名全局唯一** → V3.0 DDL 中跨表重名索引会触发 PostgreSQL 错误。缓解：所有索引名按表前缀化（决策 10）。
- **[风险] 视图依赖表已存在** → 在 `db.create_all()` 之前执行 `v3_views.sql` 会因表不存在而失败。缓解：`init_db.py` 固定调用顺序为 `db.create_all()` → 执行 `v3_views.sql`；视图使用 `CREATE OR REPLACE VIEW` 容错。
- **[风险] 障碍诊断表字段众多（43 列）** → `obstacle_diagnosis_result` 表含 12 隶属度 + 12 障碍度 + 12 障碍等级 + 7 汇总列 = 43 列，模型类较长。缓解：按 V3.0 §8.7 完整定义，分组添加 comment 注释便于维护。
- **[权衡] `organic_matter_result` 无 `parcel_id` 列** → V3.0 §8.9 该表无 `parcel_id`（Model-5 是县级分析，无地块关联）；与项目记忆"Model-5 是县级分析"一致。
- **[权衡] Spec 大幅重写** → V3.0 要求改写 `specs/thematic-model-orm/spec.md` 全部 Requirement 的字段名（拼音 → 英文 snake_case）。已标记为设计发现并由用户通过方案 A 确认。
- **[风险] Model-6 升级后占位状态误用** → 元数据升级后可能被误认为可用能力。缓解：`runtime_requirement` 明确标注占位状态，路由层不应将 question_type=6 路由到实际执行。

## Migration Plan

1. 在 `pyproject.toml` 新增 `geoalchemy2>=0.14.0` 依赖并安装
2. 创建 `scripts/thematic_models_v3_ddl.sql`（V3.0 §8 完整 DDL，索引名按表前缀化）
3. 创建 `scripts/v3_views.sql`（V3.0 §5 的 3 个视图 DDL）
4. 创建 `framework/models/thematic_model.py`，定义全部 15 个 ORM 模型类（V3.0 字段名 + FK + COMMENT + 索引按表前缀化）
5. 修改 `framework/models/__init__.py`，导入 `thematic_model` 模块中的全部模型类
6. 修改 `framework/agents/capabilities.py`，升级 Model-6 的 `ProfessionalCapability` 元数据
7. 修改 `init_db.py`，在 `db.create_all()` 之后执行 `scripts/v3_views.sql`
8. 在 PostgreSQL 16 + PostGIS 3.4 环境运行 `python init_db.py` 验证全部 15 张表 + 3 个视图创建成功
9. **回滚策略**：删除 `thematic_model.py`、还原 `__init__.py` 和 `capabilities.py`、删除两个 SQL 脚本、移除 `init_db.py` 中视图执行、移除 `geoalchemy2` 依赖即可完全回滚（新表为新增，不影响旧表）。

## Open Questions

无。所有设计决策已在 V3.0 设计文档、Superpowers Design Doc 和 brainstorming 中明确，并通过用户两轮确认锁定。
