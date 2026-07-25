---
comet_change: add-parcel-id-and-type5-coverage
role: technical-design
canonical_spec: openspec
---

# Design Doc: add-parcel-id-and-type5-coverage

> 本文档是对 Open 阶段 `design.md`（D1-D4 已确认决策）的深度技术细化。OpenSpec delta spec 是能力规格的事实源；本文档聚焦实现方案、技术风险、测试策略与边界条件，不重写需求。

## 1. 背景与目标

智能体能力验证报告（`verification_full_report.md`）暴露两个验证盲点：

1. **model-7 从未被触发** — `REFERENCE_QUESTIONS`（`framework/agents/nodes.py:75-104`）只覆盖 type 1-4；`QUESTION_TYPE_5_KEYWORDS`（`nodes.py:57-61`）已定义但 `_identify_question_type_keyword`（`nodes.py:183-196`）无 type 5 分支；`RoleRouter.ROLE_AGENTS['farmer']`（`framework/agents/router.py:17`）不含 model-7。
2. **farmer 问题全返回 mock** — `execute_models`（`nodes.py:283-310`）构建 context 时不提取 `parcel_id`/`parcel_code`，而 model-1/3/4/7 的真实计算路径早已就绪（agents 读 `context.get("parcel_id")` / `context.get("parcel_code")`），管道未接通。

**目标**：接通 parcel 标识符透传管道 + 补全 type 5 触发路径 + 验证脚本预设真实 ID，使验证报告显示 model-7 真实 fortran exe 结果与 model-1/4 真实 DB 记录。

## 2. 已确认决策（Open 阶段 D1-D4）

| 决策 | 内容 |
|------|------|
| D1 | 双 ID 并存：`parcel_id`（数字字符串，给 model-1/3/4 查 DB）+ `parcel_code`（字母数字，给 model-7 调 fortran exe），无映射关系 |
| D2 | model-7 加到 `ROLE_AGENTS['farmer']` 末尾，变为 `["model-4","model-5","model-6","model-7"]` |
| D3 | type 5（质量等级）问题只在 farmer 角色触发，问题文本含 farmer 关键词 |
| D4 | `AgentManager._should_execute_agent` 对 model-7 增加关键词过滤，仅 `QUESTION_TYPE_5_KEYWORDS` 命中时执行 |

## 3. 技术实现决策（Design 阶段 T1-T4）

### T1: `execute_models` 透传位置 — top-level context

**决策**：`parcel_id`/`parcel_code` 放到 top-level context，与 `area_code`/`longitude`/`latitude`/`target_ph` 并列。

**理由**：
- 现有 `execute_models` 模式（`nodes.py:289-296`）将标量字段放 top-level，`data` 作为嵌套 dict
- 4 个 agent 的 `_get_real_*` 方法都先读 `context.get("parcel_id")`（top-level），再回退 `context.get("data",{}).get("parcel_id")`
- top-level 是首选查找路径，命中最快，与现有字段一致

**实现**（`framework/agents/nodes.py` `execute_models` 函数）：
```python
context = {
    "area_code": state["request"].get("area_code", "lechang"),
    "data": state.get("data", {}),
}
# 透传可能的土壤参数与地块标识符
for key in ("longitude", "latitude", "target_ph", "context",
            "parcel_id", "parcel_code"):  # 新增 parcel_id, parcel_code
    if key in state["request"]:
        context[key] = state["request"][key]
```

### T2: `_should_execute_agent` model-7 过滤 — 本地关键词副本

**决策**：在 `manager.py` 顶部定义 `GRADE_KEYWORDS` 本地副本，不从 `nodes.py` import。

**理由**：
- `nodes.py` 已 `from framework.agents.manager import agent_manager`（`nodes.py:286`），反向 import 会循环依赖
- 现有 `FERTILITY_KEYWORDS`（`manager.py:9-14`）就是这种模式，注释明确"与 FertilityMLAgent.FERTILITY_KEYWORDS 保持一致"
- 关键词列表稳定，本地副本维护成本低

**实现**（`framework/agents/manager.py`）：
```python
# 质量等级相关关键词（与 nodes.QUESTION_TYPE_5_KEYWORDS 保持一致）
GRADE_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]

# 在 _should_execute_agent 方法中追加 model-7 分支：
def _should_execute_agent(self, agent_id: str, question: str) -> bool:
    """问题感知过滤：model-6 仅肥力问题执行，model-7 仅质量等级问题执行。"""
    if agent_id == "model-6":
        q_lower = (question or "").lower()
        return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
    if agent_id == "model-7":
        return any(kw in (question or "") for kw in GRADE_KEYWORDS)
    return True
```

### T3: API 字段位置 — top-level 优先 + context 兼容

**决策**：`chat.py` 同时支持 top-level `parcel_id`/`parcel_code`（spec 要求）和 `context.parcel_id`（现有 `**context` 展平已支持），top-level 优先。

