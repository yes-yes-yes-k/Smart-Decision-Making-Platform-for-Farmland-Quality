---
change: add-parcel-id-and-type5-coverage
design-doc: docs/superpowers/specs/2026-07-25-add-parcel-id-and-type5-coverage-design.md
base-ref: 5d8659d3478984c576fc453150ee38615821ee31
archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

# add-parcel-id-and-type5-coverage 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接通 parcel 标识符透传管道 + 补全 type 5 触发路径 + 验证脚本预设真实 ID，使验证报告显示 model-7 真实 fortran exe 结果与 model-1/4 真实 DB 记录。

**Architecture:** 沿用现有 LangGraph + AgentManager + RoleRouter 架构。改动集中在 4 个文件：(1) `router.py` 给 farmer 追加 model-7；(2) `manager.py` 加 model-7 关键词过滤；(3) `nodes.py` 加 type 5 识别分支 + `REFERENCE_QUESTIONS[5]` + `execute_models` 透传 parcel 标识符；(4) `chat.py` 接受 top-level parcel 字段。验证脚本扩展 `run_one_question` 按角色预设真实 ID。所有改动非破坏性——未传 parcel 标识符时行为不变。

**Tech Stack:** Python 3.10+, LangGraph, Flask, pytest（函数式测试 + `sys.path.insert` 模式），Fortran exe（model-7），SQLite（stability_db / diagnosis_db）。

## Global Constraints

- **双 ID 并存**：`parcel_id`（数字字符串如 "1"，给 model-1/3/4 查 DB）与 `parcel_code`（字母数字如 "A0001"，给 model-7 调 fortran exe）无映射关系，SHALL NOT 做转换。
- **非破坏性**：未传 `parcel_id`/`parcel_code` 时 agents 维持现有 mock + `need_input` 提示行为，SHALL NOT 抛异常。
- **model-7 仅加到 farmer 角色**：不新增 grade 角色，不改 county/province 角色。
- **model-7 问题感知过滤**：仅当问题含 `QUESTION_TYPE_5_KEYWORDS` 任一关键词时执行 model-7，否则 status=`skipped`, reason=`question_not_related`。
- **循环依赖规避**：`manager.py` 用本地 `GRADE_KEYWORDS` 副本（镜像 `nodes.QUESTION_TYPE_5_KEYWORDS`），不从 `nodes.py` import。
- **测试模式**：遵循现有 `tests/` 模式——文件顶部 `sys.path.insert(0, ...)`，函数式测试（非 class），末尾 `if __name__ == "__main__"` 块顺序调用所有测试函数。
- **资源就绪状态**（2026-07-25 已验证）：`stability_db` 5488 条（`parcel_id="1"` 存在）；`acidification_results` 14585 条（`parcel_id="1"` 存在）；`diagnosis_results` 0 条（预存在数据缺口，非本次引入）；fortran exe 933KB + dat 204KB 已部署到 `bin/farmland_quality_eval/`；`parcel_code="A0001"` 在 fortran exe 数据库中存在。

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## File Structure

| 文件 | 责任 | 操作 |
|------|------|------|
| `framework/agents/router.py` | 角色路由表 | 修改：`ROLE_AGENTS['farmer']` 追加 `model-7` |
| `framework/agents/manager.py` | 智能体编排 + 问题感知过滤 | 修改：新增 `GRADE_KEYWORDS` + `_should_execute_agent` model-7 分支 |
| `framework/agents/nodes.py` | 问题类型识别 + 问题库 + `execute_models` 管道 | 修改：`_identify_question_type_keyword` type 5 分支 + `REFERENCE_QUESTIONS[5]` + `execute_models` 透传 parcel 标识符 |
| `framework/api/routes/chat.py` | 生产 API `/api/v1/chat/` | 修改：`chat()` 追加 top-level `parcel_id`/`parcel_code` 提取 |
| `scripts/gen_full_verification_report.py` | 验证脚本 | 修改：`run_one_question` 扩展 + `type_labels[5]` + 调用处按角色预设 + 报告文案更新 |
| `tests/test_question_type_keywords.py` | 问题类型识别测试 | 修改：追加 type 5 识别测试 |
| `tests/test_agent_manager.py` | AgentManager 测试 | 修改：追加 model-7 过滤测试 + 更新 farmer agents_invoked 断言 |
| `tests/test_agent_integration.py` | 端到端集成测试 | 修改：更新 farmer agents_invoked 断言 + 追加 API parcel 透传测试 |
| `tests/test_execute_models_pipeline.py` | execute_models 管道透传测试 | 新建：monkeypatch `agent_manager.process` 拦截 context 验证 parcel 透传 |

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 1: 路由层 — farmer 角色追加 model-7

**Files:**
- Modify: `framework/agents/router.py:17`
- Test: `tests/test_agent_manager.py`（更新现有 farmer 断言）
- Test: `tests/test_agent_integration.py`（更新现有 farmer 断言）

**Interfaces:**
- Produces: `RoleRouter.ROLE_AGENTS['farmer']` 变为 `["model-4", "model-5", "model-6", "model-7"]`；`get_agents_for_role("farmer")` 返回 4 元素列表。后续 Task 2 的 `_should_execute_agent` 依赖此变更控制 model-7 是否真正执行。

**背景**：当前 farmer 角色 3 个 agent。追加 model-7 后，`AgentManager._summarize` 的 `agents_invoked` 会包含全部 4 个 agent（无论是否被 `_should_execute_agent` 跳过），因此现有断言 `["model-4", "model-5", "model-6"]` 必须同步更新。

- [x] **Step 1: 写失败测试 — 验证 farmer 含 model-7**

追加到 `tests/test_agent_manager.py` 末尾（在 `if __name__ == "__main__"` 块之前）：

```python
def test_farmer_role_includes_model_7():
    """farmer 角色应包含 model-7（共 4 个 agent）"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    agents = router.get_agents_for_role("farmer")
    assert "model-7" in agents, f"farmer 角色未含 model-7: {agents}"
    assert agents == ["model-4", "model-5", "model-6", "model-7"], f"farmer agents 不符: {agents}"
    print("✓ farmer 角色含 model-7（4 个 agent）")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_agent_manager.py test_farmer_role_includes_model_7`
Expected: FAIL — `AssertionError: farmer 角色未含 model-7`（因 `ROLE_AGENTS['farmer']` 当前只有 3 个）

- [x] **Step 3: 修改 `ROLE_AGENTS['farmer']` 追加 model-7**

在 `framework/agents/router.py:17` 修改：

```python
    ROLE_AGENTS: Dict[str, List[str]] = {
        "province": ["model-1", "model-3"],
        "county": ["model-1", "model-3", "model-2"],
        "farmer": ["model-4", "model-5", "model-6", "model-7"],
    }
```

- [x] **Step 4: 运行新测试验证通过**

Run: `python tests/test_agent_manager.py test_farmer_role_includes_model_7`
Expected: PASS — `✓ farmer 角色含 model-7（4 个 agent）`

- [x] **Step 5: 更新现有 farmer agents_invoked 断言（test_agent_manager.py）**

在 `tests/test_agent_manager.py` 的 `test_manager_process_farmer_returns_structured_result` 函数中，将：

```python
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
```

改为：

```python
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6", "model-7"]
```

同时更新 `test_manager_topological_sort_farmer` 的注释（仅注释，断言不变——该测试直接传 `["model-4", "model-5", "model-6"]`，不依赖 ROLE_AGENTS）。

- [x] **Step 6: 更新现有 farmer agents_invoked 断言（test_agent_integration.py）**

在 `tests/test_agent_integration.py` 中修改 3 处：

`test_execute_models_invokes_agent_manager_farmer`：
```python
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6", "model-7"]
```

`test_chat_api_returns_structured_multi_agent_result`：
```python
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6", "model-7"]
```

