# 单地块综合诊断与改良报告编排设计

## 1. 背景

参考资料《提示词设计.docx》及其流程图展示了一条由意图识别、任务规划、参数补齐、模型工具调用、证据检索、报告生成和两次人工确认组成的工作流。其可复用价值主要在于：角色化 Prompt、结构化计划、缺参恢复、人工中断、确定性工具和报告溯源。它本质上是受控工作流，不是多个自治 Agent 自由协商。

当前项目已经具备 LangGraph 编排、RAG、LLM/关键词路由、Function Calling、`AgentManager`、能力目录和模型 1—5 的工具入口，但当前专业问题仍按 `question_type -> 单个 agent` 一对一路由。现有图没有综合任务计划、跨模型依赖、checkpoint 恢复、统一人工确认和报告预览。流式与非流式聊天也存在重复组装逻辑。

本设计在保留现有快路径的前提下，新增一条面向“单地块综合诊断与改良报告”的受约束任务路径。第一阶段不扩展到县域批处理、任意工作流生成或自治 Agent 群聊。

## 2. 目标

- 保持知识问答和单模型分析的现有速度、路由语义与响应兼容性。
- 支持单地块综合质量评价、障碍诊断、条件专项分析和改良报告。
- 允许 LLM 生成结构化计划，但所有执行权由确定性校验、调度和状态机掌握。
- 仅在关键输入缺失、结果相关默认值、高成本任务或上下文变化时中断用户。
- 使用 checkpoint 跨请求恢复，不因确认或补参重复执行已完成任务。
- 确保每个数值和关键主张可追溯到模型结果、数据版本或知识来源。
- 可选模型失败时允许显式降级；核心模型失败时禁止生成正式综合报告。
- 通过 feature flag 和 shadow mode 渐进上线，不一次性替换现有编排器。

## 3. 非目标

- 不在本阶段实现多地块、县域或批量诊断。
- 不允许 Planner 创建新模型、任意代码、SQL 或工具。
- 不实现 Agent 之间的自由对话、互相委派或无界循环。
- 不修改模型 1—5 的领域算法。
- 不把当前占位的模型 6 当作真实综合计算模型；综合报告由确定性汇总和 Reporter 生成。
- 不改变知识库摄取、索引或检索算法本身。
- 不实现新的报告编辑器 UI；只定义后端交互状态和 API 契约。
- 不允许生产路径使用 MOCK 地块、默认区域或模拟模型结果。

## 4. 选定方案与备选方案

采用“受约束 Planner + 确定性执行图”。LLM 负责识别意图、给出结构化任务计划、绑定证据和组织语言；代码负责白名单、依赖、输入、确认、执行、验证、重试、状态转移和溯源。

未采用的方案：

- 固定 DAG：最容易验证，但随着任务组合增加会产生大量分支，难以复用现有能力目录。
- 自治 Supervisor：扩展性强，但调用成本、可重复性、越权风险和调试难度不适合当前生产阶段。

## 5. 设计原则

1. **状态是唯一协作通道。** 各角色不直接自由对话，只读写经过 schema 约束的状态字段。
2. **规划不是授权。** Planner 的输出只有通过 `PlanValidator` 后才可执行。
3. **模型是工具，不是调度者。** 模型 1—5 只计算本领域结果，不能选择后续模型。
4. **先验证结果，再生成叙述。** 未通过 schema、对象、单位和溯源校验的结果不能进入报告。
5. **快慢路径隔离。** 未明确表达综合诊断/综合报告意图的请求默认保留现有快路径。
6. **可恢复且幂等。** 所有中断状态都能恢复；同一 `task_id` 不重复产生模型副作用。
7. **无证据不主张。** Reporter 不得补写模型没有给出的数值或知识库没有支持的关键事实。

## 6. 总体架构

