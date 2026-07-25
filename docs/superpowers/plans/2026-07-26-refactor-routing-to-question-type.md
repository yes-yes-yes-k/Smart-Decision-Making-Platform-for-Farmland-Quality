---
change: refactor-routing-to-question-type
design-doc: docs/superpowers/specs/2026-07-26-refactor-routing-to-question-type-design.md
base-ref: b6d8a5dda947f296c15f4dffe3a32c7aaa0feaab
---

# 重构路由为 question_type-based 1:1 映射 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将多智能体路由从 role-based 改为 question_type-based 1:1 映射（type 1→model-1、2→model-4、3→model-3、4→model-6、5→model-7），新增知识性问题预检，移除 API 响应中的 `role` 字段。

**Architecture:** 删除 `RoleRouter` 与 `_should_execute_agent` 二次过滤层，新增 `QuestionTypeRouter` 类做 1:1 类型映射。`AgentManager.process` 直接从 `context["question_type"]` 取类型并路由到单一智能体。`identify_question_type` 在最前端增加 `_is_knowledge_question` 预检，命中即返回 `(0, 1.0)` 走 RAG。`execute_models` 透传 `question_type` 到 context，`chat.py` 不再写回 `role` 字段。

**Tech Stack:** Python 3.10+、Flask、pytest、numpy（向量相似度）、LangChain/RAG（知识库链路）。

## Global Constraints

- 1:1 映射表固定为 `TYPE_AGENTS = {1:["model-1"], 2:["model-4"], 3:["model-3"], 4:["model-6"], 5:["model-7"]}`，不得扩展为 1:N
- `model-2`（PotentialAssessmentAgent）和 `model-5`（OrganicMatterAgent）保留注册但不路由
- `QuestionTypeRouter.get_agents_for_type` 对未知 type 返回空列表（不抛异常）
- 知识性预检模式列表保守：仅匹配「什么是/何为/解释」开头与「是什么意思/什么意思/定义/概念/含义」包含；不得包含「为什么/区别/差异」
- API 响应必须删除 `role` 字段；`question_type`、`agents_invoked`、`summary`、`recommendations` 字段保持不变
- 23 个端到端问题（`scripts/gen_full_verification_report.py`）的回答结果不变
- `parcel_id`/`parcel_code` 透传链路不变
- `QUESTION_TYPE_TO_MODEL_ID` 字典仅用于 `_execute_models_fallback`，保留原 1:N 值，仅新增 `5: "model-7"`
- 代码风格：`from __future__ import annotations`、类型注解、4 空格缩进
- 提交粒度：每个 Task 一次 commit，commit message 使用 `feat:`/`refactor:`/`test:`/`chore:` 前缀

## File Structure

| 文件 | 状态 | 职责 |
|------|------|------|
| `framework/agents/router.py` | 完全重写 | `QuestionTypeRouter` 类，1:1 映射 question_type → model_id |
| `framework/agents/manager.py` | 重写 process + _summarize，删 _should_execute_agent | 按 question_type 路由执行 |
| `framework/agents/nodes.py` | 新增知识性预检 + execute_models 透传 | 类型识别与 context 透传 |
| `framework/api/routes/chat.py` | 删除 role 字段写入 | API 响应清理 |
| `tests/test_question_type_router.py` | 新建 | QuestionTypeRouter 单元测试 |
| `tests/test_knowledge_question.py` | 新建 | _is_knowledge_question + identify_question_type 集成测试 |
| `tests/test_agent_manager.py` | 重写 | 删除 role/_should_execute_agent 测试，新增 type 1-5 路由测试 |
| `tests/test_multi_agent.py` | 扩展 | 新增 type 5 → model-7 路由集成测试 |
| `tests/test_execute_models_pipeline.py` | 更新 | 验证 question_type 透传到 context |

---

## 任务组 1: Router 重构（TDD）

### Task 1.1: 编写 QuestionTypeRouter 失败测试

**Files:**
- Create: `tests/test_question_type_router.py`

**Interfaces:**
- Produces: `QuestionTypeRouter` 类（待 Task 1.2 实现），方法 `get_agents_for_type(question_type: int) -> List[str]`，类常量 `TYPE_AGENTS: Dict[int, List[str]]`

- [x] **Step 1: 创建测试文件 `tests/test_question_type_router.py`**

```python
"""测试 QuestionTypeRouter 基于 question_type 的 1:1 路由"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.router import QuestionTypeRouter, TYPE_AGENTS


def test_type_agents_mapping_is_one_to_one():
    """TYPE_AGENTS 必须为 1:1 映射：1→model-1、2→model-4、3→model-3、4→model-6、5→model-7"""
    assert TYPE_AGENTS == {
        1: ["model-1"],
        2: ["model-4"],
        3: ["model-3"],
        4: ["model-6"],
        5: ["model-7"],
    }, f"TYPE_AGENTS 映射不符: {TYPE_AGENTS}"
    # 每个 type 仅映射到单一 agent
    for q_type, agents in TYPE_AGENTS.items():
        assert len(agents) == 1, f"type {q_type} 应仅映射 1 个 agent，实际: {agents}"
    print("✓ TYPE_AGENTS 为 1:1 映射")


def test_get_agents_for_type_known_types():
    """已知 type 1-5 各返回对应单一 agent ID 列表"""
    router = QuestionTypeRouter()
    assert router.get_agents_for_type(1) == ["model-1"]
    assert router.get_agents_for_type(2) == ["model-4"]
    assert router.get_agents_for_type(3) == ["model-3"]
    assert router.get_agents_for_type(4) == ["model-6"]
    assert router.get_agents_for_type(5) == ["model-7"]
    print("✓ get_agents_for_type 对 type 1-5 返回正确映射")


def test_get_agents_for_type_returns_copy():
    """返回的列表应是副本，修改不影响 TYPE_AGENTS"""
    router = QuestionTypeRouter()
    result = router.get_agents_for_type(1)
    result.append("model-999")
    assert "model-999" not in TYPE_AGENTS[1], "修改返回值污染了 TYPE_AGENTS"
    print("✓ get_agents_for_type 返回列表副本")


def test_get_agents_for_type_unknown_returns_empty():
    """未知 type（0、6、-1、None）返回空列表"""
    router = QuestionTypeRouter()
    assert router.get_agents_for_type(0) == []
    assert router.get_agents_for_type(6) == []
    assert router.get_agents_for_type(-1) == []
    assert router.get_agents_for_type(None) == []
    print("✓ 未知 type 返回空列表")


def test_role_router_removed():
    """RoleRouter 类已移除"""
    import framework.agents.router as router_mod
    assert not hasattr(router_mod, "RoleRouter"), "RoleRouter 仍存在，应已删除"
    print("✓ RoleRouter 已移除")


if __name__ == "__main__":
    test_type_agents_mapping_is_one_to_one()
    test_get_agents_for_type_known_types()
    test_get_agents_for_type_returns_copy()
    test_get_agents_for_type_unknown_returns_empty()
    test_role_router_removed()
    print("\n所有 QuestionTypeRouter 测试通过！")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_question_type_router.py`
Expected: FAIL with `ImportError: cannot import name 'QuestionTypeRouter'`

- [x] **Step 3: Commit 失败测试**