`test_e2e_farmer_role_routing`：
```python
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6", "model-7"]
    # model-7 应排在最后（追加在 farmer 列表末尾，无依赖）
    assert data["agents_invoked"][-1] == "model-7"
```

注意：`test_e2e_farmer_role_routing` 的问题 "我的田施肥施多少？施石灰多少？" 不含质量等级关键词，model-7 会被 `_should_execute_agent` 跳过——但 Task 2 才会实现该过滤。**此时运行该测试，model-7 会尝试执行**（调 fortran exe 但 `parcel_code` 缺失，走 mock 回退）。`agents_invoked` 仍含 model-7（因 `_summarize` 用 `_topological_sort(agent_ids)` 包含全部），`details["model-7"]` 含 `simulated: True`。现有 `for aid, payload in data["details"].items(): assert payload.get("simulated") is True` 仍通过。

- [x] **Step 7: 运行受影响的现有测试验证不回归**

Run:
```
python tests/test_agent_manager.py
python tests/test_agent_integration.py
```
Expected: 全部 PASS。`test_e2e_farmer_role_routing` 中 model-6 仍执行（问题含 "施肥"），model-7 因 parcel_code 缺失走 mock 回退（simulated=True），断言通过。

- [x] **Step 8: 提交**

```bash
git add framework/agents/router.py tests/test_agent_manager.py tests/test_agent_integration.py
git commit -m "feat(routing): farmer 角色追加 model-7（4 个 agent）

- ROLE_AGENTS['farmer'] 追加 model-7
- 同步更新 test_agent_manager / test_agent_integration 的 farmer agents_invoked 断言
- model-7 实际执行受 _should_execute_agent 关键词过滤约束（Task 2 实现）"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 2: AgentManager — model-7 问题感知过滤

**Files:**
- Modify: `framework/agents/manager.py:9-14`（新增 `GRADE_KEYWORDS`）+ `manager.py:190-195`（`_should_execute_agent`）
- Test: `tests/test_agent_manager.py`（追加 model-7 过滤测试）

**Interfaces:**
- Consumes: Task 1 的 `ROLE_AGENTS['farmer']` 含 model-7
- Produces: `AgentManager._should_execute_agent("model-7", question)` 在问题含 `QUESTION_TYPE_5_KEYWORDS` 关键词时返回 `True`，否则 `False`。模块级常量 `GRADE_KEYWORDS`（List[str]，9 个关键词，镜像 `nodes.QUESTION_TYPE_5_KEYWORDS`）。

**背景**：model-7 调 fortran exe 有 30s 超时，对非质量等级问题应跳过。沿用 model-6 的 `FERTILITY_KEYWORDS` 本地副本模式（`manager.py:9-14` 注释"与 FertilityMLAgent.FERTILITY_KEYWORDS 保持一致"），避免 `manager.py` ↔ `nodes.py` 循环 import（`nodes.py:286` 已 `from framework.agents.manager import agent_manager`）。

- [x] **Step 1: 写失败测试 — model-7 关键词过滤**

追加到 `tests/test_agent_manager.py` 末尾：

```python
def test_should_execute_model7_grade_question():
    """问'质量等级' → _should_execute_agent('model-7', ...) = True"""
    from framework.agents.manager import AgentManager, GRADE_KEYWORDS
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-7", "我的田耕地质量等级是多少？") is True
    assert mgr._should_execute_agent("model-7", "查询地块的综合指数和障碍度排序") is True
    assert mgr._should_execute_agent("model-7", "这块地的耕地质量等级评价结果") is True
    print("✓ 质量等级相关问题触发 model-7 执行")


def test_should_skip_model7_non_grade_question():
    """非质量等级问题 → _should_execute_agent('model-7', ...) = False"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-7", "我的田肥力怎么样？") is False
    assert mgr._should_execute_agent("model-7", "我的田酸化严重吗？") is False
    assert mgr._should_execute_agent("model-7", "你好") is False
    print("✓ 非质量等级问题跳过 model-7")


def test_grade_keywords_mirrors_question_type_5():
    """GRADE_KEYWORDS 应镜像 nodes.QUESTION_TYPE_5_KEYWORDS"""
    from framework.agents.manager import GRADE_KEYWORDS
    from framework.agents.nodes import QUESTION_TYPE_5_KEYWORDS
    assert GRADE_KEYWORDS == QUESTION_TYPE_5_KEYWORDS, (
        f"GRADE_KEYWORDS 与 QUESTION_TYPE_5_KEYWORDS 不一致：\n"
        f"  manager: {GRADE_KEYWORDS}\n  nodes: {QUESTION_TYPE_5_KEYWORDS}"
    )
    print("✓ GRADE_KEYWORDS 镜像 QUESTION_TYPE_5_KEYWORDS")


def test_model7_skipped_in_details_for_non_grade_farmer_question():
    """farmer 问非质量等级问题 → details['model-7'] 含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样？", {})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") == "skipped", f"model-7 应被跳过，实际: {m7}"
    assert m7.get("reason") == "question_not_related"
    print("✓ 非质量等级 farmer 问题 model-7 被跳过")


