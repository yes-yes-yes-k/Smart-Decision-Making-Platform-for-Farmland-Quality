## MODIFIED Requirements

### Requirement: 本地路由调用日志落库

系统 SHALL 将每次路由判定记录为本地 JSON 行式日志并同步写入 `routing_decision_log` 数据库表（双写模式），包含候选 Agent 列表、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因与结果版本，并在对话式调用链路中贯穿唯一 trace_id，使 chat 接口响应可返回该 trace_id 供后续追溯。DB 写入失败时 SHALL 回退至 JSONL 文件写入并告警，不得影响路由主流程。entry 结构 SHALL 与 `routing_decision_log` 表字段对齐，包含 router_method、llm_reason、llm_duration_ms、total_duration_ms、five_dim_context、relevance 等字段。

#### Scenario: 记录一次正常路由

- **WHEN** 一次路由判定完成（命中排他规则且无冲突）
- **THEN** 系统 SHALL 同时向 JSONL 文件和 `routing_decision_log` 表追加一条记录，包含 question、question_type、目标 Agent、命中排他规则、routing_status=normal、耗时
- **AND** 记录带唯一 trace_id
- **AND** DB 写入失败时 SHALL 回退 JSONL 并告警

#### Scenario: 对话响应返回 trace_id

- **WHEN** 一次对话请求（非流式或流式）完成路由与调用
- **THEN** chat 接口响应包含本次调用使用的 trace_id
- **AND** 该 trace_id 与本地路由日志和 `routing_decision_log` 表中该次判定的 trace_id 一致

#### Scenario: 记录边界待确认降级

- **WHEN** 多条排他规则同时命中且无法消解
- **THEN** 本地日志和 `routing_decision_log` 表均记录 routing_status=boundary_pending
- **AND** 不记录任何被调用的 Agent 结果

#### Scenario: DB 写入失败降级

- **WHEN** `routing_decision_log` 表写入抛出异常
- **THEN** 系统 SHALL 回退至 JSONL 文件写入
- **AND** 系统 SHALL 发出告警提示 DB 写入失败
- **AND** 路由主流程 SHALL 不受影响

#### Scenario: entry 字段与表结构对齐

- **WHEN** 系统构造路由日志 entry
- **THEN** entry SHALL 包含 `routing_decision_log` 表定义的全部业务字段
- **AND** router_method、llm_reason、llm_duration_ms、total_duration_ms、five_dim_context、relevance 字段 SHALL 被填充

## ADDED Requirements

### Requirement: 混淆矩阵评估结果落库

系统 SHALL 在路由回归脚本执行完成后，将混淆矩阵评估结果写入 `model_evaluation_metrics` 数据库表，包含 model_pair、positive_label、tp、fp、fn、tn、total、accuracy、confusion_rate、evaluation_mode、sample_count、evaluated_at 字段。DB 写入失败时 SHALL 保留原有 JSON 文件输出并告警。

#### Scenario: 评估结果写入 DB

- **WHEN** 路由回归脚本完成一组易混淆对的混淆矩阵计算
- **THEN** 系统 SHALL 将该对的评估指标写入 `model_evaluation_metrics` 表
- **AND** 记录包含 model_pair、tp、fp、fn、tn、accuracy、confusion_rate、evaluation_mode、sample_count、evaluated_at

#### Scenario: DB 不可用时保留 JSON 输出

- **WHEN** 路由回归脚本完成但 `model_evaluation_metrics` 表写入失败
- **THEN** 系统 SHALL 保留原有 JSON 文件输出
- **AND** 系统 SHALL 发出告警提示 DB 写入失败
- **AND** 脚本退出码 SHALL 不因 DB 写入失败而改变
