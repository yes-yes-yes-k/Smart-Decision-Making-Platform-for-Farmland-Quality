# Comet Design Handoff

- Change: refactor-routing-to-question-type
- Phase: design
- Mode: compact
- Context hash: 4d42c6133688692823917074884f3277bee7008934247803141a92964a2ba548

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/refactor-routing-to-question-type/proposal.md

- Source: openspec/changes/refactor-routing-to-question-type/proposal.md
- Lines: 1-55
- SHA256: 6963c4384c913262dca7ead18b6fce9d61cf6376f033f6fad69fa8955006fead

```md
## Why

当前多智能体路由基于用户角色（province/county/farmer）固定调用模型组合，导致每个问题被路由到多个模型（如 farmer 角色固定调用 model-4/5/6/7），即使问题只涉及其中一个领域。这种 role-based 路由产生冗余调用、需要 `_should_execute_agent` 二次关键词过滤补救，且与已稳定的 `identify_question_type`（type 1-5）能力重复。

将路由改为 question_type-based（1:1 映射）后，每个问题精准调用对应单一模型，消除二次过滤逻辑，简化心智模型，使路由语义与用户问题领域直接对应。

## What Changes

- **BREAKING** 移除 `RoleRouter` 的 `ROLE_KEYWORDS`、`ROLE_AGENTS`、`identify_role`、`get_agents_for_role`，替换为 `TYPE_AGENTS`（question_type → 单一 model_id 映射）和 `get_agents_for_type`
- **BREAKING** `AgentManager.process` 改为接收 `question_type` 参数，按 `TYPE_AGENTS` 路由；移除 `_should_execute_agent` 二次过滤逻辑及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量
- **BREAKING** API 响应移除 `role` 字段；保留 `question_type`、`agents_invoked`、`summary`、`recommendations`
- 新增 question_type=5 → model-7 的 1:1 映射（原 farmer 角色下 model-7 受关键词过滤，现由路由直接保证）
- `execute_models` 节点透传 `question_type` 到 `AgentManager.process` 的 context
- `QUESTION_TYPE_TO_MODEL_ID` 字典新增 `5: "model-7"` 条目
- question_type=0（识别失败/知识性问题）走 RAG，行为不变
- 新增知识性问题预检：`identify_question_type` 在关键词匹配前检测知识性问题模式（「什么是」「何为」「解释」「是什么意思」「什么意思」「定义」「概念」「含义」），命中则返回 type 0 走 RAG，避免知识性问题被领域关键词误路由到专业模型
- model-2、model-5 保留注册（向后兼容），但不被任何 question_type 路由调用
- 1:1 映射表：type 1→model-1、type 2→model-4、type 3→model-3、type 4→model-6、type 5→model-7

## Capabilities

### New Capabilities

无。本次变更是对现有路由架构的重构，不引入新能力。

### Modified Capabilities

- `role-based-routing`: 重写 spec——移除「用户角色识别」requirement，将「智能体组合执行」「API 集成」「Question Type Identification」改为 question_type-based 1:1 路由语义。spec 目录名保持 `role-based-routing` 不变（避免目录重命名复杂度），但内容完全替换为 question_type 路由规则。
- `multi-agent-orchestrator`: 更新「Type 5 质量等级评价问题库」requirement 的 Scenario——从「type 5 + farmer 角色 → model-4/5/6/7 + model-7 关键词过滤」改为「type 5 → 仅 model-7」；移除「model-7 问题感知过滤」requirement（路由已保证，无需二次过滤）。

## Impact

**代码影响**：
- `framework/agents/router.py` — 完全重写（约 30 行 → 约 20 行）
- `framework/agents/manager.py` — process 方法重写，删除 _should_execute_agent 及相关常量（约减少 40 行）
- `framework/agents/nodes.py` — execute_models 透传 question_type，QUESTION_TYPE_TO_MODEL_ID 加 type 5（约 5 行改动）
- `framework/api/routes/chat.py` — 移除 role 字段读取和写入（约 5 行删除）

**测试影响**：
- `tests/test_agent_manager.py` — 重写所有 role 断言为 question_type 断言（约 15 个测试用例改动）
- `tests/test_multi_agent.py` — 验证 type 5 路由到 model-7
- 其他依赖 role 字段的测试需排查

**API 影响**：
- **BREAKING**：`POST /api/v1/chat/` 响应 `data.role` 字段移除。客户端不应再依赖该字段。
- `data.question_type`、`data.agents_invoked`、`data.summary`、`data.recommendations` 保持不变。

**依赖关系**：
- 无新增依赖
- model-2/model-5 智能体实现保留，但不再被路由调用

**向后兼容**：
- `identify_question_type` 关键词和向量识别逻辑不变
- `parcel_id`/`parcel_code` 透传逻辑不变
- RAG 链路（type=0）不变

```

