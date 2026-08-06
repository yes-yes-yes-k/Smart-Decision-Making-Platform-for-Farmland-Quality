---
change: add-routing-exclusive-rules
design-doc: docs/superpowers/specs/2026-08-06-five-dim-routing-exclusive-rules-design.md
base-ref: 574b1a8a86fba188e6c875072a75fa4130a1ad82
---

# 五维路由升级与排他规则建立 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `framework/agents/nodes.py` 中耦合的 question_type 路由升级为五维路由（业务任务/分析尺度/数据类型/预期输出/模型依赖），引入数据驱动的排他规则配置以消除 model-3/7、model-2/7、model-4/6 三组易混淆对的误选，并对无法消解的重叠返回 `routing_status="boundary_pending"` 显式降级；同时将路由判定逻辑抽离为独立模块 `routing.py`。

**Architecture:** 保持 `question_type`→Agent 的既有 1:1 映射不变，在其之上叠加五维特征与排他规则。新建 `framework/agents/routing.py` 承载判定逻辑（迁移 `identify_question_type` 等函数，签名向后兼容），新建 `framework/agents/exclusive_rules.py` 声明数据驱动的排他规则列表。`nodes.py` 保留图节点状态组装与分支调度，从 `routing.py` 导入路由函数；新增 `boundary_pending` 图节点与分支，`aggregate_results` 透传 `routing_status` 与降级提示到 API 响应。

**Tech Stack:** Python 3（`dataclasses`、`typing`）、`langgraph`（StateGraph）、Flask（API）。

## Global Constraints

- 语言：所有代码注释、日志、测试断言消息、API 提示文案使用中文。
- 向后兼容（决策 A）：`identify_question_type(question)` 扩展为 `identify_question_type(question, context=None)`；`context` 为 `None` 时行为与现状完全一致，现有约 470 个测试不得破坏。
- 不改变 `question_type`→Agent 的 1:1 映射数据结构（决策/Non-Goals），仅叠加五维特征与排他规则。
- 排他规则无法消解重叠时返回 `routing_status="boundary_pending"` + 「模型边界待确认」提示，不自行调用任一易混淆专业 Agent（决策 D）。
- 路由判定逻辑必须从 `nodes.py` 抽离到独立模块（决策 E），`nodes.py` 仅保留图节点状态组装与分支调度。
- 易混淆对测试：model-3/7、model-2/7、model-4/6 各 ≥20 条正例 + 反例。
- 测试文件位于 `tests/`，运行方式：`python -m pytest tests/ -v`（或逐文件 `python tests/test_xxx.py`）。

---

## 文件结构与职责

| 文件 | 职责 | 操作 |
|------|------|------|
| `framework/agents/capabilities.py` | `ProfessionalCapability` 增加 `analysis_scale`/`data_type` 字段并填充 7 个能力默认值 | 修改 |
| `framework/agents/routing.py` | 独立路由模块：迁移 `identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance` 及全部路由常量 | 新建 |
| `framework/agents/exclusive_rules.py` | 数据驱动排他规则配置 + 判定逻辑 + `boundary_pending` 降级 | 新建 |
| `framework/agents/nodes.py` | 图节点状态组装与分支调度；从 `routing.py` 导入路由函数并保留向后兼容再导出；新增 `boundary_pending_node`、`_extract_five_dim_context` | 修改 |
| `framework/agents/state.py` | `MultiAgentState` 增加 `routing_status` 字段 | 修改 |
| `framework/agents/orchestrator.py` | 注册 `boundary_pending` 节点与条件分支边 | 修改 |
| `framework/api/routes/chat.py` | 透传 `routing_status` 与降级提示到 API 响应 | 修改 |
| `tests/test_question_type_keywords.py` | 扩充三组易混淆对正/反例测试 | 修改 |
| `tests/test_exclusive_rules.py` | 排他规则与「模型边界待确认」降级测试 | 新建 |

### 关键接口约定（跨任务一致）

- `identify_question_type(question: str, context: Optional[dict] = None) -> tuple[int, float]`（`routing.py`）
- `check_relevance(question: str) -> float`（`routing.py`）
- `_identify_question_type_keyword(question: str) -> tuple[int, float]`、`_identify_question_type_vector(question: str) -> tuple[int, float]`（`routing.py`）
- `apply_exclusive_rules(question: str, question_type: int, context: Optional[dict] = None) -> tuple[int, str]`，返回值 `(question_type, routing_status)`，其中 `routing_status ∈ {"normal","boundary_pending"}`（`exclusive_rules.py`）
- 常量：`ROUTING_STATUS_NORMAL = "normal"`、`ROUTING_STATUS_BOUNDARY_PENDING = "boundary_pending"`、`BOUNDARY_PENDING_MESSAGE`（`exclusive_rules.py`）
- 模型→question_type 映射：`model_id_to_question_type(model_id: str) -> Optional[int]`（`exclusive_rules.py`）
- 图节点：`boundary_pending_node(state) -> MultiAgentState`（`nodes.py`）
- `route_models(state) -> str` 返回值新增分支 `"boundary_pending"`（`nodes.py`）

---

### Task 1: 五维路由特征扩展（capabilities 字段 + routing.py 模块化 + nodes.py 再导出）

**Files:**
- Modify: `framework/agents/capabilities.py`
- Create: `framework/agents/routing.py`
- Modify: `framework/agents/nodes.py`
- Test: `tests/test_question_type_keywords.py`（新增少量迁移/字段断言）

**Interfaces:**
- Consumes: 现有 `nodes.py` 中已实现的常量与函数（`QUESTION_TYPE_1..7_KEYWORDS`、`RELEVANCE_KEYWORDS`、`REFERENCE_QUESTIONS`、`identify_question_type`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`check_relevance`、`_is_knowledge_question`、`_cosine_similarity`、`_precompute_reference_vectors`、`EMBEDDING_AVAILABLE`）。
- Produces: `routing.py` 中同名可调用的路由函数与常量；`capabilities.ProfessionalCapability` 新增 `analysis_scale`、`data_type` 字段；`nodes.py` 对以上名称的向后兼容再导出。

- [x] **Step 1: 写失败测试 —— capabilities 字段与 routing 模块迁移**

在 `tests/test_question_type_keywords.py` 顶部追加以下测试函数：

