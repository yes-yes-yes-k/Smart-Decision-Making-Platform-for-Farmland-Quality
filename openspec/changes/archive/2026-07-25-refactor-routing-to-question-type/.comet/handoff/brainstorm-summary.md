# Brainstorm Summary

- Change: refactor-routing-to-question-type
- Date: 2026-07-26

## 确认的技术方案

### 1. question_type-based 1:1 路由
- `RoleRouter` → `QuestionTypeRouter`，`TYPE_AGENTS` 字典映射 type 1-5 到单一 model
- type 1→model-1、type 2→model-4、type 3→model-3、type 4→model-6、type 5→model-7
- model-2/model-5 保留注册但不路由

### 2. AgentManager.process 重构
- 从 `context.get("question_type")` 读取类型，调用 `router.get_agents_for_type(question_type)`
- 防御性行为：question_type 为 None/0/未知 → 返回 `{status: "no_routing", data: {question_type, agents_invoked: [], summary: "未识别问题类型", details: {}, recommendations: []}}`
- `_summarize` 签名：`(question_type, agent_ids, results)` 替换 `(role, agent_ids, results)`

### 3. 移除 _should_execute_agent
- 完全删除 `_should_execute_agent` 方法及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量
- `_execute_with_dependencies` 中每个 agent 直接执行，无二次过滤

### 4. model-3 依赖清理
- `model-3.dependencies` 从 `["model-2"]` 改为 `[]`（1:1 映射后 model-2 永不与 model-3 同调，依赖是死代码）

### 5. 知识性问题预检（设计阶段新增）
- 在 `identify_question_type` 最前端插入 `_is_knowledge_question` 预检
- 开头匹配：`"什么是"`、`"何为"`、`"解释"`
- 包含匹配：`"是什么意思"`、`"什么意思"`、`"定义"`、`"概念"`、`"含义"`
- 命中则返回 `(0, 1.0)` 走 RAG，先于领域关键词匹配
- 保守模式避免误报具体诊断问题

### 6. API 响应
- 移除 `role` 字段
- 保留 `question_type`、`agents_invoked`、`summary`、`recommendations`

## 关键取舍与风险

- **1:1 vs 1:N**：选择 1:1，失去多模型协同，但 model-2/5 为桩实现，协同价值有限
- **移除 _should_execute_agent**：路由已保证精准性，二次过滤冗余；风险是若 identify_question_type 误判则无补救
- **知识性预检保守模式**：精度优先，可能漏报「为什么」「区别」类；测试覆盖边界场景
- **spec 目录名不一致**：`role-based-routing` 目录保留但内容改为 question_type-based，避免 git 重命名复杂度
- **BREAKING**：API 移除 `role` 字段，客户端需改用 `question_type`

## 测试策略

- **TDD 顺序**：先写失败测试 → 实现 → 验证通过
- `tests/test_question_type_router.py`（新建）：QuestionTypeRouter 单元测试
- `tests/test_agent_manager.py`：重写 role 断言为 question_type；删除 _should_execute_agent 测试；新增 type 1-5 路由测试和 no_routing 测试
- `tests/test_multi_agent.py`：新增 type 5 → model-7 路由测试
- `tests/test_knowledge_question.py`（新建）：_is_knowledge_question 和 identify_question_type 知识性问题检测测试
- 端到端：运行 gen_full_verification_report.py 确认 23 问题回答不变 + 新增知识性问题验证

## Spec Patch

已回写 `specs/role-based-routing/spec.md` 的「Question Type Identification」requirement，新增 5 个知识性问题检测 Scenarios（开头匹配走 RAG、含义匹配走 RAG、解释类走 RAG、具体诊断问题不误判×2）。同时更新 proposal.md 和 design.md 反映知识性问题检测范围扩展。
