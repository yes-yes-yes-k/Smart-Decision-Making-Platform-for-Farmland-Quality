---
change: sync-model-specs-from-overview
design-doc: docs/superpowers/specs/2026-07-24-sync-model-specs-from-overview-design.md
base-ref: 251ac1cefb1a2e49f8766565c51f1ce5e5713f7b
---

# 同步专业模型 spec 与 xlsx 总览表 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `专业模型总览表(2).xlsx` 的六模型输入输出定义与 3 角色经典问题同步到 OpenSpec delta spec、`nodes.py` 关键词、6 个 agent 的 `answer_question` 回复模板与 `RoleRouter` 路由，并以测试断言一致性。

**Architecture:** 以 delta spec（professional-model-agents / role-based-routing）为契约源头，先校对 spec（含 model 6 名称回退 D1、TYPE 描述与 D5 关键词对齐），再以 TDD 更新 `nodes.py` 关键词（D5）与各 agent 回复模板（D4 最小化改动），最后用 spec 一致性 / 关键词路由 / agent Q&A / 回归四类测试收口。`RoleRouter` 三角色路由已与 xlsx 三端一致，仅做验证性测试。

**Tech Stack:** Python 3.12、pytest、OpenSpec（Markdown spec）、LangGraph 风格的 multi-agent framework（`framework/agents/`）。

## 关联设计决策（来自 design.md）

- **D1**：model 6 spec 名称回退为「耕地综合地力改良提升模型」（xlsx 版），`FertilityMLAgent` 的 ML 预测作为内部实现保留。
- **D2**：xlsx 详细输入输出列表写入 spec 的 requirement 描述（契约），agent 代码按需引用。
- **D3**：3 角色经典问题提炼为约 30 个 scenario 写入 spec（delta spec 已采用），非 90 个完整版。
- **D4**：agent 代码最小化改动——仅 `answer_question` 关键词分支与回复模板，不重构架构。
- **D5**：更新 `nodes.py` 的 `QUESTION_TYPE_1~4_KEYWORDS` 覆盖 xlsx 经典问题关键词；移除 TYPE_2 通用词（"施加""用量"）保留具体词；关键词匹配优先于向量匹配。

## Global Constraints

- 产物语言：中文（zh-CN）。spec、代码注释、回复模板、commit message 均用中文。
- **不修改** `model_6_execution` 核心逻辑（`framework/domain/other_models/model_6.py`）。
- **不修改** API 路由结构（`framework/api/`）。
- **不导入新数据**、**不训练新 ML 模型**。
- agent 改动遵循 D4：仅 `answer_question` 内的关键词分支与回复文案，不改 `execute`、不改 `__init__`、不改 `model_id`。
- 关键词匹配优先级保持：`identify_question_type` → embedding 可用时先向量、不可用回退关键词；`_identify_question_type_keyword` 按 TYPE_1→2→3→4 顺序首次命中返回，关键词不得跨类型重叠。
- 测试遵循现有风格：`tests/` 下文件，`sys.path.insert` 引入项目根，断言 `simulated is True`、`0.0 <= confidence <= 1.0`。
- 每个任务结束执行 `python -m pytest <相关测试> -v` 并 commit。

## File Structure

**Spec（delta，变更对象，归档时合并到主 spec）：**
- `openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md` — 6 模型输入输出 + scenario（已存在，本计划校对/修正）
- `openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md` — TYPE 关键词与路由映射（已存在，修正 TYPE_1 描述）

**代码（修改）：**
- `framework/agents/nodes.py` — `QUESTION_TYPE_1~4_KEYWORDS`、`RELEVANCE_KEYWORDS`、`REFERENCE_QUESTIONS`、`QUESTION_TYPE_TO_MODEL_ID`
- `framework/agents/specialized/stability_risk_agent.py` — `StabilityRiskAgent.answer_question`
- `framework/agents/specialized/potential_agent.py` — `PotentialAssessmentAgent.answer_question`
- `framework/agents/specialized/problem_agent.py` — `ProblemIdentificationAgent.answer_question`
- `framework/agents/specialized/acidification_agent.py` — `AcidificationRemediationAgent.answer_question`
- `framework/agents/specialized/organic_matter_agent.py` — `OrganicMatterAgent.answer_question`
- `framework/agents/specialized/fertility_ml_agent.py` — `FertilityMLAgent.answer_question`（仅文案对齐"综合地力"）
- `framework/agents/router.py` — `RoleRouter`（仅验证，预期不改）

**测试（新建/修改）：**
- `tests/test_model_specs_sync.py` — 新建：delta spec 一致性
- `tests/test_question_type_keywords.py` — 新建：xlsx 经典问题路由
- `tests/test_agent_classic_qa.py` — 新建：6 agent × 经典问题 Q&A
- `tests/test_agent_specialized.py` — 已存在：回归
- `tests/test_fertility_ml_prediction.py` — 已存在：model-6 回归

---

## Task 1: 校对 professional-model-agents delta spec 模型 1-3

**对应 tasks.md：** 1.1 / 1.2 / 1.3

**Files:**
- 校对: `openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md`

**Interfaces:**
- Consumes: design.md D2（输入输出写入 spec）、D3（提炼版 scenario）
- Produces: 模型 1-3 的 requirement 含完整输入输出列表与 3 角色 scenario，供 Task 10 的 spec 一致性测试断言

**说明：** delta spec 已在 design 阶段写入（D3 Spec Patch）。本任务逐条校对模型 1-3 的输入输出数据名称与 xlsx 一致、scenario 覆盖 3 角色经典问题核心行为。预期无需大改；如发现缺失则补全。

- [x] **Step 1: 校对模型 1 StabilityRiskAgent requirement**

打开 `openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md`，确认模型 1 requirement 包含：
- 标题行含「耕地质量等级稳定性与退化风险识别模型」
- **模型输入**含：广东省-市-县行政边界（面 shp）、三普耕地评价单元（面 shp）、耕地质量等级及综合指数、11 个评价指标及权重（pH、有机质、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层）、施肥措施单价、酸化治理措施单价
- **模型输出**含：等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险、持续低质风险
- 5 个 scenario：等级稳定性评价、退化风险识别、县域稳定性薄弱片区、农户地块稳定性判断、重点关注清单

若任一项缺失，按上述内容补全到对应 requirement。

- [x] **Step 2: 校对模型 2 PotentialAssessmentAgent requirement**

确认模型 2 requirement 包含：
- 标题行含「耕地质量提升潜力评估模型」
- **模型输入**含：地块唯一编码、地块经纬度、pH值、有机质、有效磷、速效钾、土壤容重、有效土层厚度、耕层质地、质地构型、灌溉能力、排水能力、地形部位、耕地质量等级、pH增加值（模型4传参）、有机质增加值（模型5传参）
- **模型输出**含：潜在pH值、潜在有机质、潜在有效磷、潜在速效钾、潜在土壤容重、潜在有效土层厚度、潜在耕层质地、潜在灌溉能力、潜在地形部位、潜在排水能力、潜在耕地质量等级、11 个评价指标的潜在障碍度值
- 4 个 scenario：提升潜力评估、目标 pH 计算、县域潜力分布、农户地块诊断

- [x] **Step 3: 校对模型 3 ProblemIdentificationAgent requirement**

确认模型 3 requirement 包含：
- 标题行含「耕地质量主要问题精准识别模型」
- **模型输入**含：一级农业区、二级农业区、土壤pH、有机质、pH、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、地块唯一编码、地块经纬度、地块边界、行政区划边界、农田类型（水田/旱地）
- **模型输出**含：主要障碍因素、次要障碍因素、各指标障碍等级（pH/有机质/有效磷/速效钾/容重/耕层质地/灌溉能力/排水能力/地形部位/质地构型/有效土层）、障碍因素组合
- 4 个 scenario：障碍因素识别、指标障碍等级统计、县域障碍诊断、农户地块问题

- [x] **Step 4: 验证文件可被解析**

Run: `python -c "p='openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md'; s=open(p,encoding='utf-8').read(); assert 'StabilityRiskAgent' in s and 'PotentialAssessmentAgent' in s and 'ProblemIdentificationAgent' in s; print('OK')"`
Expected: 输出 `OK`

- [x] **Step 5: Commit**（spec 无变更，无需提交）

```bash
git add openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md
git commit -m "docs(sync-models): 校对 professional-model-agents delta spec 模型1-3 输入输出与 scenario"
```

---

## Task 2: 校对 professional-model-agents delta spec 模型 4-6（含 D1 名称回退）

**对应 tasks.md：** 1.4 / 1.5 / 1.6

**Files:**
- 校对: `openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md`

**Interfaces:**
- Consumes: D1（model 6 名称回退为「耕地综合地力改良提升模型」）、D2、D3
- Produces: 模型 4-6 requirement 完整，model 6 名称已回退且标注内部实现来源

- [ ] **Step 1: 校对模型 4 AcidificationRemediationAgent requirement**

确认模型 4 requirement 包含：
- 标题行含「耕地土壤酸化改良模型」
- **模型输入**含：土壤pH、有机质、阳离子交换量、土壤黏粒、总氮、游离铁、总铁、交换性氢离子、交换性铝离子、全氮、全磷、全钾、游离氧化铁、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标pH（或pH增加值）
- **模型输出**含：土壤酸化程度级别、土壤本底酸量、农业活动产酸量、碱性调理剂施用量、木本泥炭施用量
- 4 个 scenario：酸化程度判定（引用 GB/T 42817-2023）、调理剂施用量计算（引用 GB/T 42817-2023 与 NY/T 443-2019）、不同土地利用类型酸化、农户酸化判断

- [ ] **Step 2: 校对模型 5 OrganicMatterAgent requirement**

