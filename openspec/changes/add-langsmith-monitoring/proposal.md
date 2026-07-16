## Why

项目多智能体流程使用 LangGraph 编排 6 个专业智能体、LLM 调用和 RAG 检索链，但缺少可观测性手段。当智能体调用失败、LLM 响应异常或检索质量下降时，无法快速定位问题环节。LangSmith 作为 LangChain 生态的官方可观测性平台，可通过环境变量自动追踪全链路执行，零代码改动即可获得完整的 trace 可视化。

## What Changes

- 新增 LangSmith 环境变量配置（`LANGCHAIN_API_KEY`、`LANGCHAIN_TRACING_V2`、`LANGCHAIN_PROJECT`、`LANGCHAIN_ENDPOINT`），通过 `.env` 文件管理
- 在 `deploy/production.env.example` 中添加 LangSmith 配置项（生产环境默认开启 tracing）
- 开发环境默认关闭 tracing（避免噪音），通过 `.env` 控制开关
- 更新 `pyproject.toml` 确认 `langchain-core` 依赖版本支持 LangSmith tracing（langchain ≥ 0.2 已内置）
- 更新 `README.md` 和 `deploy/deployment.md` 添加 LangSmith 配置和使用说明
- 不修改任何智能体业务代码（`framework/agents/`、`framework/rag/`、`framework/llm/` 保持不变）

## Capabilities

### New Capabilities

- `langsmith-monitoring`: LangSmith 可观测性监控能力，通过环境变量自动追踪 LangGraph 编排图节点、专业智能体调用、LLM API 调用和 RAG 检索链的执行轨迹，支持 graceful degradation（未配置 API Key 时静默关闭）

### Modified Capabilities

（无现有 capability 的 spec 级别需求变更）

## Impact

- **配置文件**：`.env`、`deploy/production.env.example` 新增 LangSmith 环境变量
- **依赖**：`pyproject.toml` 确认 langchain-core 版本（无需新增依赖，langchain ≥ 0.2 已内置 LangSmith tracing 支持）
- **文档**：`README.md`、`deploy/deployment.md` 新增 LangSmith 配置说明
- **代码**：无业务代码改动，零侵入式集成
- **运行时**：未设置 `LANGCHAIN_API_KEY` 时 tracing 静默关闭，不影响系统运行
