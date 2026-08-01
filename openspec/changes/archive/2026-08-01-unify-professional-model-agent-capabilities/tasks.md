# 实施任务

## 1. 能力注册与基础契约

- [x] 1.1 新建统一专业能力注册表，登记 7 个 Agent、公开模型 ID、名称、输入前提、可靠性和 question_type。
- [x] 1.2 为 `BaseAgent` 增加结构化 `analyze(payload)` 契约，并定义统一成功、未就绪、输入不足和降级字段。
- [x] 1.3 为注册表与基础分析契约编写单元测试。

## 2. 专业能力迁移

- [x] 2.1 将 `model-1` 至 `model-7` 的专业计算封装到各 Agent 的 `analyze(payload)`，使 `answer_question()` 复用分析结果。
- [x] 2.2 将单模型专题 API 改为按公开 `model_id` 查询注册表并调用对应 Agent 的结构化分析。
- [x] 2.3 将空间结构、关键指标标注为辅助能力，将协同提升标注为实验性能力；默认正式模型清单不包含它们。
- [x] 2.4 为旧模型 ID 的可无歧义映射增加兼容别名和弃用标识；为不可映射能力返回明确分类而非错误映射。
- [x] 2.5 编写 API 与 Agent 分析结果一致性、分类和兼容行为测试。

## 3. 路由统一

- [x] 3.1 将 `QuestionTypeRouter` 改为从注册表生成 1 至 7 的一对一映射。
- [x] 3.2 新增提升潜力（type 6）与有机质培肥（type 7）的关键词、典型问题和聊天路由。
- [x] 3.3 调整 type 4/type 7 的关键词优先级，验证 SOC/Dose 预测与培肥方案不互相误路由。
- [x] 3.4 删除旧 `QUESTION_TYPE_TO_MODEL_ID` 组合式异常回退；失败时返回当前能力的结构化状态。
- [x] 3.5 为 0 至 7 的路由、错误降级和 API 响应添加回归测试。

## 4. 文档、规格与验证

- [x] 4.1 更新 OpenAPI、`docs/api.md`、README 中的正式模型清单、问题类型、输入前提和辅助/实验性能力说明。
- [x] 4.2 修复规格同步测试引用已归档变更目录的问题，改为校验正式 `openspec/specs`。
- [x] 4.3 运行专题模型、Agent、路由、聊天 API 和文档相关测试；记录依赖或环境前提。
- [x] 4.4 运行 `openspec validate unify-professional-model-agent-capabilities --strict`。