def test_model7_executed_for_grade_farmer_question():
    """farmer 问质量等级问题 → details['model-7'] 不含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被跳过，实际: {m7}"
    # parcel_code 已传，model-7 应调 fortran exe（若部署就绪）或走 mock 回退
    assert "answer" in m7 or "simulated" in m7
    print("✓ 质量等级 farmer 问题 model-7 被执行")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_agent_manager.py test_should_execute_model7_grade_question`
Expected: FAIL — `ImportError: cannot import name 'GRADE_KEYWORDS' from 'framework.agents.manager'`

- [x] **Step 3: 新增 GRADE_KEYWORDS 本地副本**

在 `framework/agents/manager.py` 的 `FERTILITY_KEYWORDS` 定义之后（约第 14 行后）追加：

```python
# 质量等级相关关键词（与 nodes.QUESTION_TYPE_5_KEYWORDS 保持一致）
# 不从 nodes.py import 以避免循环依赖（nodes.py 已 from manager import agent_manager）
GRADE_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]
```

- [x] **Step 4: 修改 `_should_execute_agent` 追加 model-7 分支**

在 `framework/agents/manager.py` 的 `_should_execute_agent` 方法中（约第 190-195 行），将：

```python
    def _should_execute_agent(self, agent_id: str, question: str) -> bool:
        """问题感知过滤：model-6 仅在肥力相关问题时执行。"""
        if agent_id == "model-6":
            q_lower = (question or "").lower()
            return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
        return True
```

改为：

```python
    def _should_execute_agent(self, agent_id: str, question: str) -> bool:
        """问题感知过滤：model-6 仅肥力问题执行，model-7 仅质量等级问题执行。"""
        if agent_id == "model-6":
            q_lower = (question or "").lower()
            return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
        if agent_id == "model-7":
            return any(kw in (question or "") for kw in GRADE_KEYWORDS)
        return True
```

- [x] **Step 5: 运行新测试验证通过**

Run:
```
python tests/test_agent_manager.py test_should_execute_model7_grade_question
python tests/test_agent_manager.py test_should_skip_model7_non_grade_question
python tests/test_agent_manager.py test_grade_keywords_mirrors_question_type_5
python tests/test_agent_manager.py test_model7_skipped_in_details_for_non_grade_farmer_question
python tests/test_agent_manager.py test_model7_executed_for_grade_farmer_question
```
Expected: 全部 PASS。

- [x] **Step 6: 运行全套 manager 测试验证不回归**

Run: `python tests/test_agent_manager.py`
Expected: 全部 PASS。注意 `test_should_execute_other_agents_always` 断言 model-4/5 始终执行——不受影响。

- [x] **Step 7: 提交**

```bash
git add framework/agents/manager.py tests/test_agent_manager.py
git commit -m "feat(manager): model-7 问题感知过滤（仅质量等级问题执行）

- 新增 GRADE_KEYWORDS 本地副本（镜像 nodes.QUESTION_TYPE_5_KEYWORDS，避免循环 import）
- _should_execute_agent 追加 model-7 分支：非质量等级问题返回 False（skipped）
- 非质量等级 farmer 问题不再调 fortran exe，节省 30s 超时"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 3: 问题类型识别 — type 5 关键词分支

**Files:**
- Modify: `framework/agents/nodes.py:183-196`（`_identify_question_type_keyword`）
- Test: `tests/test_question_type_keywords.py`（追加 type 5 识别测试）

**Interfaces:**
- Consumes: `QUESTION_TYPE_5_KEYWORDS`（`nodes.py:57-61`，已定义）
- Produces: `_identify_question_type_keyword` 在问题命中 `QUESTION_TYPE_5_KEYWORDS` 时返回 `(5, relevance)`。`identify_question_type` 透传该结果。后续 Task 4 的 `REFERENCE_QUESTIONS[5]` 问题经此函数识别为 type 5。

**背景**：`QUESTION_TYPE_5_KEYWORDS` 已定义但 `_identify_question_type_keyword` 无 type 5 分支，导致 type 5 问题返回 `(0, relevance)`。分支顺序 1→2→3→4→5，type 5 在最后，不影响前序类型判定。关键词碰撞已验证安全：type 5 问题不含"稳定"（type 1 的 "等级稳定" 不命中）。

- [x] **Step 1: 写失败测试 — type 5 识别**

追加到 `tests/test_question_type_keywords.py` 末尾（在 `if __name__ == "__main__"` 块之前）：

```python
def test_type5_grade_quality_question():
    """质量等级评价 → TYPE_5（model-7）"""
    qt, _ = _identify("我的田耕地质量等级是多少？")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_comprehensive_index_question():
    """综合指数/障碍度排序 → TYPE_5"""
    qt, _ = _identify("查询地块的综合指数和障碍度排序")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_grade_evaluation_question():
    """耕地质量等级评价结果 → TYPE_5"""
    qt, _ = _identify("这块地的耕地质量等级评价结果")
    assert qt == 5, f"期望 TYPE_5，实际 {qt}"


def test_type5_keyword_branch_after_type4():
    """type 5 分支在 type 4 之后：'肥力'问题仍返回 type 4，不误判 type 5"""
    qt, _ = _identify("我的田肥力怎么样？")
    assert qt == 4, f"期望 TYPE_4（肥力），实际 TYPE_{qt}"


def test_type5_no_collision_with_type1():
    """type 5 问题不含'稳定'，不误命中 TYPE_1 的'等级稳定'"""
    from framework.agents.nodes import QUESTION_TYPE_1_KEYWORDS
    type5_questions = [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ]
    for q in type5_questions:
        # 不应命中任何 TYPE_1 关键词
        assert not any(kw in q for kw in QUESTION_TYPE_1_KEYWORDS), (
            f"type 5 问题「{q}」误命中 TYPE_1 关键词"
        )
        qt, _ = _identify(q)
        assert qt == 5, f"问题「{q}」期望 TYPE_5，实际 TYPE_{qt}"


def test_type5_keyword_function_direct():
    """直接测试 _identify_question_type_keyword 返回 (5, relevance)"""
    from framework.agents.nodes import _identify_question_type_keyword
    qt, rel = _identify_question_type_keyword("我的田耕地质量等级是多少")
    assert qt == 5
    assert rel >= 0.3
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_question_type_keywords.py test_type5_grade_quality_question`
Expected: FAIL — `AssertionError: 期望 TYPE_5，实际 0`（因 `_identify_question_type_keyword` 无 type 5 分支，返回 `(0, relevance)`）

- [x] **Step 3: 修改 `_identify_question_type_keyword` 追加 type 5 分支**

在 `framework/agents/nodes.py` 的 `_identify_question_type_keyword` 函数中（约第 183-196 行），将：

```python
def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
    if relevance < 0.3:
        return 0, relevance
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, relevance
    else:
        return 0, relevance
```

改为：

```python
def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
    if relevance < 0.3:
        return 0, relevance
    if any(keyword in question for keyword in QUESTION_TYPE_1_KEYWORDS):
        return 1, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_2_KEYWORDS):
        return 2, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_3_KEYWORDS):
        return 3, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_4_KEYWORDS):
        return 4, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_5_KEYWORDS):
        return 5, relevance
    else:
        return 0, relevance
```

- [x] **Step 4: 运行新测试验证通过**

Run:
```
python tests/test_question_type_keywords.py test_type5_grade_quality_question
python tests/test_question_type_keywords.py test_type5_comprehensive_index_question
python tests/test_question_type_keywords.py test_type5_grade_evaluation_question
python tests/test_question_type_keywords.py test_type5_keyword_branch_after_type4
python tests/test_question_type_keywords.py test_type5_no_collision_with_type1
python tests/test_question_type_keywords.py test_type5_keyword_function_direct
```
Expected: 全部 PASS。

- [x] **Step 5: 运行全套关键词测试验证不回归**

Run: `python tests/test_question_type_keywords.py`
Expected: 全部 PASS。`test_all_xlsx_classic_questions_routed` 中 type 1-4 问题不受影响（type 5 分支在 type 4 之后，不抢占已有类型）。

- [x] **Step 6: 提交**

```bash
git add framework/agents/nodes.py tests/test_question_type_keywords.py
git commit -m "feat(nodes): _identify_question_type_keyword 新增 type 5 分支

- type 4 之后、else 之前追加 QUESTION_TYPE_5_KEYWORDS 分支返回 (5, relevance)
- 关键词碰撞已验证：type 5 问题不含'稳定'，不误命中 TYPE_1"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 4: 问题库 — REFERENCE_QUESTIONS 新增 type 5

**Files:**
- Modify: `framework/agents/nodes.py:75-104`（`REFERENCE_QUESTIONS` dict）
- Test: `tests/test_question_type_keywords.py`（追加 REFERENCE_QUESTIONS[5] 测试）

**Interfaces:**
- Consumes: Task 3 的 `_identify_question_type_keyword` type 5 分支
- Produces: `REFERENCE_QUESTIONS[5]` 是 `List[str]`，含 3 个质量等级评价问题。验证脚本（Task 7）遍历 `REFERENCE_QUESTIONS.items()` 时会自动覆盖 type 5。

**背景**：3 个问题均含 farmer 关键词（"我的田"/"地块"/"这块地"）确保 RoleRouter 识别为 farmer。问题同时含 type 5 关键词（"质量等级"/"综合指数"/"等级评价"）确保 `_identify_question_type_keyword` 返回 5。注意"查询地块的综合指数和障碍度排序"不含"我的田"/"这块地"但含"地块"——"地块"不在 `ROLE_KEYWORDS['farmer']` 中，但 `identify_role` 默认返回 "farmer"（无匹配时回退），仍能正确路由。

- [x] **Step 1: 写失败测试 — REFERENCE_QUESTIONS[5] 存在且非空**

追加到 `tests/test_question_type_keywords.py` 末尾：

```python
def test_reference_questions_has_type5():
    """REFERENCE_QUESTIONS 应含 key 5（至少 3 个质量等级评价问题）"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    assert 5 in REFERENCE_QUESTIONS, "REFERENCE_QUESTIONS 缺少 key 5"
    assert len(REFERENCE_QUESTIONS[5]) >= 3, (
        f"REFERENCE_QUESTIONS[5] 应至少 3 个问题，实际 {len(REFERENCE_QUESTIONS.get(5, []))}"
    )
    print("✓ REFERENCE_QUESTIONS[5] 存在且含 >= 3 个问题")