```text
用户请求
  -> Coordinator（严格枚举意图）
  -> TrafficGate（确定性分流）
       ├─ knowledge            -> 现有 RAG -> 简洁答复
       ├─ single_analysis      -> 现有一对一模型路由 -> 简洁答复
       ├─ unsupported          -> 明确拒绝/能力说明
       └─ comprehensive_analysis
            -> AnalysisContextGuard
            -> DiagnosticPlanner
            -> PlanValidator
            -> InputResolver
            -> ConfirmationPolicy / interrupt
            -> ExecutionScheduler（两波执行）
            -> ResultValidator
            -> EvidenceResearcher
            -> ReportComposer
            -> 发布确认 / 最多 3 次修订
            -> FinalResponse + Provenance
```

新任务路径作为独立子图接入现有 `MultiAgentOrchestrator`。现有 RAG 和单模型节点继续工作。图编译时启用 LangGraph checkpointer；每次综合任务使用独立 `run_id`，避免同一会话中的并发任务共享 checkpoint。

## 7. 角色与组件边界

### 7.1 LLM 控制角色

| 角色 | 唯一职责 | 允许输出 | 禁止行为 |
|---|---|---|---|
| Coordinator | 将请求归类 | `InteractionIntent` | 调工具、计算结果、生成任务计划 |
| DiagnosticPlanner | 从能力目录选择任务并描述原因 | `DiagnosticPlan` | 创建未知 Agent、修改输入、直接执行 |
| EvidenceResearcher | 为已验证结论检索并绑定证据 | `EvidenceBundle` | 重新解释模型数值、制造结论 |
| Reporter | 按固定结构组织用户可读报告 | `ReportPayload` | 修改数值、删除降级说明、生成溯源字段 |

所有角色 Prompt 均有显式版本号。结构化输出解析失败时只允许一次 schema 修复调用；第二次失败进入对应失败状态，不执行未经校验的文本。

### 7.2 确定性组件

| 组件 | 职责 |
|---|---|
| `TrafficGate` | 根据合法 `InteractionIntent` 选择快路径或任务路径 |
| `AnalysisContextGuard` | 复用当前分析对象设计，验证地块、权限、对象版本和计算模式 |
| `PlanValidator` | 校验 Agent 白名单、任务数、唯一性、依赖、输入和触发器 |
| `InputResolver` | 从地块快照和用户补充中解析任务输入，并记录来源 |
| `ConfirmationPolicy` | 根据确定性规则决定继续、补参或确认 |
| `ExecutionScheduler` | 按依赖分波执行，提供幂等、超时和受限重试 |
| `ResultValidator` | 校验状态、对象、schema、单位、数据时间和模型版本 |
| `ProvenanceBuilder` | 用代码生成不可变溯源包络 |
| `ReportPolicyValidator` | 检查报告中的数值、主张、来源、降级和修订上限 |

### 7.3 领域能力

能力目录是 Planner 可见的唯一工具清单。每项能力至少声明：

- `agent_id`、显示名称和版本；
- `supported_object_types`；
- `required_inputs` 和输入 schema；
- `result_schema`；
- `cost_class`；
- `timeout_seconds`；
- `retry_policy`；
- 是否为综合诊断核心任务；
- 允许的触发条件。

任务路径的 Function Calling 只绑定已验证计划中的工具，不再把全部模型工具暴露给 LLM 二次选择。

## 8. 路由规则

`InteractionIntent.kind` 只能取：

- `knowledge`：概念、政策、方法或知识库问答；
- `single_analysis`：明确只询问一个现有专题模型；
- `comprehensive_analysis`：明确请求单地块综合诊断、综合报告或完整改良方案；
- `unsupported`：超出系统能力。

为保持兼容，只有明确表达“综合诊断”“综合报告”“整体问题及改良方案”等意图时才进入任务路径。其余专业问题继续使用现有 `QuestionTypeRouter` 一对一路由。Coordinator 输出无效时先执行一次 schema 修复；仍无效则回退到现有确定性识别逻辑，但该回退不得把请求升级为综合任务。

## 9. 核心数据契约

### 9.1 InteractionIntent

```json
{
  "kind": "comprehensive_analysis",
  "confidence": 0.96,
  "reason_code": "EXPLICIT_COMPREHENSIVE_REPORT",
  "prompt_version": "coordinator-v1"
}
```

`reason_code` 必须来自预定义枚举；自由文本理由只允许写入调试元数据，不能参与路由。

