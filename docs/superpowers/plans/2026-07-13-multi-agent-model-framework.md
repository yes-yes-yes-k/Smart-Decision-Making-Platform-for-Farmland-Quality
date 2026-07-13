---
change: multi-agent-model-framework
design-doc: docs/superpowers/specs/2026-07-13-multi-agent-model-framework-design.md
base-ref: 71b01a7a57692941710d6edfb2167ed78b101f98
archived-with: 2026-07-13-multi-agent-model-framework
---

# 多智能体专业模型框架实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 LangGraph 编排器中引入 AgentManager 中心化编排器与 6 个专业智能体（BaseAgent 抽象基类 + 模拟数据层），通过角色路由将用户问题分发到对应智能体组合，并通过 `/api/v1/chat/` 接口返回结构化多智能体协作结果。

**Architecture:** 采用方案 A —— AgentManager 作为独立模块在 `execute_models` 节点中被调用，不替换现有 LangGraph 图结构。每个专业智能体内置模拟数据与阈值规则，所有输出携带 `simulated: True` 标记。Manager 负责注册、依赖拓扑排序、按序执行与结果汇总。

**Tech Stack:** Python 3.10+，Flask 3.x，LangGraph 0.1.x，LangChain 0.2.x；无新增依赖，沿用现有 `pyproject.toml`。

## Global Constraints

- 所有智能体输出 SHALL 包含 `simulated: True` 标记，明确标注为模拟数据。
- 所有智能体 SHALL 实现 `BaseAgent` 抽象基类的 `execute(task)` 和 `answer_question(question, context)` 两个方法。
- `execute` 返回字典结构：`{"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}`。
- `answer_question` 返回字典结构：`{"answer": str, "evidence": list, "confidence": float, "simulated": True}`。
- 智能体注册键为 `model-1` 至 `model-6`，按设计文档第 4 节定义。
- 角色路由关键词与智能体组合严格遵循设计文档第 5 节定义，默认角色为 `farmer`。
- 不引入新的第三方依赖；测试沿用 `tests/` 目录中现有的"脚本式测试"风格（`assert` + `print` + `if __name__ == "__main__":`）。
- 测试运行命令为 `python tests/<file>.py`（项目未配置 pytest）。
- 不修改现有 `framework/domain/` 下的占位模型实现，仅在其之上新增 `framework/agents/specialized/` 层。

## 文件结构

**新建文件：**

- `framework/agents/base.py` — `BaseAgent` 抽象基类，定义统一接口与公共属性。
- `framework/agents/mock_data.py` — `MockDataLoader` 工具类，提供默认值合并、阈值匹配、`simulated` 标记辅助函数。
- `framework/agents/router.py` — `RoleRouter` 角色路由器，关键词匹配 + 智能体组合映射。
- `framework/agents/manager.py` — `AgentManager` 中心化编排器，包含注册、拓扑排序、按序执行、汇总逻辑，模块级导出单例 `agent_manager`。
- `framework/agents/specialized/__init__.py` — 子包初始化，导出 6 个智能体类。
- `framework/agents/specialized/stability_risk_agent.py` — 模型1 `StabilityRiskAgent`。
- `framework/agents/specialized/potential_agent.py` — 模型2 `PotentialAssessmentAgent`。
- `framework/agents/specialized/problem_agent.py` — 模型3 `ProblemIdentificationAgent`。
- `framework/agents/specialized/acidification_agent.py` — 模型4 `AcidificationRemediationAgent`。
- `framework/agents/specialized/organic_matter_agent.py` — 模型5 `OrganicMatterAgent`。
- `framework/agents/specialized/comprehensive_agent.py` — 模型6 `ComprehensiveImprovementAgent`。
- `tests/test_agent_base.py` — `BaseAgent`、`MockDataLoader`、`RoleRouter` 单元测试。
- `tests/test_agent_manager.py` — `AgentManager` 注册、拓扑排序、汇总逻辑测试。
- `tests/test_agent_specialized.py` — 6 个专业智能体的功能测试。
- `tests/test_agent_integration.py` — 多智能体协同 + API 集成端到端测试。

**修改文件：**

- `framework/agents/__init__.py` — 导出 `agent_manager`、`BaseAgent`、`RoleRouter`。
- `framework/agents/nodes.py` — `execute_models` 函数优先调用 `agent_manager.process`，保留原 `_execute_models_fallback` 作为兜底。
- `framework/api/routes/chat.py` — `chat()` 端点解析 Manager 返回的结构化字段，合并到响应 JSON 中。

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 1: BaseAgent 抽象基类与 MockDataLoader 工具

**Files:**
- Create: `framework/agents/base.py`
- Create: `framework/agents/mock_data.py`
- Test: `tests/test_agent_base.py`

**Interfaces:**
- Produces: `BaseAgent`（抽象基类，子类必须实现 `execute(task: dict) -> dict` 与 `answer_question(question: str, context: dict) -> dict`；构造参数 `name, description, model_id, domain`；属性 `dependencies: list[str]`）。
- Produces: `MockDataLoader.merge_defaults(input_data, defaults) -> dict`、`MockDataLoader.mark_simulated(payload: dict) -> dict`、`MockDataLoader.apply_threshold(value, rules) -> str`。

- [x] **Step 1: 编写失败测试**

写入 `tests/test_agent_base.py`：

```python
"""测试 BaseAgent 抽象基类与 MockDataLoader 工具"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.base import BaseAgent
from framework.agents.mock_data import MockDataLoader


def test_baseagent_cannot_instantiate():
    """BaseAgent 是抽象类，不能直接实例化"""
    try:
        BaseAgent("x", "y", "model-0", "test")
        raise AssertionError("应抛出 TypeError")
    except TypeError:
        pass
    print("✓ BaseAgent 抽象类阻止直接实例化")


def test_baseagent_subclass_must_implement_methods():
    """子类必须实现 execute 和 answer_question"""

    class IncompleteAgent(BaseAgent):
        def execute(self, task):
            return {"status": "ok", "result": {}, "metadata": {"simulated": True}}

    try:
        IncompleteAgent("x", "y", "model-0", "test")
        raise AssertionError("应抛出 TypeError 因 answer_question 未实现")
    except TypeError:
        pass
    print("✓ 子类未实现全部抽象方法时抛出 TypeError")


def test_baseagent_complete_subclass():
    """完整子类可正常构造并访问属性"""

    class DummyAgent(BaseAgent):
        def execute(self, task):
            return {"status": "ok", "result": task, "metadata": {"simulated": True}}

        def answer_question(self, question, context):
            return {"answer": "ok", "evidence": [], "confidence": 0.5, "simulated": True}

    agent = DummyAgent("dummy", "测试", "model-0", "test")
    assert agent.name == "dummy"
    assert agent.description == "测试"
    assert agent.model_id == "model-0"
    assert agent.domain == "test"
    assert agent.dependencies == []
    ex = agent.execute({"foo": 1})
    assert ex["status"] == "ok"
    assert ex["metadata"]["simulated"] is True
    aq = agent.answer_question("问题", {})
    assert aq["simulated"] is True
    print("✓ BaseAgent 完整子类构造与方法调用正常")


def test_mock_data_merge_defaults():
    defaults = {"ph": 5.5, "cec": 8.5}
    merged = MockDataLoader.merge_defaults({"ph": 4.2}, defaults)
    assert merged["ph"] == 4.2
    assert merged["cec"] == 8.5
    print("✓ MockDataLoader.merge_defaults 优先使用输入值")


def test_mock_data_mark_simulated():
    payload = {"answer": "x"}
    out = MockDataLoader.mark_simulated(payload)
    assert out["simulated"] is True
    assert out["answer"] == "x"
    # 不应修改原对象
    assert "simulated" not in payload
    print("✓ MockDataLoader.mark_simulated 添加标记且不污染原对象")


def test_mock_data_apply_threshold():
    rules = [
        (lambda v: v < 4.5, "强酸性"),
        (lambda v: 4.5 <= v < 5.5, "酸性"),
        (lambda v: 5.5 <= v < 6.5, "弱酸性"),
        (lambda v: v >= 6.5, "正常"),
    ]
    assert MockDataLoader.apply_threshold(4.2, rules) == "强酸性"
    assert MockDataLoader.apply_threshold(5.0, rules) == "酸性"
    assert MockDataLoader.apply_threshold(6.0, rules) == "弱酸性"
    assert MockDataLoader.apply_threshold(7.0, rules) == "正常"
    print("✓ MockDataLoader.apply_threshold 按顺序匹配规则")


if __name__ == "__main__":
    test_baseagent_cannot_instantiate()
    test_baseagent_subclass_must_implement_methods()
    test_baseagent_complete_subclass()
    test_mock_data_merge_defaults()
    test_mock_data_mark_simulated()
    test_mock_data_apply_threshold()
    print("\n所有 BaseAgent 与 MockDataLoader 测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_base.py`
Expected: FAIL，提示 `No module named 'framework.agents.base'`

- [x] **Step 3: 实现 BaseAgent**

