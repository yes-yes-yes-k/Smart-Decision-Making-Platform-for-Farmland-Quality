# langsmith-monitoring Specification

## Purpose
在 LangSmith 远端追踪基础上提供本地持久化调用日志，路由判定与 Agent 调用记录到本地 JSON 行式文件，与远端 trace 并行覆盖并可对账。

## Requirements
### Requirement: 本地持久化调用日志

在 LangSmith 远端追踪基础上，系统 SHALL 提供本地持久化调用日志，将路由判定与 Agent 调用记录到本地 JSON 行式文件，与远端 trace 并行覆盖。

#### Scenario: 本地日志与远端 trace 并行

- **WHEN** 一次智能体问答请求完成
- **AND** LangSmith 追踪已启用
- **THEN** 远端生成 trace，同时本地日志文件追加对应记录
- **AND** 本地记录与远端 trace 共享同一 trace_id，便于对账

#### Scenario: 无 LangSmith 时本地日志仍可用

- **WHEN** 未配置 `LANGCHAIN_API_KEY`（远端追踪关闭）
- **THEN** 本地调用日志仍正常写入
- **AND** 主流程不受影响

### Requirement: LangSmith 环境变量配置

系统 SHALL 通过 `.env` 文件管理 LangSmith 监控配置，支持以下环境变量：

- `LANGCHAIN_API_KEY`：LangSmith API Key（必填，未设置时 tracing 静默关闭）
- `LANGCHAIN_TRACING_V2`：是否启用 tracing（`true` 启用，未设置或非 `true` 时关闭）
- `LANGCHAIN_ENDPOINT`：LangSmith API 端点（默认 `https://api.smith.langchain.com`）
- `LANGCHAIN_PROJECT`：LangSmith 项目名称（默认 `agent-culti-demo`）

#### Scenario: 生产环境配置 tracing

- **WHEN** `.env` 文件设置 `LANGCHAIN_API_KEY=<valid-key>` 且 `LANGCHAIN_TRACING_V2=true`
- **THEN** 应用启动后 LangChain 自动追踪所有 LLM 调用、LangGraph 节点执行和 RAG 检索链
- **AND** trace 数据在 LangSmith 平台对应项目中可见

#### Scenario: 开发环境默认关闭 tracing

- **WHEN** `.env` 文件未设置 `LANGCHAIN_TRACING_V2` 或设置为非 `true` 值
- **THEN** LangChain tracing 保持关闭
- **AND** 不产生任何 trace 上报请求

### Requirement: Graceful Degradation

系统 SHALL 在未配置 `LANGCHAIN_API_KEY` 时正常运行，不因缺少 LangSmith 配置而报错或影响主流程。

#### Scenario: 未设置 API Key

- **WHEN** 环境变量中未设置 `LANGCHAIN_API_KEY`
- **THEN** 应用正常启动并提供全部 API 服务
- **AND** 智能体流程、RAG 检索、LLM 调用均正常执行
- **AND** 不向 LangSmith 发送任何 trace 数据

#### Scenario: LangSmith 服务不可达

- **WHEN** `LANGCHAIN_API_KEY` 已设置但 LangSmith 服务网络不可达
- **THEN** 主流程正常完成，不因 trace 上报失败而中断
- **AND** 应用日志可记录 tracing 上报超时警告（非致命）

### Requirement: 全链路追踪覆盖

当 tracing 启用时，系统 SHALL 自动追踪以下 4 个环节的执行轨迹：

1. **LangGraph 编排图节点**：initialize、identify_question、execute_models、llm_generate、rag_chat、aggregate_results、finalize
2. **专业智能体调用**：6 个专业智能体的 execute/answer_question 方法调用
3. **LLM API 调用**：SiliconFlow LLM 的 chat completions 调用（含 token 用量、延迟、模型名称）
4. **RAG 检索链**：ChromaDB 向量检索的 query 执行（含检索耗时、召回文档数）

#### Scenario: 一次完整的智能体问答请求

- **WHEN** 用户通过 `/api/v1/chat/` 发起问答请求
- **AND** `LANGCHAIN_TRACING_V2=true` 且 `LANGCHAIN_API_KEY` 已设置
- **THEN** LangSmith 平台可见一条完整 trace
- **AND** trace 包含 LangGraph 各节点的执行顺序、耗时和状态
- **AND** trace 包含触发的专业智能体调用详情
- **AND** trace 包含 LLM 调用的 token 用量和响应延迟
- **AND** trace 包含 RAG 检索的召回结果和耗时（如触发 RAG 路径）

### Requirement: 生产环境配置模板

`deploy/production.env.example` SHALL 包含 LangSmith 配置项，生产环境默认开启 tracing。

#### Scenario: 生产环境模板包含 LangSmith 配置

- **WHEN** 查阅 `deploy/production.env.example` 文件
- **THEN** 文件包含 `LANGCHAIN_API_KEY`、`LANGCHAIN_TRACING_V2=true`、`LANGCHAIN_PROJECT=agent-culti-demo` 配置项
- **AND** 每项配置附有注释说明用途

### Requirement: 文档说明

`README.md` 和 `deploy/deployment.md` SHALL 包含 LangSmith 监控的配置说明章节。

#### Scenario: README 包含 LangSmith 说明

- **WHEN** 查阅 `README.md` 的配置章节
- **THEN** 包含 LangSmith 环境变量说明（API Key、Tracing 开关、项目名称）
- **AND** 说明开发环境默认关闭、生产环境默认开启

#### Scenario: 部署文档包含 LangSmith 说明

- **WHEN** 查阅 `deploy/deployment.md`
- **THEN** 包含 LangSmith 配置步骤和故障排查说明
- **AND** 说明如何在 LangSmith 平台查看 trace

