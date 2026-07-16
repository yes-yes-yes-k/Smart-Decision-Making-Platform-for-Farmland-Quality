## Context

项目多智能体流程基于 LangGraph StateGraph 构建，编排路径为 `initialize → identify_question → (rag_chat | execute_models → llm_generate) → aggregate_results → finalize`。6 个专业智能体通过 AgentManager 管理，LLM 调用通过 SiliconFlow API，RAG 检索基于 ChromaDB。

当前缺少可观测性手段：当智能体调用失败、LLM 响应异常或检索质量下降时，只能通过应用日志排查，无法可视化全链路执行轨迹。LangSmith 是 LangChain 生态的官方可观测性平台，langchain ≥ 0.2 已内置 tracing 支持，通过环境变量即可自动追踪 LangGraph、LLM 和检索链的执行。

## Goals / Non-Goals

**Goals:**
- 通过环境变量启用 LangSmith 自动追踪，覆盖 LangGraph 编排图节点、专业智能体调用、LLM API 调用、RAG 检索链
- 生产环境默认开启 tracing，开发环境默认关闭（避免噪音）
- 未配置 API Key 时系统正常运行（graceful degradation）
- 零业务代码改动，仅靠环境变量和 LangChain 内置 tracing 机制

**Non-Goals:**
- 不添加 `@traceable` 装饰器或自定义 Callbacks（保持零代码改动）
- 不在 `framework/config.py` 中新增 LangSmith 配置类（配置完全由 .env 管理）
- 不改变智能体业务逻辑、API 接口或数据库 schema
- 不实现 LangSmith 的 evaluation 或 dataset 功能（仅 tracing）

## Decisions

### 决策 1：环境变量自动追踪（非 @traceable 装饰器）

**选择**：通过 `LANGCHAIN_TRACING_V2=true` 环境变量启用 LangChain 内置自动追踪。

**理由**：LangChain ≥ 0.2 的 `langchain-core` 已内置 tracing 机制，设置环境变量后会自动拦截 LangGraph 的 `invoke()`、LLM 的 `chat.completions.create()`、ChromaDB 的 `similarity_search()` 等调用，无需修改任何业务代码。

**备选方案**：
- `@traceable` 装饰器：提供更细粒度的 trace 元数据，但需要修改每个智能体和节点的函数签名，违反"零代码改动"目标
- 自定义 Callbacks：最大化监控粒度，但增加维护成本和代码复杂度

### 决策 2：.env 配置管理（非 Config 类）

**选择**：LangSmith 配置完全通过 `.env` 文件管理，不在 `framework/config.py` 中新增配置类。

**理由**：LangSmith 的 tracing 机制由 `langchain-core` 在库层面通过 `os.environ.get()` 读取环境变量，不经过应用的 Config 类。在 Config 类中管理会导致配置分散在两处（Config 类和 langchain 内部读取），增加混乱。

**备选方案**：
- Config 类集中管理：需要在应用启动时手动设置 `os.environ`，增加启动逻辑复杂度
- 两者结合：.env 提供 API Key，Config 类提供项目名和开关，但 langchain 内部直接读环境变量，Config 类的值不会生效

### 决策 3：开发环境默认关闭 tracing

**选择**：开发环境 `.env` 不设置 `LANGCHAIN_TRACING_V2`（默认关闭），生产环境 `deploy/production.env.example` 设置 `LANGCHAIN_TRACING_V2=true`。

**理由**：开发环境频繁调试会产生大量 trace 噪音，且开发环境可能没有 LangSmith API Key。生产环境需要监控线上运行状况，默认开启。

### 决策 4：LangSmith 项目名称约定

**选择**：使用 `LANGCHAIN_PROJECT=agent-culti-demo` 作为默认项目名，不区分 dev/prod。

**理由**：LangSmith 平台本身支持按 tag、metadata 筛选，无需通过项目名区分环境。如果用户需要区分，可在 `.env` 中修改 `LANGCHAIN_PROJECT` 值。

## Risks / Trade-offs

- **[风险] LangSmith 服务不可达导致请求变慢** → LangChain tracing 使用异步上报，超时后静默跳过，不影响主流程。但首次连接可能有轻微延迟。
- **[风险] API Key 泄露** → `.env` 已在 `.gitignore` 中排除，`deploy/production.env.example` 仅提供占位符。
- **[风险] trace 数据量过大** → LangSmith 免费层有 trace 数量限制。生产环境如 trace 量过大，可通过 `LANGCHAIN_TRACING_SAMPLING_RATE` 控制采样率。
- **[权衡] 自动追踪的粒度不如 @traceable** → 自动追踪覆盖 LangGraph 节点、LLM 调用和检索链，但无法添加自定义业务元数据（如用户 ID、问题类型）。当前阶段可接受，后续如需更细粒度可增量添加 @traceable。
