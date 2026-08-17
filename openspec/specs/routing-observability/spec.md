# routing-observability Specification

## Purpose
为五维路由系统补齐本地可观测性闭环：本地路由/调用日志、混淆矩阵、路由回归自动化、路由看板与结果追溯链，量化「正确路由率、重叠 Agent 混淆率、漏调用率」，支持对不调用或错调用进行精准定位与自动回归。

## Requirements

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

### Requirement: 路由混淆矩阵

系统 SHALL 提供混淆矩阵计算，对 model-1/5、model-2/3 两组易混淆对基于真实标签与预测结果输出 TP/FP/FN/TN、路由正确率与混淆率。

#### Scenario: 计算混淆矩阵

- **WHEN** 输入一组真实标签与预测结果
- **THEN** 输出包含 TP/FP/FN/TN、accuracy、confusion_rate 的统计字典

#### Scenario: 混淆率目标

- **WHEN** 统计两组易混淆对的路由结果
- **THEN** 重叠 Agent 混淆率不高于 3%

### Requirement: 路由回归自动化

系统 SHALL 提供可自动运行的路由回归脚本，对 model-1/5、model-2/3 两组易混淆对各提供不少于 20 条正反例并输出混淆矩阵。

#### Scenario: 运行回归脚本

- **WHEN** 执行路由回归脚本
- **THEN** 对两组易混淆对各运行不少于 20 条正反例
- **AND** 输出混淆矩阵与分类性能统计
- **AND** 退出码反映是否满足正确率与混淆率目标

### Requirement: 路由看板

系统 SHALL 提供看板，展示路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率等关键指标；看板既可本地 CLI 生成，也可通过 HTTP API 查询。

#### Scenario: 生成看板

- **WHEN** 执行看板命令
- **THEN** 输出文本看板，包含路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率
- **AND** 可导出为 Markdown 报告

#### Scenario: 通过 API 查询看板

- **WHEN** 客户端请求路由观测看板指标 API
- **THEN** 返回 JSON 结构，包含总调用数、漏调用率、参数完整率，以及混淆矩阵各对的 TP/FP/FN/TN、正确率、混淆率

### Requirement: 结果可追溯链

系统 SHALL 使每个结果可通过 trace_id 追溯到数据版本、Agent 版本、参数与调用时间；追溯能力既可通过本地函数调用，也可通过 HTTP API 查询。

#### Scenario: 追溯结果

- **WHEN** 按 trace_id 查询
- **THEN** 返回该次调用的数据版本、Agent 版本、参数与调用时间
- **AND** 结果可追溯率为 100%

#### Scenario: 通过 API 追溯结果

- **WHEN** 客户端按一个已写入路由日志的 trace_id 调用追溯 API
- **THEN** 返回包含 trace_id、data_version、agent_version、params、call_time 的追溯信息
- **AND** 响应为 HTTP 200

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