```python
def test_capability_has_five_dim_fields():
    """ProfessionalCapability 应含 analysis_scale/data_type 字段且 7 个能力均已填充"""
    from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES
    for cap in PROFESSIONAL_CAPABILITIES:
        assert hasattr(cap, "analysis_scale"), f"{cap.agent_id} 缺少 analysis_scale"
        assert hasattr(cap, "data_type"), f"{cap.agent_id} 缺少 data_type"
        assert cap.analysis_scale, f"{cap.agent_id} 的 analysis_scale 为空"
        assert cap.data_type, f"{cap.agent_id} 的 data_type 为空"
    assert len(PROFESSIONAL_CAPABILITIES) == 7


def test_routing_module_migrated():
    """路由判定函数应从 routing 模块导出且签名向后兼容"""
    from framework.agents import routing
    for name in ("identify_question_type", "_identify_question_type_keyword",
                 "_identify_question_type_vector", "check_relevance"):
        assert hasattr(routing, name), f"routing 缺少 {name}"
    # identify_question_type 支持可选 context 参数
    qt, rel = routing.identify_question_type("我的这块田质量等级稳不稳")
    assert qt == 1
    qt2, rel2 = routing.identify_question_type("我的这块田质量等级稳不稳", {"scale": "地块"})
    assert qt2 == qt  # context 追加不改变无规则命中的既有行为
```

在 `tests/test_question_type_keywords.py` 的 `if __name__ == "__main__":` 块末尾追加：

```python
    test_capability_has_five_dim_fields()
    test_routing_module_migrated()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: FAIL —— `test_capability_has_five_dim_fields` 报 `AttributeError: 'ProfessionalCapability' object has no attribute 'analysis_scale'`；`test_routing_module_migrated` 报 `ModuleNotFoundError: No module named 'framework.agents.routing'`。

- [x] **Step 3: capabilities.py 增加五维字段并填充默认值**

在 `framework/agents/capabilities.py` 中，`ProfessionalCapability` 末尾（`runtime_requirement` 之后）追加两个带默认值的字段：

```python
    runtime_requirement: str = "无需额外运行时前置条件"
    analysis_scale: str = "地块"        # 分析尺度：省/县/片区/地块
    data_type: str = "指标数据"          # 数据类型：指标数据/评价结果/处方用量
```

为 7 个 capability 的构造调用追加关键字实参（保持位置参数顺序不变）：

```python
        "需完成稳定性离线预计算并提供 parcel_id。",
        "地块", "评价结果",   # model-1 稳定性风险：地块级评价结果
    ),
    ...
        "可使用结构化土壤指标；缺失字段将按 Agent 既有规则处理。",
        "县", "指标数据",     # model-2 提升潜力：县级指标数据
    ),
    ...
        "需完成障碍诊断批量计算并提供 parcel_id。",
        "地块", "指标数据",   # model-3 障碍诊断：地块级指标数据
    ),
    ...
        "需完成酸化评估并提供 parcel_id；结构化指标可用于规则降级。",
        "地块", "处方用量",   # model-4 酸化改良：地块级处方用量
    ),
    ...
        "可使用结构化土壤指标；当前规则结果会明确模拟状态。",
        "县", "处方用量",     # model-5 有机质培肥：县级处方用量
    ),
    ...
        "需提供模型特征；模型文件不可用时返回训练集均值降级结果。",
        "地块", "处方用量",   # model-6 肥力 SOC/Dose 预测：地块级处方用量
    ),
    ...
        "真实评价需部署 exe/dat 文件并提供 parcel_code。",
        "地块", "评价结果",   # model-7 质量等级评价：地块级评价结果
    ),
```

- [x] **Step 4: 新建 routing.py 并迁移全部判定逻辑**

创建 `framework/agents/routing.py`，内容为对 `nodes.py` 中以下定义的完整迁移（`question_type` 常量、知识性问题模式、相关性关键词、参考问题、参考向量、判定函数），并新增 `context` 可选参数与排他规则挂接：

```python
"""独立路由模块：五维路由判定逻辑。

从 nodes.py 迁移而来，保持对外函数签名向后兼容。
context 为 None 时行为与旧版 nodes.py 完全一致。
"""
from __future__ import annotations
import numpy as np
from typing import Any, List, Dict, Optional

try:
    from framework.embedding.service import embedding_service
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False

from .exclusive_rules import apply_exclusive_rules

QUESTION_TYPE_1_KEYWORDS = [
    "等级稳定", "稳定性", "稳不稳", "稳定吗", "稳定性较弱", "退化风险",
    "关注清单", "重点关注", "临界状态", "风险类型", "等级整体", "掉级",
    "稳定性评价", "等级边界安全度", "指标支撑均衡度", "关键指标临界度",
    "空间邻域一致性", "历史变化趋势", "掉级风险", "关键因子退化",
    "退化空间集聚", "持续低质风险",
]
QUESTION_TYPE_2_KEYWORDS = [
    "酸化程度", "酸化等级", "酸化现状", "酸化严重", "酸化了", "酸化治理",
    "调理剂", "碱性材料", "碱性调理剂", "木本泥炭", "石灰", "pH提升",
    "土地利用类型", "酸化",
    "酸化改良", "酸化分区", "改良方案", "土壤酸化", "酸性改良",
]
QUESTION_TYPE_3_KEYWORDS = [
    "障碍因素", "主要问题", "障碍诊断", "障碍组合", "地块诊断", "毛病",
    "障碍等级", "哪些问题", "有问题",
    "障碍识别", "障碍程度", "障碍因子", "精准识别", "单一障碍", "多障碍",
]
QUESTION_TYPE_4_KEYWORDS = [
    "肥力预测", "SOC预测", "有机碳预测", "有机碳", "SOC", "soc",
    "Dose", "dose", "施肥量预测", "预测施肥量", "预测置信度", "综合肥力",
    "肥力", "施多少肥", "氮肥",
]
QUESTION_TYPE_5_KEYWORDS = [
    "质量等级", "等级评价", "综合指数", "指标隶属度", "障碍度排序",
    "耕地质量等级", "质量评价", "等级评定", "指标权重",
]
QUESTION_TYPE_6_KEYWORDS = [
    "提升潜力", "潜力评估", "增产潜力", "潜力分布", "改良片区", "潜力多大", "潜力",
    "提升空间", "目标等级",
]
QUESTION_TYPE_7_KEYWORDS = [
    "有机质", "有机肥", "秸秆", "秸秆还田", "培肥", "培肥方案",
    "有机肥施用", "有机肥每亩", "提升有机质", "有机质含量",
]

KNOWLEDGE_QUESTION_PATTERNS_START = ["什么是", "何为", "解释"]
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = ["是什么意思", "什么意思", "定义", "概念", "含义"]