```bash
git add tests/test_question_type_router.py
git commit -m "test: add failing tests for QuestionTypeRouter 1:1 mapping"
```

---

### Task 1.2: 重写 router.py 实现 QuestionTypeRouter

**Files:**
- Modify: `framework/agents/router.py` (完全重写)

**Interfaces:**
- Consumes: 无
- Produces: `QuestionTypeRouter` 类、`TYPE_AGENTS` 字典、`QuestionTypeRouter.get_agents_for_type(question_type: int) -> List[str]`

- [x] **Step 1: 完全重写 `framework/agents/router.py`**

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

- [x] **Step 2: Commit 实现**

```bash
git add framework/agents/router.py
git commit -m "refactor: replace RoleRouter with QuestionTypeRouter (1:1 mapping)"
```

---

### Task 1.3: 验证 router 单元测试通过

**Files:**
- Verify: `tests/test_question_type_router.py`

- [x] **Step 1: 运行 router 单元测试**

Run: `python tests/test_question_type_router.py`
Expected: PASS，输出「所有 QuestionTypeRouter 测试通过！」

- [x] **Step 2: 运行 pytest 确认 router 模块无回归**

Run: `python -m pytest tests/test_question_type_router.py -v`
Expected: 5 passed

- [x] **Step 3: 全局搜索 RoleRouter 残留引用**

Run: `findstr /S /N "RoleRouter" d:\17417\Documents\agent_culti_demo\framework d:\17417\Documents\agent_culti_demo\tests`
Expected: 无输出（或仅在 `__pycache__` 中），源码与测试中不应再引用 `RoleRouter`

---

## 任务组 2: AgentManager 重构（TDD）

### Task 2.1: 编写 AgentManager.process 的 question_type 路由失败测试

**Files:**
- Modify: `tests/test_agent_manager.py` (新增测试函数)

**Interfaces:**
- Consumes: `AgentManager.process(question: str, context: Dict) -> Dict`，context 须含 `question_type` 键
- Produces: 验证 `process` 按 question_type 1:1 路由到单一 agent；返回结构含 `data.question_type` 而非 `data.role`

- [x] **Step 1: 在 `tests/test_agent_manager.py` 末尾追加测试函数**

```python
def test_process_type1_routes_to_model1_only():
    """type=1 → 仅调 model-1，不调 model-2/3"""
    mgr = AgentManager()
    result = mgr.process("查询区域内耕地质量等级整体稳定吗", {"question_type": 1})
    assert result["status"] == "ok"
    assert result["data"]["agents_invoked"] == ["model-1"]
    assert result["data"]["question_type"] == 1
    print("✓ type=1 路由到 model-1")


def test_process_type2_routes_to_model4_only():
    """type=2 → 仅调 model-4"""
    mgr = AgentManager()
    result = mgr.process("我的田酸化严重吗", {"question_type": 2})
    assert result["data"]["agents_invoked"] == ["model-4"]
    assert result["data"]["question_type"] == 2
    print("✓ type=2 路由到 model-4")


def test_process_type3_routes_to_model3_only():
    """type=3 → 仅调 model-3，不调 model-2"""
    mgr = AgentManager()
    result = mgr.process("我这块地到底有啥毛病", {"question_type": 3})
    assert result["data"]["agents_invoked"] == ["model-3"]
    assert "model-2" not in result["data"]["agents_invoked"]
    print("✓ type=3 路由到 model-3（不调 model-2）")


def test_process_type4_routes_to_model6_only():
    """type=4 → 仅调 model-6，不调 model-5"""
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样", {"question_type": 4})
    assert result["data"]["agents_invoked"] == ["model-6"]
    assert "model-5" not in result["data"]["agents_invoked"]
    assert "model-4" not in result["data"]["agents_invoked"]
    print("✓ type=4 路由到 model-6（不调 model-4/5）")


def test_process_type5_routes_to_model7_only():
    """type=5 → 仅调 model-7，不调 model-4/5/6"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 5, "parcel_code": "A0001"})
    assert result["data"]["agents_invoked"] == ["model-7"]
    assert "model-4" not in result["data"]["agents_invoked"]
    assert "model-5" not in result["data"]["agents_invoked"]
    assert "model-6" not in result["data"]["agents_invoked"]
    print("✓ type=5 路由到 model-7（不调 model-4/5/6）")


def test_process_no_routing_when_question_type_none():
    """question_type=None（context 缺失）→ no_routing 空结果"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    assert result["data"]["summary"] == "未识别问题类型"
    print("✓ question_type=None 返回 no_routing")


def test_process_no_routing_when_question_type_zero():
    """question_type=0 → no_routing（route_models 保证不进入，此处为防御性）"""
    mgr = AgentManager()
    result = mgr.process("什么是土壤酸化", {"question_type": 0})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    print("✓ question_type=0 返回 no_routing")


def test_process_no_routing_when_question_type_unknown():
    """question_type=6（超出范围）→ no_routing"""
    mgr = AgentManager()
    result = mgr.process("未知问题", {"question_type": 6})
    assert result["status"] == "no_routing"
    assert result["data"]["question_type"] == 6
    print("✓ 未知 question_type 返回 no_routing")
```

- [x] **Step 2: 运行新测试验证失败**

Run: `python -m pytest tests/test_agent_manager.py::test_process_type1_routes_to_model1_only tests/test_agent_manager.py::test_process_no_routing_when_question_type_none -v`
Expected: FAIL（当前 process 仍走 role 路由，`agents_invoked` 为 farmer 的 4 个 agent）

- [x] **Step 3: Commit 失败测试**

```bash
git add tests/test_agent_manager.py
git commit -m "test: add failing tests for AgentManager question_type routing"
```

---

### Task 2.2: 编写 _should_execute_agent 移除后的回归测试

**Files:**
- Modify: `tests/test_agent_manager.py` (新增测试函数)

**Interfaces:**
- Consumes: `AgentManager` 不再有 `_should_execute_agent` 方法、`FERTILITY_KEYWORDS`、`GRADE_KEYWORDS`
- Produces: 验证 details 中不出现 `skipped` 条目（因路由精准，无需二次过滤）

- [x] **Step 1: 在 `tests/test_agent_manager.py` 追加回归测试**

```python
def test_no_skipped_entries_in_details_for_type4():
    """type=4 路由到 model-6，details 中 model-6 不应有 skipped 状态"""
    mgr = AgentManager()
    result = mgr.process("我的田肥力怎么样", {"question_type": 4})
    details = result["data"]["details"]
    m6 = details.get("model-6", {})
    assert m6.get("status") != "skipped", f"model-6 不应被 skipped: {m6}"
    assert m6.get("reason") != "question_not_related"
    print("✓ type=4 details 中 model-6 未被 skipped")


def test_no_skipped_entries_in_details_for_type5():
    """type=5 路由到 model-7，details 中 model-7 不应有 skipped 状态"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少", {"question_type": 5, "parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被 skipped: {m7}"
    print("✓ type=5 details 中 model-7 未被 skipped")


def test_should_execute_agent_method_removed():
    """_should_execute_agent 方法应已删除"""
    mgr = AgentManager()
    assert not hasattr(mgr, "_should_execute_agent"), "_should_execute_agent 仍存在"
    print("✓ _should_execute_agent 已移除")


def test_fertility_keywords_constant_removed():
    """FERTILITY_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "FERTILITY_KEYWORDS"), "FERTILITY_KEYWORDS 仍存在"
    print("✓ FERTILITY_KEYWORDS 已移除")


def test_grade_keywords_constant_removed():
    """GRADE_KEYWORDS 常量应已删除"""
    import framework.agents.manager as mgr_mod
    assert not hasattr(mgr_mod, "GRADE_KEYWORDS"), "GRADE_KEYWORDS 仍存在"
    print("✓ GRADE_KEYWORDS 已移除")
```

