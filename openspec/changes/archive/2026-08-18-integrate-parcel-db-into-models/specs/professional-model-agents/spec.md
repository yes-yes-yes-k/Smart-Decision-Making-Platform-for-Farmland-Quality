## ADDED Requirements

### Requirement: 专题模型优先从数据库 parcel_info 表读取地块指标

所有专题模型 Agent（Model-1 到 Model-5）的 `_collect_inputs` SHALL 优先按 `parcel_id` 从 PostgreSQL `parcel_info` 表查询 `soil_indicators` JSON 字段获取地块指标数据。当 `parcel_info` 表中存在该 `parcel_id` 记录时，Agent SHALL 使用 DB 中的指标数据作为模型输入。当 DB 查询失败或 `parcel_id` 不存在时，Agent SHALL 降级到现有数据源（Model-1 的 MOCK_COUNTIES、Model-2 的 CSV、Model-3/4 的 SQLite、Model-5 的用户传入参数），并记录 WARNING 级别日志标明降级原因。降级响应 SHALL 包含 `data_source: "fallback"` 标识，DB 命中时 SHALL 包含 `data_source: "db"` 标识。

#### Scenario: DB 命中时使用 DB 地块指标
- **WHEN** Agent 的 `_collect_inputs` 被调用且 `parcel_id` 在 `parcel_info` 表中存在
- **THEN** Agent SHALL 从 `soil_indicators` JSON 字段解析土壤指标（soil_ph、organic_matter、available_potassium 等）作为模型输入
- **AND** 返回结果 SHALL 包含 `data_source: "db"` 标识

#### Scenario: DB 未命中时降级到现有数据源
- **WHEN** Agent 的 `_collect_inputs` 被调用且 `parcel_id` 在 `parcel_info` 表中不存在，或 DB 连接失败
- **THEN** Agent SHALL 降级到现有数据源（SQLite/CSV/MOCK_COUNTIES/用户传入参数）
- **AND** SHALL 记录 WARNING 日志标明降级原因（parcel_id_not_found 或 db_unavailable）
- **AND** 返回结果 SHALL 包含 `data_source: "fallback"` 标识

#### Scenario: Model-1 移除硬编码 MOCK_COUNTIES 优先路径
- **WHEN** StabilityRiskAgent 的 `_collect_inputs` 被调用且提供了 `parcel_id`
- **THEN** Agent SHALL 优先查询 `parcel_info` 表获取稳定性相关指标
- **AND** 仅在 DB 未命中时才使用 `MOCK_COUNTIES` 硬编码数据作为 fallback

#### Scenario: SoilDataLoader 接入生产代码
- **WHEN** 任意专题模型 Agent 需要从 DB 读取地块指标
- **THEN** SHALL 通过 `SoilDataLoader` 或等价的数据访问层统一查询 `parcel_info` 表
- **AND** SHALL NOT 在 Agent 中直接编写裸 SQL 查询

### Requirement: 专题模型结果同步持久化到 V3.0 结果表

每个专题模型 Agent 在计算成功后 SHALL 同步将结果写入对应的 V3.0 结果表和 `model_execution_log` 表。`model_execution_log` SHALL 记录 `agent_id`、`parcel_id`（县级分析除外）、`status`、`input_snapshot`（JSON 快照）、`output_snapshot`（JSON 快照）、`started_at` 和 `completed_at`。结果表 SHALL 通过 `execution_id` 外键关联 `model_execution_log.id`。DB 写入失败时 Agent SHALL 记录 ERROR 日志，但 SHALL NOT 阻断返回给用户的计算结果。`model_execution_log.status` SHALL 在计算成功时为 `ok`，计算失败时为 `error`，降级时为 `degraded`。

结果表映射：
- Model-1 → `stability_risk_result`
- Model-2 → `quality_grade_result`
- Model-3 → `obstacle_diagnosis_result`
- Model-4 → `acidification_remediation_result`
- Model-5 → `organic_matter_result`（县级分析，无 `parcel_id`）

#### Scenario: 计算成功后同步写入结果表和执行日志
- **WHEN** 专题模型 Agent 计算成功返回结果
- **THEN** Agent SHALL 先写入 `model_execution_log` 记录（`status: "ok"`，含输入/输出快照和时间戳）
- **AND** SHALL 通过 `execution_id` 外键写入对应结果表
- **AND** SHALL 在持久化完成后才返回结果给调用方

#### Scenario: DB 持久化失败不影响用户结果
- **WHEN** 专题模型 Agent 计算成功但 DB 写入结果表或 `model_execution_log` 失败
- **THEN** Agent SHALL 记录 ERROR 日志标明持久化失败原因
- **AND** SHALL NOT 抛出异常或阻断返回给用户的计算结果
- **AND** 返回结果 SHALL 包含 `persisted: false` 标识

#### Scenario: 降级计算时的执行日志记录
- **WHEN** 专题模型 Agent 因 DB 未命中而降级到 fallback 数据源完成计算
- **THEN** `model_execution_log.status` SHALL 为 `degraded`
- **AND** `input_snapshot` SHALL 记录实际使用的数据源标识（`data_source: "fallback"`）

#### Scenario: 计算失败时的执行日志记录
- **WHEN** 专题模型 Agent 计算失败
- **THEN** Agent SHALL 写入 `model_execution_log` 记录（`status: "error"`，含错误信息）
- **AND** SHALL NOT 写入结果表