RELEVANCE_KEYWORDS = [
    "酸化", "pH", "土壤", "耕地", "治理", "改良", "氮肥", "施肥",
    "调理剂", "石灰", "碱性", "酸性", "交换性酸", "CEC", "阳离子交换量",
    "土壤质量", "农业", "农田", "养分", "种植", "作物", "水稻", "小麦",
    "玉米", "肥料", "有机质", "酸碱度", "酸性土", "碱性土", "改良剂",
    "田", "地", "质量", "等级", "稳定", "潜力", "障碍", "问题",
    "乡镇", "县", "片区", "地块", "农户", "风险", "关注", "清单",
    "诊断", "毛病", "增产", "粮食", "碳氮比", "全氮", "容重",
    "有机肥", "施用量", "秸秆", "培肥", "SOC", "Dose",
]

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
        "我这块地到底有啥毛病",
        "全省耕地质量存在哪些问题",
        "县乡镇里的耕地在哪些方面有问题",
    ],
    4: [
        "我的田肥力怎么样",
        "我的田土壤有机碳含量大概多少",
        "预测这块地需要多少施肥量",
    ],
    5: [
        "我的田耕地质量等级是多少",
        "查询地块的综合指数和障碍度排序",
        "这块地的耕地质量等级评价结果",
    ],
    6: [
        "辖区耕地质量提升的总体潜力有多大可增产多少粮食",
        "我们县划定的优先改良片区具体在哪几个村每块潜力多大",
    ],
    7: [
        "全省耕地土壤有机质含量如何空间分布情况",
        "为了提升耕地土壤有机质有机肥或者秸秆每亩施用量多少",
        "本县耕地土壤有机质平均含量是多少",
    ],
}

REFERENCE_VECTORS: Dict[int, List[List[float]]] = {}

def _precompute_reference_vectors() -> None:
    if not EMBEDDING_AVAILABLE or not embedding_service.is_available():
        return
    global REFERENCE_VECTORS
    for q_type, questions in REFERENCE_QUESTIONS.items():
        vectors = embedding_service.embed_documents(questions)
        REFERENCE_VECTORS[q_type] = vectors

def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(dot_product / (norm1 * norm2))

_precompute_reference_vectors()

def check_relevance(question: str) -> float:
    if not question:
        return 0.0
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _check_relevance_vector(question)
    else:
        return _check_relevance_keyword(question)

def _check_relevance_vector(question: str) -> float:
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _check_relevance_keyword(question)
    max_similarity = 0.0
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
    return max_similarity

def _check_relevance_keyword(question: str) -> float:
    if not question:
        return 0.0
    match_count = sum(1 for keyword in RELEVANCE_KEYWORDS if keyword in question)
    return min(match_count / 3, 1.0)

def _is_knowledge_question(question: str) -> bool:
    if not question:
        return False
    if question.startswith(("什么是", "何为", "解释")):
        return True
    contains_patterns = ["是什么意思", "什么意思", "定义", "概念", "含义"]
    if any(p in question for p in contains_patterns):
        return True
    return False

def identify_question_type(question: str, context: Optional[dict] = None) -> tuple[int, float]:
    """识别问题类型（向后兼容：context 为 None 时与旧版完全一致）。

    返回 (question_type, relevance)。question_type ∈ 1..7 与 0=RAG。
    context 提供时，在既有判定之上叠加五维排他规则精化。
    """
    if _is_knowledge_question(question):
        return 0, 1.0
    base_type, base_rel = _identify_question_type_keyword(question)
    if base_type == 0:
        if EMBEDDING_AVAILABLE and embedding_service.is_available():
            base_type, base_rel = _identify_question_type_vector(question)
        # 关键词与向量均未命中时 base_type 保持 0
    if context is not None:
        refined_type, _status = apply_exclusive_rules(question, base_type, context)
        return refined_type, base_rel
    return base_type, base_rel

def _identify_question_type_vector(question: str) -> tuple[int, float]:
    keyword_relevance = _check_relevance_keyword(question)
    query_vector = embedding_service.embed_query(question)
    if not query_vector:
        return _identify_question_type_keyword(question)
    max_similarity = 0.0
    best_type = 1
    for q_type, vectors in REFERENCE_VECTORS.items():
        for ref_vector in vectors:
            similarity = _cosine_similarity(query_vector, ref_vector)
            if similarity > max_similarity:
                max_similarity = similarity
                best_type = q_type
    if max_similarity < 0.75:
        return 0, max_similarity
    if max_similarity < 0.55:
        if keyword_relevance >= 0.3:
            return 2, keyword_relevance
        return 0, max_similarity
    return best_type, max_similarity

def _identify_question_type_keyword(question: str) -> tuple[int, float]:
    relevance = _check_relevance_keyword(question)
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
    elif any(keyword in question for keyword in QUESTION_TYPE_6_KEYWORDS):
        return 6, relevance
    elif any(keyword in question for keyword in QUESTION_TYPE_7_KEYWORDS):
        return 7, relevance
    else:
        return 0, relevance
