# Comet Design Handoff

- Change: add-langsmith-monitoring
- Phase: design
- Mode: compact
- Context hash: 9d6ad374fa028d05b77d782d46dc6c652678ff1ce869085ef4df0401af755827

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-langsmith-monitoring/proposal.md

- Source: openspec/changes/add-langsmith-monitoring/proposal.md
- Lines: 1-30
- SHA256: 5fa3c691ed6fb37b40969c66006ce76ad7aa5eb7e137759ce902190e82b1f337

```md
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

```

## openspec/changes/add-langsmith-monitoring/design.md

- Source: openspec/changes/add-langsmith-monitoring/design.md
- Lines: 1-60
- SHA256: 6d7df22c4fb870b05baecd92ff498b4b2cdbf8edcf06bd5cb48560448f544749

```md
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

```

## openspec/changes/add-langsmith-monitoring/tasks.md

- Source: openspec/changes/add-langsmith-monitoring/tasks.md
- Lines: 1-18
- SHA256: a5676d7828aaed84850c128e7365da4bf6b2c19366360e45908b4d9a2af79e84

```md
## 1. 环境变量配置

- [ ] 1.1 在 `deploy/production.env.example` 添加 LangSmith 配置项（`LANGCHAIN_API_KEY`、`LANGCHAIN_TRACING_V2=true`、`LANGCHAIN_ENDPOINT`、`LANGCHAIN_PROJECT=agent-culti-demo`），每项附注释说明
- [ ] 1.2 确认 `.gitignore` 已排除 `.env` 文件（避免 API Key 泄露）

## 2. 依赖确认

- [ ] 2.1 确认 `pyproject.toml` 中 `langchain ^0.2.0` 和 `langchain-core` 版本支持 LangSmith tracing v2（langchain ≥ 0.2 已内置，无需新增依赖）

## 3. 文档更新

- [ ] 3.1 在 `README.md` 配置章节添加 LangSmith 环境变量说明（API Key、Tracing 开关、项目名称），说明开发环境默认关闭、生产环境默认开启
- [ ] 3.2 在 `deploy/deployment.md` 添加 LangSmith 配置步骤（如何在 .env 中配置）、查看 trace 说明和故障排查（tracing 不生效、服务不可达）

## 4. 验证

- [ ] 4.1 运行全部测试（`python -m pytest tests/ -q`）确认零代码改动不影响现有功能
- [ ] 4.2 验证未设置 `LANGCHAIN_API_KEY` 时应用正常启动（graceful degradation）

```

## openspec/changes/add-langsmith-monitoring/specs/langsmith-monitoring/spec.md

- Source: openspec/changes/add-langsmith-monitoring/specs/langsmith-monitoring/spec.md
- Lines: 1-84
- SHA256: 4f38df2ec2ecdb948562b70a8f1d9a09171fc98815a2222abef6b3445f911713

[TRUNCATED]

```md
## ADDED Requirements

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

```

Full source: openspec/changes/add-langsmith-monitoring/specs/langsmith-monitoring/spec.md