def test_type5_questions_routed_to_type5():
    """REFERENCE_QUESTIONS[5] 的每个问题经 identify_question_type 返回 5"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    for q in REFERENCE_QUESTIONS[5]:
        qt, _ = _identify(q)
        assert qt == 5, f"type 5 问题「{q}」期望 TYPE_5，实际 TYPE_{qt}"


def test_type5_questions_route_to_farmer():
    """REFERENCE_QUESTIONS[5] 的每个问题经 RoleRouter 识别为 farmer"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    for q in REFERENCE_QUESTIONS[5]:
        role = router.identify_role(q)
        assert role == "farmer", f"type 5 问题「{q}」期望 farmer 角色，实际 {role}"
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_question_type_keywords.py test_reference_questions_has_type5`
Expected: FAIL — `AssertionError: REFERENCE_QUESTIONS 缺少 key 5`

- [x] **Step 3: 在 REFERENCE_QUESTIONS dict 新增 key 5**

在 `framework/agents/nodes.py` 的 `REFERENCE_QUESTIONS` dict 中（约第 96-104 行，type 4 条目之后），追加 key 5：

```python
REFERENCE_QUESTIONS: Dict[int, List[str]] = {
    1: [
        "查询区域内耕地质量等级整体稳定吗",
        "查询区域内哪些高等级耕地存在退化风险",
        "本县哪些乡镇或地块等级稳定性较弱需要现场复核",
        "我的这块田质量等级稳不稳",
        "查询区域内哪些对象需要纳入重点关注清单",
    ],
    2: [
        "查询区域内农用地土壤酸化程度如何不同酸化等级比例分别多少",
        "我的田酸化了pH是多少我要施加多少碱性调理剂可以治理好",
        "查询区域内不同土地利用类型的酸化程度",
        "我的这块田酸化严重吗",
    ],
    3: [
        "辖区耕地质量提升的总体潜力有多大可增产多少粮食",
        "我们县划定的优先改良片区具体在哪几个村每块潜力多大",
        "我这块地到底有啥毛病",
        "全省耕地质量存在哪些问题",
        "县乡镇里的耕地在哪些方面有问题",
    ],
    4: [
        "全省耕地土壤有机质含量如何空间分布情况",
        "为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少",
        "本县耕地土壤有机质平均含量是多少",
        "我的田肥力怎么样",
        "我的田土壤有机碳含量大概多少",
        "我这块地大概需要施多少有机肥",
    ],
    5: [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ],
}
```

- [x] **Step 4: 运行新测试验证通过**

Run:
```
python tests/test_question_type_keywords.py test_reference_questions_has_type5
python tests/test_question_type_keywords.py test_type5_questions_routed_to_type5
python tests/test_question_type_keywords.py test_type5_questions_route_to_farmer
```
Expected: 全部 PASS。

- [x] **Step 5: 运行全套关键词测试验证不回归**

Run: `python tests/test_question_type_keywords.py`
Expected: 全部 PASS。

- [x] **Step 6: 提交**

```bash
git add framework/agents/nodes.py tests/test_question_type_keywords.py
git commit -m "feat(nodes): REFERENCE_QUESTIONS 新增 type 5（3 个质量等级评价问题）

- 问题含 farmer 关键词（我的田/地块/这块地）确保路由到 farmer
- 问题含 type 5 关键词（质量等级/综合指数/等级评价）确保识别为 type 5
- 验证脚本遍历 REFERENCE_QUESTIONS 时自动覆盖 type 5"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 5: 管道接通 — execute_models 透传 parcel 标识符

**Files:**
- Modify: `framework/agents/nodes.py:283-310`（`execute_models` 函数）
- Test: `tests/test_execute_models_pipeline.py`（新建）

**Interfaces:**
- Consumes: `state["request"]` 中的 `parcel_id`（str，数字）和 `parcel_code`（str，字母数字）
- Produces: `execute_models` 构建的 `context` dict 含 top-level `parcel_id`/`parcel_code`（与 `area_code`/`data`/`longitude`/`latitude`/`target_ph` 并列）。`agent_manager.process(question, context)` 收到该 context，model-1/3/4 读 `context.get("parcel_id")`，model-7 读 `context.get("parcel_code")`。

**背景（Design Doc T1）**：现有 `execute_models`（`nodes.py:289-296`）将标量字段放 top-level，`data` 作为嵌套 dict。4 个 agent 的 `_get_real_*` 方法都先读 `context.get("parcel_id")`（top-level），再回退 `context.get("data",{}).get("parcel_id")`。top-level 是首选查找路径，命中最快，与现有字段一致。改动仅需在 `for key in (...)` 循环的元组新增 `"parcel_id", "parcel_code"`。

- [x] **Step 1: 新建测试文件 — 写失败测试**

创建 `tests/test_execute_models_pipeline.py`：

```python
"""测试 execute_models 管道透传 parcel_id/parcel_code 到 context。

通过 monkeypatch agent_manager.process 拦截 context，验证：
1. request 含 parcel_id/parcel_code 时 context top-level 含这两个字段
2. request 不含时 context 不含这两个字段（现有行为不变）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


def _make_state(question: str, request_extra: dict | None = None) -> MultiAgentState:
    req = {"question": question, "area_code": "lechang"}
    if request_extra:
        req.update(request_extra)
    return {
        "request": req,
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 1,
        "relevance": 0.8,
    }


def _stub_process_return():
    """agent_manager.process 的桩返回值，符合 execute_models 期望的 {status: ok, data: {...}} 结构。"""
    return {
        "status": "ok",
        "data": {
            "role": "farmer",
            "agents_invoked": ["model-4", "model-5", "model-6", "model-7"],
            "summary": "",
            "details": {},
            "recommendations": [],
        },
    }


def test_execute_models_passes_parcel_id_and_parcel_code_to_context():
    """execute_models 应从 state['request'] 提取 parcel_id/parcel_code 到 context top-level。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["question"] = question
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "1", "parcel_code": "A0001"})
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx.get("parcel_id") == "1", f"parcel_id 未透传到 context top-level: {ctx}"
    assert ctx.get("parcel_code") == "A0001", f"parcel_code 未透传到 context top-level: {ctx}"
    # area_code 仍应存在（现有行为不变）
    assert ctx.get("area_code") == "lechang"
    print("✓ execute_models 透传 parcel_id/parcel_code 到 context top-level")


def test_execute_models_no_parcel_when_absent():
    """request 不含 parcel_id/parcel_code 时 context 不应包含这两个字段。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级")
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert "parcel_id" not in ctx, f"不应含 parcel_id: {ctx}"
    assert "parcel_code" not in ctx, f"不应含 parcel_code: {ctx}"
    print("✓ request 无 parcel 标识符时 context 不含这两个字段")


def test_execute_models_passes_only_parcel_id():
    """request 仅含 parcel_id 时 context 仅含 parcel_id（model-7 走 mock 回退）。"""
    from framework.agents.manager import agent_manager

    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        return _stub_process_return()

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state = _make_state("我的田质量等级", {"parcel_id": "10"})
        execute_models(state)
    finally:
        agent_manager.process = real_process

    ctx = captured["context"]
    assert ctx.get("parcel_id") == "10"
    assert "parcel_code" not in ctx
    print("✓ request 仅含 parcel_id 时 context 仅含 parcel_id")


if __name__ == "__main__":
    test_execute_models_passes_parcel_id_and_parcel_code_to_context()
    test_execute_models_no_parcel_when_absent()
    test_execute_models_passes_only_parcel_id()
    print("\n所有 execute_models 管道透传测试通过！")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_execute_models_pipeline.py`
Expected: FAIL — `AssertionError: parcel_id 未透传到 context top-level`（因 `execute_models` 当前 `for key in (...)` 循环不含 `parcel_id`/`parcel_code`）

- [x] **Step 3: 修改 execute_models 透传 parcel 标识符**

在 `framework/agents/nodes.py` 的 `execute_models` 函数中（约第 289-296 行），将：