```

> 注：`routing.py` 顶部 `from .exclusive_rules import apply_exclusive_rules` 依赖 Task 2 创建该模块。为保证 Task 1 可独立跑通，请先创建 `exclusive_rules.py`（Task 2 Step 3 的完整内容）并保留其默认导出 `apply_exclusive_rules`。若希望 Task 1 先于 Task 2 完全独立，可将该 import 改为函数内延迟导入，但本计划按顺序执行，前者已足够。

- [x] **Step 5: nodes.py 改为从 routing.py 导入并保留向后兼容再导出**

`framework/agents/nodes.py` 中删除以下已迁移的定义（改为从 `routing.py` 再导入）：`QUESTION_TYPE_1_KEYWORDS`..`QUESTION_TYPE_7_KEYWORDS`、`KNOWLEDGE_QUESTION_PATTERNS_START`、`KNOWLEDGE_QUESTION_PATTERNS_CONTAIN`、`RELEVANCE_KEYWORDS`、`REFERENCE_QUESTIONS`、`REFERENCE_VECTORS`、`_precompute_reference_vectors`、`_cosine_similarity`、`_check_relevance_vector`、`_check_relevance_keyword`、`check_relevance`、`_is_knowledge_question`、`identify_question_type`、`_identify_question_type_vector`、`_identify_question_type_keyword`。

在 `nodes.py` 顶部（`from .state import MultiAgentState` 之后）追加再导出；并移除 `numpy` 与 `embedding_service` 的 import（不再直接使用，flag 改由 routing 提供）：

```python
from .state import MultiAgentState
from .routing import (
    identify_question_type,
    _identify_question_type_keyword,
    _identify_question_type_vector,
    check_relevance,
    EMBEDDING_AVAILABLE,
    QUESTION_TYPE_1_KEYWORDS,
    QUESTION_TYPE_2_KEYWORDS,
    QUESTION_TYPE_3_KEYWORDS,
    QUESTION_TYPE_4_KEYWORDS,
    QUESTION_TYPE_5_KEYWORDS,
    QUESTION_TYPE_6_KEYWORDS,
    QUESTION_TYPE_7_KEYWORDS,
    REFERENCE_QUESTIONS,
)
```

保留 `nodes.py` 中 `LLM_AVAILABLE`、`RAG_AVAILABLE`、`CORE_ENGINE_AVAILABLE` 的 try/except 定义（`rag_chat_node`/`llm_generate` 仍使用）。删除 `nodes.py` 里原有的 `embedding_service` try/except 与 `EMBEDDING_AVAILABLE` 定义（现由 `routing.py` 提供并再导出）。

> 注意：`nodes.EMBEDDING_AVAILABLE` 现在指向 `routing.py` 中的同名模块属性。旧测试 `test_unrelated_question_returns_zero` 通过 `nodes.EMBEDDING_AVAILABLE = False` 打补丁将不再影响 `routing.identify_question_type`，需在 Task 4 一并把该测试的补丁目标改为 `routing.EMBEDDING_AVAILABLE`（见 Task 4 Step 1）。

- [x] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: PASS —— 新增的 `test_capability_has_five_dim_fields`、`test_routing_module_migrated` 通过；既有问题类型关键词测试全部通过。若 `test_unrelated_question_returns_zero` 因补丁目标变更失败，属预期，Task 4 Step 1 修复。

- [x] **Step 7: Commit**

```bash
git add framework/agents/capabilities.py framework/agents/routing.py framework/agents/nodes.py tests/test_question_type_keywords.py
git commit -m "feat: 五维路由特征扩展并抽离独立路由模块 routing.py"
```

---

### Task 2: 排他规则配置（exclusive_rules.py）

**Files:**
- Create: `framework/agents/exclusive_rules.py`
- Create: `tests/test_exclusive_rules.py`
- Modify: `framework/agents/nodes.py`（Step 3 中 `identify_question_node` 挂接排他规则属 Task 3，此处不动）

**Interfaces:**
- Consumes: `framework/agents/capabilities.py` 的 `CAPABILITY_BY_QUESTION_TYPE`、`CAPABILITY_BY_MODEL_ID`。
- Produces: `EXCLUSIVE_RULES`、`EXCLUSIVE_CONDITION_KEYWORDS`、`ROUTING_STATUS_NORMAL`、`ROUTING_STATUS_BOUNDARY_PENDING`、`BOUNDARY_PENDING_MESSAGE`、`apply_exclusive_rules(question, question_type, context=None) -> tuple[int, str]`、`model_id_to_question_type(model_id) -> Optional[int]`。

- [x] **Step 1: 写失败测试 —— 排他规则与边界待确认**

创建 `tests/test_exclusive_rules.py`：

```python
"""排他规则与「模型边界待确认」降级测试。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _apply(q, base_type, ctx=None):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    return apply_exclusive_rules(q, base_type, ctx)


def test_rule_status_refers_to_model():
    """现状评价 → model-3：候选为 model-7 时修正到 model-3(5→3)"""
    final_type, status = _apply("耕地质量现状评价如何", 5, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 3, f"现状评价应路由到 model-3(type 3)，实际 type {final_type}"


def test_rule_potential_refers_to_model2():
    """潜力 → model-2：候选为 model-7 时修正到 model-2(5→6)"""
    final_type, status = _apply("耕地质量提升潜力多大", 5, {"scale": "县"})
    assert status == "normal"
    assert final_type == 6, f"潜力应路由到 model-2(type 6)，实际 type {final_type}"


def test_rule_organic_input_refers_to_model6():
    """有机质投入量 → model-6(4)"""
    final_type, status = _apply("有机肥每亩施用量多少", 7, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 4, f"有机质投入量应路由到 model-6(type 4)，实际 type {final_type}"


def test_rule_acidification_refers_to_model4():
    """酸化调理剂 → model-4(2)"""
    final_type, status = _apply("我要施加多少酸化调理剂", 4, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 2, f"酸化调理剂应路由到 model-4(type 2)，实际 type {final_type}"


def test_rule_stability_refers_to_model1():
    """稳定性风险 → model-1(1)"""
    final_type, status = _apply("这块地稳定性退化风险如何", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 1, f"稳定性风险应路由到 model-1(type 1)，实际 type {final_type}"


def test_rule_grade_refers_to_model7():
    """质量等级评价 → model-7(5)"""
    final_type, status = _apply("耕地质量等级评价结果", 3, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 5, f"质量等级评价应路由到 model-7(type 5)，实际 type {final_type}"


def test_conflicting_rules_return_boundary_pending():
    """同一易混淆对内两条规则同时命中 → 边界待确认"""
    final_type, status = _apply("酸化调理剂每亩施用量多少", 2, {"scale": "地块"})
    assert status == "boundary_pending", f"冲突应降级 boundary_pending，实际 {status}"


def test_type0_untouched():
    """TYPE_0(RAG) 不应用排他规则"""
    final_type, status = _apply("什么是土壤酸化", 0, {"scale": "地块"})
    assert (final_type, status) == (0, "normal")


def test_model_id_to_question_type_mapping():
    from framework.agents.exclusive_rules import model_id_to_question_type
    assert model_id_to_question_type("model-3") == 3
    assert model_id_to_question_type("model-7") == 5
    assert model_id_to_question_type("model-2") == 6
    assert model_id_to_question_type("model-6") == 4
    assert model_id_to_question_type("model-4") == 2
    assert model_id_to_question_type("model-1") == 1


if __name__ == "__main__":
    test_rule_status_refers_to_model()
    test_rule_potential_refers_to_model2()
    test_rule_organic_input_refers_to_model6()
    test_rule_acidification_refers_to_model4()
    test_rule_stability_refers_to_model1()
    test_rule_grade_refers_to_model7()
    test_conflicting_rules_return_boundary_pending()
    test_type0_untouched()
    test_model_id_to_question_type_mapping()
    print("\n全部排他规则测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_exclusive_rules.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'framework.agents.exclusive_rules'`。

- [x] **Step 3: 实现 exclusive_rules.py**

创建 `framework/agents/exclusive_rules.py`：

```python
"""数据驱动的排他规则配置与判定。

