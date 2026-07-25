# Brainstorm Summary

- Change: add-parcel-id-and-type5-coverage
- Date: 2026-07-25

## 确认的技术方案

基于 Open 阶段已确认的 D1-D4 决策（双 ID 并存 / model-7 加 farmer / type 5 仅 farmer 触发 / model-7 问题感知过滤），深度技术细化如下 4 个实现决策：

- **T1: execute_models 透传位置** — `parcel_id`/`parcel_code` 放到 top-level context（与 `area_code`/`longitude`/`latitude`/`target_ph` 并列），不放进 `context["data"]`。4 个 agent 都先读 top-level，命中最快。
- **T2: _should_execute_agent model-7 过滤** — 在 `manager.py` 顶部定义 `GRADE_KEYWORDS` 本地副本（镜像 `QUESTION_TYPE_5_KEYWORDS`），不从 `nodes.py` import（避免循环依赖，遵循现有 `FERTILITY_KEYWORDS` 模式）。
- **T3: API 字段位置** — `chat.py` 同时支持 top-level `parcel_id`/`parcel_code`（spec 要求）和 `context.parcel_id`（现有 `**context` 展平已支持），top-level 优先。
- **T4: 验证脚本 parcel 映射** — `run_one_question` 扩展接受可选 `parcel_id`/`parcel_code` 参数；farmer 问题预设 `parcel_id="1"` + `parcel_code="A0001"`，county/province 不预设。

**type 5 问题集**（3 个，含 farmer 关键词 + type 5 关键词，避开 "稳定" 等 type 1 词）：
1. `我的田耕地质量等级是多少`
2. `查询地块的综合指数和障碍度排序`
3. `这块地的耕地质量等级评价结果`

**关键词碰撞已验证安全**：TYPE_1 检查 `"等级稳定"`（含"稳定"），type 5 问题不含"稳定" → 不误命中 TYPE_1。

## 关键取舍与风险

- **diagnosis_results 表空（0 条）**：预存在数据缺口，model-3 仍返回 mock。本次只接通管道，数据填充后自动生效。验证报告注明此局限。
- **diagnosis_db 路径不一致**（`data/farmland_diagnosis/farmland_diagnosis.db` 空文件 vs `src/data/farmland_diagnosis/farmland_diagnosis.db` 真实 6.6MB）：预存在问题，agents 的 `db_path=None` 时用默认路径，build 阶段验证实际路径解析。
- **fortran exe 30s 超时**：已有超时机制，验证脚本单题耗时记录即可。
- **循环依赖风险**：`nodes.py` 已 import `manager.py`，反向 import 会循环。T2 用本地副本规避。

## 测试策略

遵循现有 `test_agent_manager.py` / `test_question_type_keywords.py` 模式（直接函数调用 + sys.path.insert）：

1. `test_question_type_keywords.py` 追加：type 5 识别（3 个问题 → 5）、type 4 不被误判为 5
2. `test_agent_manager.py` 追加：farmer 角色 4 agent 含 model-7、`_should_execute_agent("model-7", ...)` 质量等级问题 True / 非质量等级问题 False
3. `test_execute_models_pipeline.py`（新文件）：monkeypatch `agent_manager.process` 拦截 context，断言 `parcel_id`/`parcel_code` 透传到 top-level
4. `test_chat_route.py` 追加：POST body 含 top-level `parcel_id` → orchestrator request 含 `parcel_id`

验证脚本运行：跑 `scripts/gen_full_verification_report.py` 重新生成 `verification_full_report.md`，断言 type 5 触发 model-7 且 `simulated: False`、farmer 问题 model-1/4 返回真实 DB 记录。

## Spec Patch

无。Open 阶段 delta spec 已包含完整验收场景（地块标识符上下文透传、Type 5 质量等级评价问题库、model-7 问题感知过滤、生产 API 接受地块标识符），无需补充。