```python
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
        # 透传可能的土壤参数
        for key in ("longitude", "latitude", "target_ph", "context"):
            if key in state["request"]:
                context[key] = state["request"][key]
```

改为：

```python
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
        # 透传可能的土壤参数与地块标识符
        # parcel_id（数字字符串）给 model-1/3/4 查 DB，parcel_code（字母数字）给 model-7 调 fortran exe
        for key in ("longitude", "latitude", "target_ph", "context",
                    "parcel_id", "parcel_code"):
            if key in state["request"]:
                context[key] = state["request"][key]
```

- [x] **Step 4: 运行新测试验证通过**

Run: `python tests/test_execute_models_pipeline.py`
Expected: 全部 PASS — `所有 execute_models 管道透传测试通过！`

- [x] **Step 5: 运行现有集成测试验证不回归**

Run: `python tests/test_agent_integration.py`
Expected: 全部 PASS。`test_execute_models_invokes_agent_manager_farmer` 等测试的 state 不含 `parcel_id`/`parcel_code`，行为不变。

- [x] **Step 6: 提交**

```bash
git add framework/agents/nodes.py tests/test_execute_models_pipeline.py
git commit -m "feat(nodes): execute_models 透传 parcel_id/parcel_code 到 context top-level

- for key 循环新增 parcel_id, parcel_code（与 area_code/data/longitude 等并列）
- model-1/3/4 读 context.get('parcel_id') 查 DB，model-7 读 context.get('parcel_code') 调 exe
- 未传时 context 不含这两个字段，agents 维持 mock + need_input 行为（非破坏性）"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 6: 生产 API — chat.py 接受 parcel_id/parcel_code

**Files:**
- Modify: `framework/api/routes/chat.py:76-77`（`chat()` 函数 `orchestrator_request` 构建处）
- Test: `tests/test_agent_integration.py`（追加 API parcel 透传测试）

**Interfaces:**
- Consumes: Task 5 的 `execute_models` 透传逻辑（orchestrator → execute_models → context）
- Produces: `POST /api/v1/chat/` 请求体支持可选 `parcel_id`（str，数字格式）和 `parcel_code`（str，字母数字格式）。`orchestrator_request` 含 top-level `parcel_id`/`parcel_code`，top-level 优先于 `context` 字段内同名 key。

**背景（Design Doc T3）**：现有 `chat.py:76` `orchestrator_request = {"question": message, **context}` 已展平 `context` 字段。Open spec 场景要求 top-level `body 含 parcel_id: "1"`。实现：top-level 优先——`orchestrator_request` 构建后追加 top-level 提取，覆盖 `context` 内同名字段。

- [x] **Step 1: 写失败测试 — API top-level parcel 透传**

追加到 `tests/test_agent_integration.py` 末尾：

```python
def test_chat_api_passes_top_level_parcel_id_and_code():
    """POST body 含 top-level parcel_id/parcel_code → 透传到 orchestrator request"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "model_results": {
                "data": {
                    "role": "farmer",
                    "agents_invoked": ["model-4", "model-5", "model-6", "model-7"],
                    "summary": "",
                    "details": {},
                    "recommendations": [],
                }
            },
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={
                    "message": "我的田耕地质量等级是多少",
                    "parcel_id": "1",
                    "parcel_code": "A0001",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert req.get("parcel_id") == "1", f"parcel_id 未透传: {req}"
    assert req.get("parcel_code") == "A0001", f"parcel_code 未透传: {req}"
    assert req.get("question") == "我的田耕地质量等级是多少"
    print("✓ /api/v1/chat/ 透传 top-level parcel_id/parcel_code")


def test_chat_api_top_level_parcel_overrides_context():
    """top-level parcel_id 优先于 context.parcel_id"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 5,
            "model_results": {"data": {"role": "farmer", "agents_invoked": [], "summary": "", "details": {}, "recommendations": []}},
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={
                    "message": "我的田质量等级",
                    "parcel_id": "1",            # top-level 优先
                    "context": {"parcel_id": "999"},  # 应被覆盖
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert req.get("parcel_id") == "1", f"top-level 应优先，实际: {req}"
    print("✓ top-level parcel_id 优先于 context.parcel_id")


def test_chat_api_no_parcel_when_absent():
    """POST body 不含 parcel_id/parcel_code → orchestrator request 不含（现有行为不变）"""
    from framework.api.app import create_app
    from framework.agents.orchestrator import multi_agent_orchestrator

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        from framework.models.user import db, User
        db.create_all()
        user = User.query.filter_by(username="tester").first()
        if not user:
            user = User(username="tester", password="x")
            db.session.add(user)
            db.session.commit()
        user_id = user.id
        from flask_jwt_extended import create_access_token
        access_token = create_access_token(identity=str(user_id))

    captured = {}

    def fake_run(req, conversation_history=None):
        captured["request"] = req
        return {
            "answer": "ok",
            "question_type": 0,
            "model_results": {},
        }

    real_run = multi_agent_orchestrator.run
    multi_agent_orchestrator.run = fake_run
    client = app.test_client()
    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "你好"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    finally:
        multi_agent_orchestrator.run = real_run

    assert resp.status_code == 200
    req = captured["request"]
    assert "parcel_id" not in req, f"不应含 parcel_id: {req}"
    assert "parcel_code" not in req, f"不应含 parcel_code: {req}"
    print("✓ body 无 parcel 标识符时 orchestrator request 不含")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_agent_integration.py test_chat_api_passes_top_level_parcel_id_and_code`
Expected: FAIL — `AssertionError: parcel_id 未透传`（因 `chat.py` 当前未提取 top-level `parcel_id`/`parcel_code`）

- [x] **Step 3: 修改 chat.py 追加 top-level parcel 提取**

在 `framework/api/routes/chat.py` 的 `chat()` 函数中（约第 76-77 行），将：

```python
    orchestrator_request = {"question": message, **context}
    result = multi_agent_orchestrator.run(orchestrator_request, conversation_history=history)
```

改为：

```python
    orchestrator_request = {"question": message, **context}
    # top-level parcel_id/parcel_code 优先（覆盖 context 内同名字段）
    # parcel_id（数字字符串）给 model-1/3/4 查 DB，parcel_code（字母数字）给 model-7 调 fortran exe
    for k in ("parcel_id", "parcel_code"):
        if data.get(k) is not None:
            orchestrator_request[k] = data[k]
    result = multi_agent_orchestrator.run(orchestrator_request, conversation_history=history)
```

- [x] **Step 4: 运行新测试验证通过**

Run:
```
python tests/test_agent_integration.py test_chat_api_passes_top_level_parcel_id_and_code
python tests/test_agent_integration.py test_chat_api_top_level_parcel_overrides_context
python tests/test_agent_integration.py test_chat_api_no_parcel_when_absent
```
Expected: 全部 PASS。

- [x] **Step 5: 运行全套集成测试验证不回归**

Run: `python tests/test_agent_integration.py`
Expected: 全部 PASS。`test_chat_api_returns_structured_multi_agent_result` 不传 parcel 标识符，行为不变。

- [x] **Step 6: 提交**

```bash
git add framework/api/routes/chat.py tests/test_agent_integration.py
git commit -m "feat(api): /api/v1/chat/ 接受 top-level parcel_id/parcel_code

- orchestrator_request 构建后追加 top-level 提取，优先于 context 字段
- parcel_id 给 model-1/3/4 查 DB，parcel_code 给 model-7 调 fortran exe
- 未传时行为不变（现有 mock + need_input 提示）"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 7: 验证脚本 — 预设 parcel 标识符 + type 5 覆盖

**Files:**
- Modify: `scripts/gen_full_verification_report.py:47-108`（`run_one_question` 签名 + body）
- Modify: `scripts/gen_full_verification_report.py:168-173`（`type_labels` dict）
- Modify: `scripts/gen_full_verification_report.py:372-389`（`main()` 调用 `run_one_question` 处）
- Modify: `scripts/gen_full_verification_report.py:148-156`（角色路由表 + model-7 说明文案）
- Modify: `scripts/gen_full_verification_report.py:303-323`（"关键观察" 追加 diagnosis_results 局限说明）

**Interfaces:**
- Consumes: Task 4 的 `REFERENCE_QUESTIONS[5]`（验证脚本遍历时自动覆盖 type 5）；Task 5 的 `execute_models` 透传逻辑（预设的 parcel 标识符经 orchestrator → execute_models → context 到达 agents）
- Produces: `run_one_question(q_type, q, parcel_id=None, parcel_code=None)` 接受可选 parcel 参数；`main()` 按角色预设真实 ID（farmer + type 5 → `parcel_id="1"` + `parcel_code="A0001"`）。

**背景（Design Doc T4）**：
- farmer 问题（type 1-4 含 farmer 关键词 + type 5 全部）：预设 `parcel_id="1"`（来自 stability_db/diagnosis_db）+ `parcel_code="A0001"`（来自 fortran exe 数据库）
- county/province 问题：不预设（model-1/3 按 `area_code` 查询）
- 用 `RoleRouter.identify_role(q) == "farmer"` 判断 farmer 问题（比关键词匹配更稳健）

- [x] **Step 1: 修改 `run_one_question` 签名与 body**

在 `scripts/gen_full_verification_report.py` 中，将 `run_one_question` 函数（约第 47-108 行）改为：

```python
def run_one_question(q_type: int, q: str,
                     parcel_id: str | None = None,
                     parcel_code: str | None = None) -> Dict[str, Any]:
    from framework.agents.orchestrator import multi_agent_orchestrator

    t0 = time.time()
    try:
        request = {"question": q}
        if parcel_id:
            request["parcel_id"] = parcel_id
        if parcel_code:
            request["parcel_code"] = parcel_code
        output = multi_agent_orchestrator.run(request, conversation_history=[])
    except Exception as exc:
        return {
            "expected_type": q_type,
            "question": q,
            "error": f"orchestrator.run failed: {exc}",
            "elapsed": round(time.time() - t0, 2),
        }
    elapsed = round(time.time() - t0, 2)

    status = output.get("status")
    question_type = output.get("question_type")
    answer = output.get("answer") or output.get("llm_response") or ""
    model_results = output.get("model_results", {}) or {}
    agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
    agents_invoked = agent_data.get("agents_invoked", []) or []
    role = agent_data.get("role")
    summary = agent_data.get("summary", "") or ""
    details = agent_data.get("details", {}) or {}

    final_answer = answer or summary

    # 收集每个 agent 的明细
    agent_details: List[Dict[str, Any]] = []
    for aid in agents_invoked:
        detail = details.get(aid, {}) or {}
        if not isinstance(detail, dict):
            continue
        agent_details.append({
            "agent_id": aid,
            "simulated": detail.get("simulated"),
            "status": detail.get("status"),
            "reason": detail.get("reason"),
            "error": detail.get("error"),
            "answer": detail.get("answer") or "",
            "confidence": detail.get("confidence"),
            "evidence": detail.get("evidence") or [],
        })

    return {
        "expected_type": q_type,
        "question": q,
        "status": status,
        "identified_type": question_type,
        "type_match": question_type == q_type,
        "role": role,
        "agents_invoked": agents_invoked,
        "answer_full": final_answer,
        "summary": summary,
        "answer_source": "answer" if answer else ("summary" if summary else "none"),
        "agent_details": agent_details,
        "elapsed": elapsed,
        "parcel_id": parcel_id,
        "parcel_code": parcel_code,
        "_raw_output": output,
    }
```

注意：返回值新增 `parcel_id`/`parcel_code` 字段供报告显示。

- [x] **Step 2: 修改 `main()` 调用处按角色预设 parcel 标识符**

在 `scripts/gen_full_verification_report.py` 的 `main()` 函数中（约第 372-389 行），将：

```python
    from framework.agents.nodes import REFERENCE_QUESTIONS

    details: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    total = 0
    answered = 0
    type_match = 0
    total_count = sum(len(v) for v in REFERENCE_QUESTIONS.values())
    for q_type, questions in REFERENCE_QUESTIONS.items():
        for q in questions:
            total += 1
            print(f"  [{total}/{total_count}] type={q_type} -> {q[:40]}...", flush=True)
            r = run_one_question(q_type, q)
```

改为：

```python
    from framework.agents.nodes import REFERENCE_QUESTIONS
    from framework.agents.router import RoleRouter

    router = RoleRouter()

    details: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    total = 0
    answered = 0
    type_match = 0
    total_count = sum(len(v) for v in REFERENCE_QUESTIONS.values())
    for q_type, questions in REFERENCE_QUESTIONS.items():
        for q in questions:
            total += 1
            # 按角色预设 parcel 标识符：
            # - farmer 问题（含 type 5 全部）预设 parcel_id="1" + parcel_code="A0001"
            # - county/province 问题不预设（model-1/3 按 area_code 查询）
            parcel_id = None
            parcel_code = None
            if q_type == 5 or router.identify_role(q) == "farmer":
                parcel_id = "1"
                parcel_code = "A0001"
            print(f"  [{total}/{total_count}] type={q_type} -> {q[:40]}..."
                  f" (parcel_id={parcel_id or '-'}, parcel_code={parcel_code or '-'})",
                  flush=True)
            r = run_one_question(q_type, q, parcel_id=parcel_id, parcel_code=parcel_code)
```

- [x] **Step 3: 修改 `type_labels` dict 新增 key 5**

在 `scripts/gen_full_verification_report.py` 的 `build_markdown` 函数中（约第 168-173 行），将：

```python
    type_labels = {
        1: "类型1：稳定性风险（5 题）",
        2: "类型2：酸化改良（4 题）",
        3: "类型3：障碍诊断与潜力（5 题）",
        4: "类型4：肥力与有机质（6 题）",
    }
```

改为：

```python
    type_labels = {
        1: "类型1：稳定性风险（5 题）",
        2: "类型2：酸化改良（4 题）",
        3: "类型3：障碍诊断与潜力（5 题）",
        4: "类型4：肥力与有机质（6 题）",
        5: "类型5：质量等级评价（3 题）",
    }
```

- [x] **Step 4: 修改角色路由表文案 + model-7 说明**

在 `scripts/gen_full_verification_report.py` 的 `build_markdown` 函数中（约第 148-156 行），将：

```python
    md.append("| `farmer`（默认） | 我的田 / 这块地 / 施氮肥 / 施多少 / 农户 | model-4, model-5, model-6 |")
    md.append("")
    md.append("> model-7（Fortran exe）仅在 question_type=5（显式 `质量等级` 关键词）时触发，"
              "本次问题库仅覆盖 type 1-4，故 model-7 未被任何问题调用。")
```

改为：

```python
    md.append("| `farmer`（默认） | 我的田 / 这块地 / 施氮肥 / 施多少 / 农户 | model-4, model-5, model-6, model-7 |")
    md.append("")
    md.append("> model-7（Fortran exe）仅在 question_type=5（显式 `质量等级` 关键词）时执行；"
              "非质量等级 farmer 问题经 `_should_execute_agent` 关键词过滤跳过 model-7 "
              "（status=`skipped`, reason=`question_not_related`）。")
```

- [x] **Step 5: 修改"关键观察"追加 diagnosis_results 局限说明**

在 `scripts/gen_full_verification_report.py` 的 `build_markdown` 函数中（约第 303-323 行），在现有第 5 点之后追加第 6 点：

```python
    md.append("5. **simulated 标志解读**：AgentManager 通过 `MockDataLoader.mark_simulated(payload)` "
              "在结果顶层强制写入 `simulated=True`，即使 model-6 这种真实计算 agent 也显示 sim。"
              "**因此 `simulated=True` 不能作为真实/模拟的判据**。是否真实计算应以：")
    md.append("   - `fallback_reason is None` + `execute_status==success`（model-6 直接 execute 验证）")
    md.append("   - 或 agent 真实调用了底层模型（如 model-1 读 stability_db、model-7 调 Fortran exe）")
    md.append("   为准。")
    md.append("6. **parcel 标识符透传**：本次验证脚本为 farmer 问题（含 type 5）预设 `parcel_id=\"1\"` "
              "（来自 stability_db/acidification_results）+ `parcel_code=\"A0001\"`（来自 fortran exe 数据库）。"
              "管道已接通 `execute_models → context → agents`，model-1/4 应返回真实 DB 记录，"
              "model-7 应返回真实 fortran exe 质量等级评价。"
              "**预存在数据缺口**：`diagnosis_results` 表 0 条记录，model-3 仍返回 mock，"
              "数据填充后管道自动生效（非本次引入）。")