**理由**：
- Open spec 场景明确要求 top-level：`body 含 parcel_id: "1"`
- 现有 `chat.py:76` `orchestrator_request = {"question": message, **context}` 已展平 `context` 字段，不破坏向后兼容
- top-level 优先确保 spec 场景命中，`context` 字段内同名 key 被覆盖

**实现**（`framework/api/routes/chat.py` `chat()` 函数）：
```python
orchestrator_request = {"question": message, **context}
# top-level parcel_id/parcel_code 优先（覆盖 context 内同名字段）
for k in ("parcel_id", "parcel_code"):
    if data.get(k) is not None:
        orchestrator_request[k] = data[k]
```

### T4: 验证脚本 parcel 映射 — 按角色预设

**决策**：`run_one_question` 扩展接受可选 `parcel_id`/`parcel_code` 参数；按 Open tasks 6.2-6.4 角色映射预设。

**映射规则**：
- farmer 问题（type 1-4 中含"我的田/这块地"的 + type 5 全部）：`parcel_id="1"` + `parcel_code="A0001"`
- county/province 问题：不预设（model-1/3 按 `area_code` 查询）

**实现**（`scripts/gen_full_verification_report.py`）：
```python
def run_one_question(q_type: int, q: str,
                     parcel_id: str | None = None,
                     parcel_code: str | None = None) -> Dict[str, Any]:
    request = {"question": q}
    if parcel_id:
        request["parcel_id"] = parcel_id
    if parcel_code:
        request["parcel_code"] = parcel_code
    output = multi_agent_orchestrator.run(request, conversation_history=[])
    # ... 其余逻辑不变
```

调用处按角色判断是否注入 parcel 标识符（基于问题文本含 farmer 关键词或 type==5）。

## 4. type 5 问题集设计

`REFERENCE_QUESTIONS[5]` 新增 3 个问题，确保含 farmer 关键词 + type 5 关键词，避开 type 1 关键词：

```python
5: [
    "我的田耕地质量等级是多少",          # "我的田" + "质量等级"
    "查询地块的综合指数和障碍度排序",    # "地块" + "综合指数" + "障碍度排序"
    "这块地的耕地质量等级评价结果",      # "这块地" + "耕地质量等级" + "等级评价"
],
```

**关键词碰撞分析**（已验证安全）：
- TYPE_1 关键词 `"等级稳定"` 含"稳定"，type 5 问题不含"稳定" → 不误命中 TYPE_1
- TYPE_5 关键词 `"质量等级"` 命中 type 5 问题 → `_identify_question_type_keyword` 在 type 4 分支后新增 type 5 分支返回 `(5, relevance)`
- `_identify_question_type_keyword` 分支顺序 1→2→3→4→5，type 5 在最后，不影响前序类型判定

**`_identify_question_type_keyword` 实现**（`nodes.py:183-196`）：
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
        return 5, relevance  # 新增分支
    else:
        return 0, relevance
```

## 5. 数据流

```
客户端 POST /api/v1/chat/
  body: {message, parcel_id?, parcel_code?, context?}
    ↓
chat.py: orchestrator_request = {"question": message, **context, parcel_id?, parcel_code?}
    ↓
multi_agent_orchestrator.run(request, history)
    ↓
identify_question_node → identify_question_type(question)
  → _identify_question_type_keyword → 命中 QUESTION_TYPE_5_KEYWORDS → return (5, relevance)
    ↓
route_models: question_type=5 != 0 → "execute_models"
    ↓
execute_models(state):
  context = {area_code, data, parcel_id?, parcel_code?}  # T1: top-level 透传
  agent_manager.process(question, context)
    ↓
AgentManager.process:
  role = RoleRouter.identify_role(question)  # type 5 问题含"我的田" → farmer
  agent_ids = ["model-4","model-5","model-6","model-7"]  # D2: farmer 含 model-7
  _execute_with_dependencies(agent_ids, question, context)
    ↓
对每个 agent_id:
  _should_execute_agent(agent_id, question)?
    model-6: 问"质量等级" → 不含肥力词 → skipped
    model-7: 问"质量等级" → 含 GRADE_KEYWORDS → 执行
    model-4/5: 始终执行
    ↓
agent.answer_question(question, context):
  model-7: context.get("parcel_code")="A0001" → run_grade_evaluation → fortran exe 真实结果
  model-4: context.get("parcel_id")="1" → query_acidification → DB 真实记录
  model-1: context.get("parcel_id")="1" → StabilityStorage.get_result → DB 真实记录
