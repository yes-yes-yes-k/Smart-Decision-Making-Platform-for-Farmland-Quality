---
comet_change: refactor-routing-to-question-type
role: technical-design
canonical_spec: openspec
---

# Design Doc: 重构路由为 question_type-based 1:1 映射

## 1. 背景与目标

### 1.1 背景

当前多智能体框架采用 role-based 路由：`RoleRouter` 通过关键词识别用户角色（province/county/farmer），每个角色固定映射到一组 agents。`AgentManager.process` 调用 `identify_role` → `get_agents_for_role` → `_execute_with_dependencies`，其中 `_should_execute_agent` 对 model-6/model-7 做二次关键词过滤。

与此同时 `nodes.py` 中已存在稳定的 `identify_question_type` 函数（基于关键词+向量相似度识别 5 种问题类型）。两套路由机制并存导致冗余调用、语义重复和心智负担。

此外，`identify_question_type` 的关键词匹配过于激进——知识性问题（如「什么是土壤酸化」）因包含领域关键词被错误路由到专业模型，而非走 RAG 知识库。

### 1.2 目标

1. 将路由统一为 question_type-based 1:1 映射，消除 role 路由和二次过滤
2. 新增知识性问题预检，确保概念解释类问题走 RAG
3. 移除 API 响应中的 `role` 字段
4. 保持 `identify_question_type` 现有关键词/向量逻辑、`parcel_id`/`parcel_code` 透传、RAG 链路不变

## 2. 架构设计

### 2.1 重构后数据流

```
用户问题
   │
   ▼
┌─────────────────────────────────────┐
│ identify_question_node (nodes.py)   │
│   identify_question_type(question)  │
│   ├─ 1. 知识性问题预检 → type 0     │  ← 新增
│   ├─ 2. relevance 检查 (≥0.3)       │
│   ├─ 3. 领域关键词匹配 → type 1-5   │
│   └─ 4. 向量降级匹配 → type 1-5/0   │
└───────────────┬─────────────────────┘
                │ state.question_type ∈ {0,1,2,3,4,5}
                ▼
┌─────────────────────────────────────┐
│ route_models (nodes.py)             │
│   type=0 → rag_chat_node            │
│   type≠0 → execute_models           │
└───────────────┬─────────────────────┘
                │ (仅 type 1-5)
                ▼
┌─────────────────────────────────────────────┐
│ execute_models (nodes.py)                   │
│   context["question_type"] = state.get(...) │  ← 新增透传
│   agent_manager.process(question, context)  │
└───────────────┬─────────────────────────────┘
                ▼
┌─────────────────────────────────────────────┐
│ AgentManager.process (manager.py)           │
│   question_type = context.get("question_type")│
│   agent_ids = QuestionTypeRouter            │
│       .get_agents_for_type(question_type)   │
│   ├─ 若 agent_ids 为空 → no_routing 空结果  │  ← 防御性
│   └─ 否则 → _execute_with_dependencies      │
│             → _summarize(question_type,...) │
└─────────────────────────────────────────────┘
```

### 2.2 组件职责

| 组件 | 职责 | 改动 |
|------|------|------|
| `QuestionTypeRouter` (router.py) | 1:1 映射 question_type → model_id | 完全重写 |
| `AgentManager.process` (manager.py) | 按 question_type 路由执行 | 重写 process + _summarize，删 _should_execute_agent |
| `identify_question_type` (nodes.py) | 识别问题类型 | 新增知识性预检分支 |
| `execute_models` (nodes.py) | 透传 question_type 到 context | 新增 1 行 |
| `chat.py` | API 响应 | 移除 role 字段 |

## 3. 详细设计

### 3.1 QuestionTypeRouter（router.py 完全重写）

```python
from __future__ import annotations
from typing import Dict, List


class QuestionTypeRouter:
    """基于问题类型的路由器，1:1 映射 question_type 到单一智能体。"""

    TYPE_AGENTS: Dict[int, List[str]] = {
        1: ["model-1"],  # StabilityRiskAgent - 稳定性/退化风险
        2: ["model-4"],  # AcidificationRemediationAgent - 酸化改良
        3: ["model-3"],  # ProblemIdentificationAgent - 障碍诊断
        4: ["model-6"],  # FertilityMLAgent - 肥力/SOC/Dose
        5: ["model-7"],  # FarmlandGradeAgent - 耕地质量等级评价
    }

    def get_agents_for_type(self, question_type: int) -> List[str]:
        """返回该问题类型对应的智能体 ID 列表。未知类型返回空列表。"""
        return list(self.TYPE_AGENTS.get(question_type, []))
```

**设计要点**：
- `TYPE_AGENTS` 是类常量，集中管理映射，便于测试和维护
- `get_agents_for_type` 对未知 type 返回空列表（而非抛异常），使调用方能做防御性处理
- model-2（PotentialAssessmentAgent）和 model-5（OrganicMatterAgent）不在映射中，保留注册但不路由

