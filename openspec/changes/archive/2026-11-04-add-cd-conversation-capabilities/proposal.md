# Cd 统计、参数与计算对话接入

## Why

现有土壤 Cd 指标统计、作物与有效态 Cd 预测服务已经具备独立入口，但聊天工具尚未提供相应查询、补参和计算流程。用户需要在指定地区和时期查询结果，了解参数，并连续修改参数试算。本变更补齐 Agent 编排层到现有专业能力层的连接。

## What Changes

- 接入土壤 Cd 统计、作物及有效态 Cd 预测结果、参数定义和地区参数值查询、纯参数预测。
- 建立按指标、操作、地区、时间和单位状态声明可用性的能力清单，登记八类通量及未就绪原因。
- 支持跨消息补参、参数来源追踪、改参重算和地区／年份切换后的参数更新。
- 按数据类别保留统计口径，区分来源、年度快照、实际测量年份和查询时间。
- 明确要求保存时持久化独立试算记录，支持同一结果重复保存与并发重试。

## Capabilities

### New Capabilities

- `cd-conversation-analysis` 提供有能力边界的 Cd 查询、参数计算、多轮交互与保存规范。

### Modified Capabilities

现有能力通过适配复用。本变更新增对话要求，继续遵守现有分析对象守卫、工具注册和认证契约。

## Impact

涉及 `framework/function_calling/`、`framework/agents/`、聊天服务与会话状态，以及独立试算记录的数据模型和迁移。复用土壤统计、区域解析及 `heavy_metal_cd*` 服务。新增存储需要迁移、回滚及幂等验证，既有预测结果查询仍读取原有结果表。

## Roadmap

- 阶段 C1，见 `docs/cd-migration-roadmap.md`。
- 前置 change 为 `add-heavy-metal-cd-prediction`、`add-heavy-metal-cd-database-backend`、`add-heavy-metal-cd-statistics-api`、`add-heavy-metal-cd-spatial-analysis`、`import-cd-ported-dataset`。
- 后续对话扩展依赖 `add-cd-flux-accounting` 与 `add-cd-removal-calculation` 提供经过验证的服务，分别立项接入。
- 本批聚焦已有服务的对话闭环及通量能力状态。通量公式、数据迁移、地图和未来浓度预测沿各自阶段推进。

## Validation

实施时覆盖普通聊天及流式入口、对象消歧、时间和来源过滤、统计口径、缺参及单位状态、多轮改参、能力不可用、授权与保存幂等。提案阶段运行 OpenSpec 严格校验及文档差异检查。
