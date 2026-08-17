## Why

当前 5 个专题模型（Model-1 到 Model-5）均未使用数据库 `parcel_info` 表的地块指标数据进行计算：Model-1 使用硬编码 `MOCK_COUNTIES`，Model-2 读取 CSV 文件，Model-3/4 查询 SQLite 文件，Model-5 从 joblib 文件加载 ML 模型。同时 V3.0 定义的 15 张 ORM 表（`ParcelInfo`、5 个结果表、`ModelExecutionLog` 等）虽已建表但从未被生产代码引用，计算结果无法追溯、无法空间可视化、无法历史对比。

## What Changes

- 5 个专题模型 Agent 的 `_collect_inputs` 优先从 PostgreSQL `parcel_info` 表按 `parcel_id` 查询 `soil_indicators` JSON 字段获取地块指标
- 查询失败或 `parcel_id` 不存在时降级到现有数据源（SQLite/CSV/MOCK_COUNTIES），并记录 WARNING 日志
- `BaseAgent` 增加同步持久化钩子：模型计算成功后写入对应 V3.0 结果表（`stability_risk_result`/`quality_grade_result`/`obstacle_diagnosis_result`/`acidification_remediation_result`/`organic_matter_result`）和 `model_execution_log`
- DB 写入失败时记录 ERROR 日志但不影响返回给用户的计算结果
- `SoilDataLoader`（已存在但仅测试代码调用）接入生产代码，作为 DB 读取的统一入口

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `professional-model-agents`: 新增数据源优先级要求（DB `parcel_info` 优先 + 现有数据源 fallback）和结果持久化要求（同步写入 V3.0 结果表 + `model_execution_log`）

## Impact

- **代码**：`framework/agents/base.py`（增加持久化钩子）、`framework/agents/specialized/` 下 5 个 Agent 的 `_collect_inputs`/`execute`、`framework/domain/data/soil_data_loader.py`（接入生产代码）
- **数据库**：使用已有 V3.0 表（`parcel_info`、5 个结果表、`model_execution_log`），不变更 schema
- **依赖**：依赖 PostgreSQL 16 + PostGIS 3.4 已部署且 `parcel_info` 表有数据
- **向后兼容**：保留现有数据源作为 fallback，DB 不可达时不阻断服务
