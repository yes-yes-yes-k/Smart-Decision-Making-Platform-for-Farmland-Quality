## MODIFIED Requirements

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

### Requirement: 本地路由调用日志落库

系统 SHALL 将每次路由判定记录为本地 JSON 行式日志，包含候选 Agent 列表、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因与结果版本，并在对话式调用链路中贯穿唯一 trace_id，使 chat 接口响应可返回该 trace_id 供后续追溯。

#### Scenario: 记录一次正常路由

- **WHEN** 一次路由判定完成（命中排他规则且无冲突）
- **THEN** 本地日志追加一条记录，包含 question、question_type、目标 Agent、命中排他规则、routing_status=normal、耗时
- **AND** 记录带唯一 trace_id

#### Scenario: 对话响应返回 trace_id

- **WHEN** 一次对话请求（非流式或流式）完成路由与调用
- **THEN** chat 接口响应包含本次调用使用的 trace_id
- **AND** 该 trace_id 与本地路由日志中该次判定的 trace_id 一致

#### Scenario: 记录边界待确认降级

- **WHEN** 多条排他规则同时命中且无法消解
- **THEN** 本地日志记录 routing_status=boundary_pending
- **AND** 不记录任何被调用的 Agent 结果