## openspec/changes/refactor-routing-to-question-type/design.md

- Source: openspec/changes/refactor-routing-to-question-type/design.md
- Lines: 1-184
- SHA256: 95ee9bbe23ffd58d4edb7fc70388694a3d05e3d40a7a366f220b82b9b52ab982

[TRUNCATED]

```md
## Context

当前多智能体框架采用 **role-based 路由**：`RoleRouter` 通过关键词识别用户角色（province/county/farmer），每个角色固定映射到一组 agents。`AgentManager.process` 调用 `identify_role` → `get_agents_for_role` → `_execute_with_dependencies`，其中 `_should_execute_agent` 对 model-6/model-7 做二次关键词过滤。

与此同时，`nodes.py` 中已存在稳定的 `identify_question_type` 函数，基于关键词+向量相似度识别 5 种问题类型（type 1-5）。`QUESTION_TYPE_TO_MODEL_ID` 字典已建立 type→model 映射（但缺少 type 5）。两套路由机制并存导致：

1. 冗余调用：farmer 问「我的田质量等级」会路由到 model-4/5/6/7 全部，再靠 `_should_execute_agent` 跳过 model-4/5/6
2. 语义重复：role 识别和 question_type 识别都在做问题分类
3. 心智负担：开发者需同时理解 role 路由 + question_type 路由 + 二次过滤三层逻辑

本次重构将路由统一为 question_type-based，消除冗余层次。

## Goals / Non-Goals

**Goals:**
- 将 `AgentManager.process` 的路由依据从 `role` 改为 `question_type`
- 实现 question_type → model 的 1:1 映射（type 1→model-1、type 2→model-4、type 3→model-3、type 4→model-6、type 5→model-7）
- 移除 `_should_execute_agent` 二次过滤逻辑（路由本身已保证精准性）
- 移除 API 响应中的 `role` 字段
- 保持 `identify_question_type`、`parcel_id`/`parcel_code` 透传、RAG 链路（type=0）不变

**Non-Goals:**
- 不修改 `identify_question_type` 的现有关键词列表和向量识别逻辑（但新增知识性问题预检分支）
- 不修改各专业模型（model-1/3/4/6/7）的内部实现
- 不重构 LangGraph 工作流节点拓扑（`initialize_state` → `identify_question_node` → `route_models` → `execute_models`/`rag_chat_node` → `llm_generate` → `aggregate_results`）
- 不移除 model-2/model-5 的注册（保留向后兼容，仅不被路由调用）
- 不重命名 `role-based-routing` spec 目录（仅修改内容）

## Decisions

### Decision 1: 1:1 映射而非 1:N

**选择**：每个 question_type 严格映射到单一 model（type 3→model-3 而非 model-2+model-3，type 4→model-6 而非 model-5+model-6）。

**理由**：
- 用户示例明确暗示 1:1（「障碍诊断问题调用诊断模型」「耕地质量评价调用 model7」均用单数）
- 1:1 消除拓扑排序复杂性，无需处理 model-3 依赖 model-2 的依赖链
- model-2（PotentialAssessmentAgent）和 model-5（OrganicMatterAgent）当前为桩/未完整实现，调用它们无实际价值
- 路由精准性由 `identify_question_type` 保证，无需多模型协同

**备选方案考虑**：
- 1:N（保留依赖链）：会保留冗余调用和拓扑排序复杂性，与重构目标相悖
- 混合（type 3 用 1:N，type 4 用 1:1）：增加心智负担，无充分理由

### Decision 2: 移除 `_should_execute_agent` 而非保留

**选择**：完全删除 `_should_execute_agent` 方法及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量。

**理由**：
- 1:1 路由后，question_type 已精确决定调用哪个模型，二次过滤是冗余
- model-6 仅在 type 4 时调用（type 4 关键词已含肥力语义），无需再检查肥力关键词
- model-7 仅在 type 5 时调用（type 5 关键词已含等级语义），无需再检查等级关键词
- 移除后 `_execute_with_dependencies` 逻辑简化，每个 agent 直接执行

**备选方案考虑**：
- 保留作为「双保险」：增加维护成本，且关键词列表重复（GRADE_KEYWORDS 镜像 QUESTION_TYPE_5_KEYWORDS）

### Decision 3: `AgentManager.process` 通过 context 接收 question_type

**选择**：`process(question, context)` 从 `context.get("question_type")` 读取 question_type，不改变方法签名。

**理由**：
- 保持向后兼容（现有调用方无需改签名）
- `execute_models` 已构建 context dict，新增 `context["question_type"] = state.get("question_type")` 即可
- question_type=0（识别失败）时，`TYPE_AGENTS` 查不到对应 key，回退到调用所有真实模型——但这不会发生，因为 type=0 在 `route_models` 阶段已路由到 `rag_chat_node`，不会进入 `execute_models`

**备选方案考虑**：
- 改签名为 `process(question, context, question_type)`：更显式但破坏所有调用方
- 新增 `process_by_type(question_type, question, context)`：增加 API 表面积

### Decision 4: type=0 仍走 RAG，不在 AgentManager 处理

**选择**：保持现有 `route_models` 逻辑——type=0 → `rag_chat_node`，type≠0 → `execute_models`。

**理由**：
- type=0 是「识别失败/通用问题」，走 RAG 知识库是合理兜底
- 调用所有真实模型会产生大量无关回答，UX 不佳
- 用户明确选择保留现有行为

### Decision 5: `TYPE_AGENTS` 定义在 `router.py`，`RoleRouter` 类重命名为 `QuestionTypeRouter`

```