```

## 6. 边界条件

| 场景 | 行为 |
|------|------|
| request 不含 parcel_id/parcel_code | agents 维持现有 mock + `need_input` 提示（现有行为不变） |
| request 含 parcel_id 但不含 parcel_code | model-1/3/4 真实查询，model-7 返回 mock + `need_input: "parcel_code"` 提示 |
| request 含 parcel_code 但不含 parcel_id | model-7 真实调用 fortran exe，model-1/3/4 返回 mock + `need_input: "parcel_id"` 提示 |
| farmer 问非质量等级问题（如"我的田肥力怎么样"） | model-7 被 `_should_execute_agent` 跳过（status=skipped, reason=question_not_related），不调 fortran exe |
| farmer 问质量等级问题但 fortran exe 未部署 | model-7 `answer_question` 走 mock 回退（GRADE_EVAL_AVAILABLE=False），返回模拟数据 |
| parcel_id 在 DB 中不存在 | agent `_get_real_*` 返回 {}，走 mock 回退，不抛异常 |
| fortran exe 超时（30s） | `run_grade_evaluation` 已有超时机制，返回 error，agent 走 mock 回退 |

## 7. 测试策略

### 单元测试（遵循现有 `tests/` 模式）

| 测试文件 | 新增/追加 | 断言 |
|----------|-----------|------|
| `tests/test_question_type_keywords.py` | 追加 | `identify_question_type("我的田耕地质量等级是多少") == 5`；3 个 type 5 问题均返回 5；`"我的田肥力怎么样"` 仍返回 4（非 5） |
| `tests/test_agent_manager.py` | 追加 | `RoleRouter.get_agents_for_role("farmer")` 含 model-7（4 个 agent）；`_should_execute_agent("model-7", "质量等级问题") is True`；`_should_execute_agent("model-7", "肥力问题") is False`；farmer 问质量等级 → details["model-7"] 不含 skipped |
| `tests/test_execute_models_pipeline.py`（新文件） | 新建 | monkeypatch `agent_manager.process` 拦截 context，断言 `context["parcel_id"]=="1"` 且 `context["parcel_code"]=="A0001"`（top-level，非嵌套在 data 内） |
| `tests/test_chat_route.py`（若存在）或 `tests/test_agent_integration.py` | 追加 | POST body 含 top-level `parcel_id` → orchestrator_request 含 `parcel_id`；POST body 含 `context.parcel_id` → 同样透传；top-level 优先于 context |

### 验证脚本运行（端到端）

跑 `scripts/gen_full_verification_report.py` 重新生成 `verification_full_report.md`：
- type 5 问题触发 model-7，`agent_details` 中 model-7 的 `simulated: False`（真实 fortran exe 结果）
- farmer 问题（type 1-4 含"我的田"）的 model-1/4 `simulated: False`（真实 DB 记录）
- type 5 问题在报告中有独立章节"类型5：质量等级评价（3 题）"

## 8. 关键风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `diagnosis_results` 表空（0 条记录） | model-3 仍返回 mock，验证报告 model-3 行显示 sim | **预存在数据缺口，非本次引入**；管道已接通，数据填充后自动生效。验证报告"关键观察"注明此局限 |
| `diagnosis_db` 路径不一致（`data/` 空 0B vs `src/data/` 真实 6.6MB） | model-3/4 查库可能命中空 DB | **预存在问题**；build 阶段验证 `query_acidification`/`query_parcel` 的默认 db_path 解析；若指向空 DB，在验证报告注明 |
| fortran exe 30s 超时 | type 5 验证单题可能超时 | 已有超时机制，验证脚本记录单题耗时；超时走 mock 回退不阻断 |
| 循环依赖 | `manager.py` import `nodes.py` 会循环 | T2 用本地 `GRADE_KEYWORDS` 副本规避 |
| type 5 关键词与 type 1 碰撞 | "质量等级"含"等级"，"等级稳定"含"等级" | 已分析：type 5 问题不含"稳定"，TYPE_1 优先检查但不命中；type 5 在分支末尾不影响前序 |
| model-7 加到 farmer 后所有 farmer 问题都调 fortran exe | 非质量等级 farmer 问题耗时增加 | D4 的 `_should_execute_agent` 关键词过滤已规避：非质量等级问题跳过 model-7 |

## 9. 资源就绪状态（已验证 2026-07-25）

| 资源 | 状态 | 验证结果 |
|------|------|----------|
| `stability_db` | ✓ 就绪 | 5488 条记录，`parcel_id="1"` 存在 |
| `acidification_results` 表 | ✓ 就绪 | 14585 条记录，`parcel_id="1"` 存在 |
| `diagnosis_results` 表 | ✗ 空表 | 0 条记录（预存在数据缺口） |
| fortran exe | ✓ 就绪 | 933KB，已部署到 `bin/farmland_quality_eval/` |
| fortran dat | ✓ 就绪 | 204KB，已部署 |
| `parcel_code="A0001"` | ✓ 有效 | 前序会话已验证在 fortran exe 数据库中存在 |

## 10. 不在本次范围（Non-Goals，承袭 Open 阶段）

- 不做 fortran exe parcel_code 与 DB parcel_id 的映射表（无数据支撑）
- 不改 model-6（按特征预测，不按地块查库）
- 不重构 agents 的真实计算路径（已就绪）
- 不改 storage 层和 fortran exe 本身
- 不改 county/province 角色（model-7 仅加到 farmer）
- 不填充 `diagnosis_results` 表数据（预存在缺口，另行处理）