确认模型 5 requirement 包含：
- 标题行含「耕地土壤有机质培肥提升模型」
- **模型输入**含：土壤pH、有机质、有效磷、速效钾、总氮、阳离子交换量、土壤黏粒、交换性氢离子、交换性铝离子、游离铁、总铁、全氮、全磷、全钾、游离氧化铁、土壤容重、年降雨量、年降雨pH年均值、施肥类型及施肥量、作物类型及产量、农田类型（水田/旱地）、目标土壤有机质
- **模型输出**含：有机肥/秸秆、有机肥施用量、秸秆施用量
- 4 个 scenario：有机质含量评估、有机肥施用量计算、有机质低值区域识别、有机质低值原因

- [ ] **Step 3: 校对模型 6 名称回退（D1）**

确认模型 6 requirement 的标题行与描述使用「耕地综合地力改良提升模型」（xlsx 版），而非「耕地肥力机器学习预测模型」。若仍为旧名，执行修正。

读取当前标题行，应为类似：
```
系统 SHALL 实现 `FertilityMLAgent` 智能体，对应模型6「耕地综合地力改良提升模型」，负责综合多个模型结果形成分区分类的综合提升建议。该智能体内部使用预训练的 ExtraTreesRegressor 模型对 SOC 和 Dose 进行 ML 预测作为综合地力评估的计算单元，并通过 `framework/agents/manager.py` 注册为 `model-6`。
```

确认 requirement 内含来源标注（xlsx 未填写，保留现有实现）：
```
**模型输入**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合上述模型1-5的输入指标，包括土壤理化指标、农田类型、目标有机质等

**模型输出**（来源：xlsx 总览表，xlsx 未填写，保留现有实现）：
- 综合提升建议（基于 SOC 预测和 Dose 预测的综合地力评估）
```

若标注缺失，补全"（xlsx 未填写，保留现有实现）"。

- [ ] **Step 4: 验证 model 6 名称已回退**

Run: `python -c "p='openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md'; s=open(p,encoding='utf-8').read(); assert '耕地综合地力改良提升模型' in s; assert '耕地肥力机器学习预测模型' not in s; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md
git commit -m "docs(sync-models): 校对 delta spec 模型4-6，确认 model6 名称回退为综合地力改良提升模型(D1)"
```

---

## Task 3: 修正 role-based-routing delta spec 的 TYPE 描述与 D5 对齐

**对应 tasks.md：** 1.7

**Files:**
- 修改: `openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md`

**Interfaces:**
- Consumes: D5 关键词映射（TYPE_1=稳定性/退化风险→model-1；TYPE_2=酸化治理→model-4；TYPE_3=潜力/障碍→model-2/3；TYPE_4=有机质/肥力→model-5/6）
- Produces: delta spec 的 TYPE 描述与 Task 4/5 的 nodes.py 关键词一致，供 Task 11 路由测试断言

**说明：** 当前 delta spec 第 7 行 TYPE_1 描述为「酸化程度/退化风险」，与 D5 不一致（D5 把"酸化程度"移入 TYPE_2）。需修正 4 条 TYPE 描述。

- [ ] **Step 1: 修正 4 条 TYPE 描述**

将 `openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md` 中的映射块替换为：

```markdown
问题类型与模型映射：
- TYPE_1（等级稳定性/退化风险）→ StabilityRiskAgent (model-1)
- TYPE_2（酸化程度/调理剂/改良方案）→ AcidificationRemediationAgent (model-4)
- TYPE_3（潜力/障碍因素/主要问题）→ ProblemIdentificationAgent (model-3) / PotentialAssessmentAgent (model-2)
- TYPE_4（有机质/有机肥/肥力/有机碳）→ FertilityMLAgent (model-6) / OrganicMatterAgent (model-5)
```

- [ ] **Step 2: 确认 scenario 块保持不变**

确认以下 6 个 scenario 仍存在且未改：识别省市管理端问题、识别县域执行端问题、识别农户种植端问题、识别酸化治理问题、识别有机质培肥问题、关键词优先于向量匹配。

- [ ] **Step 3: 验证描述已对齐**

Run: `python -c "p='openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md'; s=open(p,encoding='utf-8').read(); assert 'TYPE_1（等级稳定性/退化风险）' in s; assert 'TYPE_2（酸化程度/调理剂/改良方案）' in s; print('OK')"`
Expected: 输出 `OK`

- [ ] **Step 4: Commit**

```bash
git add openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md
git commit -m "docs(sync-models): 修正 role-based-routing delta spec TYPE 描述与 D5 关键词对齐"
```

---

## Task 4: 更新 nodes.py 关键词 TYPE_1/TYPE_2 与 RELEVANCE_KEYWORDS（TDD）

**对应 tasks.md：** 2.1 / 2.2

**Files:**
- 修改: `framework/agents/nodes.py`（`QUESTION_TYPE_1_KEYWORDS`、`QUESTION_TYPE_2_KEYWORDS`、`RELEVANCE_KEYWORDS`、`REFERENCE_QUESTIONS`、`QUESTION_TYPE_TO_MODEL_ID`）
- 测试: `tests/test_question_type_keywords.py`（本任务先建该文件并写 TYPE_1/TYPE_2 用例）

**Interfaces:**
- Consumes: D5 关键词表；role-based-routing delta spec（Task 3 已对齐）
- Produces: `identify_question_type` 对 xlsx model-1/model-4 经典问题返回正确 TYPE；`_identify_question_type_keyword` 新关键词签名不变（`str -> tuple[int, float]`）

**说明：** 当前 `QUESTION_TYPE_1_KEYWORDS` 是酸化词（与 D5 冲突），TYPE_2 含"施加""用量"通用词（D5 要求移除）。同时 `RELEVANCE_KEYWORDS` 缺"田""地""等级""稳定"等词，导致 xlsx 经典问题 relevance<0.3 被判 0，必须扩展。

- [ ] **Step 1: 写失败测试（TYPE_1 稳定性 + TYPE_2 酸化治理）**

创建 `tests/test_question_type_keywords.py`：

```python
"""测试问题类型关键词路由覆盖 xlsx 经典问题（D5）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _identify(question):
    from framework.agents.nodes import identify_question_type
    return identify_question_type(question)


def test_type1_stability_province_question():
    """省市端稳定性问题 → TYPE_1"""
    qt, _ = _identify("查询区域内耕地质量等级整体稳定吗？")
    assert qt == 1, f"期望 TYPE_1，实际 {qt}"


def test_type1_stability_county_question():
    """县域端稳定性薄弱片区 → TYPE_1"""
    qt, _ = _identify("本县哪些乡镇或地块等级稳定性较弱，需要现场复核？")
    assert qt == 1


def test_type1_stability_farmer_question():
    """农户端稳不稳 → TYPE_1"""
    qt, _ = _identify("我的这块田质量等级稳不稳？")
    assert qt == 1


def test_type1_attention_list_question():
    """关注清单 → TYPE_1"""
    qt, _ = _identify("查询区域内哪些对象需要纳入重点关注清单？")
    assert qt == 1


def test_type2_acidification_degree_question():
    """酸化程度判定 → TYPE_2（model-4）"""
    qt, _ = _identify("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？")
    assert qt == 2


def test_type2_remediation_dosage_question():
    """农户端碱性调理剂施用量 → TYPE_2"""
    qt, _ = _identify("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？")
    assert qt == 2


def test_type2_landuse_acidification_question():
    """不同土地利用类型酸化 → TYPE_2"""
    qt, _ = _identify("查询区域内不同土地利用类型的酸化程度")
    assert qt == 2


def test_type2_no_generic_words_collision():
    """TYPE_2 已移除通用词"施加""用量"，但含具体词"调理剂"仍命中 TYPE_2"""
    from framework.agents.nodes import QUESTION_TYPE_2_KEYWORDS
    assert "施加" not in QUESTION_TYPE_2_KEYWORDS
    assert "用量" not in QUESTION_TYPE_2_KEYWORDS
    assert "调理剂" in QUESTION_TYPE_2_KEYWORDS


if __name__ == "__main__":
    test_type1_stability_province_question()
    test_type1_stability_county_question()
    test_type1_stability_farmer_question()
    test_type1_attention_list_question()
    test_type2_acidification_degree_question()
    test_type2_remediation_dosage_question()
    test_type2_landuse_acidification_question()
    test_type2_no_generic_words_collision()
    print("\nTYPE_1/TYPE_2 关键词测试通过！")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 多个用例 FAIL（当前 TYPE_1 是酸化词，稳定性问题会命中 TYPE_2 或返回 0；"稳不稳""关注清单"无关键词命中）

- [ ] **Step 3: 更新 nodes.py 关键词与相关性词**

在 `framework/agents/nodes.py` 中，将第 32-35 行的关键词常量替换为：

```python
QUESTION_TYPE_1_KEYWORDS = [
    "等级稳定", "稳定性", "稳不稳", "稳定吗", "稳定性较弱", "退化风险",
    "关注清单", "重点关注", "临界状态", "风险类型", "等级整体", "掉级",
]
QUESTION_TYPE_2_KEYWORDS = [
    "酸化程度", "酸化等级", "酸化现状", "酸化严重", "酸化了", "酸化治理",
    "调理剂", "碱性材料", "碱性调理剂", "木本泥炭", "石灰", "pH提升",
    "土地利用类型", "酸化",
]
QUESTION_TYPE_3_KEYWORDS = [
    "潜力", "障碍因素", "主要问题", "障碍诊断", "潜力分布", "障碍组合",
    "提升潜力", "地块诊断", "毛病", "障碍等级",
]
QUESTION_TYPE_4_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "肥力", "综合地力", "有机碳", "SOC", "soc",
    "施用量", "施肥量", "Dose", "dose", "培肥", "综合肥力",
]
```

将第 37-42 行的 `RELEVANCE_KEYWORDS` 替换为（扩展通用词确保 xlsx 经典问题 relevance≥0.3）：

```python
RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂",
    # 扩展：覆盖 xlsx 经典问题通用词，确保 relevance >= 0.3
    "田", "地", "质量", "等级", "稳定", "潜力", "障碍", "问题",
    "乡镇", "县", "片区", "地块", "农户", "风险", "关注", "清单",
    "诊断", "毛病", "增产", "粮食", "碳氮比", "全氮", "容重",
]
```

将第 44-49 行的 `REFERENCE_QUESTIONS` 替换为（对齐 xlsx 经典问题，供向量匹配参考）：

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
}
```