Full source: openspec/changes/refactor-routing-to-question-type/design.md

## openspec/changes/refactor-routing-to-question-type/tasks.md

- Source: openspec/changes/refactor-routing-to-question-type/tasks.md
- Lines: 1-45
- SHA256: 990b4882248fa7bd4f5d3d5e058d6d041af5efe36d8d5c6b62983f1939531d69

```md
## 1. Router 重构（TDD）

- [ ] 1.1 编写 `QuestionTypeRouter` 单元测试：验证 `TYPE_AGENTS` 映射（1→model-1、2→model-4、3→model-3、4→model-6、5→model-7）和 `get_agents_for_type(question_type)` 返回对应列表；验证未知 type 返回空列表
- [ ] 1.2 重写 `framework/agents/router.py`：将 `RoleRouter` 类重命名为 `QuestionTypeRouter`，删除 `ROLE_KEYWORDS`、`ROLE_AGENTS`、`identify_role`、`get_agents_for_role`，新增 `TYPE_AGENTS` 字典和 `get_agents_for_type` 方法
- [ ] 1.3 验证 router 单元测试通过

## 2. AgentManager 重构（TDD）

- [ ] 2.1 编写 `AgentManager.process` 的 question_type 路由测试：为 type 1/2/3/4/5 各编写一个测试，验证仅调用对应的单一模型（如 type 3 仅调 model-3，不调 model-2；type 4 仅调 model-6，不调 model-5；type 5 仅调 model-7，不调 model-4/5/6）
- [ ] 2.2 编写 `_should_execute_agent` 移除后的回归测试：验证非 type 5 问题不会在 `details` 中出现 model-7 的 `skipped` 条目（因路由未包含 model-7）
- [ ] 2.3 重写 `framework/agents/manager.py`：`process` 方法从 `context.get("question_type")` 读取类型，调用 `router.get_agents_for_type(question_type)` 获取 agent_ids；`_summarize` 移除 `role` 参数，改用 `question_type`
- [ ] 2.4 删除 `_should_execute_agent` 方法及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量；从 `_execute_with_dependencies` 中移除 `_should_execute_agent` 调用
- [ ] 2.5 验证 AgentManager 测试通过

## 3. nodes.py 透传 question_type

- [ ] 3.1 修改 `framework/agents/nodes.py` 的 `execute_models` 函数：在构建 context 时新增 `context["question_type"] = state.get("question_type")`
- [ ] 3.2 更新 `QUESTION_TYPE_TO_MODEL_ID` 字典新增 `5: "model-7"` 条目
- [ ] 3.3 验证 `test_execute_models_pipeline.py` 测试通过（如需更新断言则同步修改）

## 4. API 响应移除 role 字段

- [ ] 4.1 修改 `framework/api/routes/chat.py`：删除 `role = agent_data.get("role")` 行和 `if role: response_data["role"] = role` 块
- [ ] 4.2 验证 API 响应不再包含 `role` 字段，`question_type`、`agents_invoked`、`summary`、`recommendations` 字段保持不变

## 5. 测试套件更新

- [ ] 5.1 重写 `tests/test_agent_manager.py` 中所有 `role` 相关断言：`test_manager_process_farmer_returns_structured_result`、`test_manager_process_unknown_question_defaults_farmer`、`test_farmer_role_includes_model_7` 等改为 question_type 断言
- [ ] 5.2 移除已失效的测试：`test_should_execute_model6_fertility_question`、`test_should_skip_model6_non_fertility_question`、`test_should_execute_model7_grade_question`、`test_should_skip_model7_non_grade_question`、`test_grade_keywords_mirrors_question_type_5`、`test_model6_skipped_in_details_for_non_fertility`、`test_model7_skipped_in_details_for_non_grade_farmer_question`
- [ ] 5.3 新增 type 1-5 路由到单一模型的集成测试（在 `test_multi_agent.py` 或新文件中）
- [ ] 5.4 运行完整测试套件（`pytest tests/`）确认全部通过，无残留 role 引用

## 6. 端到端验证

- [ ] 6.1 运行 `python scripts/gen_full_verification_report.py` 确认 23 个问题回答结果不变（特别是 type 5 的 Q21/Q22/Q23 仍返回真实 model-7 结果）
- [ ] 6.2 验证 API 响应字段符合 spec：无 `role` 字段，含 `question_type`、`agents_invoked`；type 5 问题的 `agents_invoked` 仅含 `model-7`
- [ ] 6.3 新增知识性问题验证用例：确认「什么是土壤酸化」「耕地质量等级是什么意思」走 RAG 而非专业模型

## 7. 知识性问题检测（TDD）

- [ ] 7.1 编写 `_is_knowledge_question` 单元测试：验证开头匹配（"什么是X"、"何为X"、"解释X"）和包含匹配（"X是什么意思"、"X什么意思"、"X定义"、"X概念"、"X含义"）均返回 True；验证具体诊断问题（"我的田耕地质量等级是多少"、"我的田酸化严重吗"）返回 False
- [ ] 7.2 在 `framework/agents/nodes.py` 中新增 `KNOWLEDGE_QUESTION_PATTERNS_START`、`KNOWLEDGE_QUESTION_PATTERNS_CONTAIN` 常量和 `_is_knowledge_question` 函数
- [ ] 7.3 修改 `identify_question_type` 函数：在最前端调用 `_is_knowledge_question`，命中则返回 `(0, 1.0)` 走 RAG
- [ ] 7.4 编写 `identify_question_type` 集成测试：验证「什么是土壤酸化」返回 type 0（而非 type 2）；「耕地质量等级是什么意思」返回 type 0（而非 type 5）；「我的田耕地质量等级是多少」仍返回 type 5
- [ ] 7.5 验证知识性问题检测测试通过，且不影响现有 type 1-5 路由测试

```