用于消除 model-3/7、model-2/7、model-4/6 三组易混淆对的误选。
排他规则无法消解重叠（优先级冲突）时返回「模型边界待确认」显式降级，
不自行选择任一易混淆专业 Agent。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional, Tuple

from .capabilities import CAPABILITY_BY_MODEL_ID, CAPABILITY_BY_QUESTION_TYPE

# routing_status 取值
ROUTING_STATUS_NORMAL = "normal"
ROUTING_STATUS_BOUNDARY_PENDING = "boundary_pending"

BOUNDARY_PENDING_MESSAGE = (
    "该问题的模型边界尚未由专业团队确认，系统返回「模型边界待确认」，"
    "暂不调用任一易混淆专业模型，请补充更明确的分析尺度或数据类型信息。"
)


@dataclass(frozen=True)
class ExclusiveRule:
    """一条排他规则。

    当问题命中 condition 时，将易混淆对判定到 target 模型。
    pair 仅用于文档化该规则所属的易混淆模型对。
    """
    pair: FrozenSet[str]
    discriminator: str   # 判别维度：业务任务/分析尺度/数据类型/预期输出/模型依赖
    condition: str       # 条件短语（对应 EXCLUSIVE_CONDITION_KEYWORDS 中的键）
    target: str          # 目标 model_id


# 条件短语 → 触发关键词（子串匹配）
EXCLUSIVE_CONDITION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "现状评价": ("现状评价", "现状如何", "现状诊断", "现状评估"),
    "潜力": ("潜力", "提升空间", "增产潜力", "目标等级"),
    "有机质投入量": ("施多少", "每亩施", "施用量", "投入量", "用量"),
    "酸化调理剂": ("调理剂", "石灰", "碱性材料", "木本泥炭", "酸性改良"),
    "稳定性风险": ("稳定性", "退化风险", "掉级", "重点关注清单", "等级稳定"),
    "质量等级评价": ("质量等级", "等级评价", "综合指数", "等级评定", "评价结果"),
}

EXCLUSIVE_RULES: Tuple[ExclusiveRule, ...] = (
    # model-3 vs model-7：现状评价 → model-3（障碍诊断）
    ExclusiveRule(frozenset({"model-3", "model-7"}), "业务任务", "现状评价", "model-3"),
    # model-2 vs model-7：潜力 → model-2（潜力评估）
    ExclusiveRule(frozenset({"model-2", "model-7"}), "业务任务", "潜力", "model-2"),
    # model-4 vs model-6：有机质投入量 → model-6（SOC/Dose 预测）
    ExclusiveRule(frozenset({"model-4", "model-6"}), "预期输出", "有机质投入量", "model-6"),
    # model-4 vs model-6：酸化调理剂 → model-4（酸化改良）
    ExclusiveRule(frozenset({"model-4", "model-6"}), "业务任务", "酸化调理剂", "model-4"),
    # model-1：稳定性风险 → model-1
    ExclusiveRule(frozenset({"model-1"}), "业务任务", "稳定性风险", "model-1"),
    # model-7：质量等级评价 → model-7
    ExclusiveRule(frozenset({"model-7"}), "预期输出", "质量等级评价", "model-7"),
)


def _condition_matches(question: str, condition: str) -> bool:
    for kw in EXCLUSIVE_CONDITION_KEYWORDS.get(condition, ()):
        if kw in question:
            return True
    return False


def model_id_to_question_type(model_id: str) -> Optional[int]:
    capability = CAPABILITY_BY_MODEL_ID.get(model_id)
    return capability.question_type if capability else None


def apply_exclusive_rules(
    question: str,
    question_type: int,
    context: Optional[dict] = None,
) -> Tuple[int, str]:
    """应用排他规则判定，返回 (question_type, routing_status)。

    - routing_status == "normal"：正常路由。
    - routing_status == "boundary_pending"：规则优先级冲突、重叠无法消解，显式降级，
      不调用任何易混淆专业 Agent。
    - TYPE_0(RAG) 与未知类型不应用排他规则。
    """
    if question_type == 0:
        return question_type, ROUTING_STATUS_NORMAL
    capability = CAPABILITY_BY_QUESTION_TYPE.get(question_type)
    if capability is None:
        return question_type, ROUTING_STATUS_NORMAL

    matched_targets = {
        rule.target
        for rule in EXCLUSIVE_RULES
        if _condition_matches(question, rule.condition)
    }

    if len(matched_targets) > 1:
        # 优先级冲突：同一问题命中指向不同模型的规则，无法消解
        return question_type, ROUTING_STATUS_BOUNDARY_PENDING
    if len(matched_targets) == 1:
        target = next(iter(matched_targets))
        target_qtype = model_id_to_question_type(target)
        return target_qtype, ROUTING_STATUS_NORMAL
    # 未命中任何规则：维持既有 question_type 判定
    return question_type, ROUTING_STATUS_NORMAL
```

- [x] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_exclusive_rules.py -v`
Expected: PASS —— 全部排他规则、边界待确认、TYPE_0 不变、model_id→question_type 映射测试通过。

- [x] **Step 5: Commit**

```bash
git add framework/agents/exclusive_rules.py tests/test_exclusive_rules.py
git commit -m "feat: 新增数据驱动排他规则与边界待确认降级"
```

---

### Task 3: 路由集成与 API 响应（state / nodes / orchestrator / chat）

**Files:**
- Modify: `framework/agents/state.py`
- Modify: `framework/agents/nodes.py`
- Modify: `framework/agents/orchestrator.py`
- Modify: `framework/api/routes/chat.py`
- Test: `tests/test_exclusive_rules.py`（追加集成断言）

**Interfaces:**
- Consumes: `apply_exclusive_rules`、`BOUNDARY_PENDING_MESSAGE`（`exclusive_rules.py`）；`identify_question_type`、`EMBEDDING_AVAILABLE`（`routing.py`）。
- Produces: `MultiAgentState` 新增键 `routing_status`；`identify_question_node` 写入 `routing_status`；`boundary_pending_node`；`route_models` 新增分支 `"boundary_pending"`；`aggregate_results` 透传 `routing_status`/`degradation`；`orchestrator.py` 注册节点与分支；`chat.py` 响应新增 `routing_status`/`degradation` 字段。

- [x] **Step 1: 写失败测试 —— 集成降级透传**

在 `tests/test_exclusive_rules.py` 追加：