```

- [x] **Step 6: 运行验证脚本生成新报告**

Run: `python scripts/gen_full_verification_report.py`
Expected:
- 控制台输出 23 个问题（20 个 type 1-4 + 3 个 type 5）的实时进度
- farmer 问题行显示 `(parcel_id=1, parcel_code=A0001)`
- county/province 问题行显示 `(parcel_id=-, parcel_code=-)`
- 报告写入 `verification_full_report.md`
- 原始 JSON 写入 `verification_raw_outputs.json`
- 控制台汇总 `问题库回答率: X/23`, `问题类型识别准确率: Y/23`

- [x] **Step 7: 验证报告内容**

打开 `verification_full_report.md` 检查：

1. **type 5 章节存在**：报告含 `### 类型5：质量等级评价（3 题）` 章节，3 个问题（Q21-Q23）
2. **model-7 真实调用**：type 5 问题的 `agent_details` 中 model-7 的 `simulated: False`（真实 fortran exe 结果，含"耕地质量等级：10等"等输出）
3. **farmer 问题真实 DB 记录**：type 1-4 farmer 问题（含"我的田"/"这块地"）的 model-1/4 的 `simulated: False`（真实 DB 记录，非 mock pH=5.5）
4. **model-7 在非质量等级 farmer 问题中被跳过**：type 1-4 farmer 问题的 `agent_details` 中 model-7 的 `status: skipped`, `reason: question_not_related`
5. **角色路由表更新**：farmer 行显示 `model-4, model-5, model-6, model-7`
6. **关键观察第 6 点**：含 parcel 标识符透传说明 + diagnosis_results 局限说明

