## Purpose

将本地路由观测能力（结果追溯链与路由质量看板指标）以 HTTP API 暴露给产品前端与外部调用方，支持按 trace_id 追溯一次调用的详情，并实时查询路由正确率、重叠 Agent 混淆率、漏调用率与参数完整率等关键指标。

## ADDED Requirements

### Requirement: 按 trace_id 追溯调用详情

系统 SHALL 提供 HTTP API，接受一个 trace_id，返回该次路由/调用对应的数据版本、Agent 版本、参数与调用时间；未找到时返回明确的未找到结果。

#### Scenario: 追溯已存在的调用

- **WHEN** 客户端按一个已写入路由日志的 trace_id 查询
- **THEN** 返回包含 trace_id、data_version、agent_version、params、call_time 的追溯信息
- **AND** 响应为 HTTP 200

#### Scenario: 追溯不存在的调用

- **WHEN** 客户端按一个不存在的 trace_id 查询
- **THEN** 返回明确的未找到结果（HTTP 404）
- **AND** 不抛出服务端异常

### Requirement: 查询路由观测看板指标

系统 SHALL 提供 HTTP API 返回路由观测看板指标，包含总调用数、漏调用率、参数完整率，以及混淆矩阵中各组易混淆对的正确率与混淆率；本地无日志或矩阵时返回默认值而非报错。

#### Scenario: 查询看板指标

- **WHEN** 客户端请求路由观测看板指标
- **THEN** 返回 JSON 结构，包含总调用数、漏调用率、参数完整率，以及混淆矩阵各对的 TP/FP/FN/TN、正确率、混淆率

#### Scenario: 看板数据缺失

- **WHEN** 本地无路由日志或混淆矩阵文件
- **THEN** 返回默认指标（0 调用、0% 率值、空矩阵）
- **AND** 响应为 HTTP 200

### Requirement: 观测 API 需鉴权

系统 SHALL 对追溯与看板 API 端点要求合法身份认证，未认证请求被拒绝。

#### Scenario: 未认证请求

- **WHEN** 未携带有效 JWT 访问追溯或看板端点
- **THEN** 返回 401 未授权
