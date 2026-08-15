## Why

数据库设计文档 V2.0 定义了 15 张面向专题模型的表，覆盖专题模型注册、执行日志、空间数据图层、地块几何、稳定性/质量等级/障碍诊断/酸化改良/有机质/综合地力等评价结果、路由决策日志、模型评估指标、排他规则配置、地块信息和模型版本历史。当前代码仅在 `framework/models/soil_data.py` 中提供 8 张土壤数据表，缺乏专题模型结果持久化、空间数据管理和路由日志 DB 存储能力。同时 `framework/agents/capabilities.py` 中 Model-6 仍标记为"占位模型"，需升级为"耕地综合地力改良提升模型"的元数据定义（业务逻辑仍标记为占位状态），为后续综合地力能力接入数据库结构做好准备。

## What Changes

- 新增 `framework/models/thematic_model.py`，包含 15 张 V2.0 设计表的 SQLAlchemy ORM 模型：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`
- 修改 `framework/models/__init__.py`，导入 `thematic_model.py` 中的模型，使 `db.create_all()` 能发现全部新表
- 修改 `framework/agents/capabilities.py`，将 Model-6 从"占位模型"升级为"耕地综合地力改良提升模型"的元数据（`model_id`、`name`、`description`、`domain` 等字段更新，`runtime_requirement` 仍标记为占位状态）
- 字段名使用数据字段标准化表的拼音缩写（如 `sjd`、`yjz`、`ytk`、`gdzldj`、`safe_abs` 等），与数据库设计文档 V2.0 保持一致
- 空间几何列使用 GeoAlchemy2 的 `Geometry` 类型（`geom` 列）
- JSONB 列使用 SQLAlchemy 的 `JSON` 类型
- 在 `pyproject.toml` 中新增 `geoalchemy2` 运行时依赖

## Capabilities

### New Capabilities
- `thematic-model-orm`: 专题模型数据库 ORM，定义 15 张 V2.0 设计表的 SQLAlchemy 模型，支持 `db.create_all()` 一次性创建全部新表，覆盖专题模型注册、执行日志、空间数据、评价结果、路由日志、评估指标、排他规则和版本历史

### Modified Capabilities
- `professional-model-agents`: Model-6 元数据从"占位模型"升级为"耕地综合地力改良提升模型"，更新 `model_id`、`name`、`description`、`domain` 等字段，`runtime_requirement` 仍标记为占位状态（业务逻辑不实现）

## Impact

- **新增代码**：`framework/models/thematic_model.py`（15 个 ORM 模型类）
- **修改代码**：`framework/models/__init__.py`（导入新模型）、`framework/agents/capabilities.py`（Model-6 元数据升级）
- **依赖变更**：`pyproject.toml` 新增 `geoalchemy2` 依赖
- **数据库结构**：`db.create_all()` 将创建 15 张新表，依赖 PostgreSQL/PostGIS（与 `migrate-to-postgresql-postgis` change 协同）
- **非影响**：不修改旧表结构、不实现 Model-6 业务逻辑、不修改路由判定逻辑