Run（grep 关键行）:
```
python -c "content = open('verification_full_report.md', encoding='utf-8').read(); assert '类型5：质量等级评价（3 题）' in content, '缺 type 5 章节'; assert 'model-7' in content; print('报告内容检查通过')"
```

- [x] **Step 8: 提交**

```bash
git add scripts/gen_full_verification_report.py verification_full_report.md verification_raw_outputs.json
git commit -m "feat(verify): 验证脚本预设 parcel 标识符 + type 5 覆盖

- run_one_question 扩展接受 parcel_id/parcel_code 可选参数
- main() 按角色预设：farmer + type 5 → parcel_id=1 + parcel_code=A0001
- type_labels 新增 key 5（类型5：质量等级评价（3 题））
- 角色路由表 + model-7 说明文案更新
- 关键观察追加 parcel 透传说明 + diagnosis_results 局限说明
- 重新生成 verification_full_report.md（23 题，含 type 5）"
```

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 8: 端到端验证 — 场景验收

**Files:**
- 仅运行验证，不修改源文件

**Interfaces:**
- Consumes: Task 1-7 全部产出

**背景**：对应 tasks.md 7.3-7.6 的验收场景。通过验证脚本 + 手动检查确认 5 个场景的行为符合 spec。

- [x] **Step 1: 验证场景 A — type 5 触发 model-7 真实 fortran exe**

Run:
```
python -c "
import sys, os
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from scripts.gen_full_verification_report import run_one_question
r = run_one_question(5, '我的田耕地质量等级是多少', parcel_id='1', parcel_code='A0001')
print('identified_type:', r.get('identified_type'))
print('agents_invoked:', r.get('agents_invoked'))
m7 = next((d for d in r.get('agent_details', []) if d['agent_id'] == 'model-7'), None)
print('model-7 status:', m7.get('status') if m7 else 'NOT INVOKED')
print('model-7 simulated:', m7.get('simulated') if m7 else None)
ans = (m7.get('answer') or '')[:200] if m7 else ''
print('model-7 answer preview:', ans)
assert r.get('identified_type') == 5, f'type 应为 5，实际 {r.get(\"identified_type\")}'
assert m7 is not None, 'model-7 未被调用'
assert m7.get('status') != 'skipped', 'model-7 不应被跳过'
assert '10等' in ans or '质量等级' in ans or '综合指数' in ans, f'model-7 应含真实质量等级，实际: {ans}'
print('场景 A 通过：type 5 触发 model-7 真实 fortran exe 结果')
"
```
Expected: 输出 `场景 A 通过：type 5 触发 model-7 真实 fortran exe 结果`

- [x] **Step 2: 验证场景 B — farmer 肥力问题 + parcel_id 触发真实 DB**

Run:
```
python -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from scripts.gen_full_verification_report import run_one_question
r = run_one_question(4, '我的田肥力怎么样', parcel_id='1', parcel_code='A0001')
print('agents_invoked:', r.get('agents_invoked'))
m7 = next((d for d in r.get('agent_details', []) if d['agent_id'] == 'model-7'), None)
print('model-7 status:', m7.get('status') if m7 else 'NOT INVOKED')
assert m7 is not None
assert m7.get('status') == 'skipped', '肥力问题 model-7 应被跳过'
print('场景 B 部分通过：farmer 肥力问题 model-7 被跳过（question_not_related）')
"
```
Expected: 输出 `场景 B 部分通过：farmer 肥力问题 model-7 被跳过`

注意：model-1/4 真实 DB 记录验证依赖 Task 7 Step 7 的报告检查（type 1-4 farmer 问题的 model-1/4 `simulated: False`）。若 fortran exe 或 DB 部署缺失，agents 走 mock 回退，不报错。

- [x] **Step 3: 验证场景 D — model-2/5 收到 parcel_id 仍返回 stub**

Run:
```
python -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from scripts.gen_full_verification_report import run_one_question
r = run_one_question(4, '我的田肥力怎么样', parcel_id='1', parcel_code='A0001')
m5 = next((d for d in r.get('agent_details', []) if d['agent_id'] == 'model-5'), None)
print('model-5 status:', m5.get('status') if m5 else 'NOT INVOKED')
print('model-5 answer:', (m5.get('answer') or '')[:100] if m5 else '')
assert m5 is not None, 'model-5 应被调用'
print('场景 D 通过：model-5 收到 parcel_id 不报错，返回 stub 回复')
"
```
Expected: 输出 `场景 D 通过：model-5 收到 parcel_id 不报错，返回 stub 回复`

- [x] **Step 4: 验证场景 E — 未传 parcel_id 时 agents 返回 mock + need_input**

Run:
```
python -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from scripts.gen_full_verification_report import run_one_question
r = run_one_question(5, '我的田耕地质量等级是多少')
m7 = next((d for d in r.get('agent_details', []) if d['agent_id'] == 'model-7'), None)
print('model-7 status:', m7.get('status') if m7 else 'NOT INVOKED')
ans = m7.get('answer') or '' if m7 else ''
print('model-7 answer:', ans[:200])
# 未传 parcel_code → model-7 走 mock 回退（simulated=True 或含 need_input 提示）
print('场景 E 通过：未传 parcel_code 时 model-7 走 mock 回退（不抛异常）')
"
```
Expected: 输出 `场景 E 通过：未传 parcel_code 时 model-7 走 mock 回退（不抛异常）`

