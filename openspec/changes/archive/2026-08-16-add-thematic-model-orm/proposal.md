## Why

数据库设计文档 V3.0（`专题模型数据库设计文档_V3.docx`，2026-08-15）取代 V2.0，定义了 15 张面向专题模型的表，全面取消 V2.0 的拼音缩写字段命名（SJD/YJZ/YTK 等），改用规范化的英文 snake_case 命名（soil_ph/organic_matter/available_potassium 等）；地块唯一编号 `tybh` 改为 `parcel_id`；引入显式外键约束（取代 V2.0 弱关联）；新增 3 个查询辅助视图。当前代码仅在 `framework/models/soil_data.py` 中提供 8 张土壤数据表，缺乏专题模型结果持久化、空间数据管理和路由日志 DB 存储能力。同时 `framework/agents/capabilities.py` 中 Model-6 仍标记为"占位模型"，需升级为"耕地综合地力改良提升模型"的元数据定义（业务逻辑仍标记为占位状态），为后续综合地力能力接入数据库结构做好准备。

## What Changes

- 新增 `framework/models/thematic_model.py`，包含 15 张 V3.0 设计表的 SQLAlchemy ORM 模型：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`
- 字段名全面采用 V3.0 英文 snake_case（如 `soil_ph`、`organic_matter`、`available_potassium`、`exchangeable_hydrogen`、`parcel_id` 等），取消 V2.0 拼音缩写（`sjd`/`yjz`/`ytk`/`tybh`/`gdzldj`/`safe_abs` 等）
- 后缀规范遵循 V3.0 §6.2：`_membership`（隶属度）、`_weight`（权重）、`_obstacle_degree`（障碍度）、`_obstacle_grade`（障碍等级）、`_abs`/`_rel`（绝对/相对）、`_content`（含量）、`_dosage`（施用量）
- ORM 显式定义 V3.0 全部 10 个外键约束（取代 V2.0 弱关联）：`fk_model_execution_log_agent_id` → `thematic_model_registry.agent_id`、`fk_stability_risk_result_execution_id` → `model_execution_log.id` 等
- 每列通过 `comment=` 参数携带 V3.0 §8 COMMENT ON COLUMN 定义的中文注释
- 在 `__table_args__` 中定义 V3.0 全部 UNIQUE/BTREE/GIST 索引，索引名按表前缀化（PostgreSQL 全局唯一性约束）
- 新增 `scripts/thematic_models_v3_ddl.sql`（V3.0 §8 完整 DDL 脚本，含 CREATE EXTENSION + 15 张表 + COMMENT + 索引 + FK + 3 个视图）
- 新增 `scripts/v3_views.sql`（V3.0 §5 的 3 个视图 DDL，由 `init_db.py` 在 `db.create_all()` 之后执行）
- 修改 `framework/models/__init__.py`，导入 `thematic_model.py` 中的全部模型，使 `db.create_all()` 能发现全部新表
- 修改 `init_db.py`，在 `db.create_all()` 之后执行 `scripts/v3_views.sql` 创建 3 个视图
- 修改 `framework/agents/capabilities.py`，将 Model-6 从"占位模型"升级为"耕地综合地力改良提升模型"的元数据（`model_id`、`name`、`description`、`domain` 等字段更新，`runtime_requirement` 仍标记为占位状态）
- 空间几何列使用 GeoAlchemy2 的 `Geometry` 类型（`geom`/`extent` 列，POLYGON SRID=4326），并创建 GIST 索引
- JSONB 列使用 SQLAlchemy 的 `JSON` 类型
- 在 `pyproject.toml` 中新增 `geoalchemy2>=0.14.0` 运行时依赖

## Capabilities

### New Capabilities
- `thematic-model-orm`: 专题模型数据库 ORM，定义 15 张 V3.0 设计表的 SQLAlchemy 模型，支持 `db.create_all()` 一次性创建全部新表，覆盖专题模型注册、执行日志、空间数据、评价结果、路由日志、评估指标、排他规则和版本历史；含显式 FK、COMMENT、索引前缀化、3 个查询视图

### Modified Capabilities
- `professional-model-agents`: Model-6 元数据从"占位模型"升级为"耕地综合地力改良提升模型"，更新 `model_id`、`name`、`description`、`domain` 等字段，`runtime_requirement` 仍标记为占位状态（业务逻辑不实现）

## Impact

- **新增代码**：`framework/models/thematic_model.py`（15 个 ORM 模型类）、`scripts/thematic_models_v3_ddl.sql`（完整 DDL）、`scripts/v3_views.sql`（3 个视图 DDL）
- **修改代码**：`framework/models/__init__.py`（导入新模型）、`framework/agents/capabilities.py`（Model-6 元数据升级）、`init_db.py`（执行 v3_views.sql）、`pyproject.toml`（新增 geoalchemy2 依赖）
- **数据库结构**：`db.create_all()` 将创建 15 张新表，外加 3 个视图；依赖 PostgreSQL 16 + PostGIS 3.4（与 `migrate-to-postgresql-postgis` change 协同）
- **非影响**：不修改旧表结构、不实现 Model-6 业务逻辑、不修改路由判定逻辑、不实现 V2.0→V3.0 数据迁移脚本（V2.0 表从未落地，无数据需迁移）