## openspec/changes/refactor-routing-to-question-type/specs/multi-agent-orchestrator/spec.md

- Source: openspec/changes/refactor-routing-to-question-type/specs/multi-agent-orchestrator/spec.md
- Lines: 1-30
- SHA256: cc0230dfb3de6b7dcb4aa7edb2513a03af0fb55272020e4a469a068e8728ca81

```md
## REMOVED Requirements

### Requirement: model-7 问题感知过滤
**Reason**: 本次重构将路由改为 question_type-based 1:1 映射后，model-7 仅在 question_type=5 时被 `TYPE_AGENTS` 路由调用，路由本身已保证 model-7 不会在非质量等级问题上执行。`AgentManager._should_execute_agent` 二次关键词过滤逻辑完全移除，无需单独为 model-7 维护过滤要求。
**Migration**: 不再需要 `GRADE_KEYWORDS` 常量镜像 `QUESTION_TYPE_5_KEYWORDS`。type 5 问题的路由由 `identify_question_type` 关键词识别 + `TYPE_AGENTS[5] = ["model-7"]` 映射共同保证。非 type 5 问题不会进入 model-7 的执行路径。

## MODIFIED Requirements

### Requirement: Type 5 质量等级评价问题库
系统 SHALL 在 `REFERENCE_QUESTIONS` 字典中维护 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」），使验证脚本能覆盖 model-7。

`_identify_question_type_keyword` 函数 SHALL 维护 type 5 分支，当问题命中 `QUESTION_TYPE_5_KEYWORDS`（"质量等级"、"等级评价"、"综合指数"、"指标隶属度"、"障碍度排序"、"耕地质量等级"、"质量评价"、"等级评定"、"指标权重"）时返回 `(5, relevance)`。

`TYPE_AGENTS` 映射表 SHALL 将 question_type=5 严格映射到 `["model-7"]`（1:1 映射），SHALL NOT 包含 model-4/5/6。type 5 问题的路由 SHALL NOT 依赖用户角色识别（role-based 路由已移除）。

#### Scenario: 识别质量等级问题为 type 5
- **WHEN** 用户询问「我的田耕地质量等级是多少」
- **THEN** `identify_question_type` SHALL 返回 `question_type=5`

#### Scenario: type 5 问题仅路由到 model-7
- **WHEN** 问题被识别为 type 5
- **THEN** `QuestionTypeRouter.get_agents_for_type(5)` SHALL 返回 `["model-7"]`
- **AND** `AgentManager.process` SHALL 仅调用 model-7（FarmlandGradeAgent）
- **AND** SHALL NOT 调用 model-4/5/6
- **AND** model-7 SHALL 被执行（status ≠ `skipped`），无需 `_should_execute_agent` 二次过滤

#### Scenario: 非 type 5 问题不调用 model-7
- **WHEN** 问题被识别为 type 1/2/3/4（如「我的田肥力怎么样」识别为 type 4）
- **THEN** `AgentManager.process` SHALL NOT 调用 model-7
- **AND** SHALL NOT 在 `details` 中出现 model-7 的 `skipped` 条目（因路由未包含 model-7）

```

