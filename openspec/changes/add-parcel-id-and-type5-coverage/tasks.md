## 1. 路由层：farmer 角色追加 model-7

- [ ] 1.1 修改 `framework/agents/router.py` 的 `ROLE_AGENTS['farmer']`，追加 `model-7`，变为 `["model-4", "model-5", "model-6", "model-7"]`
- [ ] 1.2 在 `framework/agents/manager.py` 的 `_should_execute_agent` 中增加 model-7 关键词过滤：仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 任一关键词时执行 model-7，否则返回 `False`（跳过）
- [ ] 1.3 新增/更新单元测试 `tests/test_role_router.py`（或对应测试文件）：验证 farmer 角色返回 4 个 agent 含 model-7；验证 model-7 在非质量等级问题时被 `_should_execute_agent` 跳过

## 2. 问题类型识别：type 5 分支

- [ ] 2.1 修改 `framework/agents/nodes.py` 的 `_identify_question_type_keyword`，在 type 4 分支后新增 type 5 分支：当问题命中 `QUESTION_TYPE_5_KEYWORDS` 时返回 `(5, relevance)`
- [ ] 2.2 新增/更新单元测试：验证「我的田耕地质量等级是多少」识别为 type 5；验证「我的田肥力怎么样」仍识别为 type 4（非 5）

## 3. 问题库：REFERENCE_QUESTIONS 新增 type 5

- [ ] 3.1 在 `framework/agents/nodes.py` 的 `REFERENCE_QUESTIONS` dict 新增 key `5`，包含至少 3 个质量等级评价问题（如「我的田耕地质量等级是多少」「查询地块的综合指数和障碍度排序」「这块地的耕地质量等级评价结果」）
- [ ] 3.2 确认 type 5 问题文本包含 farmer 关键词（"我的田"/"地块"/"这块地"），使 RoleRouter 识别为 farmer 角色
- [ ] 3.3 新增/更新单元测试：验证 `REFERENCE_QUESTIONS[5]` 存在且非空；验证 type 5 问题经 `identify_question_type` 返回 5

## 4. 管道接通：execute_models 透传地块标识符

- [ ] 4.1 修改 `framework/agents/nodes.py` 的 `execute_models`，从 `state["request"]` 提取 `parcel_id` 和 `parcel_code`，加入 `context` 字典（与现有 `area_code`/`data`/`longitude`/`latitude`/`target_ph` 并列）
- [ ] 4.2 确认 `context["parcel_id"]` 透传到 `agent_manager.process(question, context)`，model-1/3/4 能读到
- [ ] 4.3 确认 `context["parcel_code"]` 透传到 `agent_manager.process(question, context)`，model-7 能读到
- [ ] 4.4 新增/更新单元测试：验证 `execute_models` 在 request 含 `parcel_id`/`parcel_code` 时正确透传到 context（可用 monkeypatch 拦截 `agent_manager.process` 检查 context 内容）

## 5. 生产 API：接受 parcel_id/parcel_code

- [ ] 5.1 找到生产 API 路由文件（`POST /api/v1/chat/` 端点），在 request 解析逻辑中新增可选字段 `parcel_id`（string）和 `parcel_code`（string）
- [ ] 5.2 将 `parcel_id`/`parcel_code` 传入 `multi_agent_orchestrator.run(request)` 的 request dict
- [ ] 5.3 更新 API 文档/README：说明 `parcel_id`（数字，用于 DB 查询）和 `parcel_code`（字母数字，用于质量等级评价）的用途和可选性
- [ ] 5.4 新增/更新 API 集成测试：验证带 `parcel_id`/`parcel_code` 的请求被正确透传

## 6. 验证脚本：预设地块标识符 + type 5 覆盖

- [ ] 6.1 修改 `scripts/gen_full_verification_report.py`：扩展 `run_one_question` 接受可选 `parcel_id`/`parcel_code` 参数，传入 `orchestrator.run` 的 request
- [ ] 6.2 为 type 1-4 的 farmer 问题预设 `parcel_id="1"`（来自 stability_db/diagnosis_db）
- [ ] 6.3 为 type 5 问题预设 `parcel_code="A0001"`（来自 fortran exe 数据库）
- [ ] 6.4 county/province 问题不预设 parcel_id（model-1/3 按 area_code 查询）
- [ ] 6.5 运行验证脚本，确认 type 5 问题触发 model-7 且返回真实 fortran exe 结果（非 mock）
- [ ] 6.6 运行验证脚本，确认 farmer 问题（type 1-4）的 model-1/3/4 返回真实 DB 记录（非 mock pH=5.5）
- [ ] 6.7 重新生成 `verification_full_report.md`，确认 model-7 出现在 agents_invoked 列表且 answer 含真实质量等级

## 7. 回归测试与验收

- [ ] 7.1 运行现有测试套件（`pytest tests/`），确认无破坏性回归（特别是 test_role_router、test_question_type_keywords、test_interfaces）
- [ ] 7.2 运行新增的单元测试，确认全部通过
- [ ] 7.3 验证场景 A：问「我的田 A0001 耕地质量等级是多少」→ model-7 调 fortran exe 返回真实质量等级
- [ ] 7.4 验证场景 B：问「我的田肥力怎么样」+ parcel_id=1 → model-1/3/4 返回真实 DB 记录
- [ ] 7.5 验证场景 D：model-2/5 收到 parcel_id 仍返回 stub 回复（不报错）
- [ ] 7.6 验证场景 E：未传 parcel_id 时 agents 返回 mock + need_input 提示（现有行为不变）