### 9.2 DiagnosticPlan

```json
{
  "plan_version": 1,
  "analysis_mode": "single_parcel_comprehensive",
  "planner_prompt_version": "planner-v1",
  "tasks": [
    {
      "task_id": "quality-evaluation",
      "agent_id": "model-2",
      "required": true,
      "depends_on": [],
      "trigger": {"type": "always"}
    },
    {
      "task_id": "acidification-remediation",
      "agent_id": "model-4",
      "required": false,
      "depends_on": ["problem-diagnosis"],
      "trigger": {
        "type": "any",
        "predicates": ["user_requested_acidification", "acidification_evidence"]
      }
    }
  ],
  "planner_reason": "先完成质量与障碍诊断，再按证据触发专项改良。"
}
```

`PlanValidator` 强制以下规则：

- 最多 5 个任务，每个 `agent_id` 最多出现一次；
- 只允许 `model-1` 至 `model-5`；
- `model-2` 和 `model-3` 必须存在、标记为必需且无前置依赖；
- `model-1` 只允许在存在合格历史或预计算数据时触发；
- `model-4` 只允许在用户明确请求或酸化证据成立时触发；
- `model-5` 只允许在用户明确请求或有机质障碍证据成立时触发；
- `model-4`、`model-5` 即使由用户直接请求，也进入第二波执行；
- 所有依赖必须存在且无环；
- 工具别名、输入键和触发谓词必须来自能力目录。

Validator 不静默修补非法计划。规划失败只允许一次重新生成；再次失败返回 `FAILED_PLANNING`。

### 9.3 ComprehensiveDiagnosticState

状态至少包含：

```text
标识与控制
  run_id, trace_id, conversation_id, interaction_state,
  checkpoint_version, retry_count, error

请求与对象
  normalized_request, interaction_intent, output_mode,
  analysis_context_snapshot, object_version, calculation_mode

计划与输入
  diagnostic_plan, plan_version, resolved_inputs, missing_inputs,
  proposed_defaults, confirmation

执行与证据
  task_results, validation_issues, degradations, task_attempts,
  evidence_queries, evidence_items, unsupported_claims

报告与溯源
  report_payload, report_draft, report_revision_count,
  release_confirmation, provenance
```

`interaction_state` 只允许按下列方向前进：

```text
received -> planned
planned -> needs_analysis_object | needs_input | needs_confirmation | executing
needs_* -> planned | needs_confirmation | executing
executing -> validating
validating -> executing | researching | partial_complete | failed
researching -> draft_ready
draft_ready -> awaiting_release
awaiting_release -> draft_ready | completed
```

恢复请求必须携带 `run_id` 和 `expected_checkpoint_version`。版本过期返回 HTTP 409，不合并到新状态。

### 9.4 TaskResult

每个任务统一返回：

```json
{
  "task_id": "quality-evaluation",
  "agent_id": "model-2",
  "status": "succeeded",
  "payload": {},
  "key_inputs": [],
  "model_version": "...",
  "data_as_of": "...",
  "data_version": "...",
  "calculated_at": "...",
  "trace_id": "..."
}
```

领域 `payload` 由各能力自己的 schema 校验，其中所有对外数值字段必须带明确单位或由 schema 固定单位。

## 10. 单地块综合任务数据流

### 10.1 请求与对象解析

1. 归一化消息、会话、计算模式和交互响应。
2. 通过 `AnalysisContextGuard` 获取不可变地块快照和 `object_version`。
3. 对象缺失时进入 `needs_analysis_object`；对象不存在、越权或冲突时按既有分析对象规范返回错误。
4. 对象未通过验证时不得调用 Planner、模型工具或报告 LLM。

### 10.2 规划与智能确认

1. Planner 基于用户请求、能力目录和地块快照生成 `DiagnosticPlan`。
2. Validator 验证计划，不允许 Planner 结果直接进入调度器。
3. `InputResolver` 优先使用经验证的地块数据库字段，再使用本次用户输入；每项输入记录值、单位、来源和数据版本。
4. 以下任一情况进入 `needs_input` 或 `needs_confirmation`：
   - 缺少会改变模型结果的必需输入；
   - 计划使用会影响结论的默认值；
   - 任一任务在能力目录中标记为 `cost_class=high`；
   - 地块、上下文版本或已确认计划发生变化。
