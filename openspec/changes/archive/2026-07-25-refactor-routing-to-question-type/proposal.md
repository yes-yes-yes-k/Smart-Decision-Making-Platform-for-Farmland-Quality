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