## openspec/changes/refactor-routing-to-question-type/specs/role-based-routing/spec.md

- Source: openspec/changes/refactor-routing-to-question-type/specs/role-based-routing/spec.md
- Lines: 1-139
- SHA256: abd837f6383796d792f15b3d73e42f0c712f07fe69319975ee742340599c7025

[TRUNCATED]

```md
## REMOVED Requirements

### Requirement: 用户角色识别
**Reason**: 本次重构将路由依据从用户角色（province/county/farmer）改为问题类型（question_type 1-5）。角色识别逻辑（`ROLE_KEYWORDS` 关键词匹配、`identify_role` 方法、`ROLE_AGENTS` 角色到智能体映射）完全移除，由 `identify_question_type` + `TYPE_AGENTS` 1:1 映射取代。
**Migration**: 客户端不应再依赖 API 响应中的 `role` 字段。改用 `question_type` 字段（1=稳定性、2=酸化、3=障碍诊断、4=肥力、5=质量等级、0=通用/RAG）。`RoleRouter` 类重命名为 `QuestionTypeRouter`，`get_agents_for_role(role)` 替换为 `get_agents_for_type(question_type)`。

## MODIFIED Requirements

### Requirement: 智能体组合执行
系统 SHALL 根据 `question_type` 路由结果，按 1:1 映射执行对应的单一专业智能体，并将结果汇总返回。`TYPE_AGENTS` 映射表定义如下：

- question_type=1 → model-1（StabilityRiskAgent）
- question_type=2 → model-4（AcidificationRemediationAgent）
- question_type=3 → model-3（ProblemIdentificationAgent）
- question_type=4 → model-6（FertilityMLAgent）
- question_type=5 → model-7（FarmlandGradeAgent）
- question_type=0 → 不调用 AgentManager，走 RAG 链路（由 `route_models` 节点保证）

系统 SHALL NOT 对已路由的智能体进行二次关键词过滤（移除 `_should_execute_agent` 方法）。每个 question_type 严格对应单一模型，路由即执行。

model-2（PotentialAssessmentAgent）和 model-5（OrganicMatterAgent）SHALL 保留在 `AgentManager.agents` 注册表中用于向后兼容，但 SHALL NOT 出现在 `TYPE_AGENTS` 映射中，即不被任何 question_type 路由调用。

#### Scenario: type 1 问题仅调用 model-1
- **WHEN** 用户问题被 `identify_question_type` 识别为 type 1（如「我的这块田质量等级稳不稳」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-1（StabilityRiskAgent）
- **AND** SHALL NOT 调用 model-2/3/4/5/6/7

#### Scenario: type 2 问题仅调用 model-4
- **WHEN** 用户问题被识别为 type 2（如「我的田酸化了，pH 是 XX，我要施加多少碱性调理剂」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-4（AcidificationRemediationAgent）
- **AND** SHALL NOT 调用其他模型

#### Scenario: type 3 问题仅调用 model-3
- **WHEN** 用户问题被识别为 type 3（如「我这块地到底有啥毛病」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-3（ProblemIdentificationAgent）
- **AND** SHALL NOT 调用 model-2（PotentialAssessmentAgent）

#### Scenario: type 4 问题仅调用 model-6
- **WHEN** 用户问题被识别为 type 4（如「我的田肥力怎么样」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-6（FertilityMLAgent）
- **AND** SHALL NOT 调用 model-5（OrganicMatterAgent）

#### Scenario: type 5 问题仅调用 model-7
- **WHEN** 用户问题被识别为 type 5（如「我的田耕地质量等级是多少」）
- **THEN** `AgentManager.process` SHALL 仅调用 model-7（FarmlandGradeAgent）
- **AND** SHALL NOT 调用 model-4/5/6

#### Scenario: 单智能体直接回答
- **WHEN** 路由结果只包含一个智能体（1:1 映射的常态）
- **THEN** 系统 SHALL 直接调用该智能体的 `answer_question` 方法返回结果

### Requirement: API 集成
系统 SHALL 通过现有 `/api/v1/chat/` 接口集成多智能体框架，用户提问后触发基于 `question_type` 的智能体调度。

#### Scenario: 聊天接口触发多智能体
- **WHEN** 用户通过 `/api/v1/chat/` 接口提交问题
- **THEN** 系统 SHALL 调用 AgentManager 进行 question_type 路由和智能体调度，返回综合结果
- **AND** SHALL NOT 在响应中返回 `role` 字段（已移除）

#### Scenario: 返回结构化结果
- **WHEN** 多智能体执行完成
- **THEN** API SHALL 返回包含 `question_type`、`agents_invoked`、`summary` 和 `recommendations` 的结构化 JSON 响应
- **AND** SHALL NOT 包含 `role` 字段

### Requirement: Question Type Identification
系统 SHALL 根据用户问题识别问题类型（question_type），路由到对应的专业模型。问题类型关键词 SHALL 覆盖 `专业模型总览表(2).xlsx` 中 3 角色（省市管理端、县域执行端、农户种植端）的经典问题。

问题类型与模型 1:1 映射：
- TYPE_1（等级稳定性/退化风险）→ StabilityRiskAgent (model-1)
- TYPE_2（酸化程度/调理剂/改良方案）→ AcidificationRemediationAgent (model-4)
- TYPE_3（潜力/障碍因素/主要问题）→ ProblemIdentificationAgent (model-3)
- TYPE_4（有机质/有机肥/肥力/有机碳）→ FertilityMLAgent (model-6)
- TYPE_5（耕地质量等级评价/综合指数/障碍度排序）→ FarmlandGradeAgent (model-7)

系统 SHALL NOT 将 TYPE_3 路由到 model-2（PotentialAssessmentAgent），SHALL NOT 将 TYPE_4 路由到 model-5（OrganicMatterAgent）。model-2 和 model-5 保留注册但不被路由调用。

系统 SHALL 在 `identify_question_type` 函数最前端执行知识性问题预检（`_is_knowledge_question`），命中知识性问题模式时直接返回 `(0, 1.0)` 走 RAG，先于 relevance 检查和领域关键词匹配。知识性问题模式 SHALL 包含：
- 开头匹配（强信号）：`"什么是"`、`"何为"`、`"解释"`
- 包含匹配（含义类）：`"是什么意思"`、`"什么意思"`、`"定义"`、`"概念"`、`"含义"`


```

Full source: openspec/changes/refactor-routing-to-question-type/specs/role-based-routing/spec.md