5. 数据库输入完整、采用标准无争议配置且没有高成本任务时自动继续。

确认对象是规范化计划摘要、关键输入、默认值、预计任务和地块快照的哈希。确认后任何相关字段变化都会使旧确认失效。

### 10.3 两波执行

第一波并行执行：

- `model-2`：质量等级评价，必需；
- `model-3`：障碍诊断，必需；
- `model-1`：仅当合格历史或预计算结果可用时执行。

第一波结果逐项通过 `ResultValidator` 后，调度器解析条件谓词。第二波执行：

- `model-4`：用户明确请求，或 `model-3`/权威指标形成酸化证据，且必要输入完整；
- `model-5`：用户明确请求，或障碍结论指向有机质，且必要输入完整。

每个任务使用稳定 `task_id` 作为幂等键。恢复时先读取已验证结果，只重放尚未成功的任务。对瞬时超时或临时服务不可用最多重试 2 次；对象、输入、schema、权限和数据来源错误不重试。

### 10.4 证据与报告

1. 只有已验证的 `TaskResult` 能生成证据查询和报告主张。
2. EvidenceResearcher 为解释性主张检索 RAG 证据，返回 `source_id`、文档元数据、关联主张和检索分数。
3. Reporter 按固定结构输出：分析对象、执行摘要、质量评价、障碍诊断、条件专项结果、优先改良措施、数据缺口/降级说明和溯源。
4. `ReportPolicyValidator` 将报告数值与 `TaskResult` 做精确对照，并检查所有关键主张的来源引用。
5. 首稿进入 `awaiting_release`。用户可以发布、终止或请求修改；首稿不计入修订次数，每次重新生成加 1，最多 3 次。
6. 达到 3 次后不再调用 Reporter；用户只能发布当前稿或结束任务。

Reporter 只生成报告正文和结构，`ProvenanceBuilder` 用代码写入对象、关键输入、模型版本、数据版本、计算时间、Prompt 版本、来源 ID 和 `trace_id`。

## 11. 交互与 API 契约

继续使用现有聊天入口，不新增平行聊天 API。初始请求沿用当前字段，并复用《AI 对话当前分析对象与结果溯源设计》中的 `analysis_context` 与 `calculation_mode`。

恢复请求增加：

```json
{
  "conversation_id": 12,
  "interaction_response": {
    "run_id": "...",
    "expected_checkpoint_version": 4,
    "action": "provide_input",
    "values": {"...": "..."},
    "comment": ""
  }
}
```

`action` 只能取：`provide_input`、`confirm_plan`、`request_revision`、`release_report`、`cancel`。不同 `interaction_state` 只接受对应 action，非法组合返回 HTTP 422。

正常交互状态使用 HTTP 200：

- `needs_analysis_object`；
- `needs_input`；
- `needs_confirmation`；
- `awaiting_release`；
- `completed`；
- `partial_complete`。

过期 checkpoint 返回 HTTP 409；对象或输入非法返回 HTTP 422；依赖服务不可用且没有安全降级时返回 HTTP 503。

非流式和流式请求必须复用同一服务方法、状态机和结果封装。SSE 在需要用户操作时发送 `interaction` 事件，最终都发送相同结构的 `done` 包络；流式路径不得手工复制另一套路由和结果汇总。

## 12. 失败、重试与降级

| 情况 | 动作 | 最终语义 |
|---|---|---|
| 缺对象、关键输入或确认 | 保存 checkpoint，等待补齐 | `needs_*`，可恢复 |
| Planner schema/计划非法 | 修复或重生成一次，仍失败则停止 | `failed_planning` |
| 瞬时超时、临时服务不可用 | 同一任务最多重试 2 次 | `retrying` 或后续失败语义 |
| 对象不一致、数据/schema 非法、来源缺失 | 立即停止该任务，不重试 | `failed_validation` |
| 可选 `model-1/4/5` 不可用 | 记录缺口，继续核心链路 | `partial_complete`，报告显式降级 |
| 核心 `model-2/3` 重试后失败 | 终止正式报告 | `failed`，只返回失败说明 |
| RAG 不可用 | 保留已验证模型事实，不生成外部解释性主张 | `partial_complete`，标明证据检索缺口 |
| Report 校验失败 | 重生成一次；再次失败停止 | `failed_reporting`，不发布未验证报告 |