```python
def test_route_models_boundary_pending():
    """route_models 对 boundary_pending 返回降级分支，且缺省时保持旧行为"""
    from framework.agents.nodes import route_models
    assert route_models({"question_type": 2, "routing_status": "boundary_pending"}) == "boundary_pending"
    assert route_models({"question_type": 1}) == "execute_models"
    assert route_models({"question_type": 0}) == "rag_chat"


def test_aggregate_results_passthrough_boundary_pending():
    """aggregate_results 透传 routing_status 与降级提示"""
    from framework.agents.nodes import aggregate_results
    state = {
        "request": {"question": "酸化调理剂每亩施用量多少"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": 2,
        "relevance": 0.8,
        "routing_status": "boundary_pending",
    }
    result = aggregate_results(state)
    assert result["status"] == "completed"
    assert result["model_results"]["routing_status"] == "boundary_pending"
    assert result["model_results"]["degradation"]
    assert "模型边界待确认" in result["model_results"]["answer"]


def test_identify_question_node_writes_routing_status():
    """identify_question_node 写入 routing_status（缺省 normal）"""
    from framework.agents.nodes import identify_question_node
    state = {"request": {"question": "耕地质量现状评价如何", "scale": "地块"}}
    result = identify_question_node(state)
    assert result["routing_status"] == "normal"
```

在 `tests/test_exclusive_rules.py` 的 `__main__` 块追加调用：

```python
    test_route_models_boundary_pending()
    test_aggregate_results_passthrough_boundary_pending()
    test_identify_question_node_writes_routing_status()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_exclusive_rules.py -v`
Expected: FAIL —— `KeyError: 'routing_status'`（`aggregate_results` 未透传）或 `route_models` 返回值不符；`identify_question_node` 未写入 `routing_status`。

- [x] **Step 3: state.py 增加 routing_status 字段**

`framework/agents/state.py` 的 `MultiAgentState` 末尾追加：

```python
    question_type: Optional[int]
    relevance: Optional[float]
    routing_status: Optional[str]
```

并在 `framework/agents/nodes.py` 的 `initialize_state` 中追加初始化：

```python
        "question_type": None,
        "relevance": None,
        "routing_status": "normal",
```

- [x] **Step 4: nodes.py 集成排他规则、降级节点、路由分支与聚合透传**

`framework/agents/nodes.py` 顶部追加再导出：

```python
from .exclusive_rules import (
    apply_exclusive_rules,
    BOUNDARY_PENDING_MESSAGE,
    ROUTING_STATUS_NORMAL,
    ROUTING_STATUS_BOUNDARY_PENDING,
)
```

将 `identify_question_node` 替换为提取五维上下文并写入 routing_status：

```python
def _extract_five_dim_context(state: MultiAgentState) -> dict:
    """从请求提取五维特征上下文（分析尺度/数据类型）。"""
    request = state.get("request", {})
    context: dict = {}
    scale = request.get("scale")
    if not scale:
        question = request.get("question", "")
        if any(w in question for w in ("我的田", "我的地", "这块", "这个地块", "地块")):
            scale = "地块"
        elif any(w in question for w in ("片区", "村")):
            scale = "片区"
        elif any(w in question for w in ("全省", "全市", "全省耕地")):
            scale = "省"
        elif any(w in question for w in ("全县", "县域", "我们县", "本县")):
            scale = "县"
    context["scale"] = scale or "县"
    if request.get("indicators"):
        context["data_type"] = "指标数据"
    elif request.get("parcel_id") or request.get("parcel_code"):
        context["data_type"] = "评价结果"
    else:
        question = request.get("question", "")
        if any(w in question for w in ("施多少", "每亩", "施用量", "用量", "投入量")):
            context["data_type"] = "处方用量"
        else:
            context["data_type"] = "指标数据"
    return context


def identify_question_node(state: MultiAgentState) -> MultiAgentState:
    question = state["request"].get("question", "")
    context = _extract_five_dim_context(state)
    question_type, relevance = identify_question_type(question, context)
    final_type, routing_status = apply_exclusive_rules(question, question_type, context)
    return {
        **state,
        "question_type": final_type,
        "relevance": relevance,
        "routing_status": routing_status,
        "error": None,
    }
```

将 `route_models` 替换为处理降级信号：

```python
def route_models(state: MultiAgentState) -> str:
    routing_status = state.get("routing_status", ROUTING_STATUS_NORMAL)
    if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
        return "boundary_pending"
    question_type = state["question_type"]
    if question_type == 0:
        return "rag_chat"
    return "execute_models"
```

新增降级节点：

```python
def boundary_pending_node(state: MultiAgentState) -> MultiAgentState:
    """模型边界待确认：不调用任一易混淆专业 Agent，返回显式降级。"""
    return {
        **state,
        "model_results": {
            "status": "boundary_pending",
            "data": {
                "question_type": state.get("question_type"),
                "agents_invoked": [],
                "summary": BOUNDARY_PENDING_MESSAGE,
                "details": {},
                "recommendations": [],
            },
        },
        "status": "model_completed",
        "error": None,
    }
```

将 `aggregate_results` 的 `final_result` 初始化与分支开头替换为透传 routing_status 与降级：

```python
        routing_status = state.get("routing_status", ROUTING_STATUS_NORMAL)
        final_result = {
            "status": "ok",
            "question": question,
            "question_type": question_type,
            "relevance": relevance,
            "routing_status": routing_status,
        }

        if routing_status == ROUTING_STATUS_BOUNDARY_PENDING:
            final_result["answer"] = BOUNDARY_PENDING_MESSAGE
            final_result["sources"] = []
            final_result["model_results"] = model_results
            final_result["llm_response"] = ""
            final_result["degradation"] = BOUNDARY_PENDING_MESSAGE
        elif question_type == 0:
            final_result["answer"] = rag_response.get("answer", "")
            final_result["sources"] = rag_response.get("sources", [])
            final_result["model_results"] = {}
            final_result["llm_response"] = ""
        else:
```

（`else:` 以下保持原专业模型分支逻辑不变。）

- [x] **Step 5: orchestrator.py 注册降级节点与分支**

`framework/agents/orchestrator.py`：

```python
from .nodes import (
    initialize_state,
    identify_question_node,
    route_models,
    execute_models,
    llm_generate,
    rag_chat_node,
    boundary_pending_node,
    aggregate_results,
    finalize,
)
```

在 `build_graph` 中注册节点并追加条件分支：

```python
        graph.add_node("rag_chat", rag_chat_node)
        graph.add_node("boundary_pending", boundary_pending_node)
        graph.add_node("aggregate_results", aggregate_results)
```