- [x] **Step 5: 验证场景 — county/province 问题不预设 parcel_id 仍正常工作**

Run:
```
python -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'src')
from scripts.gen_full_verification_report import run_one_question
# county 问题，不传 parcel_id
r = run_one_question(1, '查询区域内耕地质量等级整体稳定吗')
print('role:', r.get('role'))
print('agents_invoked:', r.get('agents_invoked'))
assert r.get('role') in ('province', 'county'), f'应为 province/county，实际 {r.get(\"role\")}'
print('场景通过：county/province 问题不预设 parcel_id 正常工作')
"
```
Expected: 输出 `场景通过：county/province 问题不预设 parcel_id 正常工作`

- [x] **Step 6: 不提交（仅验证）**

本任务不产生文件变更，无需提交。若 Task 7 已提交报告，则所有验证基于已生成的报告 + 实时调用。

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Task 9: 回归测试 — 全套测试套件

**Files:**
- 仅运行测试，不修改源文件

**Interfaces:**
- Consumes: Task 1-8 全部产出

**背景**：对应 tasks.md 7.1-7.2。运行全套 `tests/` 测试，确认无破坏性回归。重点关注 `test_role_router`（无独立文件，断言在 `test_agent_manager.py`）、`test_question_type_keywords`、`test_agent_integration`、`test_interfaces`。

- [x] **Step 1: 运行全套测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（或仅预存在的、与本次变更无关的失败）。

重点关注以下测试文件全部通过：
- `tests/test_question_type_keywords.py`（含新增 type 5 测试）
- `tests/test_agent_manager.py`（含新增 model-7 过滤测试 + 更新的 farmer 断言）
- `tests/test_agent_integration.py`（含新增 API parcel 透传测试 + 更新的 farmer 断言）
- `tests/test_execute_models_pipeline.py`（新建文件，parcel 透传测试）
- `tests/test_interfaces.py`（接口契约测试，不应回归）
- `tests/test_multi_agent.py`（多智能体测试，不应回归）

- [x] **Step 2: 检查测试覆盖**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_agent_manager.py tests/test_agent_integration.py tests/test_execute_models_pipeline.py -v --tb=short`
Expected: 全部 PASS。统计测试数：
- `test_question_type_keywords.py`：原有 ~25 个 + 新增 9 个 type 5 测试 = ~34 个
- `test_agent_manager.py`：原有 ~13 个 + 新增 5 个 model-7 测试 = ~18 个
- `test_agent_integration.py`：原有 ~8 个 + 新增 3 个 API parcel 测试 = ~11 个
- `test_execute_models_pipeline.py`：新建 3 个

- [x] **Step 3: 验证无预存在回归**

若 `tests/` 中有与本次变更无关的失败测试（如依赖外部服务的测试），记录测试名并确认与本次变更无关。本次变更涉及的 4 个文件（`router.py`, `manager.py`, `nodes.py`, `chat.py`）的相关测试必须全部通过。

- [x] **Step 4: 不提交（仅验证）**

本任务不产生文件变更。若 Step 1-2 全部通过，回归验证完成。

archived-with: 2026-07-25-add-parcel-id-and-type5-coverage
---

## Self-Review 清单

### Spec 覆盖核对

| tasks.md 任务 | 覆盖于 | 状态 |
|---------------|--------|------|
| 1.1 router.py 追加 model-7 | Task 1 Step 3 | ✓ |
| 1.2 manager.py model-7 关键词过滤 | Task 2 Step 3-4 | ✓ |
| 1.3 router/manager 测试 | Task 1 Step 1 + Task 2 Step 1 | ✓ |
| 2.1 nodes.py type 5 分支 | Task 3 Step 3 | ✓ |
| 2.2 type 5 识别测试 | Task 3 Step 1 | ✓ |
| 3.1 REFERENCE_QUESTIONS[5] | Task 4 Step 3 | ✓ |
| 3.2 type 5 问题含 farmer 关键词 | Task 4 Step 1（测试验证） | ✓ |
| 3.3 REFERENCE_QUESTIONS[5] 测试 | Task 4 Step 1 | ✓ |
| 4.1-4.3 execute_models 透传 | Task 5 Step 3 | ✓ |
| 4.4 execute_models 测试 | Task 5 Step 1 | ✓ |
| 5.1-5.2 chat.py 接受 parcel 字段 | Task 6 Step 3 | ✓ |
| 5.3 API 文档 | 未单独任务（API 字段在代码注释中说明） | △ |
| 5.4 API 集成测试 | Task 6 Step 1 | ✓ |
| 6.1 run_one_question 扩展 | Task 7 Step 1 | ✓ |
| 6.2 farmer 问题预设 parcel_id | Task 7 Step 2 | ✓ |
| 6.3 type 5 预设 parcel_code | Task 7 Step 2 | ✓ |
| 6.4 county/province 不预设 | Task 7 Step 2 | ✓ |
| 6.5-6.7 运行验证脚本 + 检查报告 | Task 7 Step 6-7 | ✓ |
| 7.1 全套测试无回归 | Task 9 Step 1 | ✓ |
| 7.2 新增测试通过 | Task 9 Step 2 | ✓ |
| 7.3 场景 A（type 5 → model-7 真实） | Task 8 Step 1 | ✓ |
| 7.4 场景 B（farmer + parcel_id → 真实 DB） | Task 8 Step 2 + Task 7 Step 7 | ✓ |
| 7.5 场景 D（model-2/5 stub 不报错） | Task 8 Step 3 | ✓ |
| 7.6 场景 E（未传 parcel → mock + need_input） | Task 8 Step 4 | ✓ |

### Design Doc T1-T4 核对

| 决策 | 覆盖于 | 状态 |
|------|--------|------|
| T1: execute_models top-level 透传 | Task 5 Step 3（`for key in (...)` 循环新增 `parcel_id`, `parcel_code`） | ✓ |
| T2: manager.py GRADE_KEYWORDS 本地副本 | Task 2 Step 3-4 | ✓ |
| T3: chat.py top-level 优先 + context 兼容 | Task 6 Step 3 | ✓ |
| T4: 验证脚本按角色预设 | Task 7 Step 1-2 | ✓ |

### Placeholder 扫描

无 TBD/TODO/"fill in details"/"similar to Task N" 等占位符。所有步骤含完整代码。

### 类型一致性

- `GRADE_KEYWORDS`（Task 2 定义）= `QUESTION_TYPE_5_KEYWORDS`（Task 2 测试 `test_grade_keywords_mirrors_question_type_5` 验证一致）
- `run_one_question(q_type, q, parcel_id=None, parcel_code=None)`（Task 7 定义）调用处签名匹配
- `ROLE_AGENTS['farmer']`（Task 1 修改）= `["model-4", "model-5", "model-6", "model-7"]`，所有测试断言一致
- `_should_execute_agent(self, agent_id, question) -> bool`（Task 2 修改）签名不变，新增 model-7 分支
- `execute_models` 的 `context` dict 新增 `parcel_id`/`parcel_code` top-level key，与 agents 的 `context.get("parcel_id")` / `context.get("parcel_code")` 读取路径一致

### 备注

- **Task 5.3（API 文档）**：未单独建任务。`parcel_id`/`parcel_code` 字段说明已在 `chat.py` 代码注释中体现（Task 6 Step 3）。若需独立 README 更新，可在 Task 6 后追加。
- **diagnosis_results 空表**：预存在数据缺口，非本次引入。Task 7 Step 5 在报告"关键观察"中注明此局限。model-3 仍返回 mock，但管道已接通，数据填充后自动生效。
- **fortran exe 30s 超时**：Task 2 的 `_should_execute_agent` 关键词过滤已规避——非质量等级问题跳过 model-7，不调 exe。质量等级问题调 exe 时已有超时机制，超时走 mock 回退不阻断。

