## 1. Router 重构（TDD）

- [x] 1.1 编写 `QuestionTypeRouter` 单元测试：验证 `TYPE_AGENTS` 映射（1→model-1、2→model-4、3→model-3、4→model-6、5→model-7）和 `get_agents_for_type(question_type)` 返回对应列表；验证未知 type 返回空列表
- [x] 1.2 重写 `framework/agents/router.py`：将 `RoleRouter` 类重命名为 `QuestionTypeRouter`，删除 `ROLE_KEYWORDS`、`ROLE_AGENTS`、`identify_role`、`get_agents_for_role`，新增 `TYPE_AGENTS` 字典和 `get_agents_for_type` 方法
- [x] 1.3 验证 router 单元测试通过

## 2. AgentManager 重构（TDD）

- [x] 2.1 编写 `AgentManager.process` 的 question_type 路由测试：为 type 1/2/3/4/5 各编写一个测试，验证仅调用对应的单一模型（如 type 3 仅调 model-3，不调 model-2；type 4 仅调 model-6，不调 model-5；type 5 仅调 model-7，不调 model-4/5/6）
- [x] 2.2 编写 `_should_execute_agent` 移除后的回归测试：验证非 type 5 问题不会在 `details` 中出现 model-7 的 `skipped` 条目（因路由未包含 model-7）
- [x] 2.3 重写 `framework/agents/manager.py`：`process` 方法从 `context.get("question_type")` 读取类型，调用 `router.get_agents_for_type(question_type)` 获取 agent_ids；`_summarize` 移除 `role` 参数，改用 `question_type`
- [x] 2.4 删除 `_should_execute_agent` 方法及 `FERTILITY_KEYWORDS`、`GRADE_KEYWORDS` 常量；从 `_execute_with_dependencies` 中移除 `_should_execute_agent` 调用
- [x] 2.5 验证 AgentManager 测试通过

## 3. nodes.py 透传 question_type

- [x] 3.1 修改 `framework/agents/nodes.py` 的 `execute_models` 函数：在构建 context 时新增 `context["question_type"] = state.get("question_type")`
- [x] 3.2 更新 `QUESTION_TYPE_TO_MODEL_ID` 字典新增 `5: "model-7"` 条目
- [x] 3.3 验证 `test_execute_models_pipeline.py` 测试通过（如需更新断言则同步修改）

## 4. API 响应移除 role 字段

- [x] 4.1 修改 `framework/api/routes/chat.py`：删除 `role = agent_data.get("role")` 行和 `if role: response_data["role"] = role` 块
- [x] 4.2 验证 API 响应不再包含 `role` 字段，`question_type`、`agents_invoked`、`summary`、`recommendations` 字段保持不变

## 5. 测试套件更新

- [x] 5.1 重写 `tests/test_agent_manager.py` 中所有 `role` 相关断言：`test_manager_process_farmer_returns_structured_result`、`test_manager_process_unknown_question_defaults_farmer`、`test_farmer_role_includes_model_7` 等改为 question_type 断言
- [x] 5.2 移除已失效的测试：`test_should_execute_model6_fertility_question`、`test_should_skip_model6_non_fertility_question`、`test_should_execute_model7_grade_question`、`test_should_skip_model7_non_grade_question`、`test_grade_keywords_mirrors_question_type_5`、`test_model6_skipped_in_details_for_non_fertility`、`test_model7_skipped_in_details_for_non_grade_farmer_question`
- [x] 5.3 新增 type 1-5 路由到单一模型的集成测试（在 `test_multi_agent.py` 或新文件中）
- [x] 5.4 运行完整测试套件（`pytest tests/`）确认全部通过，无残留 role 引用

## 6. 端到端验证

- [ ] 6.1 运行 `python scripts/gen_full_verification_report.py` 确认 23 个问题回答结果不变（特别是 type 5 的 Q21/Q22/Q23 仍返回真实 model-7 结果）
- [ ] 6.2 验证 API 响应字段符合 spec：无 `role` 字段，含 `question_type`、`agents_invoked`；type 5 问题的 `agents_invoked` 仅含 `model-7`
- [ ] 6.3 新增知识性问题验证用例：确认「什么是土壤酸化」「耕地质量等级是什么意思」走 RAG 而非专业模型

## 7. 知识性问题检测（TDD）

- [x] 7.1 编写 `_is_knowledge_question` 单元测试：验证开头匹配（"什么是X"、"何为X"、"解释X"）和包含匹配（"X是什么意思"、"X什么意思"、"X定义"、"X概念"、"X含义"）均返回 True；验证具体诊断问题（"我的田耕地质量等级是多少"、"我的田酸化严重吗"）返回 False
- [x] 7.2 在 `framework/agents/nodes.py` 中新增 `KNOWLEDGE_QUESTION_PATTERNS_START`、`KNOWLEDGE_QUESTION_PATTERNS_CONTAIN` 常量和 `_is_knowledge_question` 函数
- [x] 7.3 修改 `identify_question_type` 函数：在最前端调用 `_is_knowledge_question`，命中则返回 `(0, 1.0)` 走 RAG
- [x] 7.4 编写 `identify_question_type` 集成测试：验证「什么是土壤酸化」返回 type 0（而非 type 2）；「耕地质量等级是什么意思」返回 type 0（而非 type 5）；「我的田耕地质量等级是多少」仍返回 type 5
- [x] 7.5 验证知识性问题检测测试通过，且不影响现有 type 1-5 路由测试