所有异常记录 `run_id`、`trace_id`、节点、任务、错误类别、尝试次数和是否可重试。用户可见信息不包含堆栈或内部 Prompt。

## 13. 代码组织与现有模块适配

建议新增独立目录，避免继续扩大 `nodes.py`：

```text
framework/agents/workflows/comprehensive/
├── state.py
├── contracts.py
├── graph.py
├── coordinator.py
├── planner.py
├── validation.py
├── confirmation.py
├── scheduler.py
├── evidence.py
└── reporting.py
```

适配关系：

- `framework/agents/orchestrator.py`：保留顶层入口，增加 `TrafficGate` 和综合子图委派。
- `framework/agents/state.py`：保留快路径状态；综合状态放在新目录，避免把所有字段塞入现有浅状态。
- `framework/agents/capabilities.py`：扩展能力元数据，作为 Planner 和 Validator 的共同事实来源。
- `framework/agents/manager.py`：保留单模型快路径；综合路径通过受控调度器调用已注册 Agent，不复用当前一对一路由决策。
- `framework/agents/router.py`：继续维护快路径 `question_type -> 单 agent` 兼容规则。
- `framework/function_calling/specialized_tools.py`：保留模型适配器；增加按已验证任务生成受限工具集合的入口。
- `framework/agents/nodes.py`：逐步迁出流式手工分支和综合逻辑，不在该文件复制新状态机。
- `framework/api/routes/chat.py`：流式与非流式共享请求归一化、编排服务和响应封装。

参考架构中的“场景节点”不原样移植。项目已有模型能力目录和领域 result schema，用它们替代按场景维护的自由文本 Prompt，可减少重复规则和漂移。

## 14. 可观测性与审计

每个综合任务至少记录：

- `run_id`、`trace_id`、`conversation_id` 和对象快照；
- Coordinator、Planner、Researcher、Reporter 的 Prompt 版本；
- 原始计划、校验结果、确认摘要哈希和计划版本；
- 每个任务的排队、开始、完成、重试和耗时；
- 触发/跳过模型的确定性原因；
- 输入来源、模型版本、数据版本和计算时间；
- 报告主张与 `source_id`/`TaskResult` 的绑定；
- 降级原因、报告修订次数和最终发布动作。

敏感输入按现有日志策略脱敏。生产日志不得记录完整系统 Prompt、用户权限令牌或数据库凭证。

## 15. 测试策略

### 15.1 单元测试

- `InteractionIntent` 和 `DiagnosticPlan` 严格解析；
- 未知 Agent、重复任务、缺核心任务、非法依赖、环和超任务上限；
- 模型 1/4/5 的触发决策表；
- `ConfirmationPolicy` 的中断/不中断决策表；
- 输入来源优先级和确认失效哈希；
- `ResultValidator` 的对象、单位、版本、时间和来源检查；
- 报告数值对照、主张绑定和 3 次修订上限。

### 15.2 图与状态测试

- 每个合法状态转移和非法 action；
- `needs_analysis_object`、`needs_input`、`needs_confirmation` 和 `awaiting_release` 的 checkpoint 恢复；
- 过期 `checkpoint_version` 冲突；
- 相同 `task_id` 重复恢复时不重复调用；
- 两波执行顺序、并行核心任务、重试和降级分支；
- 核心失败不进入 Researcher 或 Reporter。

### 15.3 契约与集成测试

- 模型 1—5 现有 Agent/工具适配器的输入输出 schema；
- 对象守卫、地块数据库、模型执行日志和 LangGraph checkpointer；
- RAG 证据绑定与无结果分支；
- 流式与非流式 API 的交互状态、错误码和最终包络一致；
- feature flag 关闭时现有快路径完全不进入综合子图。

### 15.4 端到端金标场景