- [x] **Step 2: 运行回归测试验证失败**

Run: `python -m pytest tests/test_agent_manager.py::test_should_execute_agent_method_removed tests/test_agent_manager.py::test_no_skipped_entries_in_details_for_type4 -v`
Expected: FAIL（`_should_execute_agent` 仍存在）

- [x] **Step 3: Commit 失败测试**

```bash
git add tests/test_agent_manager.py
git commit -m "test: add regression tests for _should_execute_agent removal"
```

---

### Task 2.3: 重写 AgentManager.process 与 _summarize

**Files:**
- Modify: `framework/agents/manager.py:5` (import 改为 QuestionTypeRouter)
- Modify: `framework/agents/manager.py:46-136` (process + __init__ + _summarize 重写)
- Modify: `framework/agents/manager.py:76` (model-3 dependencies 清理)

**Interfaces:**
- Consumes: `QuestionTypeRouter.get_agents_for_type(question_type: int) -> List[str]`（来自 Task 1.2）
- Produces: `AgentManager.process(question, context)` 从 `context["question_type"]` 路由；返回 `data` 含 `question_type` 字段（替代原 `role`）

- [x] **Step 1: 修改 import**

将 `framework/agents/manager.py:5` 由：
```python
from .router import RoleRouter
```
改为：
```python
from .router import QuestionTypeRouter
```

- [x] **Step 2: 删除 FERTILITY_KEYWORDS 与 GRADE_KEYWORDS 常量**

删除 `framework/agents/manager.py:8-21`（即 `FERTILITY_KEYWORDS = [...]` 与 `GRADE_KEYWORDS = [...]` 两个常量及其上方注释）。

- [x] **Step 3: 修改 `__init__` 中的 router 实例化**

将 `framework/agents/manager.py:51` 由：
```python
        self.router = RoleRouter()
```
改为：
```python
        self.router = QuestionTypeRouter()
```

- [x] **Step 4: 清理 model-3 dependencies**

将 `framework/agents/manager.py:76` 由：
```python
        self.agents["model-3"].dependencies = ["model-2"]
```
改为：
```python
        self.agents["model-3"].dependencies = []
```

- [x] **Step 5: 重写 `process` 方法**

替换 `framework/agents/manager.py:128-136`（原 process 方法）为：

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

- [x] **Step 6: 重写 `_summarize` 方法签名与返回**

替换 `framework/agents/manager.py:229-267`（原 _summarize 方法）为：

```python
    def _summarize(
        self,
        question_type: int,
        agent_ids: List[str],
        results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """汇总各智能体结果为 API 响应结构。"""
        ordered_invoked = self._topological_sort(agent_ids)
        details = {aid: results[aid] for aid in ordered_invoked if aid in results}

        # 摘要：拼接各智能体的 answer
        answer_parts = [
            f"[{aid}] {results[aid].get('answer', '')}"
            for aid in ordered_invoked
            if aid in results
        ]
        summary = "\n".join(answer_parts) if answer_parts else "暂无可用结果"

        # 推荐建议：从各智能体的 evidence 中收集去重条目
        recommendations: List[str] = []
        seen = set()
        for aid in ordered_invoked:
            payload = results.get(aid, {})
            for ev in payload.get("evidence", []):
                if isinstance(ev, dict):
                    text = ev.get("recommendation") or ev.get("source")
                else:
                    text = str(ev)
                if text and text not in seen:
                    seen.add(text)
                    recommendations.append(text)

        return {
            "question_type": question_type,
            "agents_invoked": ordered_invoked,
            "summary": summary,
            "details": details,
            "recommendations": recommendations,
        }
```

- [x] **Step 7: Commit process/_summarize 重写**

```bash
git add framework/agents/manager.py
git commit -m "refactor: rewrite AgentManager.process to use question_type routing"
```

---

### Task 2.4: 删除 _should_execute_agent 方法及调用

**Files:**
- Modify: `framework/agents/manager.py:138-174` (_execute_with_dependencies 简化)
- Modify: `framework/agents/manager.py:197-204` (删除 _should_execute_agent 方法)

**Interfaces:**
- Consumes: 无
- Produces: `_execute_with_dependencies` 不再调用 `_should_execute_agent`，所有 agent 直接执行

- [x] **Step 1: 简化 `_execute_with_dependencies` 方法**

替换 `framework/agents/manager.py:138-174`（原 _execute_with_dependencies 方法）为：

```python
    def _execute_with_dependencies(
        self, agent_ids: List[str], question: str, context: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """按依赖关系顺序执行智能体，前序输出累积到 context。"""
        ordered = self._topological_sort(agent_ids)
        accumulated = dict(context)
        results: Dict[str, Dict[str, Any]] = {}

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

- [x] **Step 2: 删除 `_should_execute_agent` 方法**

删除 `framework/agents/manager.py:197-204`（即整个 `_should_execute_agent` 方法及其上方注释）。

- [x] **Step 3: Commit 删除**

```bash
git add framework/agents/manager.py
git commit -m "refactor: remove _should_execute_agent and FERTILITY/GRADE_KEYWORDS"
```

---

### Task 2.5: 验证 AgentManager 测试通过

**Files:**
- Verify: `tests/test_agent_manager.py`

- [x] **Step 1: 运行 AgentManager 全部测试**

Run: `python -m pytest tests/test_agent_manager.py -v`
Expected: Task 2.1/2.2 新增的 13 个测试全部 PASS；旧 role 相关测试（test_manager_process_farmer_returns_structured_result 等）此时可能仍 FAIL，将在任务组 5 修复

- [x] **Step 2: 单独验证新测试**

Run: `python -m pytest tests/test_agent_manager.py::test_process_type1_routes_to_model1_only tests/test_agent_manager.py::test_process_type5_routes_to_model7_only tests/test_agent_manager.py::test_process_no_routing_when_question_type_none tests/test_agent_manager.py::test_should_execute_agent_method_removed -v`
Expected: 4 passed

- [x] **Step 3: 验证 manager 模块无残留**

Run: `python -c "from framework.agents.manager import AgentManager, agent_manager; m = AgentManager(); assert not hasattr(m, '_should_execute_agent'); print('OK')"`
Expected: 输出 `OK`

---

## 任务组 3: nodes.py 透传 question_type

### Task 3.1: 修改 execute_models 透传 question_type 到 context

**Files:**
- Modify: `framework/agents/nodes.py:290-307` (execute_models 函数)

**Interfaces:**
- Consumes: `state["question_type"]`（由 identify_question_node 写入）
- Produces: `context["question_type"]` 传给 `agent_manager.process`

- [x] **Step 1: 修改 execute_models 函数中的 context 构造**

在 `framework/agents/nodes.py` 的 `execute_models` 函数中，将：
```python
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
```
改为：
```python
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
            "question_type": state.get("question_type"),
        }