将第 216-220 行的 `QUESTION_TYPE_TO_MODEL_ID` 替换为（对齐 D5 映射，消除过时 ID）：

```python
QUESTION_TYPE_TO_MODEL_ID = {
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",
    4: "model-5,model-6",
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 确认现有 nodes 相关测试不破坏**

Run: `python -m pytest tests/test_agent_specialized.py tests/test_fertility_ml_prediction.py -v`
Expected: 全部 PASS（关键词改动不影响 agent 单元测试）

- [ ] **Step 6: Commit**

```bash
git add framework/agents/nodes.py tests/test_question_type_keywords.py
git commit -m "feat(sync-models): 更新 nodes.py TYPE_1/2 关键词与相关性词覆盖 xlsx 经典问题(D5)"
```

---

## Task 5: 验证 nodes.py TYPE_3/TYPE_4 关键词与关键词优先级（TDD）

**对应 tasks.md：** 2.3 / 2.4 / 2.5

**Files:**
- 修改: `tests/test_question_type_keywords.py`（追加 TYPE_3/TYPE_4 与优先级用例）
- 校对: `framework/agents/nodes.py`（TYPE_3/TYPE_4 已在 Task 4 更新，本任务验证）

**Interfaces:**
- Consumes: Task 4 的关键词常量
- Produces: TYPE_3/TYPE_4 路由正确；关键词优先级逻辑（`_identify_question_type_keyword` 先于向量）经测试确认

- [ ] **Step 1: 追加失败测试（TYPE_3/TYPE_4 + 优先级）**

在 `tests/test_question_type_keywords.py` 末尾（`if __name__` 之前）追加：

```python
def test_type3_potential_question():
    """潜力评估 → TYPE_3（model-2/3）"""
    qt, _ = _identify("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？")
    assert qt == 3


def test_type3_county_potential_distribution():
    """县域优先改良片区 → TYPE_3"""
    qt, _ = _identify("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？")
    assert qt == 3


def test_type3_farmer_plot_diagnosis():
    """农户地块诊断"毛病" → TYPE_3"""
    qt, _ = _identify("我这块地到底有啥毛病？")
    assert qt == 3


def test_type3_problem_identification():
    """主要问题/障碍因素 → TYPE_3"""
    qt, _ = _identify("全省耕地质量存在哪些问题？")
    assert qt == 3


def test_type4_organic_matter_content():
    """有机质含量 → TYPE_4（model-5/6）"""
    qt, _ = _identify("全省耕地土壤有机质含量如何，空间分布情况？")
    assert qt == 4


def test_type4_manure_dosage():
    """有机肥/秸秆施用量 → TYPE_4"""
    qt, _ = _identify("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？")
    assert qt == 4


def test_type4_fertility_ml():
    """农户肥力/SOC → TYPE_4"""
    qt, _ = _identify("我的田肥力怎么样？")
    assert qt == 4


def test_type4_county_organic_average():
    """县域有机质平均含量 → TYPE_4"""
    qt, _ = _identify("本县耕地土壤有机质平均含量是多少？")
    assert qt == 4


def test_keyword_match_priority_over_vector():
    """D5：关键词匹配优先于向量匹配。
    即使 embedding 可用，含具体关键词的问题也应被关键词逻辑判定。
    这里直接测试 _identify_question_type_keyword 返回非 0。"""
    from framework.agents.nodes import _identify_question_type_keyword
    # 含 TYPE_4 具体词"有机肥"
    qt, _ = _identify_question_type_keyword("有机肥每亩施用量多少？")
    assert qt == 4
    # 含 TYPE_2 具体词"调理剂"
    qt, _ = _identify_question_type_keyword("我要施加多少碱性调理剂？")
    assert qt == 2