### 3.2 AgentManager.process 重构（manager.py）

```python
def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """处理用户问题，返回综合结果。"""
    question_type = context.get("question_type")
    agent_ids = self.router.get_agents_for_type(question_type)

    if not agent_ids:
        # 防御性：question_type 为 None/0/未知时返回 no_routing
        return {
            "status": "no_routing",
            "data": {
                "question_type": question_type,
                "agents_invoked": [],
                "summary": "未识别问题类型",
                "details": {},
                "recommendations": [],
            },
        }

    results = self._execute_with_dependencies(agent_ids, question, context)
    return {
        "status": "ok",
        "data": self._summarize(question_type, agent_ids, results),
    }
```

**防御性行为决策**：
- question_type=None（context 缺失）→ `get_agents_for_type(None)` → `[]` → no_routing
- question_type=0（识别失败）→ `route_models` 保证不进入 `execute_models`；若直接调用则 no_routing
- question_type=6（超出范围）→ `TYPE_AGENTS.get(6, [])` → `[]` → no_routing
- 选择 no_routing 而非抛异常：使 AgentManager.process 契约更健壮，便于测试和未来直接调用

### 3.3 _execute_with_dependencies 简化

```python
def _execute_with_dependencies(self, agent_ids, question, context):
    """按依赖关系顺序执行智能体，前序输出累积到 context。"""
    ordered = self._topological_sort(agent_ids)
    accumulated = dict(context)
    results = {}
    for agent_id in ordered:
        agent = self.agents[agent_id]
        try:
            result = agent.answer_question(question, accumulated)
        except Exception as exc:
            result = {
                "answer": f"智能体执行失败: {exc}",
                "evidence": [],
                "confidence": 0.0,
                "simulated": True,
                "error": str(exc),
            }
        results[agent_id] = result
        accumulated[agent_id] = result
    return results
```

**变更**：移除 `_should_execute_agent` 调用——1:1 路由后，每个 agent 直接执行，无需二次过滤。

### 3.4 _summarize 签名变更

```python
def _summarize(self, question_type, agent_ids, results):
    """汇总各智能体结果为 API 响应结构。"""
    ordered_invoked = self._topological_sort(agent_ids)
    details = {aid: results[aid] for aid in ordered_invoked if aid in results}
    # ... 摘要、推荐逻辑不变 ...
    return {
        "question_type": question_type,  # 替换原 "role": role
        "agents_invoked": ordered_invoked,
        "summary": summary,
        "details": details,
        "recommendations": recommendations,
    }
```

### 3.5 model-3 依赖清理

在 `_register_agents` 中：
```python
# 原：self.agents["model-3"].dependencies = ["model-2"]
# 新：
self.agents["model-3"].dependencies = []
```

**理由**：1:1 映射后 model-2 永不与 model-3 同调，依赖是死代码。`_topological_sort` 会过滤不在 agent_ids 集合内的依赖，所以保留也无害，但清理后更清晰。

### 3.6 知识性问题预检（nodes.py）

```python
KNOWLEDGE_QUESTION_PATTERNS_START = ["什么是", "何为", "解释"]
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = ["是什么意思", "什么意思", "定义", "概念", "含义"]


def _is_knowledge_question(question: str) -> bool:
    """检测是否为知识性问题（概念解释、定义等），应走 RAG。"""
    if not question:
        return False
    q = question.strip()
    if any(q.startswith(p) for p in KNOWLEDGE_QUESTION_PATTERNS_START):
        return True
    if any(p in q for p in KNOWLEDGE_QUESTION_PATTERNS_CONTAIN):
        return True
    return False


def identify_question_type(question: str) -> tuple[int, float]:
    # 1. 知识性问题预检 → type 0 (RAG)
    if _is_knowledge_question(question):
        return 0, 1.0
    # 2. 原有关键词优先 + 向量降级逻辑（不变）
    result = _identify_question_type_keyword(question)
    if result[0] != 0:
        return result
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    return result
```

**模式选择理由**：
- 开头匹配「什么是」「何为」「解释」：强知识信号，误报率极低
- 包含匹配「是什么意思」「什么意思」「定义」「概念」「含义」：明确的概念询问
- 不包含「为什么」「区别」「差异」：歧义性高，「为什么我的田酸化」是具体问题而非知识问题

### 3.7 execute_models 透传（nodes.py）

```python
def execute_models(state: MultiAgentState) -> MultiAgentState:
    try:
        from framework.agents.manager import agent_manager
        question = state["request"].get("question", "")
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
            "question_type": state.get("question_type"),  # ← 新增
        }
        # ... parcel_id/parcel_code 透传不变 ...
        result = agent_manager.process(question, context)
        ...
```