写入 `framework/agents/base.py`：

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAgent(ABC):
    """智能体抽象基类，定义统一接口。"""

    def __init__(self, name: str, description: str, model_id: str, domain: str):
        self.name = name
        self.description = description
        self.model_id = model_id
        self.domain = domain
        self.dependencies: List[str] = []

    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行模拟计算。
        返回: {"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}
        """

    @abstractmethod
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """回答用户问题。
        返回: {"answer": "...", "evidence": [...], "confidence": 0.8, "simulated": True}
        """
```

- [x] **Step 4: 实现 MockDataLoader**

写入 `framework/agents/mock_data.py`：

```python
from __future__ import annotations
from typing import Any, Callable, Dict, List, Tuple


class MockDataLoader:
    """模拟数据加载与阈值规则计算工具。"""

    @staticmethod
    def merge_defaults(input_data: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
        """合并用户输入与默认值，用户输入优先。"""
        merged = dict(defaults)
        merged.update(input_data or {})
        return merged

    @staticmethod
    def mark_simulated(payload: Dict[str, Any]) -> Dict[str, Any]:
        """返回 payload 的副本并添加 simulated: True 标记。"""
        out = dict(payload)
        out["simulated"] = True
        return out

    @staticmethod
    def apply_threshold(value: float, rules: List[Tuple[Callable[[float], bool], str]]) -> str:
        """按顺序匹配阈值规则，返回首个满足条件的标签。
        rules: [(predicate, label), ...]
        """
        for predicate, label in rules:
            try:
                if predicate(value):
                    return label
            except Exception:
                continue
        return "未知"
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_base.py`
Expected: PASS，输出 `所有 BaseAgent 与 MockDataLoader 测试通过！`

- [x] **Step 6: Commit**

```bash
git add framework/agents/base.py framework/agents/mock_data.py tests/test_agent_base.py
git commit -m "feat(agents): 添加 BaseAgent 抽象基类与 MockDataLoader 工具"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 2: RoleRouter 角色路由器

**Files:**
- Create: `framework/agents/router.py`
- Test: `tests/test_agent_base.py`（追加路由测试函数）

**Interfaces:**
- Produces: `RoleRouter` 类，方法 `identify_role(question: str) -> str`（返回 `"province"|"county"|"farmer"`）、`get_agents_for_role(role: str) -> list[str]`（返回模型 ID 列表）。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_base.py` 末尾的 `if __name__ == "__main__":` 之前追加：

```python
def test_router_identify_role_province():
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    assert router.identify_role("全省耕地酸化程度如何") == "province"
    assert router.identify_role("全市政策建议") == "province"
    print("✓ RoleRouter 识别省市角色")


def test_router_identify_role_county():
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    assert router.identify_role("本县乡镇任务如何分配") == "county"
    assert router.identify_role("片区县域情况") == "county"
    print("✓ RoleRouter 识别县域角色")


def test_router_identify_role_farmer_default():
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    assert router.identify_role("我的田施氮肥施多少") == "farmer"
    assert router.identify_role("这块地质量怎么样") == "farmer"
    # 无关键词时默认 farmer
    assert router.identify_role("你好") == "farmer"
    print("✓ RoleRouter 识别农户角色与默认值")


def test_router_get_agents_for_role():
    from framework.agents.router import RoleRouter
    router = RoleRouter()
    assert router.get_agents_for_role("province") == ["model-1", "model-3"]
    assert router.get_agents_for_role("county") == ["model-1", "model-3", "model-2"]
    assert router.get_agents_for_role("farmer") == ["model-4", "model-5", "model-6"]
    print("✓ RoleRouter 返回正确的智能体组合")
```

并在 `if __name__ == "__main__":` 块中追加调用：

```python
    test_router_identify_role_province()
    test_router_identify_role_county()
    test_router_identify_role_farmer_default()
    test_router_get_agents_for_role()
```

并更新最后一行打印为：

```python
    print("\n所有 BaseAgent、MockDataLoader、RoleRouter 测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_base.py`
Expected: FAIL，提示 `No module named 'framework.agents.router'`

- [x] **Step 3: 实现 RoleRouter**

写入 `framework/agents/router.py`：

```python
from __future__ import annotations
from typing import Dict, List


class RoleRouter:
    """用户角色路由器，基于关键词匹配识别角色并返回对应智能体组合。"""

    ROLE_KEYWORDS: Dict[str, List[str]] = {
        "province": ["全省", "全市", "全局", "政策", "省市"],
        "county": ["本县", "乡镇", "片区", "任务", "县域"],
        "farmer": ["我的田", "这块地", "施氮肥", "施多少", "农户"],
    }

    ROLE_AGENTS: Dict[str, List[str]] = {
        "province": ["model-1", "model-3"],
        "county": ["model-1", "model-3", "model-2"],
        "farmer": ["model-4", "model-5", "model-6"],
    }

    def identify_role(self, question: str) -> str:
        """基于关键词匹配识别用户角色。无匹配时默认返回 'farmer'。"""
        if not question:
            return "farmer"
        for role, keywords in self.ROLE_KEYWORDS.items():
            if any(kw in question for kw in keywords):
                return role
        return "farmer"

    def get_agents_for_role(self, role: str) -> List[str]:
        """返回该角色对应的智能体 ID 列表。未知角色回退到 farmer。"""
        return list(self.ROLE_AGENTS.get(role, self.ROLE_AGENTS["farmer"]))
```

- [x] **Step 4: 运行测试确认通过**

Run: `python tests/test_agent_base.py`
Expected: PASS，输出 `所有 BaseAgent、MockDataLoader、RoleRouter 测试通过！`

- [x] **Step 5: Commit**

```bash
git add framework/agents/router.py tests/test_agent_base.py
git commit -m "feat(agents): 添加 RoleRouter 角色路由器"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 3: AgentManager 中心化编排器

**Files:**
- Create: `framework/agents/manager.py`
- Create: `tests/test_agent_manager.py`

**Interfaces:**
- Consumes: `BaseAgent`（Task 1）、`RoleRouter`（Task 2）。
- Produces: `AgentManager` 类，方法 `process(question: str, context: dict) -> dict`（返回 `{"status": "ok", "data": {"role", "agents_invoked", "summary", "details", "recommendations"}}`），模块级单例 `agent_manager`。
- 内部方法：`_register_agents()`、`_execute_with_dependencies(agent_ids, question, context) -> dict`、`_topological_sort(agent_ids) -> list[str]`、`_summarize(role, agent_ids, results) -> dict`。

**说明：** 此 Task 在 6 个专业智能体未实现前，使用桩智能体（`_StubAgent`）占位以确保 Manager 单元测试可独立通过；Task 4-9 完成后由真实智能体替换。`_register_agents` 中先用 `try/except ImportError` 回退到桩。

- [x] **Step 1: 编写失败测试**

写入 `tests/test_agent_manager.py`：

```python
"""测试 AgentManager 中心化编排器"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.manager import AgentManager


def test_manager_register_six_agents():
    """Manager 注册 6 个智能体"""
    mgr = AgentManager()
    assert set(mgr.agents.keys()) == {
        "model-1", "model-2", "model-3",
        "model-4", "model-5", "model-6",
    }
    print("✓ AgentManager 注册 6 个智能体")


def test_manager_topological_sort_province():
    """province 角色 [model-1, model-3]，model-3 依赖 model-2 但 model-2 不在集合内，
    因此仅按现有依赖排序，输出顺序保留两个智能体。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-1", "model-3"])
    assert set(ordered) == {"model-1", "model-3"}
    print("✓ 拓扑排序处理部分依赖（依赖不在集合内时安全跳过）")


def test_manager_topological_sort_farmer():
    """farmer 角色 [model-4, model-5, model-6]，model-6 依赖 model-4 和 model-5，
    因此 model-6 应排在最后。"""
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert ordered[-1] == "model-6"
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    print("✓ 拓扑排序将依赖项放在被依赖项之后")


def test_manager_process_farmer_returns_structured_result():
    """process 返回符合 API 规范的结构化字典"""
    mgr = AgentManager()
    result = mgr.process("我的田施氮肥施多少", {"area_code": "lechang"})
    assert result["status"] == "ok"
    data = result["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
    assert "summary" in data and isinstance(data["summary"], str)
    assert "details" in data and isinstance(data["details"], dict)
    assert "recommendations" in data and isinstance(data["recommendations"], list)
    # details 中每个智能体结果应包含 simulated 标记
    for agent_id, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ AgentManager.process 返回符合规范的结构化结果")


def test_manager_process_unknown_question_defaults_farmer():
    """无关键词问题默认路由到 farmer"""
    mgr = AgentManager()
    result = mgr.process("你好", {})
    assert result["data"]["role"] == "farmer"
    print("✓ 未知问题默认路由到 farmer")


if __name__ == "__main__":
    test_manager_register_six_agents()
    test_manager_topological_sort_province()
    test_manager_topological_sort_farmer()
    test_manager_process_farmer_returns_structured_result()
    test_manager_process_unknown_question_defaults_farmer()
    print("\n所有 AgentManager 测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_manager.py`
Expected: FAIL，提示 `No module named 'framework.agents.manager'`

- [x] **Step 3: 实现 AgentManager**

写入 `framework/agents/manager.py`：

```python
from __future__ import annotations
from typing import Any, Dict, List

from .base import BaseAgent
from .router import RoleRouter


class _StubAgent(BaseAgent):
    """桩智能体，在专业智能体实现前用于 Manager 单元测试。"""

    def __init__(self, name: str, description: str, model_id: str, domain: str):
        super().__init__(name, description, model_id, domain)

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ok",
            "result": {"stub": True, "model_id": self.model_id},
            "metadata": {"simulated": True},
        }

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "answer": f"[{self.model_id}] 桩智能体回复：{question}",
            "evidence": [{"source": "stub", "model_id": self.model_id}],
            "confidence": 0.5,
            "simulated": True,
        }


class AgentManager:
    """中心化智能体编排器。"""

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.router = RoleRouter()
        self._register_agents()

    def _register_agents(self) -> None:
        """注册所有 6 个专业智能体；若专业实现尚未就绪，回退到桩智能体。"""
        specs = [
            ("model-1", "StabilityRiskAgent", "耕地质量等级稳定性与退化风险识别", "stability"),
            ("model-2", "PotentialAssessmentAgent", "耕地质量提升潜力评估", "potential"),
            ("model-3", "ProblemIdentificationAgent", "耕地质量主要问题精准识别", "problem"),
            ("model-4", "AcidificationRemediationAgent", "耕地土壤酸化改良", "acidification"),
            ("model-5", "OrganicMatterAgent", "耕地土壤有机质培肥提升", "organic_matter"),
            ("model-6", "ComprehensiveImprovementAgent", "耕地综合地力改良提升", "comprehensive"),
        ]

        real_agents = self._load_real_agents()
        for model_id, class_name, description, domain in specs:
            if model_id in real_agents:
                self.agents[model_id] = real_agents[model_id]
            else:
                self.agents[model_id] = _StubAgent(class_name, description, model_id, domain)

        # 显式声明依赖关系
        self.agents["model-1"].dependencies = []
        self.agents["model-2"].dependencies = []
        self.agents["model-3"].dependencies = ["model-2"]
        self.agents["model-4"].dependencies = []
        self.agents["model-5"].dependencies = []
        self.agents["model-6"].dependencies = ["model-4", "model-5"]

    def _load_real_agents(self) -> Dict[str, BaseAgent]:
        """尝试加载专业智能体实现，失败时返回空字典。"""
        real: Dict[str, BaseAgent] = {}
        try:
            from .specialized.stability_risk_agent import StabilityRiskAgent
            real["model-1"] = StabilityRiskAgent()
        except ImportError:
            pass
        try:
            from .specialized.potential_agent import PotentialAssessmentAgent
            real["model-2"] = PotentialAssessmentAgent()
        except ImportError:
            pass
        try:
            from .specialized.problem_agent import ProblemIdentificationAgent
            real["model-3"] = ProblemIdentificationAgent()
        except ImportError:
            pass
        try:
            from .specialized.acidification_agent import AcidificationRemediationAgent
            real["model-4"] = AcidificationRemediationAgent()
        except ImportError:
            pass
        try:
            from .specialized.organic_matter_agent import OrganicMatterAgent
            real["model-5"] = OrganicMatterAgent()
        except ImportError:
            pass
        try:
            from .specialized.comprehensive_agent import ComprehensiveImprovementAgent
            real["model-6"] = ComprehensiveImprovementAgent()
        except ImportError:
            pass
        return real

    def process(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """处理用户问题，返回综合结果。"""
        role = self.router.identify_role(question)
        agent_ids = self.router.get_agents_for_role(role)
        results = self._execute_with_dependencies(agent_ids, question, context)
        return {
            "status": "ok",
            "data": self._summarize(role, agent_ids, results),
        }

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

    def _topological_sort(self, agent_ids: List[str]) -> List[str]:
        """对给定的智能体子集进行拓扑排序。
        仅考虑位于 agent_ids 集合内的依赖；集合外的依赖被忽略。"""
        id_set = set(agent_ids)
        visited: set = set()
        order: List[str] = []

        def visit(node: str) -> None:
            if node in visited or node not in id_set:
                return
            visited.add(node)
            for dep in self.agents[node].dependencies:
                if dep in id_set:
                    visit(dep)
            order.append(node)

        for agent_id in agent_ids:
            visit(agent_id)

        return order

    def _summarize(
        self,
        role: str,
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
            "role": role,
            "agents_invoked": ordered_invoked,
            "summary": summary,
            "details": details,
            "recommendations": recommendations,
        }


# 模块级单例
agent_manager = AgentManager()
```

- [x] **Step 4: 运行测试确认通过**

Run: `python tests/test_agent_manager.py`
Expected: PASS，输出 `所有 AgentManager 测试通过！`

- [x] **Step 5: Commit**

```bash
git add framework/agents/manager.py tests/test_agent_manager.py
git commit -m "feat(agents): 添加 AgentManager 中心化编排器（含桩智能体回退）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 4: StabilityRiskAgent（模型1）

**Files:**
- Create: `framework/agents/specialized/__init__.py`
- Create: `framework/agents/specialized/stability_risk_agent.py`
- Test: `tests/test_agent_specialized.py`（创建文件并添加模型1测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`（Task 1）。
- Produces: `StabilityRiskAgent` 类，注册为 `model-1`，`dependencies = []`。

- [x] **Step 1: 编写失败测试**

写入 `tests/test_agent_specialized.py`：

```python
"""测试 6 个专业智能体"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_stability_risk_agent_execute():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    assert agent.model_id == "model-1"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    counties = result["result"]["counties"]
    assert isinstance(counties, list) and len(counties) >= 1
    first = counties[0]
    assert "name" in first and "quality_grade" in first and "stability" in first
    print("✓ StabilityRiskAgent.execute 返回县区稳定性数据")


def test_stability_risk_agent_answer_question_overall():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("全省耕地质量整体稳定吗？", {})
    assert out["simulated"] is True
    assert "稳定" in out["answer"] or "稳定" in str(out["evidence"])
    assert 0.0 <= out["confidence"] <= 1.0
    assert any("占比" in str(e) or "面积" in str(e) for e in out["evidence"])
    print("✓ StabilityRiskAgent.answer_question 返回稳定性总体评价")


def test_stability_risk_agent_answer_question_risk():
    from framework.agents.specialized.stability_risk_agent import StabilityRiskAgent
    agent = StabilityRiskAgent()
    out = agent.answer_question("哪些县区高等级耕地存在退化风险？", {})
    assert out["simulated"] is True
    assert "县" in out["answer"] or len(out["evidence"]) >= 1
    print("✓ StabilityRiskAgent.answer_question 识别退化风险区域")


if __name__ == "__main__":
    test_stability_risk_agent_execute()
    test_stability_risk_agent_answer_question_overall()
    test_stability_risk_agent_answer_question_risk()
    print("\n所有专业智能体测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.stability_risk_agent'`

- [x] **Step 3: 创建子包 __init__.py**

写入 `framework/agents/specialized/__init__.py`：

```python
from .stability_risk_agent import StabilityRiskAgent

__all__ = ["StabilityRiskAgent"]
```

- [x] **Step 4: 实现 StabilityRiskAgent**

写入 `framework/agents/specialized/stability_risk_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：10 个县区的质量等级、稳定性评分、退化风险指数
MOCK_COUNTIES: List[Dict[str, Any]] = [
    {"name": "乐昌县", "quality_grade": 4, "stability_score": 78.5, "risk_index": 0.32, "area_mu": 320000},
    {"name": "南雄县", "quality_grade": 3, "stability_score": 65.2, "risk_index": 0.48, "area_mu": 280000},
    {"name": "仁化县", "quality_grade": 5, "stability_score": 82.1, "risk_index": 0.18, "area_mu": 210000},
    {"name": "始兴县", "quality_grade": 4, "stability_score": 70.0, "risk_index": 0.42, "area_mu": 190000},
    {"name": "翁源县", "quality_grade": 3, "stability_score": 58.4, "risk_index": 0.61, "area_mu": 250000},
    {"name": "新丰县", "quality_grade": 2, "stability_score": 50.3, "risk_index": 0.72, "area_mu": 160000},
    {"name": "乳源县", "quality_grade": 4, "stability_score": 75.6, "risk_index": 0.29, "area_mu": 180000},
    {"name": "浈江区", "quality_grade": 3, "stability_score": 62.8, "risk_index": 0.55, "area_mu": 95000},
    {"name": "武江区", "quality_grade": 4, "stability_score": 73.4, "risk_index": 0.35, "area_mu": 110000},
    {"name": "曲江区", "quality_grade": 3, "stability_score": 60.7, "risk_index": 0.58, "area_mu": 220000},
]

# 稳定性阈值规则
STABILITY_RULES = [
    (lambda v: v >= 75.0, "稳定"),
    (lambda v: 60.0 <= v < 75.0, "一般"),
    (lambda v: v < 60.0, "较弱"),
]


class StabilityRiskAgent(BaseAgent):
    """模型1：耕地质量等级稳定性与退化风险识别模型。"""

    def __init__(self):
        super().__init__(
            name="StabilityRiskAgent",
            description="评价耕地质量等级稳定性并识别退化风险",
            model_id="model-1",
            domain="stability",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "counties": counties,
                "total_area_mu": sum(c["area_mu"] for c in counties),
            },
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        counties = [dict(c) for c in MOCK_COUNTIES]
        for c in counties:
            c["stability"] = MockDataLoader.apply_threshold(c["stability_score"], STABILITY_RULES)

        total_area = sum(c["area_mu"] for c in counties)
        stable_area = sum(c["area_mu"] for c in counties if c["stability"] == "稳定")
        general_area = sum(c["area_mu"] for c in counties if c["stability"] == "一般")
        weak_area = sum(c["area_mu"] for c in counties if c["stability"] == "较弱")

        if "整体" in question or "稳定" in question:
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

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS，输出 `所有专业智能体测试通过！`

- [x] **Step 6: Commit**

```bash
git add framework/agents/specialized/__init__.py framework/agents/specialized/stability_risk_agent.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 StabilityRiskAgent（模型1）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 5: PotentialAssessmentAgent（模型2）

**Files:**
- Create: `framework/agents/specialized/potential_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型2测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`。
- Produces: `PotentialAssessmentAgent` 类，注册为 `model-2`，`dependencies = []`。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_specialized.py` 中 `if __name__ == "__main__":` 之前追加：

```python
def test_potential_agent_execute():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    assert agent.model_id == "model-2"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    indicators = result["result"]["indicators"]
    assert isinstance(indicators, list) and len(indicators) == 11
    first = indicators[0]
    assert "name" in first and "current" in first and "potential" in first and "obstacle_degree" in first
    print("✓ PotentialAssessmentAgent.execute 返回 11 评价指标")


def test_potential_agent_answer_question():
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    out = agent.answer_question("耕地质量提升潜力如何？", {})
    assert out["simulated"] is True
    assert "潜力" in out["answer"] or "障碍" in out["answer"]
    assert 0.0 <= out["confidence"] <= 1.0
    print("✓ PotentialAssessmentAgent.answer_question 返回潜力评估")


def test_potential_agent_target_ph_in_context():
    """answer_question 应将 target_ph 写入 evidence 供下游使用"""
    from framework.agents.specialized.potential_agent import PotentialAssessmentAgent
    agent = PotentialAssessmentAgent()
    out = agent.answer_question("如何提升耕地质量？", {"current_ph": 5.0})
    assert any("target_ph" in str(e) for e in out["evidence"])
    print("✓ PotentialAssessmentAgent 在 evidence 中暴露 target_ph")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_potential_agent_execute()
    test_potential_agent_answer_question()
    test_potential_agent_target_ph_in_context()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.potential_agent'`

- [x] **Step 3: 实现 PotentialAssessmentAgent**

写入 `framework/agents/specialized/potential_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：11 个评价指标的当前值与潜在值
MOCK_INDICATORS: List[Dict[str, Any]] = [
    {"name": "pH", "current": 5.0, "potential": 6.5, "unit": ""},
    {"name": "有机质", "current": 22.0, "potential": 35.0, "unit": "g/kg"},
    {"name": "全氮", "current": 1.2, "potential": 2.0, "unit": "g/kg"},
    {"name": "有效磷", "current": 12.0, "potential": 25.0, "unit": "mg/kg"},
    {"name": "速效钾", "current": 80.0, "potential": 150.0, "unit": "mg/kg"},
    {"name": "阳离子交换量", "current": 8.5, "potential": 15.0, "unit": "cmol/kg"},
    {"name": "容重", "current": 1.45, "potential": 1.25, "unit": "g/cm³"},
    {"name": "孔隙度", "current": 45.0, "potential": 55.0, "unit": "%"},
    {"name": "黏粒含量", "current": 35.0, "potential": 35.0, "unit": "%"},
    {"name": "耕层厚度", "current": 15.0, "potential": 22.0, "unit": "cm"},
    {"name": "灌溉保证率", "current": 60.0, "potential": 90.0, "unit": "%"},
]

# 障碍度等级阈值
POTENTIAL_RULES = [
    (lambda v: v >= 75.0, "高潜力"),
    (lambda v: 40.0 <= v < 75.0, "中潜力"),
    (lambda v: v < 40.0, "低潜力"),
]


def _compute_obstacle_degree(current: float, potential: float, lower_is_better: bool = False) -> float:
    """计算障碍度值（0-100），值越大障碍越严重。"""
    if potential == current:
        return 0.0
    if lower_is_better:
        # 当前值越高于潜在值（理想值）障碍越大
        gap = max(0.0, current - potential)
        base = abs(current) if current != 0 else 1.0
    else:
        gap = max(0.0, potential - current)
        base = abs(potential) if potential != 0 else 1.0
    return round(min(100.0, gap / base * 100.0), 2)


class PotentialAssessmentAgent(BaseAgent):
    """模型2：耕地质量提升潜力评估模型。"""

    def __init__(self):
        super().__init__(
            name="PotentialAssessmentAgent",
            description="评估耕地质量提升潜力并计算障碍度值",
            model_id="model-2",
            domain="potential",
        )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
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

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "indicators": indicators,
                "average_obstacle_degree": avg_obstacle,
                "overall_potential_level": overall_level,
            },
            "metadata": {"simulated": True},
        })

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

        # 计算目标 pH：取 pH 指标的潜在值，并结合用户上下文中的 current_ph
        ph_indicator = next((i for i in indicators if i["name"] == "pH"), None)
        target_ph = ph_indicator["potential"] if ph_indicator else 6.5

        # 主要障碍因素（障碍度最高的前 3 个）
        top_obstacles = sorted(indicators, key=lambda x: x["obstacle_degree"], reverse=True)[:3]

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

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.80,
            "target_ph": target_ph,
        })
```

- [x] **Step 4: 更新子包 __init__.py**

将 `framework/agents/specialized/__init__.py` 修改为：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent

__all__ = ["StabilityRiskAgent", "PotentialAssessmentAgent"]
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add framework/agents/specialized/potential_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 PotentialAssessmentAgent（模型2）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 6: ProblemIdentificationAgent（模型3）

**Files:**
- Create: `framework/agents/specialized/problem_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型3测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`；可选消费 context 中 `model-2.target_ph`。
- Produces: `ProblemIdentificationAgent` 类，注册为 `model-3`，`dependencies = ["model-2"]`。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_specialized.py` 中 `if __name__ == "__main__":` 之前追加：

```python
def test_problem_agent_execute():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    assert agent.model_id == "model-3"
    assert agent.dependencies == ["model-2"]
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "primary_factors" in result["result"]
    assert "secondary_factors" in result["result"]
    assert "combinations" in result["result"]
    print("✓ ProblemIdentificationAgent.execute 返回障碍因素结构")


def test_problem_agent_answer_question():
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    out = agent.answer_question("耕地在哪些方面有问题？", {})
    assert out["simulated"] is True
    assert "障碍" in out["answer"] or "问题" in out["answer"]
    assert len(out["evidence"]) >= 1
    print("✓ ProblemIdentificationAgent.answer_question 返回障碍识别")


def test_problem_agent_uses_model2_target_ph():
    """当 context 包含 model-2 结果时，应使用其 target_ph"""
    from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
    agent = ProblemIdentificationAgent()
    ctx = {"model-2": {"target_ph": 6.8, "answer": "...", "evidence": [], "confidence": 0.8, "simulated": True}}
    out = agent.answer_question("主要障碍因素是什么？", ctx)
    assert any("6.8" in str(e) for e in out["evidence"])
    print("✓ ProblemIdentificationAgent 消费 model-2 的 target_ph")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_problem_agent_execute()
    test_problem_agent_answer_question()
    test_problem_agent_uses_model2_target_ph()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.problem_agent'`

- [x] **Step 3: 实现 ProblemIdentificationAgent**

写入 `framework/agents/specialized/problem_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟数据：11 个指标的障碍等级频数分布（1~10 级）
MOCK_INDICATOR_GRADES: Dict[str, List[int]] = {
    "pH": [2, 5, 8, 15, 20, 18, 12, 10, 6, 4],
    "有机质": [1, 3, 6, 10, 15, 20, 22, 15, 6, 2],
    "全氮": [1, 2, 5, 12, 18, 22, 20, 12, 6, 2],
    "有效磷": [3, 8, 12, 18, 22, 15, 10, 7, 3, 2],
    "速效钾": [5, 10, 15, 20, 22, 15, 8, 3, 1, 1],
    "阳离子交换量": [4, 8, 12, 18, 22, 18, 10, 5, 2, 1],
    "容重": [2, 6, 10, 15, 22, 20, 15, 6, 3, 1],
    "孔隙度": [2, 5, 10, 15, 22, 20, 15, 8, 2, 1],
    "黏粒含量": [1, 3, 8, 15, 25, 22, 15, 7, 3, 1],
    "耕层厚度": [3, 7, 12, 18, 22, 18, 12, 5, 2, 1],
    "灌溉保证率": [8, 15, 20, 22, 18, 10, 5, 1, 1, 0],
}


def _severity_score(grades: List[int]) -> float:
    """障碍严重度得分：等级越高（10级）权重越大。"""
    total = sum(grades)
    if total == 0:
        return 0.0
    weighted = sum((i + 1) * g for i, g in enumerate(grades))
    return round(weighted / total, 2)


class ProblemIdentificationAgent(BaseAgent):
    """模型3：耕地质量主要问题精准识别模型。"""

    def __init__(self):
        super().__init__(
            name="ProblemIdentificationAgent",
            description="识别主要/次要障碍因素和障碍组合",
            model_id="model-3",
            domain="problem",
        )
        self.dependencies = ["model-2"]

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        scores = {name: _severity_score(grades) for name, grades in MOCK_INDICATOR_GRADES.items()}
        sorted_factors = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = [name for name, score in sorted_factors if score >= 6.5]
        secondary = [name for name, score in sorted_factors if 4.0 <= score < 6.5]

        combinations = []
        if "pH" in primary and "有机质" in primary:
            combinations.append("酸化-有机质贫瘠复合障碍")
        if "阳离子交换量" in primary and "pH" in primary:
            combinations.append("酸化-保肥力下降复合障碍")
        if "容重" in primary and "孔隙度" in primary:
            combinations.append("板结-透气性差复合障碍")

        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "primary_factors": primary,
                "secondary_factors": secondary,
                "combinations": combinations,
                "indicator_grades": MOCK_INDICATOR_GRADES,
                "severity_scores": scores,
            },
            "metadata": {"simulated": True},
        })

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
        evidence.extend([
            {"combination": c} for c in combinations
        ])
        if isinstance(model2, dict) and "target_ph" in model2:
            evidence.append({"target_ph_from_model2": model2["target_ph"]})

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": 0.83,
        })
```

- [x] **Step 4: 更新子包 __init__.py**

将 `framework/agents/specialized/__init__.py` 修改为：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent

__all__ = ["StabilityRiskAgent", "PotentialAssessmentAgent", "ProblemIdentificationAgent"]
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add framework/agents/specialized/problem_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 ProblemIdentificationAgent（模型3）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 7: AcidificationRemediationAgent（模型4）

**Files:**
- Create: `framework/agents/specialized/acidification_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型4测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`。
- Produces: `AcidificationRemediationAgent` 类，注册为 `model-4`，`dependencies = []`。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_specialized.py` 中 `if __name__ == "__main__":` 之前追加：

```python
def test_acidification_agent_execute():
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    agent = AcidificationRemediationAgent()
    assert agent.model_id == "model-4"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "degree" in result["result"]
    assert "lime_dosage" in result["result"]
    assert "ph_after_remediation" in result["result"]
    print("✓ AcidificationRemediationAgent.execute 返回酸化判定与石灰用量")


def test_acidification_agent_answer_question_degree():
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    agent = AcidificationRemediationAgent()
    out = agent.answer_question("全省耕地酸化程度如何？", {})
    assert out["simulated"] is True
    assert "酸化" in out["answer"] or "pH" in out["answer"]
    print("✓ AcidificationRemediationAgent 返回酸化程度")


def test_acidification_agent_answer_question_dosage():
    from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
    agent = AcidificationRemediationAgent()
    out = agent.answer_question("如何治理强酸性耕地？施加多少调理剂？", {})
    assert out["simulated"] is True
    assert "石灰" in out["answer"] or "kg" in out["answer"]
    assert any("lime_dosage" in str(e) or "石灰" in str(e) for e in out["evidence"])
    print("✓ AcidificationRemediationAgent 返回石灰施用量建议")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_acidification_agent_execute()
    test_acidification_agent_answer_question_degree()
    test_acidification_agent_answer_question_dosage()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.acidification_agent'`

- [x] **Step 3: 实现 AcidificationRemediationAgent**

写入 `framework/agents/specialized/acidification_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟输入参数
MOCK_INPUTS = {
    "ph": 5.5,
    "organic_matter": 25.0,
    "cec": 8.5,
    "clay_content": 35.0,
    "exchangeable_al": 3.2,
}

# 酸化程度阈值规则
ACIDIFICATION_RULES = [
    (lambda v: v < 4.5, "强酸性"),
    (lambda v: 4.5 <= v < 5.5, "酸性"),
    (lambda v: 5.5 <= v < 6.5, "弱酸性"),
    (lambda v: v >= 6.5, "正常"),
]

# 石灰施用量规则（kg/亩）
LIME_DOSAGE_RULES = {
    "强酸性": 150.0,
    "酸性": 100.0,
    "弱酸性": 50.0,
    "正常": 0.0,
}


class AcidificationRemediationAgent(BaseAgent):
    """模型4：耕地土壤酸化改良模型。"""

    def __init__(self):
        super().__init__(
            name="AcidificationRemediationAgent",
            description="判定酸化程度并计算调理剂施用量",
            model_id="model-4",
            domain="acidification",
        )

    def _compute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = MockDataLoader.merge_defaults(inputs, MOCK_INPUTS)
        ph = float(data["ph"])
        degree = MockDataLoader.apply_threshold(ph, ACIDIFICATION_RULES)
        lime_dosage = LIME_DOSAGE_RULES.get(degree, 0.0)
        # 简化预测：施用石灰后 pH 提升 0.1 * (lime_dosage / 50)
        ph_after = round(min(7.5, ph + 0.1 * (lime_dosage / 50.0) * 1.0), 2)
        return {
            "ph": ph,
            "degree": degree,
            "lime_dosage": lime_dosage,
            "ph_after_remediation": ph_after,
            "exchangeable_al": data["exchangeable_al"],
            "cec": data["cec"],
            "organic_matter": data["organic_matter"],
            "clay_content": data["clay_content"],
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        computed = self._compute(task)
        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": computed,
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        # 允许通过 context.data 或 context 顶层传入土壤参数
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        if "治理" in question or "施加" in question or "调理剂" in question or "石灰" in question:
            answer = (
                f"土壤酸化程度为{computed['degree']}，"
                f"建议施石灰 {computed['lime_dosage']} kg/亩，"
                f"预计治理后 pH 提升至 {computed['ph_after_remediation']}。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"], "unit": "cmol/kg"},
                {"metric": "lime_dosage", "value": computed["lime_dosage"], "unit": "kg/亩"},
                {"metric": "ph_after_remediation", "value": computed["ph_after_remediation"]},
                {"recommendation": "分两次施用，结合翻耕作业"},
            ]
            confidence = 0.85
        elif "酸化程度" in question or "酸化等级" in question or "酸化现状" in question:
            answer = (
                f"当前土壤 pH={computed['ph']}，酸化程度为{computed['degree']}。"
                f"交换性铝={computed['exchangeable_al']} cmol/kg。"
            )
            evidence = [
                {"metric": "ph", "value": computed["ph"]},
                {"metric": "degree", "value": computed["degree"]},
                {"metric": "exchangeable_al", "value": computed["exchangeable_al"]},
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

- [x] **Step 4: 更新子包 __init__.py**

将 `framework/agents/specialized/__init__.py` 修改为：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
]
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add framework/agents/specialized/acidification_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 AcidificationRemediationAgent（模型4）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 8: OrganicMatterAgent（模型5）

**Files:**
- Create: `framework/agents/specialized/organic_matter_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型5测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`。
- Produces: `OrganicMatterAgent` 类，注册为 `model-5`，`dependencies = []`。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_specialized.py` 中 `if __name__ == "__main__":` 之前追加：

```python
def test_organic_matter_agent_execute():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    assert agent.model_id == "model-5"
    assert agent.dependencies == []
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "level" in result["result"]
    assert "manure_dosage" in result["result"]
    assert "potential_increase" in result["result"]
    print("✓ OrganicMatterAgent.execute 返回有机质分级与施用量")


def test_organic_matter_agent_answer_question_content():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("全省耕地土壤有机质含量如何？", {})
    assert out["simulated"] is True
    assert "有机质" in out["answer"]
    print("✓ OrganicMatterAgent 返回有机质含量评估")


def test_organic_matter_agent_answer_question_dosage():
    from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent
    agent = OrganicMatterAgent()
    out = agent.answer_question("有机肥每亩施用量多少？", {})
    assert out["simulated"] is True
    assert "kg" in out["answer"] or "有机肥" in out["answer"]
    assert any("manure_dosage" in str(e) or "有机肥" in str(e) for e in out["evidence"])
    print("✓ OrganicMatterAgent 返回有机肥施用量建议")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_organic_matter_agent_execute()
    test_organic_matter_agent_answer_question_content()
    test_organic_matter_agent_answer_question_dosage()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.organic_matter_agent'`

- [x] **Step 3: 实现 OrganicMatterAgent**

写入 `framework/agents/specialized/organic_matter_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 模拟输入参数
MOCK_INPUTS = {
    "organic_matter": 22.0,      # g/kg
    "total_nitrogen": 1.2,        # g/kg
    "cn_ratio": 11.5,             # 碳氮比
    "clay_content": 35.0,         # %
}

# 有机质分级规则
ORGANIC_RULES = [
    (lambda v: v < 10.0, "极低"),
    (lambda v: 10.0 <= v < 20.0, "低"),
    (lambda v: 20.0 <= v < 30.0, "中"),
    (lambda v: 30.0 <= v < 40.0, "高"),
    (lambda v: v >= 40.0, "极高"),
]

# 有机肥施用量规则（kg/亩）
MANURE_DOSAGE_RULES = {
    "极低": 2000.0,
    "低": 1500.0,
    "中": 1000.0,
    "高": 500.0,
    "极高": 0.0,
}


class OrganicMatterAgent(BaseAgent):
    """模型5：耕地土壤有机质培肥提升模型。"""

    def __init__(self):
        super().__init__(
            name="OrganicMatterAgent",
            description="有机质提升评估与有机肥施用量计算",
            model_id="model-5",
            domain="organic_matter",
        )

    def _compute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        data = MockDataLoader.merge_defaults(inputs, MOCK_INPUTS)
        om = float(data["organic_matter"])
        level = MockDataLoader.apply_threshold(om, ORGANIC_RULES)
        manure_dosage = MANURE_DOSAGE_RULES.get(level, 0.0)
        # 简化预测：每施 1000 kg/亩 有机肥，有机质提升 1.5 g/kg
        potential_increase = round(manure_dosage / 1000.0 * 1.5, 2)
        return {
            "organic_matter": om,
            "level": level,
            "manure_dosage": manure_dosage,
            "potential_increase": potential_increase,
            "total_nitrogen": data["total_nitrogen"],
            "cn_ratio": data["cn_ratio"],
            "clay_content": data["clay_content"],
        }

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        computed = self._compute(task)
        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": computed,
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        inputs = {}
        if isinstance(context.get("data"), dict):
            inputs.update(context["data"])
        inputs.update({k: v for k, v in context.items() if k in MOCK_INPUTS})
        computed = self._compute(inputs)

        if "含量" in question or "分布" in question or "现状" in question:
            answer = (
                f"全省耕地有机质含量平均 {computed['organic_matter']} g/kg，"
                f"等级为{computed['level']}。"
                f"全氮 {computed['total_nitrogen']} g/kg，碳氮比 {computed['cn_ratio']}。"
            )
            evidence = [
                {"metric": "organic_matter", "value": computed["organic_matter"], "unit": "g/kg"},
                {"metric": "level", "value": computed["level"]},
                {"metric": "total_nitrogen", "value": computed["total_nitrogen"], "unit": "g/kg"},
                {"metric": "cn_ratio", "value": computed["cn_ratio"]},
            ]
            confidence = 0.84
        elif "施用量" in question or "有机肥" in question:
            answer = (
                f"有机质等级为{computed['level']}，"
                f"建议有机肥施用量 {computed['manure_dosage']} kg/亩，"
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

- [x] **Step 4: 更新子包 __init__.py**

将 `framework/agents/specialized/__init__.py` 修改为：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
]
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add framework/agents/specialized/organic_matter_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 OrganicMatterAgent（模型5）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 9: ComprehensiveImprovementAgent（模型6）

**Files:**
- Create: `framework/agents/specialized/comprehensive_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型6测试）

**Interfaces:**
- Consumes: `BaseAgent`、`MockDataLoader`；消费 context 中 `model-4`、`model-5` 的结果。
- Produces: `ComprehensiveImprovementAgent` 类，注册为 `model-6`，`dependencies = ["model-4", "model-5"]`。

- [x] **Step 1: 追加失败测试**

在 `tests/test_agent_specialized.py` 中 `if __name__ == "__main__":` 之前追加：

```python
def test_comprehensive_agent_execute():
    from framework.agents.specialized.comprehensive_agent import ComprehensiveImprovementAgent
    agent = ComprehensiveImprovementAgent()
    assert agent.model_id == "model-6"
    assert agent.dependencies == ["model-4", "model-5"]
    result = agent.execute({"area_code": "lechang"})
    assert result["status"] == "ok"
    assert result["metadata"]["simulated"] is True
    assert "diagnosis" in result["result"]
    assert "zoning_suggestions" in result["result"]
    assert "priority_measures" in result["result"]
    print("✓ ComprehensiveImprovementAgent.execute 返回综合诊断结构")


def test_comprehensive_agent_answer_question_farmer_plot():
    from framework.agents.specialized.comprehensive_agent import ComprehensiveImprovementAgent
    agent = ComprehensiveImprovementAgent()
    out = agent.answer_question("我这块地质量怎么样？", {})
    assert out["simulated"] is True
    assert "质量" in out["answer"] or "诊断" in out["answer"]
    print("✓ ComprehensiveImprovementAgent 返回农户地块综合诊断")


def test_comprehensive_agent_consumes_upstream_results():
    """当 context 包含 model-4、model-5 时应汇总其结论"""
    from framework.agents.specialized.comprehensive_agent import ComprehensiveImprovementAgent
    agent = ComprehensiveImprovementAgent()
    ctx = {
        "model-4": {"answer": "酸化程度为酸性", "evidence": [{"metric": "lime_dosage", "value": 100.0}],
                    "confidence": 0.85, "simulated": True},
        "model-5": {"answer": "有机质等级为中", "evidence": [{"metric": "manure_dosage", "value": 1000.0}],
                    "confidence": 0.82, "simulated": True},
    }
    out = agent.answer_question("如何综合改良？", ctx)
    # 应在 evidence 或 priority_measures 中提及上游建议
    flat = str(out["evidence"]) + str(out.get("priority_measures", []))
    assert "100.0" in flat or "石灰" in flat or "1000.0" in flat or "有机肥" in flat
    print("✓ ComprehensiveImprovementAgent 消费 model-4 和 model-5 结果")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_comprehensive_agent_execute()
    test_comprehensive_agent_answer_question_farmer_plot()
    test_comprehensive_agent_consumes_upstream_results()
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.comprehensive_agent'`

- [x] **Step 3: 实现 ComprehensiveImprovementAgent**

写入 `framework/agents/specialized/comprehensive_agent.py`：

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader


# 综合提升措施库
IMPROVEMENT_MEASURES: List[Dict[str, Any]] = [
    {"id": "M01", "name": "施用石灰调理酸度", "domain": "acidification", "priority": 1, "applies_to": ["强酸性", "酸性"]},
    {"id": "M02", "name": "增施有机肥提升有机质", "domain": "organic_matter", "priority": 1, "applies_to": ["极低", "低", "中"]},
    {"id": "M03", "name": "种植绿肥作物", "domain": "organic_matter", "priority": 2, "applies_to": ["极低", "低"]},
    {"id": "M04", "name": "秸秆还田", "domain": "organic_matter", "priority": 2, "applies_to": ["低", "中"]},
    {"id": "M05", "name": "深翻改土", "domain": "structure", "priority": 3, "applies_to": ["板结"]},
    {"id": "M06", "name": "调整施肥结构控氮", "domain": "acidification", "priority": 2, "applies_to": ["强酸性", "酸性"]},
    {"id": "M07", "name": "完善灌溉设施", "domain": "irrigation", "priority": 3, "applies_to": ["灌溉不足"]},
]


def _extract_upstream_summary(context: Dict[str, Any]) -> Dict[str, Any]:
    """从 model-4 和 model-5 的结果中提取关键信息。"""
    summary: Dict[str, Any] = {"acidification": None, "organic_matter": None}
    m4 = context.get("model-4") if isinstance(context, dict) else None
    m5 = context.get("model-5") if isinstance(context, dict) else None
    if isinstance(m4, dict):
        summary["acidification"] = {
            "answer": m4.get("answer", ""),
            "evidence": m4.get("evidence", []),
        }
    if isinstance(m5, dict):
        summary["organic_matter"] = {
            "answer": m5.get("answer", ""),
            "evidence": m5.get("evidence", []),
        }
    return summary


def _match_measures(upstream: Dict[str, Any]) -> List[Dict[str, Any]]:
    """根据上游结论匹配综合提升措施。"""
    matched: List[Dict[str, Any]] = []
    acid = upstream.get("acidification") or {}
    organic = upstream.get("organic_matter") or {}

    acid_text = acid.get("answer", "") + str(acid.get("evidence", []))
    organic_text = organic.get("answer", "") + str(organic.get("evidence", []))

    for m in IMPROVEMENT_MEASURES:
        applies = False
        if m["domain"] == "acidification" and any(k in acid_text for k in m["applies_to"]):
            applies = True
        if m["domain"] == "organic_matter" and any(k in organic_text for k in m["applies_to"]):
            applies = True
        if applies:
            matched.append({"id": m["id"], "name": m["name"], "priority": m["priority"]})

    # 若无上游匹配，回退为通用建议
    if not matched:
        matched = [
            {"id": "M02", "name": "增施有机肥提升有机质", "priority": 1},
            {"id": "M01", "name": "施用石灰调理酸度", "priority": 1},
        ]
    return sorted(matched, key=lambda x: x["priority"])


class ComprehensiveImprovementAgent(BaseAgent):
    """模型6：耕地综合地力改良提升模型。"""

    def __init__(self):
        super().__init__(
            name="ComprehensiveImprovementAgent",
            description="综合多模型结果生成分区分类提升建议",
            model_id="model-6",
            domain="comprehensive",
        )
        self.dependencies = ["model-4", "model-5"]

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        # 默认模拟综合诊断
        diagnosis = "耕地综合质量等级为中等，主要存在酸化与有机质偏低复合问题。"
        zoning_suggestions = [
            {"zone": "东部片区", "issue": "酸化", "measure": "施石灰 100 kg/亩"},
            {"zone": "西部片区", "issue": "有机质偏低", "measure": "增施有机肥 1500 kg/亩"},
            {"zone": "南部片区", "issue": "板结", "measure": "深翻改土 + 秸秆还田"},
        ]
        priority_measures = [
            {"id": "M01", "name": "施用石灰调理酸度", "priority": 1},
            {"id": "M02", "name": "增施有机肥提升有机质", "priority": 1},
            {"id": "M05", "name": "深翻改土", "priority": 3},
        ]
        return MockDataLoader.mark_simulated({
            "status": "ok",
            "result": {
                "diagnosis": diagnosis,
                "zoning_suggestions": zoning_suggestions,
                "priority_measures": priority_measures,
            },
            "metadata": {"simulated": True},
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        upstream = _extract_upstream_summary(context)
        priority_measures = _match_measures(upstream)

        if "质量怎么样" in question or "地块" in question or "诊断" in question:
            acid_summary = upstream.get("acidification", {}).get("answer", "未触发酸化模型")
            organic_summary = upstream.get("organic_matter", {}).get("answer", "未触发有机质模型")
            diagnosis = (
                f"地块综合诊断：酸化维度 — {acid_summary}；"
                f"有机质维度 — {organic_summary}。"
            )
            answer = (
                f"{diagnosis} 优先措施："
                + "；".join(f"{m['name']}" for m in priority_measures[:3])
                + "。"
            )
            evidence = [
                {"source": "model-4", "summary": acid_summary},
                {"source": "model-5", "summary": organic_summary},
            ] + [{"priority_measure": m["name"], "priority": m["priority"]} for m in priority_measures[:3]]
            confidence = 0.80
        else:
            acid_summary = upstream.get("acidification", {}).get("answer", "")
            organic_summary = upstream.get("organic_matter", {}).get("answer", "")
            answer = (
                "综合改良建议："
                + ("酸化方面 — " + acid_summary + "；" if acid_summary else "")
                + ("有机质方面 — " + organic_summary + "；" if organic_summary else "")
                + "优先措施：" + "；".join(m["name"] for m in priority_measures[:3]) + "。"
            )
            evidence = [
                {"source": "model-4", "summary": acid_summary},
                {"source": "model-5", "summary": organic_summary},
            ] + [{"priority_measure": m["name"], "priority": m["priority"]} for m in priority_measures[:3]]
            confidence = 0.78

        return MockDataLoader.mark_simulated({
            "answer": answer,
            "evidence": evidence,
            "confidence": confidence,
            "priority_measures": priority_measures,
        })
```

- [x] **Step 4: 更新子包 __init__.py**

将 `framework/agents/specialized/__init__.py` 修改为：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .comprehensive_agent import ComprehensiveImprovementAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "ComprehensiveImprovementAgent",
]
```

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_specialized.py`
Expected: PASS，输出 `所有专业智能体测试通过！`

- [x] **Step 6: 重新运行 Manager 测试以确认真实智能体被加载**

Run: `python tests/test_agent_manager.py`
Expected: PASS（应仍通过，但 `_StubAgent` 不再被使用 —— 可在 Manager 内部通过断言 `not isinstance(agent, _StubAgent)` 验证，非必需）。

- [x] **Step 7: Commit**

```bash
git add framework/agents/specialized/comprehensive_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 ComprehensiveImprovementAgent（模型6）"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 10: 在 LangGraph execute_models 节点集成 AgentManager

**Files:**
- Modify: `framework/agents/__init__.py`
- Modify: `framework/agents/nodes.py`（仅修改 `execute_models` 函数）
- Test: `tests/test_agent_integration.py`（创建并添加节点集成测试）

**Interfaces:**
- Consumes: `agent_manager`（Task 3）、`MultiAgentState`。
- Produces: `execute_models` 优先调用 `agent_manager.process`，将结果写入 `state["model_results"]` 与 `state["status"] = "model_completed"`。失败时回退到原 `_execute_models_fallback`。

- [x] **Step 1: 编写失败测试**

写入 `tests/test_agent_integration.py`：

```python
"""测试 AgentManager 与 LangGraph 节点集成"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.agents.state import MultiAgentState
from framework.agents.nodes import execute_models


def _make_state(question: str, question_type: int = 1) -> MultiAgentState:
    return {
        "request": {"question": question, "area_code": "lechang"},
        "data": {},
        "model_results": {},
        "llm_response": {},
        "rag_response": {},
        "conversation_history": [],
        "status": "running",
        "error": None,
        "question_type": question_type,
        "relevance": 0.8,
    }


def test_execute_models_invokes_agent_manager_farmer():
    """execute_models 应通过 AgentManager 路由到 farmer 智能体组合"""
    state = _make_state("我的田施氮肥施多少？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    mr = result["model_results"]
    assert mr.get("status") == "ok"
    data = mr.get("data", {})
    assert data.get("role") == "farmer"
    assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
    print("✓ execute_models 通过 AgentManager 路由到 farmer")


def test_execute_models_invokes_agent_manager_province():
    state = _make_state("全省耕地酸化程度如何？")
    result = execute_models(state)
    assert result["status"] == "model_completed"
    data = result["model_results"].get("data", {})
    assert data.get("role") == "province"
    assert set(data.get("agents_invoked", [])) == {"model-1", "model-3"}
    print("✓ execute_models 通过 AgentManager 路由到 province")


def test_execute_models_writes_structured_result():
    state = _make_state("我的田质量怎么样？")
    result = execute_models(state)
    data = result["model_results"].get("data", {})
    assert "summary" in data
    assert "details" in data
    assert "recommendations" in data
    # 每个智能体详情应携带 simulated 标记
    for aid, payload in data["details"].items():
        assert payload.get("simulated") is True
    print("✓ execute_models 写入结构化多智能体结果")


if __name__ == "__main__":
    test_execute_models_invokes_agent_manager_farmer()
    test_execute_models_invokes_agent_manager_province()
    test_execute_models_writes_structured_result()
    print("\n所有 LangGraph 集成测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_integration.py`
Expected: FAIL —— 当前 `execute_models` 不调用 `agent_manager`，`status` 不会是 `model_completed`，且 `model_results` 结构不同。

- [x] **Step 3: 更新 framework/agents/__init__.py**

将 `framework/agents/__init__.py`（当前为空）修改为：

```python
from .base import BaseAgent
from .router import RoleRouter
from .manager import agent_manager, AgentManager

__all__ = ["BaseAgent", "RoleRouter", "AgentManager", "agent_manager"]
```

- [x] **Step 4: 修改 execute_models 节点函数**

打开 `framework/agents/nodes.py`，找到现有的 `execute_models` 函数（第 218 行附近），在其函数体最前面插入 AgentManager 调用逻辑，使函数变为：

```python
def execute_models(state: MultiAgentState) -> MultiAgentState:
    # 优先调用 AgentManager 进行多智能体协作
    try:
        from framework.agents.manager import agent_manager

        question = state["request"].get("question", "")
        context = {
            "area_code": state["request"].get("area_code", "lechang"),
            "data": state.get("data", {}),
        }
        # 透传可能的土壤参数
        for key in ("longitude", "latitude", "target_ph", "context"):
            if key in state["request"]:
                context[key] = state["request"][key]

        result = agent_manager.process(question, context)
        if result.get("status") == "ok":
            return {
                **state,
                "model_results": result,
                "status": "model_completed",
                "error": None,
            }
    except Exception:
        # AgentManager 失败时回退到原模型执行逻辑
        pass

    return _execute_models_fallback(state)
```

注意：保留原 `_execute_models_fallback` 函数与文件中其他函数（`route_models`、`rag_chat_node`、`llm_generate`、`aggregate_results`、`finalize` 等）不变。

- [x] **Step 5: 运行测试确认通过**

Run: `python tests/test_agent_integration.py`
Expected: PASS，输出 `所有 LangGraph 集成测试通过！`

- [x] **Step 6: 重新运行既有测试套件确保未回归**

依次运行：
```
python tests/test_agent_base.py
python tests/test_agent_manager.py
python tests/test_agent_specialized.py
python tests/test_multi_agent.py
```
Expected: 全部 PASS。

- [x] **Step 7: Commit**

```bash
git add framework/agents/__init__.py framework/agents/nodes.py tests/test_agent_integration.py
git commit -m "feat(agents): 在 execute_models 节点集成 AgentManager"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 11: 更新 /api/v1/chat/ 接口返回多智能体结构化结果

**Files:**
- Modify: `framework/api/routes/chat.py`
- Test: `tests/test_agent_integration.py`（追加 API 集成测试，使用 Flask test client）

**Interfaces:**
- Consumes: `multi_agent_orchestrator.run` 返回的 `model_results` 中现在包含 AgentManager 的结构化结果（`status`、`data.role`、`data.agents_invoked`、`data.summary`、`data.details`、`data.recommendations`）。
- Produces: `/api/v1/chat/` POST 响应 `data` 中新增 `role`、`agents_invoked`、`recommendations` 字段。

- [x] **Step 1: 追加 API 集成测试**

在 `tests/test_agent_integration.py` 末尾 `if __name__ == "__main__":` 之前追加：

```python
def test_chat_api_returns_structured_multi_agent_result():
    """通过 Flask test client 验证 /api/v1/chat/ 返回多智能体结构化结果"""
    from framework.api.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        from framework.models.user import db
        db.create_all()

        # 注册测试用户并获取 token
        from framework.models.user import User
        user = User(username="tester", password="x", email="t@t.com")
        db.session.add(user)
        db.session.commit()

    client = app.test_client()
    # 用 JWT 装饰器要求登录；此处直接 patch jwt_required 跳过鉴权以聚焦结构验证
    import flask_jwt_extended
    real_jwt_required = flask_jwt_extended.jwt_required
    real_get_jwt_identity = flask_jwt_extended.get_jwt_identity

    class _Dummy:
        def __call__(self, fn):
            return fn

    flask_jwt_extended.jwt_required = _Dummy()
    flask_jwt_extended.get_jwt_identity = lambda: 1

    try:
        with app.app_context():
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "我的田施氮肥施多少？"},
            )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["status"] == "ok"
        data = payload["data"]
        # 多智能体结构化字段
        assert data.get("role") == "farmer"
        assert data.get("agents_invoked") == ["model-4", "model-5", "model-6"]
        assert isinstance(data.get("recommendations"), list)
        assert "answer" in data
    finally:
        flask_jwt_extended.jwt_required = real_jwt_required
        flask_jwt_extended.get_jwt_identity = real_get_jwt_identity

    print("✓ /api/v1/chat/ 返回多智能体结构化结果")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_chat_api_returns_structured_multi_agent_result()
```

并更新最后一行打印为：

```python
    print("\n所有 LangGraph 与 API 集成测试通过！")
```

- [x] **Step 2: 运行测试确认失败**

Run: `python tests/test_agent_integration.py`
Expected: FAIL —— 当前 `chat()` 端点未返回 `role` / `agents_invoked` / `recommendations` 字段。

- [x] **Step 3: 修改 chat.py 的 chat() 端点**

打开 `framework/api/routes/chat.py`，将 `chat()` 函数中处理 `result` 与构造响应的部分替换为：

```python
    answer = result.get("answer", result.get("llm_response", ""))
    sources = result.get("sources", [])
    model_results = result.get("model_results", {})
    question_type = result.get("question_type", 0)

    # 解析 AgentManager 结构化结果（若存在）
    agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
    role = agent_data.get("role")
    agents_invoked = agent_data.get("agents_invoked", [])
    recommendations = agent_data.get("recommendations", [])
    multi_agent_summary = agent_data.get("summary", "")

    assistant_message = Message(
        conversation_id=conversation.id,
        role='assistant',
        content=answer or multi_agent_summary,
        sources=sources if sources else None,
    )
    db.session.add(assistant_message)
    db.session.commit()

    response_data = {
        "answer": answer or multi_agent_summary,
        "sources": sources,
        "question_type": question_type,
        "model_results": model_results,
        "message_id": assistant_message.id,
    }
    if role:
        response_data["role"] = role
    if agents_invoked:
        response_data["agents_invoked"] = agents_invoked
    if recommendations:
        response_data["recommendations"] = recommendations

    return jsonify({
        "status": "ok",
        "data": response_data,
    })
```

注意：保留文件顶部的 import 与其他端点函数（`get_conversations`、`create_conversation` 等）不变。

- [x] **Step 4: 运行测试确认通过**

Run: `python tests/test_agent_integration.py`
Expected: PASS，输出 `所有 LangGraph 与 API 集成测试通过！`

- [x] **Step 5: Commit**

```bash
git add framework/api/routes/chat.py tests/test_agent_integration.py
git commit -m "feat(api): /api/v1/chat/ 返回多智能体结构化结果"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

### Task 12: 端到端角色路由验证与回归测试

**Files:**
- Test: `tests/test_agent_integration.py`（追加三类角色端到端验证）
- Modify: `openspec/changes/multi-agent-model-framework/tasks.md`（勾选已完成项）

**Interfaces:**
- 验证 Task 1-11 的整体协同：三类角色（province/county/farmer）均能正确路由并返回结构化结果。

- [x] **Step 1: 追加端到端验证测试**

在 `tests/test_agent_integration.py` 末尾 `if __name__ == "__main__":` 之前追加：

```python
def test_e2e_province_role_routing():
    """省市管理端问题应路由到 model-1 + model-3"""
    state = _make_state("全省耕地质量整体稳定吗？哪些县区有退化风险？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "province"
    assert data["agents_invoked"] == ["model-1", "model-3"]
    # model-3 依赖 model-2，但 model-2 不在 invoked 集合内 —— 应安全跳过
    for aid in ["model-1", "model-3"]:
        assert aid in data["details"]
        assert data["details"][aid]["simulated"] is True
    print("✓ 省市管理端路由正确（model-1 + model-3）")


def test_e2e_county_role_routing():
    """县域执行端问题应路由到 model-1 + model-3 + model-2，model-3 排在 model-2 之后"""
    state = _make_state("本县乡镇任务如何分配？县域耕地质量如何？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "county"
    assert set(data["agents_invoked"]) == {"model-1", "model-2", "model-3"}
    # model-2 应在 model-3 之前（拓扑序）
    assert data["agents_invoked"].index("model-2") < data["agents_invoked"].index("model-3")
    print("✓ 县域执行端路由正确（model-1 + model-2 + model-3，拓扑序正确）")


def test_e2e_farmer_role_routing():
    """农户种植端问题应路由到 model-4 + model-5 + model-6，model-6 排在最后"""
    state = _make_state("我的田施氮肥施多少？这块地质量怎么样？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert data["role"] == "farmer"
    assert data["agents_invoked"] == ["model-4", "model-5", "model-6"]
    # model-6 应排在最后
    assert data["agents_invoked"][-1] == "model-6"
    # model-6 应消费了 model-4 与 model-5 的结果
    m6_evidence = str(data["details"]["model-6"]["evidence"])
    assert "model-4" in m6_evidence or "model-5" in m6_evidence or "石灰" in m6_evidence or "有机肥" in m6_evidence
    print("✓ 农户种植端路由正确（model-4 + model-5 + model-6，依赖传递正确）")


def test_e2e_recommendations_aggregated():
    """汇总的 recommendations 应来自各智能体 evidence 中的 recommendation/source"""
    state = _make_state("我的田怎么改良？")
    result = execute_models(state)
    data = result["model_results"]["data"]
    assert isinstance(data["recommendations"], list)
    # 至少应包含一条建议（来自 model-4 或 model-5 或 model-6）
    assert len(data["recommendations"]) >= 1
    print("✓ recommendations 字段已聚合各智能体建议")
```

并在 `if __name__ == "__main__":` 块中追加：

```python
    test_e2e_province_role_routing()
    test_e2e_county_role_routing()
    test_e2e_farmer_role_routing()
    test_e2e_recommendations_aggregated()
```

- [x] **Step 2: 运行测试确认通过**

Run: `python tests/test_agent_integration.py`
Expected: PASS，全部 7 个测试通过。

- [x] **Step 3: 运行全部测试套件做最终回归**

依次运行：
```
python tests/test_agent_base.py
python tests/test_agent_manager.py
python tests/test_agent_specialized.py
python tests/test_agent_integration.py
python tests/test_multi_agent.py
```
Expected: 全部 PASS，无回归。

- [x] **Step 4: 勾选 openspec tasks.md 中已完成项**

打开 `openspec/changes/multi-agent-model-framework/tasks.md`，将所有 `- [ ]` 改为 `- [x]`。

- [x] **Step 5: Commit**

```bash
git add tests/test_agent_integration.py openspec/changes/multi-agent-model-framework/tasks.md
git commit -m "test(agents): 端到端验证三类角色路由并完成 tasks.md 勾选"
```

archived-with: 2026-07-13-multi-agent-model-framework
---

## 计划完成

**自我审查：**

1. **Spec 覆盖：**
   - 设计文档第 2 节 BaseAgent 抽象基类 → Task 1 ✓
   - 设计文档第 3 节模拟数据策略 → Task 1（MockDataLoader）+ Task 4-9（每个智能体内置 MOCK_INPUTS/THRESHOLDS）✓
   - 设计文档第 4 节 AgentManager → Task 3 ✓
   - 设计文档第 5 节 RoleRouter → Task 2 ✓
   - 设计文档第 6 节 6 个专业智能体 → Task 4-9 ✓
   - 设计文档第 7 节 LangGraph 集成 → Task 10 ✓
   - 设计文档第 8 节 API 响应格式 → Task 11 ✓
   - 设计文档第 9 节测试策略（4 类测试）→ Task 1-3（单元）、Task 4-9（智能体功能）、Task 3 + Task 12（协同）、Task 11 + Task 12（API 集成）✓
   - tasks.md 1.1-1.3 → Task 1-3 ✓
   - tasks.md 2.1-2.6 → Task 4-9 ✓
   - tasks.md 3.1-3.4 → Task 2、Task 10、Task 11 ✓（3.3 orchestrator.py 未单独修改，因其已正确调用 `execute_models` 节点，自动获得 AgentManager 集成）
   - tasks.md 4.1-4.5 → Task 1-3、Task 4-9、Task 3+12、Task 11、Task 12 ✓

2. **占位扫描：** 无 TBD/TODO/"fill in details" 等；所有步骤均含完整代码或确切命令。

3. **类型一致性：** `BaseAgent` 构造签名、`execute`/`answer_question` 返回结构、`RoleRouter` 方法名、`AgentManager.process` 返回结构、`agent_manager` 单例名在所有任务中一致；`model-1` 至 `model-6` ID 与依赖关系在 Task 3、Task 4-9、Task 12 中一致。

**关于 tasks.md 3.3 的说明：** `orchestrator.py` 中的 `MultiAgentOrchestrator.run` 通过 `execute_models` 节点间接调用 AgentManager，无需修改 orchestrator 本身。如需在 Task 10 验证此点，Task 12 的 `test_e2e_*` 测试已通过 `execute_models` → `agent_manager` 链路间接覆盖。