至少覆盖：

1. 完整地块成功生成综合报告；
2. 地块缺失后补齐并恢复；
3. 关键输入缺失或默认值需要确认；
4. `model-4`/`model-5` 分别触发和不触发；
5. 可选模型失败后生成带缺口说明的部分报告；
6. 核心模型失败后不生成正式报告；
7. RAG 无证据时不生成无来源主张；
8. 连续请求修订，第 4 次被拒绝；
9. 重复提交同一确认不会重复执行任务；
10. 知识问答和单模型请求仍走原快路径。

## 16. 渐进迁移

### 阶段 0：冻结基线与契约

- 建立快路径路由、响应和延迟基线；
- 增加状态、计划、任务结果和报告 schema；
- 建立角色 Prompt 版本目录与离线金标集。

进入下一阶段前，现有回归测试必须全部通过。

### 阶段 1：对象护栏与恢复

- 落地当前分析对象规范；
- 引入 checkpointer、`run_id`、交互状态和统一 API 组装；
- 此阶段不启用 Planner 和多模型执行。

进入下一阶段前，对象错配、越权和缺对象必须 100% 阻断模型调用。

### 阶段 2：只规划，不执行

- Coordinator、Planner、Validator 和 ConfirmationPolicy 以 shadow mode 运行；
- 记录与旧路由的差异，但不调用额外模型工具；
- 调整 Prompt 和确定性规则直到金标集通过。

进入下一阶段前，所有非法任务必须被 Validator 拒绝。

### 阶段 3：受控执行

- 在 feature flag 后启用两波调度、结果验证、幂等、重试和降级；
- 先对内部账号开启，再小流量试用。

进入下一阶段前，checkpoint 恢复不得产生重复模型调用。

### 阶段 4：证据报告与放量

- 启用 EvidenceResearcher、Reporter、报告校验和发布确认；
- 通过内部试点、小流量和默认开启三个发布档位推进；
- 任一验收指标退化时关闭综合任务 feature flag，快路径保持可用。

## 17. 验收标准

- 既有快路径回归集的路由与响应契约 100% 保持；P95 延迟不高于基线 10%。
- 未知 Agent、非法依赖、缺输入和超 5 个任务的计划 100% 被拒绝。
- 对象缺失、错配、越权或版本冲突时没有模型工具调用。
- `model-2`、`model-3` 在合法综合任务中始终执行；`model-1/4/5` 与触发决策表完全一致。
- 中断后可从同一 `run_id` 恢复；重复确认不重复调用已成功任务。
- 可选模型失败返回 `partial_complete` 并在报告显示缺口；核心模型失败不生成正式综合报告。
- 金标集中所有报告数值与 `TaskResult` 精确一致，所有关键主张都有 `source_id` 或模型结果绑定，未支持主张数为 0。
- 报告最多重新生成 3 次；超过上限不再调用 Reporter。
- 流式与非流式接口共享相同交互状态、错误码和最终数据包络。
- 每个正式结果都能回答：针对哪个地块、使用哪些关键输入、数据版本和时间、调用哪个模型与 Prompt 版本、何时计算以及如何追溯。

## 18. 与参考架构的取舍总结

保留：

- Coordinator、Planner、Researcher、Reporter 的角色分工；
- 结构化计划、缺参恢复、人工确认、工具调用和报告预览；
- 数值不篡改、证据绑定和报告修订上限。

调整：

- 将“场景 Prompt”改为项目现有能力目录、输入 schema 和结果 schema；
- 将五个模型从并列全量调用改为“核心第一波 + 证据驱动第二波”；
- 将 Function Calling 从全工具二次路由改为计划白名单内执行；
- 将模型 6 的综合职责拆成确定性汇总、证据检索和 Reporter，不把占位模型伪装为真实计算；
- 将人工确认从固定两次改为智能输入确认和必需的报告发布确认；
- 将所有节点纳入 checkpoint、幂等、错误语义、Prompt 版本和统一溯源。

该取舍使新架构与当前代码的 LangGraph、能力目录、模型工具、RAG 和分析对象规范兼容，同时为未来新增综合场景保留可验证的扩展点。
