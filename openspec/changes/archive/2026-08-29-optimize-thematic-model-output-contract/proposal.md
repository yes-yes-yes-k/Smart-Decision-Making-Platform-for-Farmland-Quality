## 为什么

当前六个正式专题能力通过 `BaseAgent.analyze()` 和 AgentManager 共享部分输出骨架，但 Function Calling、关键词回退、专题模型 API 和聊天 API 仍分别包装结果。模型原始结果会被重复写入 `analysis`、`evidence` 和 `findings`，能力描述同时出现在 `model` 与 `capability`，聊天接口还会暴露 AgentManager 的完整 `data/details`。这造成响应体积膨胀、字段语义不清、不同数据路径结构漂移，也增加了 LLM 上下文成本和客户端适配难度，因此需要建立一份分层、可版本化且适用于全部专题模型的输出契约。

## 实施基线

本变更以 `09db7a637d49f8fcca502428dff8772a1111ea35` 为实施基线，而不是最初提案时的 `7c6aa2a7e1f31588ba1358df645f36655768378c`。基线已经包含以下能力，本变更不重复实现，而是将其统一迁移到新契约：

- LLM Function Calling、多轮工具调用和失败后关键词路由回退；
- 地块标识透传、`ParcelDataAccessor` 的 Flask 应用上下文处理和路由回退；
- `data_source`、`simulated`、`routing_method` 等运行信息的现有透传字段；
- 现有 `status/data` HTTP 包络、SSE 响应优化、PDF 字体兼容和依赖配置。

因此，本变更的重点是统一已有路径的输出边界，而不是重新设计或替换 Function Calling、模型计算、数据库和 RAG 基础设施。

## 变更内容

- 新增统一专题模型结果信封，固定 `model_id`、`status`、`subject`、`result`、`meta` 和 `issues` 的语义、必填性与状态约束。
- 为 Model-1 至 Model-6 定义按 `model_id` 判别的业务 `result` Schema；统一同一模型的 DB、CSV、SQLite、预计算、ML 和降级路径输出，不强迫不同模型共享业务字段。
- 统一模型状态为 `ok`、`degraded`、`rejected`、`unavailable` 和 `error`，使用 `issues` 表达机器可读的警告、输入问题、拒绝、不可用和执行错误。
- 将数据来源、模型版本和模拟标记收敛到 `meta`；禁止使用非标准 JSON 数值 `NaN`，缺失数值统一返回 `null`。
- 移除或停止公开重复的 `model`、`capability`、`analysis`、通用 `evidence`、字符串化 `findings`、`reliability`、`fallback` 和 `degraded` 字段；模型目录继续作为能力描述的唯一来源。
- Model-1 删除与九模块重复的 `all_results`；Model-6 未实现时返回 `unavailable`，不得再包装为成功结果。
- 专题模型 API 返回完整模型结果信封；聊天 API 默认返回自然语言回答和消息元数据，不暴露 AgentManager/Orchestrator 内部结构。
- 聊天调用方显式请求模型结果时，只返回约定的精简模型投影；RAG 路径不返回模型结果。
- LLM 总结仅接收面向 LLM 的紧凑投影，不再接收完整内部执行对象；Function Calling 已生成的答复不再经过重复总结。
- **BREAKING**：专题模型成功响应和聊天 `model_results` 的 JSON 结构发生变化，依赖旧字段的调用方需要迁移；通过 `schema_version` 和兼容窗口管理升级。

## 功能 (Capabilities)

### 新增功能

- `thematic-model-output-contract`: 定义六个专题模型共用的版本化结果信封、状态与问题语义、各模型判别式业务结果 Schema，以及公共 API、LLM 上下文和审计数据的投影边界。

### 修改功能

- `professional-model-agents`: 将 `analyze(payload)` 从旧展示型包络迁移到统一模型结果信封，并保证单模型接口与聊天链路复用同一份业务结果。
- `multi-agent-orchestrator`: 明确聊天响应的版本化公共结构、模型结果按需返回规则、内部执行详情隔离和紧凑 LLM 上下文要求。

## 影响

- 主要代码：`framework/agents/base.py`、`framework/agents/manager.py`、六个专业 Agent、`framework/agents/nodes.py`、`framework/agents/orchestrator.py`、`framework/function_calling/`、`framework/api/routes/chat.py`、`framework/api/routes/models.py`、`src/ai_culti_demo/thematic_models.py`。
- API：`POST /api/v1/models/run`、`POST /api/v1/chat/` 和 `POST /api/v1/chat/stream`；可能需要新增请求参数以显式包含精简模型结果。
- 数据与日志：模型执行持久化继续保存规范化输出；完整中间详情仅进入 trace/审计，不进入普通 API 或 LLM 上下文。
- 客户端与文档：前端、API 示例、OpenAPI 文档及依赖旧 `analysis/evidence/findings/model_results.data.details` 的调用方需要迁移。
- 测试：补充公共契约、六模型成功/降级/错误路径、JSON 合规、响应去重、聊天非流式/流式一致性和兼容迁移测试。