```

- [x] **Step 2: Commit 透传改动**

```bash
git add framework/agents/nodes.py
git commit -m "feat: pass question_type from state to agent_manager context"
```

---

### Task 3.2: 更新 QUESTION_TYPE_TO_MODEL_ID 新增 type 5

**Files:**
- Modify: `framework/agents/nodes.py:283-288` (QUESTION_TYPE_TO_MODEL_ID 字典)

**Interfaces:**
- Consumes: 无
- Produces: `QUESTION_TYPE_TO_MODEL_ID[5] = "model-7"` 供 `_execute_models_fallback` 使用

- [x] **Step 1: 修改 QUESTION_TYPE_TO_MODEL_ID 字典**

将 `framework/agents/nodes.py:283-288` 由：
```python
QUESTION_TYPE_TO_MODEL_ID = {
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",
    4: "model-5,model-6",
}
```
改为：
```python
QUESTION_TYPE_TO_MODEL_ID = {
    1: "model-1",
    2: "model-4",
    3: "model-2,model-3",  # 保留原值（此字典用于 fallback，不影响 AgentManager 路由）
    4: "model-5,model-6",  # 保留原值
    5: "model-7",          # 新增：type 5 fallback 路径
}
```

- [x] **Step 2: Commit 字典更新**

```bash
git add framework/agents/nodes.py
git commit -m "feat: add type 5 mapping to QUESTION_TYPE_TO_MODEL_ID fallback dict"
```

---

### Task 3.3: 验证 execute_models 管道测试通过

**Files:**
- Modify: `tests/test_execute_models_pipeline.py:33-44` (更新 _stub_process_return 以匹配新结构)
- Verify: `tests/test_execute_models_pipeline.py`

- [x] **Step 1: 更新 `_stub_process_return` 桩返回值**

将 `tests/test_execute_models_pipeline.py:33-44` 由：
```python
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
```
改为：
```python
def _stub_process_return():
    """agent_manager.process 的桩返回值，符合 execute_models 期望的 {status: ok, data: {...}} 结构。"""
    return {
        "status": "ok",
        "data": {
            "question_type": 5,
            "agents_invoked": ["model-7"],
            "summary": "",
            "details": {},
            "recommendations": [],
        },
    }
```

- [x] **Step 2: 新增 question_type 透传断言**

在 `tests/test_execute_models_pipeline.py` 的 `test_execute_models_passes_parcel_id_and_parcel_code_to_context` 函数末尾（`print("✓ execute_models 透传 parcel_id/parcel_code 到 context top-level")` 之前）追加：

```python
    # question_type 应从 state 透传到 context
    assert ctx.get("question_type") == 1, f"question_type 未透传到 context: {ctx}"
```

- [x] **Step 3: 运行 execute_models 管道测试**

Run: `python -m pytest tests/test_execute_models_pipeline.py -v`
Expected: 3 passed

- [x] **Step 4: Commit 测试更新**

```bash
git add tests/test_execute_models_pipeline.py
git commit -m "test: update execute_models pipeline tests for question_type passthrough"
```

---

## 任务组 4: API 响应移除 role 字段

### Task 4.1: 修改 chat.py 删除 role 字段写入

**Files:**
- Modify: `framework/api/routes/chat.py:91` (删除 role 提取)
- Modify: `framework/api/routes/chat.py:112-113` (删除 role 写入块)

**Interfaces:**
- Consumes: `agent_data` 不再含 `role` 字段（Task 2.3 已将 _summarize 返回 `question_type` 替代 `role`）
- Produces: API 响应 `data` 中不再有 `role` 键

- [x] **Step 1: 删除 role 提取行**

在 `framework/api/routes/chat.py:91`，删除：
```python
    role = agent_data.get("role")
```

- [x] **Step 2: 删除 role 写入块**

在 `framework/api/routes/chat.py`，删除：
```python
    if role:
        response_data["role"] = role
```

修改后该段代码应为：
```python
    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
    }
    if agents_invoked:
        response_data["agents_invoked"] = agents_invoked
    if recommendations:
        response_data["recommendations"] = recommendations