```python
        graph.add_conditional_edges(
            "identify_question",
            route_models,
            {
                "rag_chat": "rag_chat",
                "execute_models": "execute_models",
                "boundary_pending": "boundary_pending",
            },
        )

        graph.add_edge("execute_models", "llm_generate")
        graph.add_edge("llm_generate", "aggregate_results")
        graph.add_edge("rag_chat", "aggregate_results")
        graph.add_edge("boundary_pending", "aggregate_results")
        graph.add_edge("aggregate_results", "finalize")
```

并在 `run` 的初始状态中追加（`initialize_state` 已兜底填充，此处显式声明类型合法性）：

```python
            "question_type": None,
            "relevance": None,
            "routing_status": "normal",
```

- [x] **Step 6: chat.py 透传 routing_status 与降级提示**

`framework/api/routes/chat.py` 的 `chat()` 中，在提取 `question_type` 之后追加：

```python
    routing_status = result.get("routing_status", "normal")
    degradation = result.get("degradation")
```

在 `response_data` 初始化中追加：

```python
    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
        "routing_status": routing_status,
    }
```

并在 `recommendations` 之后追加：

```python
    if degradation:
        response_data["degradation"] = degradation
```

- [x] **Step 7: 运行集成测试与既有节点测试确认通过**

Run: `python -m pytest tests/test_exclusive_rules.py tests/test_multi_agent.py -v`
Expected: PASS —— 新增集成断言通过；`test_multi_agent.py` 中 `test_route_models`、`test_aggregate_results_rag`、`test_aggregate_results_model` 等既有测试保持通过（缺省 `routing_status` 时行为不变）。

- [x] **Step 8: Commit**

```bash
git add framework/agents/state.py framework/agents/nodes.py framework/agents/orchestrator.py framework/api/routes/chat.py tests/test_exclusive_rules.py
git commit -m "feat: 路由集成与 API 透传 routing_status 与边界待确认降级"
```

---

### Task 4: 路由测试集扩充（三组易混淆对 + 回归）

**Files:**
- Modify: `tests/test_question_type_keywords.py`
- Run: 全部路由测试

**Interfaces:**
- Consumes: `apply_exclusive_rules`（`exclusive_rules.py`）、`identify_question_type`/`EMBEDDING_AVAILABLE`（`routing.py`）。
- Produces: 三组易混淆对（model-3/7、model-2/7、model-4/6）各 ≥20 条正例 + 反例的测试；排他规则与回归断言。

- [x] **Step 1: 修正旧测试补丁目标（路由逻辑迁移后）**

在 `tests/test_question_type_keywords.py` 的 `test_unrelated_question_returns_zero` 中，将补丁目标从 `nodes.EMBEDDING_AVAILABLE` 改为 `routing.EMBEDDING_AVAILABLE`（路由判定现位于 `routing.py`）：

```python
def test_unrelated_question_returns_zero():
    """无关问题 → TYPE_0（强制 embedding 不可用，纯关键词路径确定返回 0）"""
    from framework.agents import routing

    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False
        qt, _ = _identify("今天天气怎么样？")
        assert qt == 0, f"无关问题期望 TYPE_0，实际 {qt}"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag
    print("✓ 无关问题返回 TYPE_0")
```

- [x] **Step 2: 写失败测试 —— 三组易混淆对正/反例（≥20 条）**

在 `tests/test_question_type_keywords.py` 顶部（`_identify` 之后）追加辅助函数与模型映射：

```python
MODEL_TO_QTYPE = {
    "model-1": 1, "model-2": 6, "model-3": 3,
    "model-4": 2, "model-5": 7, "model-6": 4, "model-7": 5,
}


def _expand(stems, prefixes, suffixes):
    """由基础句干 × 前缀 × 后缀展开为 ≥20 条问题，去重保序。"""
    out, seen = [], set()
    for s in stems:
        for p in prefixes:
            for suf in suffixes:
                c = p + s + suf
                if c not in seen:
                    seen.add(c)
                    out.append(c)
    return out


def _assert_rule_batch(questions, base_qtype, expected_model):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    assert len(questions) >= 20, f"{expected_model} 正例应 ≥20，实际 {len(questions)}"
    for q in questions:
        final_type, status = apply_exclusive_rules(q, base_qtype, {"scale": "地块"})
        exp = MODEL_TO_QTYPE[expected_model]
        assert final_type == exp, f"「{q}」应路由到 {expected_model}(type {exp})，实际 type {final_type}"
        assert status == "normal", f"「{q}」状态应为 normal，实际 {status}"


def _assert_not_routed_to(questions, base_qtype, forbidden_model):
    from framework.agents.exclusive_rules import apply_exclusive_rules
    forb = MODEL_TO_QTYPE[forbidden_model]
    for q in questions:
        final_type, _ = apply_exclusive_rules(q, base_qtype, {"scale": "地块"})
        assert final_type != forb, f"「{q}」不应路由到 {forbidden_model}"


PREFIXES = ["", "全省", "全县", "我们县", "本县", "辖区"]
SUFFIXES = ["", "？"]
MODEL3_STEMS = ["耕地质量现状评价", "土壤障碍现状如何", "耕地质量现状诊断",
                "作物生长障碍现状评价", "耕地退化现状如何", "土壤环境现状评价",
                "耕地质量现状如何", "土壤肥力现状诊断", "耕地酸碱现状评价",
                "耕地质量现状评估"]
MODEL7_STEMS = ["耕地质量等级评价结果", "耕地质量等级评价", "综合指数和障碍度排序",
                "耕地质量等级评定", "耕地质量等级是多少", "质量等级评价结果",
                "耕地质量等级综合评价", "地块质量等级评价"]
MODEL2_STEMS = ["耕地质量提升潜力", "耕地质量潜力评估", "增产潜力多大",
                "改良片区提升潜力", "耕地提升空间", "目标等级提升潜力",
                "潜力分布范围", "提升潜力评估"]
MODEL4_STEMS = ["酸化调理剂施用量", "酸化调理剂用量多少", "石灰施用量",
                "碱性材料用量多少", "木本泥炭用量", "酸性改良剂用量",
                "酸化治理调理剂用量"]
MODEL6_STEMS = ["有机肥每亩施用量", "有机质投入量", "秸秆每亩施用量",
                "有机肥施用量多少", "有机质投入量多少", "有机肥投入量"]
```

追加三组易混淆对目标测试函数：