def test_type_order_no_cross_collision():
    """关键词不跨类型重叠：TYPE_1 不含酸化词，TYPE_2 不含稳定词"""
    from framework.agents.nodes import (
        QUESTION_TYPE_1_KEYWORDS, QUESTION_TYPE_2_KEYWORDS,
        QUESTION_TYPE_3_KEYWORDS, QUESTION_TYPE_4_KEYWORDS,
    )
    # "酸化"属 TYPE_2，不应出现在 TYPE_1
    assert not any("酸化" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    # "稳定"属 TYPE_1，不应出现在 TYPE_2
    assert not any("稳定" in kw for kw in QUESTION_TYPE_2_KEYWORDS)
    # "潜力"属 TYPE_3，不应出现在其他
    assert not any("潜力" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    assert not any("潜力" in kw for kw in QUESTION_TYPE_2_KEYWORDS)
    # "有机质"属 TYPE_4，不应出现在 TYPE_1/2/3
    assert not any("有机质" in kw for kw in QUESTION_TYPE_1_KEYWORDS)
    assert not any("有机质" in kw for kw in QUESTION_TYPE_3_KEYWORDS)
```

并更新文件末尾的 `if __name__ == "__main__":` 块，追加新用例调用：

```python
if __name__ == "__main__":
    test_type1_stability_province_question()
    test_type1_stability_county_question()
    test_type1_stability_farmer_question()
    test_type1_attention_list_question()
    test_type2_acidification_degree_question()
    test_type2_remediation_dosage_question()
    test_type2_landuse_acidification_question()
    test_type2_no_generic_words_collision()
    test_type3_potential_question()
    test_type3_county_potential_distribution()
    test_type3_farmer_plot_diagnosis()
    test_type3_problem_identification()
    test_type4_organic_matter_content()
    test_type4_manure_dosage()
    test_type4_fertility_ml()
    test_type4_county_organic_average()
    test_keyword_match_priority_over_vector()
    test_type_order_no_cross_collision()
    print("\n全部问题类型关键词测试通过！")
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 PASS（TYPE_3/4 关键词已在 Task 4 写入；优先级用例验证 `_identify_question_type_keyword` 命中具体词）

若有用例 FAIL，检查 `framework/agents/nodes.py` 的 TYPE_3/TYPE_4 关键词是否与 Task 4 Step 3 写入一致，必要时补词。

- [ ] **Step 3: 确认 _identify_question_type_keyword 优先级逻辑未被破坏**

Run: `python -c "from framework.agents.nodes import identify_question_type; print(identify_question_type('有机肥每亩施用量多少？'))"`
Expected: 输出形如 `(4, 0.x)`，TYPE=4

- [ ] **Step 4: Commit**

```bash
git add tests/test_question_type_keywords.py
git commit -m "test(sync-models): 补充 TYPE_3/4 关键词路由与优先级测试(D5)"
```

---

## Task 6: 更新 StabilityRiskAgent 与 PotentialAssessmentAgent 回复模板（TDD）

**对应 tasks.md：** 3.1 / 3.2

**Files:**
- 修改: `framework/agents/specialized/stability_risk_agent.py`（`answer_question`）
- 修改: `framework/agents/specialized/potential_agent.py`（`answer_question`）
- 测试: `tests/test_agent_classic_qa.py`（本任务新建并写 model-1/model-2 用例）

**Interfaces:**
- Consumes: delta spec 模型 1/2 scenario（Task 1）；`answer_question(question: str, context: Dict) -> Dict` 签名不变
- Produces: model-1/model-2 对 xlsx 三角色经典问题返回对齐回复；`StabilityRiskAgent.answer_question` 新增"县域薄弱片区""农户稳不稳""关注清单"分支；`PotentialAssessmentAgent.answer_question` 新增"县域潜力分布""农户地块诊断"分支

- [ ] **Step 1: 写失败测试（model-1/model-2 经典 Q&A）**

创建 `tests/test_agent_classic_qa.py`：

```python
"""测试 6 个 agent 对 xlsx 3 角色经典问题的回复（D4 最小化改动）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stability_overall_province():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内耕地质量等级整体稳定吗？", {})
    assert out["simulated"] is True
    assert "稳定" in out["answer"]
    assert 0.0 <= out["confidence"] <= 1.0


def test_stability_weak_county_list():
    """县域端：稳定性较弱乡镇/地块清单"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question(
        "本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", {})
    assert out["simulated"] is True
    # 回复应包含薄弱片区清单语义
    assert "较弱" in out["answer"] or "薄弱" in out["answer"] or "稳定" in out["answer"]
    assert len(out["evidence"]) >= 1


def test_stability_farmer_plain_language():
    """农户端：通俗语言说明稳不稳"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("我的这块田质量等级稳不稳？", {})
    assert out["simulated"] is True
    assert "稳" in out["answer"]
    # 通俗语言：包含"比较稳""一般稳""不太稳"之一或稳定性类型说明
    assert any(w in out["answer"] for w in ["比较稳", "一般稳", "不太稳", "稳定", "一般", "较弱"])


def test_stability_attention_list():
    """重点关注清单"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    out = StabilityRiskAgent().answer_question("查询区域内哪些对象需要纳入重点关注清单？", {})
    assert out["simulated"] is True
    assert "关注" in out["answer"] or "清单" in out["answer"] or "风险" in out["answer"]


def test_potential_overall_uplift():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question(
        "辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", {})
    assert out["simulated"] is True
    assert "潜力" in out["answer"] or "障碍" in out["answer"]


def test_potential_county_distribution():
    """县域端：优先改良片区潜力分布"""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question(
        "我们县划定的优先改良片区具体在哪几个村？每块潜力多大？", {})
    assert out["simulated"] is True
    assert "潜力" in out["answer"] or "障碍" in out["answer"] or "片区" in out["answer"]


def test_potential_farmer_plot_diagnosis():
    """农户端：地块诊断"毛病""""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    out = PotentialAssessmentAgent().answer_question("我这块地到底有啥毛病？", {})
    assert out["simulated"] is True
    # 回复应给出诊断/障碍因子
    assert "障碍" in out["answer"] or "毛病" in out["answer"] or "潜力" in out["answer"] or "诊断" in out["answer"]


if __name__ == "__main__":
    test_stability_overall_province()
    test_stability_weak_county_list()
    test_stability_farmer_plain_language()
    test_stability_attention_list()
    test_potential_overall_uplift()
    test_potential_county_distribution()
    test_potential_farmer_plot_diagnosis()
    print("\nmodel-1/model-2 经典 Q&A 测试通过！")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_classic_qa.py -v`
Expected: `test_stability_weak_county_list` / `test_stability_farmer_plain_language` / `test_stability_attention_list` / `test_potential_county_distribution` / `test_potential_farmer_plot_diagnosis` FAIL（当前分支未覆盖这些关键词）

- [ ] **Step 3: 更新 StabilityRiskAgent.answer_question**

将 `framework/agents/specialized/stability_risk_agent.py` 的 `answer_question` 方法（第 55-100 行）替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        total_area = sum(c["area_mu"] for c in counties)
        stable_area = sum(c["area_mu"] for c in counties if c["stability"] == "稳定")
        general_area = sum(c["area_mu"] for c in counties if c["stability"] == "一般")
        weak_area = sum(c["area_mu"] for c in counties if c["stability"] == "较弱")

        # 农户端：通俗语言说明稳不稳
        if "稳不稳" in question or ("我的" in question and "田" in question and "稳定" not in question and "风险" not in question):
            plain = "比较稳" if stable_area >= general_area and stable_area >= weak_area else (
                "一般稳" if general_area >= weak_area else "不太稳")
            answer = (
                f"您的地块耕地质量等级稳定性为「{plain}」。"
                f"参考全县稳定性分布：稳定占比 {stable_area/total_area*100:.1f}%，"
                f"一般占比 {general_area/total_area*100:.1f}%，较弱占比 {weak_area/total_area*100:.1f}%。"
            )
            evidence = [
                {"metric": "稳定性类型", "value": plain},
                {"metric": "稳定面积占比", "value": f"{stable_area/total_area*100:.1f}%"},
            ]
            confidence = 0.80
        # 县域端：稳定性较弱片区清单
        elif "稳定性较弱" in question or "现场复核" in question or ("乡镇" in question and "地块" in question):
            weak_counties = sorted(
                [c for c in counties if c["stability"] == "较弱"],
                key=lambda c: c["stability_score"],
            )
            names = "、".join(c["name"] for c in weak_counties[:5]) or "无明显薄弱片区"
            answer = (
                f"本县稳定性较弱的乡镇/地块清单：{names}。"
                f"建议对上述区域现场复核当前等级、稳定性类型与是否接近等级边界。"
            )
            evidence = [
                {"county": c["name"], "stability": c["stability"],
                 "stability_score": c["stability_score"], "area_mu": c["area_mu"]}
                for c in weak_counties[:5]
            ]
            confidence = 0.82
        # 重点关注清单
        elif "关注清单" in question or "重点关注" in question:
            focus = sorted(
                [c for c in counties if c["risk_index"] >= 0.40 or c["stability"] == "较弱"],
                key=lambda c: c["risk_index"], reverse=True,
            )
            names = "、".join(c["name"] for c in focus[:5])
            answer = (
                f"建议纳入重点关注清单：{names}。"
                f"关注其等级稳定性、退化风险等级、风险类型与主要风险来源，"
                f"后续可调用模型2/3进行潜力与障碍诊断。"
            )
            evidence = [
                {"county": c["name"], "risk_index": c["risk_index"],
                 "stability": c["stability"], "risk_type": "退化风险" if c["risk_index"] >= 0.5 else "临界风险"}
                for c in focus[:5]
            ]
            confidence = 0.83
        # 省市端：稳定性总体评价
        elif "整体" in question or "稳定" in question:
            answer = (
                f"全省耕地质量稳定性总体评价：稳定占比 {stable_area/total_area*100:.1f}%，"
                f"一般占比 {general_area/total_area*100:.1f}%，"
                f"较弱占比 {weak_area/total_area*100:.1f}%。"
            )
            evidence = [
                {"metric": "稳定面积占比", "value": f"{stable_area/total_area*100:.1f}%"},
                {"metric": "一般面积占比", "value": f"{general_area/total_area*100:.1f}%"},
                {"metric": "较弱面积占比", "value": f"{weak_area/total_area*100:.1f}%"},
                {"recommendation": "对较弱区域优先纳入退化风险重点关注清单"},
            ]
            confidence = 0.85
        # 退化风险
        elif "退化风险" in question or "风险" in question:
            risk_counties = sorted(
                [c for c in counties if c["quality_grade"] >= 4 and c["risk_index"] >= 0.35],
                key=lambda c: c["risk_index"],
                reverse=True,
            )
            names = "、".join(c["name"] for c in risk_counties[:3])
            answer = f"高等级耕地存在退化风险的县区（按风险指数降序）：{names}。"
            evidence = [
                {"county": c["name"], "risk_index": c["risk_index"], "area_mu": c["area_mu"]}
                for c in risk_counties[:5]
            ]
            confidence = 0.82
        else:
            answer = "已返回全省 10 个县区的质量等级、稳定性评分与退化风险指数（模拟数据）。"
            evidence = [{"county": c["name"], "stability": c["stability"]} for c in counties[:5]]
            confidence = 0.75

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
```

- [ ] **Step 4: 更新 PotentialAssessmentAgent.answer_question**

将 `framework/agents/specialized/potential_agent.py` 的 `answer_question` 方法（第 79-115 行）替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        indicators = [dict(i) for i in MOCK_INDICATORS]
        for ind in indicators:
            lower_is_better = ind["name"] in ("容重",)
            ind["obstacle_degree"] = _compute_obstacle_degree(
                ind["current"], ind["potential"], lower_is_better
            )
            ind["potential_level"] = MockDataLoader.apply_threshold(
                100.0 - ind["obstacle_degree"], POTENTIAL_RULES
            )

        avg_obstacle = round(sum(i["obstacle_degree"] for i in indicators) / len(indicators), 2)
        overall_level = MockDataLoader.apply_threshold(100.0 - avg_obstacle, POTENTIAL_RULES)

        ph_indicator = next((i for i in indicators if i["name"] == "pH"), None)
        target_ph = ph_indicator["potential"] if ph_indicator else 6.5

        top_obstacles = sorted(indicators, key=lambda x: x["obstacle_degree"], reverse=True)[:3]

        # 农户端：地块诊断"毛病"
        if "毛病" in question or ("我这块地" in question and "潜力" not in question):
            answer = (
                f"地块诊断结论：耕地质量提升潜力等级为 {overall_level}。"
                f"主要障碍因子：{', '.join(i['name'] for i in top_obstacles)}，"
                f"建议针对性改良上述指标（附示意图）。"
            )
            evidence = [
                {"indicator": i["name"], "obstacle_degree": i["obstacle_degree"],
                 "current": i["current"], "potential": i["potential"]}
                for i in top_obstacles
            ]
            confidence = 0.79
        # 县域端：优先改良片区潜力分布
        elif "片区" in question or ("村" in question and "潜力" in question):
            answer = (
                f"县域优先改良片区潜力分布：整体潜力等级 {overall_level}，"
                f"平均障碍度值 {avg_obstacle}。建议以地块为单元绘制潜力分布图，"
                f"颜色深浅表示潜力值，选中地块显示村名、地块编号、面积、当前等级、目标等级、潜力分值。"
            )
            evidence = [
                {"indicator": i["name"], "obstacle_degree": i["obstacle_degree"],
                 "potential_level": i["potential_level"]}
                for i in top_obstacles
            ]
            confidence = 0.81
        # 省市端：总体潜力评估（含增产粮食）
        elif "潜力" in question or "增产" in question or "粮食" in question:
            answer = (
                f"耕地质量提升潜力等级为 {overall_level}，"
                f"平均障碍度值 {avg_obstacle}，"
                f"主要障碍因素：{', '.join(i['name'] for i in top_obstacles)}。"
                f"可改善面积与粮食增产潜力需结合地块面积进一步汇总。"
            )
            evidence = [
                {"indicator": i["name"], "obstacle_degree": i["obstacle_degree"],
                 "potential_level": i["potential_level"]}
                for i in top_obstacles
            ]
            evidence.append({"target_ph": target_ph, "recommendation": "目标 pH 供下游模型3使用"})
            confidence = 0.80
        else:
            answer = (
                f"耕地质量提升潜力等级为 {overall_level}，"
                f"平均障碍度值 {avg_obstacle}，"
                f"主要障碍因素：{', '.join(i['name'] for i in top_obstacles)}。"
            )
            evidence = [
                {"indicator": i["name"], "obstacle_degree": i["obstacle_degree"],
                 "potential_level": i["potential_level"]}
                for i in top_obstacles
            ]
            evidence.append({"target_ph": target_ph, "recommendation": "目标 pH 供下游模型3使用"})
            confidence = 0.80

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
            "target_ph": target_ph,
        })
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_classic_qa.py -v`
Expected: 全部 PASS

- [ ] **Step 6: 回归现有 agent 单元测试**

Run: `python -m pytest tests/test_agent_specialized.py -v`
Expected: 全部 PASS（现有 `test_stability_risk_agent_answer_question_overall` 用"整体稳定吗"仍命中省市端分支；`test_potential_agent_answer_question` 用"潜力"命中潜力分支）

- [ ] **Step 7: Commit**

```bash
git add framework/agents/specialized/stability_risk_agent.py framework/agents/specialized/potential_agent.py tests/test_agent_classic_qa.py
git commit -m "feat(sync-models): 更新 StabilityRisk/Potential Agent 回复模板对齐 xlsx 三角色经典问题(D4)"
```

---

## Task 7: 更新 ProblemIdentificationAgent 与 AcidificationRemediationAgent 回复模板（TDD）

**对应 tasks.md：** 3.3 / 3.4

**Files:**
- 修改: `framework/agents/specialized/problem_agent.py`（`answer_question`）
- 修改: `framework/agents/specialized/acidification_agent.py`（`answer_question`）
- 测试: `tests/test_agent_classic_qa.py`（追加 model-3/model-4 用例）

**Interfaces:**
- Consumes: delta spec 模型 3/4 scenario；GB/T 42817-2023 与 NY/T 443-2019 标准引用
- Produces: model-3 新增"农户地块问题"分支；model-4 新增"不同土地利用类型酸化""农户酸化判断"分支，治理分支文案引用 GB/T 42817-2023 与 NY/T 443-2019

- [ ] **Step 1: 追加失败测试（model-3/model-4 经典 Q&A）**

在 `tests/test_agent_classic_qa.py` 的 `if __name__` 块之前追加：

```python
def test_problem_overall_factors():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("全省耕地质量存在哪些问题？", {})
    assert out["simulated"] is True
    assert "障碍" in out["answer"] or "问题" in out["answer"]


def test_problem_county_diagnosis():
    """县域端：县/乡镇耕地障碍诊断"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("县/乡镇里的耕地在哪些方面有问题", {})
    assert out["simulated"] is True
    assert "障碍" in out["answer"] or "问题" in out["answer"]


def test_problem_farmer_simple_language():
    """农户端：我这块地有没有问题（简单语言）"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    out = ProblemIdentificationAgent().answer_question("我这块地有没有问题？", {})
    assert out["simulated"] is True
    assert "等级" in out["answer"] or "障碍" in out["answer"] or "问题" in out["answer"]


def test_acidification_degree_with_standard():
    """酸化程度判定引用 GB/T 42817-2023"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", {})
    assert out["simulated"] is True
    assert "酸化" in out["answer"] or "pH" in out["answer"]


def test_acidification_remediation_dosage_with_standard():
    """调理剂施用量引用 GB/T 42817-2023 与 NY/T 443-2019"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", {})
    assert out["simulated"] is True
    assert "石灰" in out["answer"] or "kg" in out["answer"] or "调理剂" in out["answer"]
    assert "GB/T 42817" in out["answer"] or "NY/T 443" in out["answer"]


def test_acidification_landuse_types():
    """不同土地利用类型酸化程度"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question(
        "查询区域内不同土地利用类型的酸化程度", {})
    assert out["simulated"] is True
    assert "酸化" in out["answer"] or "pH" in out["answer"]


def test_acidification_farmer_severity():
    """农户端：我的这块田酸化严重吗"""
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    out = AcidificationRemediationAgent().answer_question("我的这块田酸化严重吗？", {})
    assert out["simulated"] is True
    assert "酸化" in out["answer"] or "pH" in out["answer"] or "酸性" in out["answer"]
```

更新 `if __name__ == "__main__":` 块追加这些用例调用。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_classic_qa.py -v -k "problem or acidification"`
Expected: `test_acidification_remediation_dosage_with_standard` FAIL（当前治理分支未引用标准）；部分农户端/土地利用用例可能 FAIL

- [ ] **Step 3: 更新 ProblemIdentificationAgent.answer_question**

将 `framework/agents/specialized/problem_agent.py` 的 `answer_question` 方法（第 71-103 行）替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        result = self.execute({})["result"]
        primary = result["primary_factors"]
        secondary = result["secondary_factors"]
        combinations = result["combinations"]

        # 消费 model-2 的 target_ph
        target_ph_note = ""
        model2 = context.get("model-2") if isinstance(context, dict) else None
        if isinstance(model2, dict) and "target_ph" in model2:
            target_ph_note = f" 结合模型2目标 pH={model2['target_ph']}，"

        # 农户端：简单语言说明
        if "有没有问题" in question or ("我这块地" in question and "问题" in question):
            answer = (
                f"您的地块耕地质量等级诊断：主要障碍为 {', '.join(primary) if primary else '无明显主要障碍'}。"
                f"低等级指标：{', '.join(primary[:3]) if primary else '无'}。"
            )
            evidence = [
                {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
                for f in primary[:3]
            ]
            confidence = 0.80
        # 县域端：障碍诊断统计
        elif "县" in question or "乡镇" in question or "方面" in question:
            answer = (
                f"县域障碍诊断：主要障碍因素 {', '.join(primary) if primary else '无明显主要障碍'}；"
                f"次要障碍因素 {', '.join(secondary) if secondary else '无明显次要障碍'}。"
                f"{target_ph_note}"
                f"每个指标按 1~10 级频数统计，最后一列标注是否主要/次要障碍因素。"
                f"障碍组合：{', '.join(combinations) if combinations else '无明显复合障碍'}。"
            )
            evidence = [
                {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
                for f in primary[:3]
            ]
            evidence.extend([{"combination": c} for c in combinations])
            if isinstance(model2, dict) and "target_ph" in model2:
                evidence.append({"target_ph_from_model2": model2["target_ph"]})
            confidence = 0.83
        # 省市端：主要问题/障碍因素识别
        else:
            answer = (
                f"主要障碍因素：{', '.join(primary) if primary else '无明显主要障碍'}；"
                f"次要障碍因素：{', '.join(secondary) if secondary else '无明显次要障碍'}。"
                f"{target_ph_note}"
                f"障碍组合：{', '.join(combinations) if combinations else '无明显复合障碍'}。"
            )
            evidence = [
                {"factor": f, "severity": result["severity_scores"][f], "type": "primary"}
                for f in primary[:3]
            ]
            evidence.extend([{"combination": c} for c in combinations])
            if isinstance(model2, dict) and "target_ph" in model2:
                evidence.append({"target_ph_from_model2": model2["target_ph"]})
            confidence = 0.83

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
```

- [ ] **Step 4: 更新 AcidificationRemediationAgent.answer_question**

将 `framework/agents/specialized/acidification_agent.py` 的 `answer_question` 方法（第 70-117 行）替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        # 农户端：酸化严重吗（地块酸化等级）
        if "酸化严重" in question or ("这块田" in question and "酸化" in question):
            answer = (
                f"您的地块土壤 pH={computed['ph']}，酸化等级为{computed['degree']}。"
                f"（依据 GB/T 42817-2023：酸性 5.5≤pH<6.5、强酸性 4.5≤pH<5.5、极强酸性 pH<4.5）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.86
        # 不同土地利用类型酸化
        elif "土地利用类型" in question or "旱地" in question or "水田" in question or "园地" in question:
            answer = (
                f"不同土地利用类型酸化程度：当前样本 pH={computed['ph']}（{computed['degree']}）。"
                f"建议按旱地、水田、园地、林地分别统计酸化等级及比例"
                f"（依据 GB/T 42817-2023 分级）。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.84
        # 农户端：调理剂施用量（引用 GB/T 42817-2023 与 NY/T 443-2019）
        elif "治理" in question or "调理剂" in question or "石灰" in question or "碱性材料" in question:
            answer = (
                f"土壤酸化程度为{computed['degree']}，"
                f"建议施石灰 {computed['lime_dosage']} kg/亩，"
                f"预计治理后 pH 提升至 {computed['ph_after_remediation']}。"
                f"（依据 GB/T 42817-2023 酸化等级判定与 NY/T 443-2019 调理剂施用量计算，"
                f"分两次施用，结合翻耕作业）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"], "unit": "cmol/kg"},
                {"metric": "lime_dosage", "value": computed["lime_dosage"], "unit": "kg/亩"},
                {"metric": "ph_after_remediation", "value": computed["ph_after_remediation"]},
                {"standard": "GB/T 42817-2023"},
                {"standard": "NY/T 443-2019"},
                {"recommendation": "分两次施用，结合翻耕作业"},
            ]
            confidence = 0.85
        # 酸化程度判定
        elif "酸化程度" in question or "酸化等级" in question or "酸化现状" in question or "酸化" in question:
            answer = (
                f"当前土壤 pH={computed['ph']}，酸化程度为{computed['degree']}。"
                f"交换性铝={computed['exchangeable_al']} cmol/kg。"
                f"（依据 GB/T 42817-2023 分级）"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"]},
                {"standard": "GB/T 42817-2023"},
            ]
            confidence = 0.88
        else:
            answer = (
                f"土壤 pH={computed['ph']}（{computed['degree']}），"
                f"建议石灰施用量 {computed['lime_dosage']} kg/亩。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "lime_dosage", "value": computed["lime_dosage"]},
            ]
            confidence = 0.80

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_classic_qa.py -v -k "problem or acidification"`
Expected: 全部 PASS

- [ ] **Step 6: 回归现有 agent 单元测试**

Run: `python -m pytest tests/test_agent_specialized.py -v -k "problem or acidification"`
Expected: 全部 PASS

- [ ] **Step 7: Commit**

```bash
git add framework/agents/specialized/problem_agent.py framework/agents/specialized/acidification_agent.py tests/test_agent_classic_qa.py
git commit -m "feat(sync-models): 更新 Problem/Acidification Agent 回复模板含 GB/T 42817 与 NY/T 443 引用(D4)"
```

---

## Task 8: 更新 OrganicMatterAgent 与 FertilityMLAgent 回复模板（TDD）

**对应 tasks.md：** 3.5 / 3.6

**Files:**
- 修改: `framework/agents/specialized/organic_matter_agent.py`（`answer_question`）
- 修改: `framework/agents/specialized/fertility_ml_agent.py`（`_format_both` 文案对齐"综合地力"）
- 测试: `tests/test_agent_classic_qa.py`（追加 model-5/model-6 用例）

**Interfaces:**
- Consumes: delta spec 模型 5/6 scenario；D1（model 6 综合地力表述）
- Produces: model-5 新增"县域有机质平均含量""低值原因"分支；model-6 `_format_both` 文案含"综合地力"

- [ ] **Step 1: 追加失败测试（model-5/model-6 经典 Q&A）**

在 `tests/test_agent_classic_qa.py` 的 `if __name__` 块之前追加：

```python
def test_organic_content_overall():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question(
        "全省耕地土壤有机质含量如何，空间分布情况？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]


def test_organic_manure_straw_dosage():
    """有机肥/秸秆施用量"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question(
        "为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", {})
    assert out["simulated"] is True
    assert "kg" in out["answer"] or "有机肥" in out["answer"] or "秸秆" in out["answer"]


def test_organic_county_average():
    """县域端：本县有机质平均含量"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question("本县耕地土壤有机质平均含量是多少？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]


def test_organic_low_value_reason():
    """有机质低值原因"""
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    out = OrganicMatterAgent().answer_question("耕地有机质含量低的原因是什么？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]


def test_fertility_ml_overall_diagnosis(monkeypatch):
    """model-6 综合诊断含'综合地力'表述（D1）"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5, "soc_confidence": 0.91,
            "dose_prediction": 150.0, "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考",
            "imputed_features": [], "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        })
    out = FertilityMLAgent().answer_question("我的田肥力怎么样？", {"data": {"pH": 6.5}})
    assert out["simulated"] is True
    assert "综合地力" in out["answer"] or "综合肥力" in out["answer"] or "SOC" in out["answer"]


def test_fertility_ml_soc_query(monkeypatch):
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5, "soc_confidence": 0.91,
            "dose_prediction": 150.0, "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [], "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        })
    out = FertilityMLAgent().answer_question("我的田土壤有机碳含量大概多少？", {"data": {"pH": 6.5}})
    assert out["simulated"] is True
    assert "SOC" in out["answer"] or "有机碳" in out["answer"]


def test_fertility_ml_dose_query(monkeypatch):
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5, "soc_confidence": 0.91,
            "dose_prediction": 150.0, "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [], "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        })
    out = FertilityMLAgent().answer_question("我这块地大概需要施多少有机肥？", {"data": {"pH": 6.5}})
    assert out["simulated"] is True
    assert "施肥" in out["answer"] or "t/ha" in out["answer"]
```

更新 `if __name__ == "__main__":` 块追加这些用例调用。

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_classic_qa.py -v -k "organic or fertility_ml"`
Expected: `test_organic_county_average` / `test_organic_low_value_reason` 可能 FAIL（当前分支未覆盖"本县""原因"）；`test_fertility_ml_overall_diagnosis` 中"综合地力"断言可能 FAIL（当前 `_format_both` 用"综合肥力诊断"）

- [ ] **Step 3: 更新 OrganicMatterAgent.answer_question**

将 `framework/agents/specialized/organic_matter_agent.py` 的 `answer_question` 方法（第 71-119 行）替换为：

```python
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        # 县域端：本县有机质平均含量与低值区域
        if "本县" in question or "平均含量" in question:
            answer = (
                f"本县耕地土壤有机质平均含量 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。"
                f"低值区域为等级"极低""低"的片区，建议作为培肥重点。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"recommendation": "识别有机质低值区域并给出明确数值"},
            ]
            confidence = 0.83
        # 有机质低值原因
        elif "原因" in question and ("有机质" in question or "低" in question):
            answer = (
                f"耕地有机质含量低的原因：受土壤类型、气候、地形、耕作制度、"
                f"秸秆还田与施肥管理影响。当前有机质 {computed['organic_matter']} g/kg"
                f"（{computed['level']}），低有机质区域应作为后续培肥重点。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"factors": "土壤类型/气候/地形/耕作制度/秸秆还田/施肥管理"},
            ]
            confidence = 0.80
        # 有机质含量评估（省市端）
        elif "含量" in question or "分布" in question or "现状" in question:
            answer = (
                f"全省耕地有机质含量平均 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。"
                f"全氮 {computed['total_nitrogen']} g/kg，碳氮比 {computed['cn_ratio']}。"
                f"空间分布建议按高/中/低等级占比与地形梯度分析。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"metric": "total_nitrogen", "value": computed["total_nitrogen"], "unit": "g/kg"},
                {"metric": "cn_ratio", "value": computed["cn_ratio"]},
            ]
            confidence = 0.84
        # 有机肥/秸秆施用量
        elif "施用量" in question or "有机肥" in question or "秸秆" in question:
            answer = (
                f"有机质等级为{computed['level']}，"
                f"建议有机肥施用量 {computed['manure_dosage']} kg/亩，"
                f"秸秆还田参考同等养分替代量，"
                f"预期有机质提升 {computed['potential_increase']} g/kg。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "manure_dosage", "value": computed["manure_dosage"], "unit": "kg/亩"},
                {"metric": "potential_increase", "value": computed["potential_increase"], "unit": "g/kg"},
                {"recommendation": "优先选用腐熟农家肥或商品有机肥，分季施用"},
            ]
            confidence = 0.82
        else:
            answer = (
                f"有机质 {computed['organic_matter']} g/kg（{computed['level']}），"
                f"建议施有机肥 {computed['manure_dosage']} kg/亩。"
            )
            evidence = [
                {"metric": "level", "value": computed["level"]},
                {"metric": "manure_dosage", "value": computed["manure_dosage"]},
            ]
            confidence = 0.78

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
        })
```

- [ ] **Step 4: 更新 FertilityMLAgent._format_both 文案对齐"综合地力"**

在 `framework/agents/specialized/fertility_ml_agent.py` 的 `_format_both` 方法（第 127-156 行）中，将返回的 `answer` 字符串替换为含"综合地力"表述。修改 `return MockDataLoader.mark_simulated({` 前的 answer 赋值：

```python
        return MockDataLoader.mark_simulated({
            "answer": (
                f"耕地综合地力改良提升综合诊断（基于 ML 预测）：\n"
                f"- SOC（土壤有机碳）：{pred['soc_prediction']:.2f} g/kg（置信度 {pred['soc_confidence']:.0%}）\n"
                f"- Dose（施肥量）：{pred['dose_prediction']:.2f} t/ha（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"
                f"{imputation_note}{fallback_note}"
            ),
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })
```

注意：仅修改 `answer` 字符串首行，`evidence`/`sources` 保持不变；`imputation_note`/`fallback_note` 逻辑保持不变。

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_classic_qa.py -v -k "organic or fertility_ml"`
Expected: 全部 PASS

- [ ] **Step 6: 回归 model-6 单元测试**

Run: `python -m pytest tests/test_agent_specialized.py tests/test_fertility_ml_prediction.py -v`
Expected: 全部 PASS（`test_fertility_ml_agent_answer_fertility_keywords` 断言 evidence 含 soc/dose，未断言 answer 文案，不受影响）

- [ ] **Step 7: Commit**

```bash
git add framework/agents/specialized/organic_matter_agent.py framework/agents/specialized/fertility_ml_agent.py tests/test_agent_classic_qa.py
git commit -m "feat(sync-models): 更新 Organic/FertilityML Agent 回复模板对齐综合地力表述(D1/D4)"
```

---

## Task 9: 验证 RoleRouter 三角色路由与 xlsx 三端一致（TDD）

**对应 tasks.md：** 4.1 / 4.2 / 4.3

**Files:**
- 测试: `tests/test_agent_classic_qa.py`（追加 RoleRouter 验证用例）
- 校对: `framework/agents/router.py`（预期不改，ROLE_AGENTS 已与 xlsx 一致）

**Interfaces:**
- Consumes: `RoleRouter.ROLE_AGENTS`（province/county/farmer → model 集合）
- Produces: 三角色路由经测试确认：province→[model-1,model-3]、county→[model-1,model-3,model-2]、farmer→[model-4,model-5,model-6]

**说明：** 当前 `router.py` 的 `ROLE_AGENTS` 已与 xlsx 三端一致。本任务以测试固化该映射，若发现不一致则修正 `router.py`。

- [ ] **Step 1: 追加路由验证测试**

在 `tests/test_agent_classic_qa.py` 的 `if __name__` 块之前追加：

```python
def test_router_province_agents():
    """省市管理端 → model-1, model-3"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    role = router.identify_role("查询区域内耕地质量等级整体稳定吗？全省情况")
    assert role == "province"
    agents = router.get_agents_for_role("province")
    assert "model-1" in agents and "model-3" in agents
    assert "model-4" not in agents and "model-6" not in agents


def test_router_county_agents():
    """县域执行端 → model-1, model-3, model-2"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    role = router.identify_role("本县哪些乡镇等级稳定性较弱？")
    assert role == "county"
    agents = router.get_agents_for_role("county")
    assert "model-1" in agents and "model-2" in agents and "model-3" in agents


def test_router_farmer_agents():
    """农户种植端 → model-4, model-5, model-6（xlsx 农户端）"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    role = router.identify_role("我的田酸化了，我要施加多少碱性调理剂？")
    assert role == "farmer"
    agents = router.get_agents_for_role("farmer")
    assert "model-4" in agents and "model-5" in agents and "model-6" in agents


def test_router_unknown_role_fallback_farmer():
    """未知角色回退 farmer"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    agents = router.get_agents_for_role("unknown_role")
    assert "model-4" in agents and "model-5" in agents and "model-6" in agents


def test_router_xlsx_three_ends_coverage():
    """xlsx 三端角色关键词覆盖：province/county/farmer 各至少一个关键词命中"""
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    assert router.identify_role("全省耕地酸化程度") == "province"
    assert router.identify_role("本县乡镇片区任务") == "county"
    assert router.identify_role("我的田这块地施多少") == "farmer"
```

更新 `if __name__ == "__main__":` 块追加这些用例调用。

- [ ] **Step 2: 运行测试**

Run: `python -m pytest tests/test_agent_classic_qa.py -v -k "router"`
Expected: 全部 PASS。若 `test_router_farmer_agents` 中 `identify_role` 未识别"我的田"为 farmer，检查 `ROLE_KEYWORDS["farmer"]` 是否含"我的田"（当前已含），无需改代码。

- [ ] **Step 3: 确认 router.py 无需修改**

若 Step 2 全部 PASS，则 `router.py` 不修改。若 FAIL，修正 `framework/agents/router.py` 的 `ROLE_KEYWORDS` 或 `ROLE_AGENTS` 使映射与 xlsx 三端一致，再运行测试至 PASS。

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_classic_qa.py
git commit -m "test(sync-models): 固化 RoleRouter 三角色路由与 xlsx 三端一致性验证"
```

---

## Task 10: 创建 spec 一致性测试

**对应 tasks.md：** 5.1

**Files:**
- 测试: `tests/test_model_specs_sync.py`（新建）

**Interfaces:**
- Consumes: Task 1/2/3 校对后的 delta spec 文件
- Produces: 断言 delta spec 含 6 模型输入输出关键词、model 6 名称已回退、role-based-routing TYPE 描述与 D5 一致

- [ ] **Step 1: 写 spec 一致性测试**

创建 `tests/test_model_specs_sync.py`：

```python
"""测试 delta spec 与 xlsx 总览表的一致性（D1/D2/D3）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROFESSIONAL_SPEC = "openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md"
ROUTING_SPEC = "openspec/changes/sync-model-specs-from-overview/specs/role-based-routing/spec.md"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_six_models_present():
    s = _read(PROFESSIONAL_SPEC)
    for name in [
        "StabilityRiskAgent", "PotentialAssessmentAgent", "ProblemIdentificationAgent",
        "AcidificationRemediationAgent", "OrganicMatterAgent", "FertilityMLAgent",
    ]:
        assert name in s, f"delta spec 缺少智能体: {name}"


def test_model1_io_keywords():
    s = _read(PROFESSIONAL_SPEC)
    # 模型1 输入关键词
    assert "11 个评价指标及权重" in s
    assert "灌溉能力" in s and "排水能力" in s and "地形部位" in s
    # 模型1 输出关键词
    assert "等级边界安全度" in s
    assert "退化空间集聚风险" in s
    assert "持续低质风险" in s


def test_model4_io_and_standards():
    s = _read(PROFESSIONAL_SPEC)
    # 模型4 输入
    assert "交换性铝离子" in s
    assert "木本泥炭施用量" in s or "碱性调理剂施用量" in s
    # 模型4 引用标准
    assert "GB/T 42817-2023" in s
    assert "NY/T 443-2019" in s


def test_model5_io_keywords():
    s = _read(PROFESSIONAL_SPEC)
    assert "目标土壤有机质" in s
    assert "秸秆施用量" in s or "有机肥施用量" in s


def test_model6_name_rollback_d1():
    """D1: model 6 名称回退为"耕地综合地力改良提升模型"，旧名不出现"""
    s = _read(PROFESSIONAL_SPEC)
    assert "耕地综合地力改良提升模型" in s
    assert "耕地肥力机器学习预测模型" not in s


def test_model6_internal_implementation_note():
    """model 6 标注内部使用 ML 预测"""
    s = _read(PROFESSIONAL_SPEC)
    assert "ExtraTreesRegressor" in s or "ML 预测" in s or "model_6_execution" in s


def test_model6_xlsx_blank_note():
    """model 6 标注 xlsx 未填写，保留现有实现"""
    s = _read(PROFESSIONAL_SPEC)
    assert "xlsx 未填写" in s or "保留现有实现" in s


def test_scenarios_count_refined_d3():
    """D3: 提炼版 scenario 约 30 个（每模型 4-7 个）"""
    s = _read(PROFESSIONAL_SPEC)
    scenario_count = s.count("#### Scenario:")
    assert 20 <= scenario_count <= 40, f"scenario 数量 {scenario_count} 不在提炼版预期范围 20-40"


def test_three_role_scenarios_covered():
    """3 角色经典问题在 scenario 中有体现"""
    s = _read(PROFESSIONAL_SPEC)
    # 县域端
    assert "县域" in s or "本县" in s or "县" in s
    # 农户端
    assert "农户" in s or "我的" in s


def test_routing_type_descriptions_align_d5():
    """D5: role-based-routing TYPE 描述对齐"""
    s = _read(ROUTING_SPEC)
    assert "TYPE_1（等级稳定性/退化风险）" in s
    assert "TYPE_2（酸化程度/调理剂/改良方案）" in s
    assert "TYPE_3（潜力/障碍因素/主要问题）" in s
    assert "TYPE_4（有机质/有机肥/肥力/有机碳）" in s


def test_routing_type_to_model_mapping():
    s = _read(ROUTING_SPEC)
    assert "StabilityRiskAgent (model-1)" in s
    assert "AcidificationRemediationAgent (model-4)" in s
    assert "FertilityMLAgent (model-6)" in s
    assert "OrganicMatterAgent (model-5)" in s


def test_routing_keyword_priority_scenario():
    """关键词优先于向量匹配 scenario 存在"""
    s = _read(ROUTING_SPEC)
    assert "关键词优先于向量匹配" in s


if __name__ == "__main__":
    test_six_models_present()
    test_model1_io_keywords()
    test_model4_io_and_standards()
    test_model5_io_keywords()
    test_model6_name_rollback_d1()
    test_model6_internal_implementation_note()
    test_model6_xlsx_blank_note()
    test_scenarios_count_refined_d3()
    test_three_role_scenarios_covered()
    test_routing_type_descriptions_align_d5()
    test_routing_type_to_model_mapping()
    test_routing_keyword_priority_scenario()
    print("\nspec 一致性测试通过！")
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python -m pytest tests/test_model_specs_sync.py -v`
Expected: 全部 PASS。若有 FAIL，回到 Task 1/2/3 补全对应 spec 内容后重跑。

- [ ] **Step 3: Commit**

```bash
git add tests/test_model_specs_sync.py
git commit -m "test(sync-models): 新增 delta spec 与 xlsx 一致性测试(D1/D2/D3)"
```

---

## Task 11: 完善关键词路由测试全量覆盖

**对应 tasks.md：** 5.2

**Files:**
- 测试: `tests/test_question_type_keywords.py`（已在 Task 4/5 创建，本任务补全 xlsx 全部经典问题路由用例并确认覆盖）

**Interfaces:**
- Consumes: Task 4/5 的关键词实现
- Produces: xlsx 3 角色×各模型经典问题全部经 `identify_question_type` 路由断言

**说明：** Task 4/5 已覆盖大部分经典问题。本任务补全剩余边界用例（如 model-6 SOC/Dose 单独问题、model-2 目标 pH 内部计算不入路由），并运行全文件确认。

- [ ] **Step 1: 补全边界用例**

在 `tests/test_question_type_keywords.py` 的 `if __name__` 块之前追加：

```python
def test_type4_soc_query():
    """model-6 SOC 查询 → TYPE_4"""
    qt, _ = _identify("我的田土壤有机碳含量大概多少？")
    assert qt == 4


def test_type4_dose_query():
    """model-6 Dose 查询 → TYPE_4"""
    qt, _ = _identify("我这块地大概需要施多少有机肥？")
    assert qt == 4


def test_type4_straw_query():
    """秸秆还田 → TYPE_4"""
    qt, _ = _identify("秸秆还田每亩施用量多少？")
    assert qt == 4


def test_type2_farmer_severity():
    """农户酸化严重 → TYPE_2"""
    qt, _ = _identify("我的这块田酸化严重吗？")
    assert qt == 2


def test_unrelated_question_returns_zero():
    """无关问题 relevance 低 → TYPE_0"""
    qt, _ = _identify("今天天气怎么样？")
    assert qt == 0


def test_all_xlsx_classic_questions_routed():
    """xlsx 全部经典问题均能路由到非 0 类型（覆盖性断言）"""
    cases = [
        ("查询区域内耕地质量等级整体稳定吗？", 1),
        ("查询区域内哪些高等级耕地存在退化风险？", 1),
        ("本县哪些乡镇或地块等级稳定性较弱，需要现场复核？", 1),
        ("我的这块田质量等级稳不稳？", 1),
        ("查询区域内哪些对象需要纳入重点关注清单？", 1),
        ("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", 3),
        ("我们县划定的优先改良片区具体在哪几个村？每块潜力多大？", 3),
        ("我这块地到底有啥毛病？", 3),
        ("全省耕地质量存在哪些问题？", 3),
        ("县/乡镇里的耕地在哪些方面有问题", 3),
        ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 2),
        ("我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？", 2),
        ("查询区域内不同土地利用类型的酸化程度", 2),
        ("我的这块田酸化严重吗？", 2),
        ("全省耕地土壤有机质含量如何，空间分布情况？", 4),
        ("为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？", 4),
        ("本县耕地土壤有机质平均含量是多少？", 4),
        ("耕地有机质含量低的原因是什么？", 4),
        ("我的田肥力怎么样？", 4),
        ("我的田土壤有机碳含量大概多少？", 4),
        ("我这块地大概需要施多少有机肥？", 4),
    ]
    for q, expected in cases:
        qt, _ = _identify(q)
        assert qt == expected, f"问题「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
```

更新 `if __name__ == "__main__":` 块追加这些用例调用。

- [ ] **Step 2: 运行全文件测试**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 PASS（含 `test_all_xlsx_classic_questions_routed` 的 21 条经典问题）

- [ ] **Step 3: Commit**

```bash
git add tests/test_question_type_keywords.py
git commit -m "test(sync-models): 补全 xlsx 全部经典问题路由覆盖用例(D5)"
```

---

## Task 12: 完善 agent 经典 Q&A 测试全量覆盖

**对应 tasks.md：** 5.3

**Files:**
- 测试: `tests/test_agent_classic_qa.py`（已在 Task 6/7/8/9 创建，本任务补全 6 agent×3 角色矩阵并运行全文件）

**Interfaces:**
- Consumes: Task 6/7/8 的 agent 回复模板
- Produces: 6 个 agent 对 xlsx 3 角色经典问题返回 `simulated is True` 且 answer 非空

- [ ] **Step 1: 补全矩阵汇总用例**

在 `tests/test_agent_classic_qa.py` 的 `if __name__` 块之前追加汇总用例：

```python
def test_all_six_agents_simulated_flag():
    """6 个 agent 对代表性经典问题均返回 simulated=True 且 answer 非空"""
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

    cases = [
        (StabilityRiskAgent(), "查询区域内耕地质量等级整体稳定吗？"),
        (PotentialAssessmentAgent(), "辖区耕地质量提升的总体潜力有多大？"),
        (ProblemIdentificationAgent(), "全省耕地质量存在哪些问题？"),
        (AcidificationRemediationAgent(), "查询区域内农用地土壤酸化程度如何？"),
        (OrganicMatterAgent(), "全省耕地土壤有机质含量如何？"),
    ]
    for agent, q in cases:
        out = agent.answer_question(q, {})
        assert out.get("simulated") is True, f"{agent.name} 未标记 simulated"
        assert out.get("answer"), f"{agent.name} answer 为空"


def test_fertility_ml_simulated_with_mock(monkeypatch):
    """model-6 需 mock model_6_execution 后验证 simulated"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5, "soc_confidence": 0.91,
            "dose_prediction": 150.0, "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [], "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        })
    out = FertilityMLAgent().answer_question("我的田肥力怎么样？", {"data": {"pH": 6.5}})
    assert out.get("simulated") is True
    assert out.get("answer")
```

更新 `if __name__ == "__main__":` 块追加这些用例调用。

- [ ] **Step 2: 运行全文件测试**

Run: `python -m pytest tests/test_agent_classic_qa.py -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_classic_qa.py
git commit -m "test(sync-models): 补全 6 agent 经典 Q&A 矩阵汇总测试(D4)"
```

---

## Task 13: 全量回归测试

**对应 tasks.md：** 5.4

**Files:**
- 测试: 全部 `tests/*.py`

**Interfaces:**
- Consumes: Task 4-12 全部改动
- Produces: 全量测试通过，不破坏现有功能

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS，无 FAIL/ERROR。

- [ ] **Step 2: 若有失败，定位并修复**

逐个分析失败用例：
- 若为 `test_agent_specialized.py` 旧用例因新分支顺序变化而失败，调整旧用例的问题文本或断言以适配新模板（优先改测试问题文本使其明确命中预期分支，不放宽断言）。
- 若为 `test_fertility_ml_prediction.py` 失败，确认 `_format_both` 改动未破坏 evidence 结构（evidence 应仍含 4 个 metric）。
- 若为 `test_multi_agent.py` / `test_agent_manager.py` 失败，确认 `nodes.py` 关键词改动未影响 `AgentManager.process` 路径。

修复后重跑 `python -m pytest tests/ -v` 直至全绿。

- [ ] **Step 3: 确认 model_6_execution 未被修改**

Run: `git diff --stat 251ac1cefb1a2e49f8766565c51f1ce5e5713f7b -- framework/domain/other_models/model_6.py`
Expected: 无输出（文件未改）。若有改动，回滚该文件：`git checkout -- framework/domain/other_models/model_6.py`

- [ ] **Step 4: Commit（若有测试修复）**

```bash
git add tests/
git commit -m "test(sync-models): 修复全量回归测试适配新关键词与回复模板"
```

若 Step 1 一次通过无需修复，则跳过 commit。

---

## Task 14: 集成验证

**对应 tasks.md：** 6.1 / 6.2 / 6.3 / 6.4

**Files:**
- 验证: delta spec、`FertilityMLAgent`、6 agent、关键词路由

**Interfaces:**
- Consumes: Task 1-13 全部产物
- Produces: 集成验证脚本断言 4 项集成点

- [ ] **Step 1: 验证 model 6 spec 名称已回退（6.1）**

Run: `python -c "s=open('openspec/changes/sync-model-specs-from-overview/specs/professional-model-agents/spec.md',encoding='utf-8').read(); assert '耕地综合地力改良提升模型' in s and '耕地肥力机器学习预测模型' not in s; print('6.1 OK')"`
Expected: 输出 `6.1 OK`

- [ ] **Step 2: 验证 FertilityMLAgent ML 预测功能正常（6.2）**

Run: `python -m pytest tests/test_fertility_ml_prediction.py tests/test_agent_specialized.py -v -k "fertility or ml"`
Expected: 全部 PASS（SOC/Dose 预测、fallback、rejected 路径均正常）

- [ ] **Step 3: 验证 6 agent answer_question 返回对齐 xlsx 回复（6.3）**

Run: `python -m pytest tests/test_agent_classic_qa.py -v`
Expected: 全部 PASS（6 agent × 经典问题均返回对齐回复）

- [ ] **Step 4: 验证关键词覆盖 xlsx 经典问题（6.4）**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 PASS（含 `test_all_xlsx_classic_questions_routed` 21 条经典问题）

- [ ] **Step 5: 集成验证脚本汇总**

Run:
```
python -c "import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_model_specs_sync.py','tests/test_question_type_keywords.py','tests/test_agent_classic_qa.py','-q']); sys.exit(r.returncode)"
```
Expected: 全部 PASS，输出含 `passed` 且无 `failed`。

- [ ] **Step 6: 确认变更范围符合非目标约束**

Run:
```
git diff --stat 251ac1cefb1a2e49f8766565c51f1ce5e5713f7b
```
Expected: 改动文件仅限：
- `openspec/changes/sync-model-specs-from-overview/specs/**/*.md`
- `framework/agents/nodes.py`
- `framework/agents/specialized/*.py`
- `framework/agents/router.py`（可选，预期不改）
- `tests/test_*.py`
- `docs/superpowers/plans/2026-07-24-sync-model-specs-from-overview.md`

不应出现 `framework/domain/other_models/model_6.py`、`framework/api/**`、数据库导入脚本等改动。

- [ ] **Step 7: Commit 验证记录**

```bash
git add docs/superpowers/plans/2026-07-24-sync-model-specs-from-overview.md
git commit -m "chore(sync-models): 集成验证通过 - 6.1/6.2/6.3/6.4 全部确认"
```

---

## Self-Review 自检

**1. Spec 覆盖：**
- D1 model 6 名称回退 → Task 2 Step 3-4 + Task 10 `test_model6_name_rollback_d1` ✓
- D2 输入输出写入 spec → Task 1/2 校对 + Task 10 `test_model1_io_keywords`/`test_model4_io_and_standards`/`test_model5_io_keywords` ✓
- D3 提炼版 scenario → Task 1/2 校对 + Task 10 `test_scenarios_count_refined_d3` ✓
- D4 agent 最小化改动 → Task 6/7/8 仅改 `answer_question` + Task 14 Step 6 范围检查 ✓
- D5 关键词更新 → Task 4/5 + Task 11 + Task 10 `test_routing_type_descriptions_align_d5` ✓
- tasks.md 6.1-6.4 → Task 14 ✓
- tasks.md 5.1-5.4 → Task 10/11/12/13 ✓
- tasks.md 4.1-4.3 → Task 9 ✓
- tasks.md 3.1-3.6 → Task 6/7/8 ✓
- tasks.md 2.1-2.5 → Task 4/5/11 ✓
- tasks.md 1.1-1.7 → Task 1/2/3 ✓

**2. 占位符扫描：** 所有 step 含可执行命令或具体代码，无 TBD/TODO。spec 校对任务（Task 1/2/3）因 delta spec 已存在，步骤为"校对确认 + 验证脚本断言 + 缺失则补全"，附具体断言命令。

**3. 类型一致性：**
- `identify_question_type` / `_identify_question_type_keyword` 返回 `tuple[int, float]`，测试用 `qt, _ = ...` ✓
- `answer_question(question: str, context: Dict) -> Dict` 签名全部保持 ✓
- 关键词常量名 `QUESTION_TYPE_1~4_KEYWORDS`、`RELEVANCE_KEYWORDS`、`REFERENCE_QUESTIONS`、`QUESTION_TYPE_TO_MODEL_ID` 与 nodes.py 现有定义一致 ✓
- `RoleRouter.identify_role` / `get_agents_for_role` 签名不变 ✓
- `FertilityMLAgent._format_both` evidence 4 个 metric 保持不变，仅改 answer 文案 ✓

**4. 潜在风险已处理：**
- RELEVANCE_KEYWORDS 扩展（Task 4 Step 3）解决 xlsx 经典问题 relevance<0.3 问题 ✓
- TYPE_2 移除"施加""用量"通用词（Task 4 + Task 5 `test_type_order_no_cross_collision`）✓
- 关键词跨类型重叠检查（Task 5 `test_type_order_no_cross_collision`）✓
- model_6_execution 未改（Task 13 Step 3 + Task 14 Step 6）✓
