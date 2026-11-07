## Why

用户反馈普通提问经常等待超过两分钟，且等待期间缺少及时反馈。现有代码显示流式接口并不意味着马上开始流：路由与专业模型执行、RAG 混合检索和重排均可能发生在首个 token 之前；项目内缺少覆盖完整请求生命周期的阶段耗时证据，因此既要定位真实长尾，也要降低可避免的等待。

## What Changes

- 对话流程建立从 HTTP 入口到前端收到首 token、收到完成事件的全链路耗时观测，按路由记录阶段耗时、调用次数、重试、错误、超时及 trace_id。
- 明确区分首 token 延迟（TTFT）、总响应时间、客户端呈现时间，并为非流式和 SSE 两条路径统一关联。
- 在不改变答案正确性、空间对象守卫、权限过滤和结果契约的前提下，优化可并发的独立专业模型、检索与生成路径，以及昂贵操作的复用。
- SSE 长任务向用户尽早发送有意义的状态/进度事件，并核查代理缓冲、同步 WSGI worker、取消和断连处理。
- 建立按 RAG、专业模型、综合工作流、恢复交互分层的延迟基线和 SLO 验收。

## Capabilities

### New Capabilities
- `chat-latency-observability`: 全链路对话延迟分段、路由归因、TTFT 与端到端基线。

### Modified Capabilities
- `rag-chain`: 在保留检索正确性及引用的前提下，流式对话要尽早反馈阶段进度并暴露检索/生成耗时。
- `multi-agent-orchestrator`: 明确独立 Agent 的并行执行与依赖约束，并让专业路线在首 token 前的阻塞阶段可观测、可反馈。

## Impact

- 后端：`framework/api/routes/chat.py`、`framework/api/services/chat_service.py`、`framework/agents/orchestrator.py`、`framework/agents/manager.py`、`framework/rag/chain.py`、向量检索、重排、LLM 服务及 observability。
- 前端：聊天 SSE 消费、首事件/进度状态与断连处理（前端具体目录需在实现阶段据仓库结构确定）。
- 运维：应用服务器并发配置、反向代理 SSE 缓冲和请求超时；指标存储及看板。
- 不修改公共答案 schema 的既有必需字段；进度事件采用向后兼容的可选 SSE 事件。