```python
def test_pair_model3_vs_model7_positive():
    """model-3/7：现状评价正例(→model-3) 与 质量等级评价正例(→model-7) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 5, "model-3")
    _assert_rule_batch(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 3, "model-7")


def test_pair_model3_vs_model7_negative():
    """model-3/7：反例（不误路由到对方）各 ≥20"""
    _assert_not_routed_to(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES), 5, "model-7")
    _assert_not_routed_to(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 3, "model-3")


def test_pair_model2_vs_model7_positive():
    """model-2/7：潜力正例(→model-2) 与 质量等级评价正例(→model-7) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 5, "model-2")
    _assert_rule_batch(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 6, "model-7")


def test_pair_model2_vs_model7_negative():
    """model-2/7：反例各 ≥20"""
    _assert_not_routed_to(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES), 5, "model-7")
    _assert_not_routed_to(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES), 6, "model-2")


def test_pair_model4_vs_model6_positive():
    """model-4/6：酸化调理剂正例(→model-4) 与 有机质投入量正例(→model-6) 各 ≥20"""
    _assert_rule_batch(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 4, "model-4")
    _assert_rule_batch(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES), 2, "model-6")


def test_pair_model4_vs_model6_negative():
    """model-4/6：反例各 ≥20"""
    _assert_not_routed_to(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES), 4, "model-6")
    _assert_not_routed_to(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES), 2, "model-4")
```

追加回归断言（叠加五维不破坏既有 1:1 路由，且正常问题不误降级）：

```python
def test_five_dim_does_not_break_existing_1to1_routing():
    """context 提供时，未命中排他规则的正常问题保持既有 question_type"""
    from framework.agents import routing
    real_flag = routing.EMBEDDING_AVAILABLE
    try:
        routing.EMBEDDING_AVAILABLE = False  # 纯关键词，确定性
        cases = [
            ("查询区域内哪些高等级耕地存在退化风险？", 1),
            ("辖区耕地质量提升的总体潜力有多大？可增产多少粮食？", 6),
            ("我这块地到底有啥毛病？", 3),
            ("查询区域内农用地土壤酸化程度如何，不同酸化等级比例分别多少？", 2),
            ("我的田土壤有机碳含量大概多少？", 4),
            ("我的田耕地质量等级是多少？", 5),
            ("全省耕地土壤有机质含量如何，空间分布情况？", 7),
        ]
        for q, expected in cases:
            qt, _ = routing.identify_question_type(q, {"scale": "县"})
            assert qt == expected, f"「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
    finally:
        routing.EMBEDDING_AVAILABLE = real_flag


def test_normal_questions_not_degraded():
    """未命中排他规则的正常问题，routing_status 保持 normal"""
    from framework.agents.exclusive_rules import apply_exclusive_rules as _apply
    final_type, status = _apply("我的田肥力怎么样", 4, {"scale": "地块"})
    assert status == "normal"
    assert final_type == 4


def test_all_confusing_pair_batches_size_ge_20():
    """三组易混淆对正例/反例批量规模均 ≥20"""
    assert len(_expand(MODEL3_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL7_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL2_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL4_STEMS, PREFIXES, SUFFIXES)) >= 20
    assert len(_expand(MODEL6_STEMS, PREFIXES, SUFFIXES)) >= 20
```

在 `tests/test_question_type_keywords.py` 的 `if __name__ == "__main__":` 块末尾追加调用：

```python
    test_pair_model3_vs_model7_positive()
    test_pair_model3_vs_model7_negative()
    test_pair_model2_vs_model7_positive()
    test_pair_model2_vs_model7_negative()
    test_pair_model4_vs_model6_positive()
    test_pair_model4_vs_model6_negative()
    test_five_dim_does_not_break_existing_1to1_routing()
    test_normal_questions_not_degraded()
    test_all_confusing_pair_batches_size_ge_20()
```

- [x] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: FAIL —— 若 Task 1-3 已实现，多数应通过；此处确认新增混淆对测试与回归断言全部通过（若发现某条反例误路由，说明 `EXCLUSIVE_CONDITION_KEYWORDS` 某关键词过宽，需在 Task 2 Step 3 调整关键词后回到本步重跑）。

- [x] **Step 4: 运行全部路由测试并核对正确率**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_exclusive_rules.py tests/test_multi_agent.py -v`
Expected: PASS —— 全部路由相关测试通过。

随后运行全量回归：

Run: `python -m pytest tests/ -v`
Expected: PASS —— 现有约 470 个测试全部通过（`test_unrelated_question_returns_zero` 经 Step 1 修正后通过）。

- [x] **Step 5: 生成扩充报告并提交配置产物**

在 `openspec/changes/add-routing-exclusive-rules/` 下追加 `routing-test-report.md`（记录：三组易混淆对各 ≥20 条正例/反例、排他规则与边界待确认测试数、全量测试通过数）：

```markdown
# 路由测试集扩充报告

- model-3/7 易混淆对：正例 ≥20（现状评价→model-3；质量等级评价→model-7），反例 ≥20。
- model-2/7 易混淆对：正例 ≥20（潜力→model-2；质量等级评价→model-7），反例 ≥20。
- model-4/6 易混淆对：正例 ≥20（酸化调理剂→model-4；有机质投入量→model-6），反例 ≥20。
- 排他规则与「模型边界待确认」降级测试：`tests/test_exclusive_rules.py`。
- 全量回归：`python -m pytest tests/` 通过（约 470 个测试）。
```

```bash
git add tests/test_question_type_keywords.py openspec/changes/add-routing-exclusive-rules/routing-test-report.md
git commit -m "test: 扩充三组易混淆对路由测试集与全量回归"
```

---

## 自审（Self-Review）

- **Spec 覆盖**：Task 1 覆盖目标/决策 A/B/E（五维字段、独立路由模块、向后兼容）；Task 2 覆盖决策 C/D（数据驱动排他规则、boundary_pending 降级、六条判别：现状评价→model-3、潜力→model-2、有机质投入量→model-6、酸化调理剂→model-4、稳定性风险→model-1、质量等级评价→model-7）；Task 3 覆盖数据流步骤 3-5 与目标「route_models 处理降级 / aggregate_results 透传 / 不破坏 1:1」；Task 4 覆盖测试策略三组混淆对各 ≥20 正反例 + 排他/降级测试 + 全量回归。
- **占位符扫描**：所有代码步骤均含完整实现，无 "TBD/TODO/稍后"。
- **类型一致性**：`apply_exclusive_rules` 返回 `(int, str)`；`identify_question_type` 返回 `(int, float)`；`route_models` 返回 `"boundary_pending"/"rag_chat"/"execute_models"`；`routing_status ∈ {"normal","boundary_pending"}`，各任务引用一致。