同时更新 `QUESTION_TYPE_TO_MODEL_ID`：
```python
QUESTION_TYPE_TO_MODEL_ID = {
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",  # 保留原值（此字典用于 fallback，不影响 AgentManager 路由）
    4: "model-5,model-6",  # 保留原值
    5: "model-7",          # ← 新增
}
```

**注**：`QUESTION_TYPE_TO_MODEL_ID` 仅在 `_execute_models_fallback` 中使用（AgentManager 失败时）。AgentManager 的正式路由由 `TYPE_AGENTS` 控制（1:1）。fallback 路径保留原 1:N 映射以维持现有行为，不在本次重构范围内。

### 3.8 chat.py 改动

```python
# 删除以下两行：
# role = agent_data.get("role")
# if role:
#     response_data["role"] = role
```

其他字段（`question_type`、`agents_invoked`、`summary`、`recommendations`）保持不变。

## 4. 错误处理与边界条件

| 场景 | 行为 | 测试覆盖 |
|------|------|---------|
| question_type=None | no_routing 空结果 | test_process_no_routing |
| question_type=0 | route_models 保证不进入；若进入则 no_routing | test_process_type0_no_routing |
| question_type=6（超出范围） | no_routing 空结果 | test_process_unknown_type |
| 单个 agent 执行异常 | catch Exception，记录 error，返回 error 结果 | 现有异常处理不变 |
| 知识性问题「什么是X」 | type 0 → RAG | test_knowledge_question_start |
| 知识性问题「X是什么意思」 | type 0 → RAG | test_knowledge_question_meaning |
| 具体问题「我的田X」 | 不匹配知识模式，走领域关键词 | test_specific_question_not_knowledge |

## 5. 测试策略

### 5.1 TDD 顺序

每个任务组遵循「先写失败测试 → 实现 → 验证通过」循环。

### 5.2 测试文件规划

| 文件 | 状态 | 测试内容 |
|------|------|---------|
| `tests/test_question_type_router.py` | 新建 | TYPE_AGENTS 映射、get_agents_for_type、未知类型返回 [] |
| `tests/test_agent_manager.py` | 重写 | 删除 role/_should_execute_agent 测试；新增 type 1-5 路由、no_routing 测试 |
| `tests/test_multi_agent.py` | 扩展 | 新增 type 5 → model-7 路由测试 |
| `tests/test_knowledge_question.py` | 新建 | _is_knowledge_question 单元测试 + identify_question_type 集成测试 |
| `tests/test_execute_models_pipeline.py` | 更新 | 验证 question_type 透传到 context |

### 5.3 端到端验证

- 运行 `scripts/gen_full_verification_report.py` 确认 23 个问题回答不变
- 新增知识性问题验证用例：「什么是土壤酸化」「耕地质量等级是什么意思」走 RAG
- 验证 API 响应：无 `role` 字段，type 5 的 `agents_invoked` 仅含 `model-7`

## 6. 风险与取舍

### 6.1 风险

| 风险 | 缓解 |
|------|------|
| model-2/model-5 永不被调用，隐藏未发现 bug | 保留注册和桩测试；未来扩展只需 TYPE_AGENTS 加映射 |
| identify_question_type 误判路由到错误模型 | 现有 23/23 测试通过；重构后影响范围更小（只调一个模型） |
| 知识性预检误报导致具体问题被误路由到 RAG | 保守模式列表；测试覆盖「我的田X」类不误判 |
| 客户端依赖 role 字段 BREAKING | proposal 标注 BREAKING；question_type 字段已存在可替代 |

### 6.2 取舍

| 取舍 | 理由 |
|------|------|
| 1:1 映射失去多模型协同 | model-2/5 为桩实现，协同价值有限；未来可扩展为 1:N |
| 移除 _should_execute_agent 双保险 | 路由已保证精准性；保留增加维护成本和关键词重复 |
| spec 目录名 role-based-routing 与内容不符 | 避免 git 重命名复杂度；spec 内容明确说明 |
| 知识性预检保守模式 | 精度优先于召回；可后续扩展模式 |

## 7. 迁移计划

### 7.1 代码改动顺序（TDD）

1. 知识性问题检测（nodes.py 新增预检）— 独立，可并行
2. Router 重构（router.py）
3. AgentManager 重构（manager.py）
4. nodes.py 透传 question_type
5. chat.py 移除 role 字段
6. 测试套件更新
7. 端到端验证

### 7.2 回滚策略

- 纯代码重构，无数据库迁移
- `git revert` 即可恢复 role-based 路由

### 7.3 验证检查点

- 单元测试：所有 type 1-5 路由测试通过
- 集成测试：知识性问题走 RAG，具体问题走对应模型
- 端到端：23 个问题回答不变 + 知识性问题验证
- API：响应无 role 字段，含 question_type