```

- [x] **Step 3: Commit chat.py 改动**

```bash
git add framework/api/routes/chat.py
git commit -m "refactor: remove role field from chat API response"
```

---

### Task 4.2: 验证 API 响应不再包含 role 字段

**Files:**
- Verify: `framework/api/routes/chat.py`

- [x] **Step 1: 全局搜索 chat.py 中 role 残留**

Run: `findstr /N "role" d:\17417\Documents\agent_culti_demo\framework\api\routes\chat.py`
Expected: 仅在 `Message(conversation_id=..., role='user', ...)` 与 `role='assistant'` 与 `history = [{"role": m.role, ...}]` 中出现（这些是消息角色，不是用户角色，应保留）。不应出现 `agent_data.get("role")` 或 `response_data["role"]`。

- [x] **Step 2: 验证 _summarize 不再返回 role**

Run: `python -c "from framework.agents.manager import AgentManager; m = AgentManager(); r = m.process('我的田肥力怎么样', {'question_type': 4}); assert 'role' not in r['data']; assert 'question_type' in r['data']; print('OK')"`
Expected: 输出 `OK`

- [x] **Step 3: 验证响应字段完整**

Run: `python -c "from framework.agents.manager import AgentManager; m = AgentManager(); r = m.process('我的田耕地质量等级是多少', {'question_type': 5, 'parcel_code': 'A0001'}); d = r['data']; assert set(['question_type','agents_invoked','summary','details','recommendations']).issubset(d.keys()); assert 'role' not in d; print('OK')"`
Expected: 输出 `OK`

---

## 任务组 5: 测试套件更新

### Task 5.1: 重写 test_agent_manager.py 中 role 相关断言

**Files:**
- Modify: `tests/test_agent_manager.py:38-60` (test_manager_process_farmer_returns_structured_result 与 test_manager_process_unknown_question_defaults_farmer)

**Interfaces:**
- Consumes: Task 2.3 重写后的 `process` 返回 `data.question_type`
- Produces: 测试断言改为 `question_type` 字段

- [x] **Step 1: 重写 `test_manager_process_farmer_returns_structured_result`**

将 `tests/test_agent_manager.py:38-52` 由：
```python
def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施肥施多少", {"area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6", "model-7"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")
```
改为：
```python
def test_manager_process_type4_returns_structured_result():
    """process 返回符合 API 规范的结构化字典（type 4 → model-6）"""
    mgr = AgentManager()
    result = mgr.process("我的田施肥施多少", {"question_type": 4, "area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["question_type"] == 4
    assert data["agents_invoked"] == ["model-6"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")
```

- [x] **Step 2: 重写 `test_manager_process_unknown_question_defaults_farmer`**

将 `tests/test_agent_manager.py:55-60` 由：
```python
def test_manager_process_unknown_question_defaults_farmer():
    """无关键词问题默认路由到 farmer"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["data"]["role"] == "farmer"
    print("✓ 未知问题默认路由到 farmer")
```
改为：
```python
def test_manager_process_no_question_type_returns_no_routing():
    """无 question_type 的问题返回 no_routing（不再默认 farmer）"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["status"] == "no_routing"
    assert result["data"]["agents_invoked"] == []
    print("✓ 无 question_type 返回 no_routing")
```

- [x] **Step 3: Commit 测试重写**

```bash
git add tests/test_agent_manager.py
git commit -m "test: rewrite role-based assertions to question_type in test_agent_manager"
```

---

### Task 5.2: 移除已失效的测试

**Files:**
- Modify: `tests/test_agent_manager.py` (删除 7 个失效测试函数)

- [x] **Step 1: 删除以下测试函数**

从 `tests/test_agent_manager.py` 中删除以下 7 个函数（连同其文档字符串与函数体）：

1. `test_should_execute_model6_fertility_question`（约 63-70 行）
2. `test_should_skip_model6_non_fertility_question`（约 73-79 行）
3. `test_should_execute_model7_grade_question`（约 141-148 行）
4. `test_should_skip_model7_non_grade_question`（约 151-158 行）
5. `test_grade_keywords_mirrors_question_type_5`（约 161-169 行）
6. `test_model6_skipped_in_details_for_non_fertility`（约 110-119 行）
7. `test_model7_skipped_in_details_for_non_grade_farmer_question`（约 172-181 行）

- [x] **Step 2: 删除 `__main__` 块中对已删除函数的调用**

修改 `tests/test_agent_manager.py` 末尾的 `if __name__ == "__main__":` 块，移除对已删除函数的调用：

```python
if __name__ == "__main__":
    test_manager_register_seven_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_type4_returns_structured_result()
    test_manager_process_no_question_type_returns_no_routing()
    test_process_type1_routes_to_model1_only()
    test_process_type2_routes_to_model4_only()
    test_process_type3_routes_to_model3_only()
    test_process_type4_routes_to_model6_only()
    test_process_type5_routes_to_model7_only()
    test_process_no_routing_when_question_type_none()
    test_process_no_routing_when_question_type_zero()
    test_process_no_routing_when_question_type_unknown()
    test_no_skipped_entries_in_details_for_type4()
    test_no_skipped_entries_in_details_for_type5()
    test_should_execute_agent_method_removed()
    test_fertility_keywords_constant_removed()
    test_grade_keywords_constant_removed()
    test_farmer_role_includes_model_7()
    test_model7_executed_for_grade_farmer_question()
    print("\n所有 AgentManager 测试通过！")
```

注：`test_farmer_role_includes_model_7` 与 `test_model7_executed_for_grade_farmer_question` 将在 Task 5.3 重写。

- [x] **Step 3: Commit 测试清理**

```bash
git add tests/test_agent_manager.py
git commit -m "test: remove obsolete _should_execute_agent and role-based tests"
```

---

### Task 5.3: 重写 farmer role 测试并新增 type 1-5 集成测试

**Files:**
- Modify: `tests/test_agent_manager.py:131-138` (重写 test_farmer_role_includes_model_7)
- Modify: `tests/test_agent_manager.py:184-194` (重写 test_model7_executed_for_grade_farmer_question)
- Modify: `tests/test_multi_agent.py` (新增 type 5 → model-7 路由集成测试)

**Interfaces:**
- Consumes: `QuestionTypeRouter.TYPE_AGENTS`（来自 Task 1.2）
- Produces: 验证 type 1-5 各路由到单一 model；type 5 → model-7 端到端

- [x] **Step 1: 重写 `test_farmer_role_includes_model_7`**

将 `tests/test_agent_manager.py:131-138` 由：
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
改为：
```python
def test_type5_routes_to_model7():
    """type=5 应路由到 model-7（1:1 映射）"""
    from framework.agents.router import QuestionTypeRouter
    router = QuestionTypeRouter()
    agents = router.get_agents_for_type(5)
    assert agents == ["model-7"], f"type 5 应仅映射 model-7: {agents}"
    print("✓ type 5 路由到 model-7（1:1 映射）")
```

- [x] **Step 2: 重写 `test_model7_executed_for_grade_farmer_question`**

将 `tests/test_agent_manager.py:184-194` 由：
```python
def test_model7_executed_for_grade_farmer_question():
    """farmer 问质量等级问题 → details['model-7'] 不含 skipped 状态"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被跳过，实际: {m7}"
    # parcel_code 已传，model-7 应调 fortran exe（若部署就绪）或走 mock 回退
    assert "answer" in m7 or "simulated" in m7
    print("✓ 质量等级 farmer 问题 model-7 被执行")
```
改为：
```python
def test_model7_executed_for_type5_question():
    """type=5 问题 → details['model-7'] 被执行（不 skipped）"""
    mgr = AgentManager()
    result = mgr.process("我的田耕地质量等级是多少？", {"question_type": 5, "parcel_code": "A0001"})
    details = result["data"]["details"]
    m7 = details.get("model-7", {})
    assert m7.get("status") != "skipped", f"model-7 不应被跳过，实际: {m7}"
    # parcel_code 已传，model-7 应调 fortran exe（若部署就绪）或走 mock 回退
    assert "answer" in m7 or "simulated" in m7
    print("✓ type=5 质量等级问题 model-7 被执行")
```

- [x] **Step 3: 在 `tests/test_multi_agent.py` 新增 type 5 → model-7 端到端集成测试**

在 `tests/test_multi_agent.py` 末尾（`if __name__ == "__main__":` 之前）追加：

```python
def test_type5_routes_to_model7_end_to_end():
    """type=5 的问题通过 execute_models 路由后，agents_invoked 仅含 model-7"""
    from framework.agents.manager import agent_manager
    captured = {}

    def fake_process(question, context):
        captured["context"] = context
        # 真实调用以验证路由
        real = agent_manager.__class__.process(agent_manager, question, context)
        captured["real_result"] = real
        return real

    real_process = agent_manager.process
    agent_manager.process = fake_process
    try:
        state: MultiAgentState = {
            "request": {"question": "我的田耕地质量等级是多少", "area_code": "lechang", "parcel_code": "A0001"},
            "data": {},
            "model_results": {},
            "llm_response": {},
            "rag_response": {},
            "conversation_history": [],
            "status": "running",
            "error": None,
            "question_type": 5,
            "relevance": 0.9,
        }
        execute_models(state)
    finally:
        agent_manager.process = real_process

    # question_type 应已透传到 context
    assert captured["context"].get("question_type") == 5
    # agents_invoked 应仅含 model-7
    agents_invoked = captured["real_result"]["data"]["agents_invoked"]
    assert agents_invoked == ["model-7"], f"type 5 应仅调 model-7: {agents_invoked}"
    print("✓ type=5 端到端路由到 model-7")
```

同时在 `if __name__ == "__main__":` 块中追加 `test_type5_routes_to_model7_end_to_end()` 调用。

- [x] **Step 4: 运行测试套件验证**

Run: `python -m pytest tests/test_agent_manager.py tests/test_multi_agent.py -v`
Expected: All passed

- [x] **Step 5: Commit 测试新增**

```bash
git add tests/test_agent_manager.py tests/test_multi_agent.py
git commit -m "test: rewrite role tests to type-based and add type 5 e2e integration"
```

---

### Task 5.4: 运行完整测试套件确认无残留

**Files:**
- Verify: 全部 `tests/` 目录

- [x] **Step 1: 全局搜索源码与测试中的 role 残留**

Run: `findstr /S /N "ROLE_KEYWORDS\|ROLE_AGENTS\|identify_role\|get_agents_for_role\|FERTILITY_KEYWORDS\|GRADE_KEYWORDS\|_should_execute_agent" d:\17417\Documents\agent_culti_demo\framework d:\17417\Documents\agent_culti_demo\tests`
Expected: 无输出（除 `__pycache__` 中可能存在的旧 .pyc）

- [x] **Step 2: 运行完整测试套件**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 全部 PASS（已知不相关的基础设施测试如 test_auth、test_upload 可能因环境跳过，不在本次范围）

- [x] **Step 3: 验证 test_agent_manager.py 独立运行**

Run: `python tests/test_agent_manager.py`
Expected: 输出「所有 AgentManager 测试通过！」

- [x] **Step 4: 验证 test_multi_agent.py 独立运行**

Run: `python tests/test_multi_agent.py`
Expected: 输出「所有多智能体并发工作流测试通过！」

---

## 任务组 6: 端到端验证

### Task 6.1: 运行完整验证报告脚本

**Files:**
- Verify: `scripts/gen_full_verification_report.py`

- [x] **Step 1: 运行 23 个问题端到端验证脚本**

Run: `python scripts/gen_full_verification_report.py`
Expected: 23 个问题全部处理成功；type 5 的 Q21/Q22/Q23 仍返回真实 model-7 结果（非 skipped、非 error）

- [x] **Step 2: 检查报告中 type 5 问题的 agents_invoked**

打开生成的报告（默认在 `scripts/` 或 `reports/` 目录），确认 Q21/Q22/Q23 的 `agents_invoked` 仅含 `["model-7"]`，无 `model-4/5/6`。

- [x] **Step 3: 检查报告中无 role 字段**

确认所有 23 个问题的 API 响应中均无 `role` 字段，仅含 `question_type`、`agents_invoked`、`summary`、`recommendations`。

---

### Task 6.2: 验证 API 响应字段符合 spec

**Files:**
- Verify: `framework/api/routes/chat.py`、`framework/agents/manager.py`

- [x] **Step 1: 构造测试请求验证响应结构**

Run:
```bash
python -c "from framework.agents.manager import AgentManager; m = AgentManager(); r = m.process('我的田耕地质量等级是多少', {'question_type': 5, 'parcel_code': 'A0001'}); d = r['data']; keys = set(d.keys()); assert 'role' not in keys; assert 'question_type' in keys; assert 'agents_invoked' in keys; assert d['agents_invoked'] == ['model-7']; print('字段检查通过:', sorted(keys))"
```
Expected: 输出「字段检查通过: ['agents_invoked', 'details', 'question_type', 'recommendations', 'summary']」

- [x] **Step 2: 验证 chat.py 中 response_data 构造逻辑无 role**

Run: `findstr /N "response_data\[" d:\17417\Documents\agent_culti_demo\framework\api\routes\chat.py`
Expected: 仅出现 `response_data["agents_invoked"]` 与 `response_data["recommendations"]`，不出现 `response_data["role"]`

---

### Task 6.3: 新增知识性问题验证用例

**Files:**
- Verify: 依赖任务组 7 完成

**注：** 本任务依赖任务组 7（知识性问题检测）完成。若任务组 7 尚未完成，先执行任务组 7 再回到本任务。

- [x] **Step 1: 验证「什么是土壤酸化」走 RAG**

Run: `python -c "from framework.agents.nodes import identify_question_type; t, r = identify_question_type('什么是土壤酸化'); print(f'type={t}, relevance={r:.2f}'); assert t == 0, f'应返回 type 0（RAG），实际: {t}'"`
Expected: 输出 `type=0, relevance=1.00`

- [x] **Step 2: 验证「耕地质量等级是什么意思」走 RAG**

Run: `python -c "from framework.agents.nodes import identify_question_type; t, r = identify_question_type('耕地质量等级是什么意思'); print(f'type={t}, relevance={r:.2f}'); assert t == 0, f'应返回 type 0（RAG），实际: {t}'"`
Expected: 输出 `type=0, relevance=1.00`

- [x] **Step 3: 验证「我的田耕地质量等级是多少」仍走 type 5**

Run: `python -c "from framework.agents.nodes import identify_question_type; t, r = identify_question_type('我的田耕地质量等级是多少'); print(f'type={t}, relevance={r:.2f}'); assert t == 5, f'应返回 type 5，实际: {t}'"`
Expected: 输出 `type=5, relevance=...`（relevance 值取决于关键词匹配，需 >= 0.3）

---

## 任务组 7: 知识性问题检测（TDD）

### Task 7.1: 编写 _is_knowledge_question 失败测试

**Files:**
- Create: `tests/test_knowledge_question.py`

**Interfaces:**
- Produces: `_is_knowledge_question(question: str) -> bool`（待 Task 7.2 实现）、常量 `KNOWLEDGE_QUESTION_PATTERNS_START`、`KNOWLEDGE_QUESTION_PATTERNS_CONTAIN`

- [x] **Step 1: 创建测试文件 `tests/test_knowledge_question.py`**

```python
"""测试知识性问题预检（_is_knowledge_question）"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.nodes import _is_knowledge_question


def test_knowledge_question_start_pattern_什么是():
    """「什么是X」开头 → True"""
    assert _is_knowledge_question("什么是土壤酸化") is True
    assert _is_knowledge_question("什么是耕地质量等级") is True
    print("✓ 「什么是X」识别为知识性问题")


def test_knowledge_question_start_pattern_何为():
    """「何为X」开头 → True"""
    assert _is_knowledge_question("何为土壤酸化") is True
    assert _is_knowledge_question("何为有机质") is True
    print("✓ 「何为X」识别为知识性问题")


def test_knowledge_question_start_pattern_解释():
    """「解释X」开头 → True"""
    assert _is_knowledge_question("解释耕地质量等级") is True
    assert _is_knowledge_question("解释土壤酸化过程") is True
    print("✓ 「解释X」识别为知识性问题")


def test_knowledge_question_contain_pattern_是什么意思():
    """「X是什么意思」包含 → True"""
    assert _is_knowledge_question("耕地质量等级是什么意思") is True
    assert _is_knowledge_question("土壤酸化是什么意思") is True
    print("✓ 「X是什么意思」识别为知识性问题")


def test_knowledge_question_contain_pattern_什么意思():
    """「X什么意思」包含 → True"""
    assert _is_knowledge_question("耕地质量等级什么意思") is True
    print("✓ 「X什么意思」识别为知识性问题")


def test_knowledge_question_contain_pattern_定义():
    """「X定义」包含 → True"""
    assert _is_knowledge_question("土壤酸化的定义") is True
    assert _is_knowledge_question("有机质定义是什么") is True
    print("✓ 「X定义」识别为知识性问题")


def test_knowledge_question_contain_pattern_概念():
    """「X概念」包含 → True"""
    assert _is_knowledge_question("耕地质量等级概念") is True
    print("✓ 「X概念」识别为知识性问题")


def test_knowledge_question_contain_pattern_含义():
    """「X含义」包含 → True"""
    assert _is_knowledge_question("土壤酸化的含义") is True
    print("✓ 「X含义」识别为知识性问题")


def test_specific_question_not_knowledge_我的田():
    """「我的田X」具体诊断问题 → False"""
    assert _is_knowledge_question("我的田耕地质量等级是多少") is False
    assert _is_knowledge_question("我的田酸化严重吗") is False
    assert _is_knowledge_question("我的田肥力怎么样") is False
    print("✓ 「我的田X」具体问题不识别为知识性问题")


def test_specific_question_not_knowledge_查询区域():
    """「查询区域内X」具体问题 → False"""
    assert _is_knowledge_question("查询区域内耕地质量等级整体稳定吗") is False
    assert _is_knowledge_question("查询区域内农用地土壤酸化程度如何") is False
    print("✓ 「查询区域内X」具体问题不识别为知识性问题")


def test_specific_question_not_knowledge_为什么():
    """「为什么X」歧义问题 → False（保守策略，不识别为知识性问题）"""
    assert _is_knowledge_question("为什么我的田酸化") is False
    print("✓ 「为什么X」不识别为知识性问题（保守策略）")


def test_specific_question_not_knowledge_区别():
    """「X区别」歧义问题 → False"""
    assert _is_knowledge_question("酸化和盐碱化的区别") is False
    print("✓ 「X区别」不识别为知识性问题（保守策略）")


def test_empty_question_returns_false():
    """空字符串或 None → False"""
    assert _is_knowledge_question("") is False
    assert _is_knowledge_question(None) is False
    assert _is_knowledge_question("   ") is False
    print("✓ 空问题返回 False")


if __name__ == "__main__":
    test_knowledge_question_start_pattern_什么是()
    test_knowledge_question_start_pattern_何为()
    test_knowledge_question_start_pattern_解释()
    test_knowledge_question_contain_pattern_是什么意思()
    test_knowledge_question_contain_pattern_什么意思()
    test_knowledge_question_contain_pattern_定义()
    test_knowledge_question_contain_pattern_概念()
    test_knowledge_question_contain_pattern_含义()
    test_specific_question_not_knowledge_我的田()
    test_specific_question_not_knowledge_查询区域()
    test_specific_question_not_knowledge_为什么()
    test_specific_question_not_knowledge_区别()
    test_empty_question_returns_false()
    print("\n所有 _is_knowledge_question 测试通过！")
```

- [x] **Step 2: 运行测试验证失败**

Run: `python tests/test_knowledge_question.py`
Expected: FAIL with `ImportError: cannot import name '_is_knowledge_question'`

- [x] **Step 3: Commit 失败测试**

```bash
git add tests/test_knowledge_question.py
git commit -m "test: add failing tests for _is_knowledge_question pre-check"
```

---

### Task 7.2: 新增知识性预检常量与 _is_knowledge_question 函数

**Files:**
- Modify: `framework/agents/nodes.py:31` (在 QUESTION_TYPE_1_KEYWORDS 之前插入常量)
- Modify: `framework/agents/nodes.py` (在 identify_question_type 之前插入 _is_knowledge_question 函数)

**Interfaces:**
- Consumes: 无
- Produces: `KNOWLEDGE_QUESTION_PATTERNS_START: List[str]`、`KNOWLEDGE_QUESTION_PATTERNS_CONTAIN: List[str]`、`_is_knowledge_question(question: str) -> bool`

- [x] **Step 1: 在 `framework/agents/nodes.py` 顶部（QUESTION_TYPE_1_KEYWORDS 之前，约第 31 行前）新增常量**

在 `QUESTION_TYPE_1_KEYWORDS = [...]` 之前插入：

```python
# 知识性问题预检模式：命中即走 RAG（type 0），避免概念解释类问题误路由到专业模型
KNOWLEDGE_QUESTION_PATTERNS_START = ["什么是", "何为", "解释"]
KNOWLEDGE_QUESTION_PATTERNS_CONTAIN = ["是什么意思", "什么意思", "定义", "概念", "含义"]

```

- [x] **Step 2: 在 `identify_question_type` 函数之前新增 `_is_knowledge_question` 函数**

在 `framework/agents/nodes.py` 的 `def identify_question_type(question: str) -> tuple[int, float]:` 行之前插入：

```python
def _is_knowledge_question(question: str) -> bool:
    """检测是否为知识性问题（概念解释、定义等），应走 RAG。

    保守匹配策略：
    - 开头匹配「什么是」「何为」「解释」：强知识信号，误报率极低
    - 包含匹配「是什么意思」「什么意思」「定义」「概念」「含义」：明确的概念询问
    - 不匹配「为什么」「区别」「差异」：歧义性高，可能是具体问题
    """
    if not question:
        return False
    q = question.strip()
    if any(q.startswith(p) for p in KNOWLEDGE_QUESTION_PATTERNS_START):
        return True
    if any(p in q for p in KNOWLEDGE_QUESTION_PATTERNS_CONTAIN):
        return True
    return False


```

- [x] **Step 3: 运行 _is_knowledge_question 单元测试**

Run: `python tests/test_knowledge_question.py`
Expected: 13 个测试全部 PASS，输出「所有 _is_knowledge_question 测试通过！」

- [x] **Step 4: Commit 函数实现**

```bash
git add framework/agents/nodes.py
git commit -m "feat: add _is_knowledge_question pre-check function"
```

---

### Task 7.3: 修改 identify_question_type 调用知识性预检

**Files:**
- Modify: `framework/agents/nodes.py:161-170` (identify_question_type 函数)

**Interfaces:**
- Consumes: `_is_knowledge_question`（来自 Task 7.2）
- Produces: `identify_question_type` 对知识性问题返回 `(0, 1.0)`

- [x] **Step 1: 修改 `identify_question_type` 函数**

将 `framework/agents/nodes.py:161-170` 由：
```python
def identify_question_type(question: str) -> tuple[int, float]:
    # D5: 关键词匹配优先于向量匹配——先查关键词，命中（返回非 0）即采用，
    # 即使向量匹配的相关性分数较高也不覆盖关键词结果
    result = _identify_question_type_keyword(question)
    if result[0] != 0:
        return result
    # 关键词未命中，降级到向量匹配（embedding 可用时）
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    return result
```
改为：
```python
def identify_question_type(question: str) -> tuple[int, float]:
    # 1. 知识性问题预检 → type 0 (RAG)：概念解释类问题直接走 RAG，避免误路由到专业模型
    if _is_knowledge_question(question):
        return 0, 1.0
    # 2. D5: 关键词匹配优先于向量匹配——先查关键词，命中（返回非 0）即采用，
    # 即使向量匹配的相关性分数较高也不覆盖关键词结果
    result = _identify_question_type_keyword(question)
    if result[0] != 0:
        return result
    # 3. 关键词未命中，降级到向量匹配（embedding 可用时）
    if EMBEDDING_AVAILABLE and embedding_service.is_available():
        return _identify_question_type_vector(question)
    return result
```

- [x] **Step 2: Commit 改动**

```bash
git add framework/agents/nodes.py
git commit -m "feat: integrate _is_knowledge_question pre-check into identify_question_type"
```

---

### Task 7.4: 编写 identify_question_type 集成测试

**Files:**
- Modify: `tests/test_knowledge_question.py` (追加集成测试)

**Interfaces:**
- Consumes: `identify_question_type`（已集成知识性预检）、`_is_knowledge_question`
- Produces: 验证「什么是X」「X是什么意思」返回 type 0；「我的田X」仍返回原 type

- [x] **Step 1: 在 `tests/test_knowledge_question.py` 末尾追加集成测试**

在文件末尾（`if __name__ == "__main__":` 之前）追加：

```python
def test_identify_question_type_knowledge_什么是_土壤酸化():
    """「什么是土壤酸化」应返回 type 0（而非 type 2 酸化）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("什么是土壤酸化")
    assert q_type == 0, f"「什么是土壤酸化」应返回 type 0，实际: type={q_type}"
    assert relevance == 1.0
    print(f"✓ 「什么是土壤酸化」→ type={q_type} (RAG)")


def test_identify_question_type_knowledge_什么是_耕地质量等级():
    """「什么是耕地质量等级」应返回 type 0（而非 type 5 等级评价）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("什么是耕地质量等级")
    assert q_type == 0, f"「什么是耕地质量等级」应返回 type 0，实际: type={q_type}"
    print(f"✓ 「什么是耕地质量等级」→ type={q_type} (RAG)")


def test_identify_question_type_knowledge_是什么意思_耕地质量等级():
    """「耕地质量等级是什么意思」应返回 type 0（而非 type 5）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("耕地质量等级是什么意思")
    assert q_type == 0, f"「耕地质量等级是什么意思」应返回 type 0，实际: type={q_type}"
    print(f"✓ 「耕地质量等级是什么意思」→ type={q_type} (RAG)")


def test_identify_question_type_knowledge_定义_有机质():
    """「有机质的定义」应返回 type 0（而非 type 4 肥力）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("有机质的定义")
    assert q_type == 0, f"「有机质的定义」应返回 type 0，实际: type={q_type}"
    print(f"✓ 「有机质的定义」→ type={q_type} (RAG)")


def test_identify_question_type_specific_我的田_质量等级_仍_type5():
    """「我的田耕地质量等级是多少」仍应返回 type 5（具体诊断问题不被误判）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("我的田耕地质量等级是多少")
    assert q_type == 5, f"「我的田耕地质量等级是多少」应返回 type 5，实际: type={q_type}"
    print(f"✓ 「我的田耕地质量等级是多少」→ type={q_type} (model-7)")


def test_identify_question_type_specific_我的田_酸化_仍_type2():
    """「我的田酸化严重吗」仍应返回 type 2（具体诊断问题不被误判）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("我的田酸化严重吗")
    assert q_type == 2, f"「我的田酸化严重吗」应返回 type 2，实际: type={q_type}"
    print(f"✓ 「我的田酸化严重吗」→ type={q_type} (model-4)")


def test_identify_question_type_specific_我的田_肥力_仍_type4():
    """「我的田肥力怎么样」仍应返回 type 4（具体诊断问题不被误判）"""
    from framework.agents.nodes import identify_question_type
    q_type, relevance = identify_question_type("我的田肥力怎么样")
    assert q_type == 4, f"「我的田肥力怎么样」应返回 type 4，实际: type={q_type}"
    print(f"✓ 「我的田肥力怎么样」→ type={q_type} (model-6)")
```

- [x] **Step 2: 在 `__main__` 块中追加新测试调用**

修改 `tests/test_knowledge_question.py` 末尾的 `if __name__ == "__main__":` 块，在 `print("\n所有 _is_knowledge_question 测试通过！")` 之前追加：

```python
    # 集成测试
    test_identify_question_type_knowledge_什么是_土壤酸化()
    test_identify_question_type_knowledge_什么是_耕地质量等级()
    test_identify_question_type_knowledge_是什么意思_耕地质量等级()
    test_identify_question_type_knowledge_定义_有机质()
    test_identify_question_type_specific_我的田_质量等级_仍_type5()
    test_identify_question_type_specific_我的田_酸化_仍_type2()
    test_identify_question_type_specific_我的田_肥力_仍_type4()
```

并将最后的 print 改为：
```python
    print("\n所有知识性问题检测测试通过！")
```

- [x] **Step 3: 运行集成测试**

Run: `python tests/test_knowledge_question.py`
Expected: 全部 PASS（13 单元 + 7 集成 = 20 测试），输出「所有知识性问题检测测试通过！」

- [x] **Step 4: Commit 集成测试**

```bash
git add tests/test_knowledge_question.py
git commit -m "test: add identify_question_type integration tests for knowledge questions"
```

---

### Task 7.5: 验证知识性检测不影响现有 type 1-5 路由测试

**Files:**
- Verify: `tests/test_question_type_keywords.py`、`tests/test_multi_agent.py`、`tests/test_knowledge_question.py`

- [x] **Step 1: 运行关键词路由测试套件**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 PASS（知识性预检不应影响现有 type 1-5 关键词匹配）

- [x] **Step 2: 运行多智能体工作流测试**

Run: `python -m pytest tests/test_multi_agent.py -v`
Expected: 全部 PASS

- [x] **Step 3: 运行知识性问题检测全量测试**

Run: `python -m pytest tests/test_knowledge_question.py -v`
Expected: 20 passed

- [x] **Step 4: 运行回归——确认 23 个端到端问题结果不变**

Run: `python scripts/gen_full_verification_report.py`
Expected: 23 个问题全部处理成功；type 1-5 的问题路由到对应单一模型；知识性问题（如有）走 RAG

- [x] **Step 5: 执行任务组 6 的 Task 6.3 知识性问题验证**

回到 Task 6.3 执行 Step 1-3，确认「什么是土壤酸化」「耕地质量等级是什么意思」走 RAG，「我的田耕地质量等级是多少」仍走 type 5。

---

## Self-Review Checklist

实施完成后，按以下清单自检：

- [x] **Spec 覆盖**：设计文档第 3 节 3.1-3.8 全部实现
  - 3.1 QuestionTypeRouter（Task 1.1-1.3）✓
  - 3.2 AgentManager.process 重构（Task 2.1-2.5）✓
  - 3.3 _execute_with_dependencies 简化（Task 2.4）✓
  - 3.4 _summarize 签名变更（Task 2.3）✓
  - 3.5 model-3 依赖清理（Task 2.3 Step 4）✓
  - 3.6 知识性问题预检（Task 7.1-7.5）✓
  - 3.7 execute_models 透传（Task 3.1-3.3）✓
  - 3.8 chat.py 改动（Task 4.1-4.2）✓
- [x] **无占位符**：所有代码块完整，无 TODO/TBD
- [x] **类型一致**：`get_agents_for_type(question_type: int) -> List[str]` 在所有任务中签名一致
- [x] **测试覆盖**：第 4 节边界条件表 7 个场景均有测试覆盖
- [x] **23 个端到端问题回答不变**（Task 6.1）

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-26-refactor-routing-to-question-type.md`. Two execution options:

**1. Subagent-Driven (recommended)** - 每个 Task 派发独立 subagent，Task 间两阶段评审，快速迭代

**2. Inline Execution** - 在当前会话使用 executing-plans 批量执行，带检查点评审

选择哪种方式？
