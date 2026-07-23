# Task 5 Implementer Brief — AgentManager 集成与按需过滤

## 身份与上下文

你是 Comet 工作流 `add-model-6-fertility-ml` 的 Task 5 implementer subagent。

- **Change**: add-model-6-fertility-ml
- **分支**: `feature/20260718/add-model-6-fertility-ml`（已 checkout，HEAD=`af6fb2e`）
- **TDD 模式**: tdd（必须先 RED 后 GREEN）
- **审查模式**: standard
- **当前 Task**: 5（AgentManager 集成与按需过滤）
- **plan 路径**: `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` 的 Task 5 章节（line 1274-1497）
- **语言**: 中文（代码注释、commit message 用中文；技术名词保持英文）

## 前置已完成产物（无需重做）

- Task 1: `data/fertility/` 训练数据 + `pyproject.toml` 依赖已声明
- Task 2: `scripts/train_fertility_models.py` + 4 个模型产物文件已生成
- Task 3: `framework/domain/other_models/model_6.py` 真实 ML 实现 + `tests/test_fertility_ml_prediction.py`
- Task 4: `framework/agents/specialized/fertility_ml_agent.py`（FertilityMLAgent）+ `framework/agents/specialized/__init__.py` 已导出 FertilityMLAgent

## 你的任务（来自 plan Task 5）

### 文件

- Modify: `framework/agents/manager.py`（当前 197 行，BASE 版本见下文）
- Test: `tests/test_agent_manager.py`（既有 5 个测试，需新增 7 个测试函数到 `if __name__ == "__main__"` 块之前）

### 必须完成的 6 个 Step（来自 plan）

#### Step 1: 在 `tests/test_agent_manager.py` 末尾（`if __name__` 之前）新增 7 个过滤测试

完整代码（按 plan 原文逐字落地，不要修改断言）：

```python
def test_should_execute_model6_fertility_question():
    """问'肥力' → _should_execute_agent('model-6', ...) = True"""
    from framework.agents.manager import AgentManager, FERTILITY_KEYWORDS
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田肥力怎么样？") is True
    assert mgr._should_execute_agent("model-6", "有机碳含量多少？") is True
    assert mgr._should_execute_agent("model-6", "需要施多少肥？") is True
    print("✓ 肥力相关问题触发 model-6 执行")


def test_should_skip_model6_non_fertility_question():
    """问'pH' → _should_execute_agent('model-6', ...) = False"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-6", "我的田pH如何？") is False
    assert mgr._should_execute_agent("model-6", "你好") is False
    print("✓ 非肥力问题跳过 model-6")


def test_should_execute_other_agents_always():
    """非 model-6 的 agent 始终执行"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr._should_execute_agent("model-4", "任何问题") is True
    assert mgr._should_execute_agent("model-5", "任何问题") is True
    print("✓ 非 model-6 agent 始终执行")


def test_model6_dependencies_empty():
    """model-6 dependencies=[]，不依赖 model-4/5"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    assert mgr.agents["model-6"].dependencies == []
    print("✓ model-6 依赖为空")


def test_topological_sort_model6_no_dep():
    """model-6 dependencies=[]，拓扑排序不强制 model-6 在最后"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    ordered = mgr._topological_sort(["model-4", "model-5", "model-6"])
    assert set(ordered) == {"model-4", "model-5", "model-6"}
    # model-6 不再依赖 model-4/5，不强制排最后
    assert ordered[-1] != "model-6" or len(ordered) == 1
    print("✓ model-6 在拓扑排序中无依赖约束")


def test_model6_skipped_in_details_for_non_fertility():
    """非肥力问题 → details['model-6'] 含 skipped 状态"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    result = mgr.process("我的田pH如何？", {})
    details = result["data"]["details"]
    # model-6 应被跳过（status 标记或 skipped 标记）
    m6 = details.get("model-6", {})
    assert m6.get("status") == "skipped" or m6.get("simulated") is True
    print("✓ 非肥力问题 model-6 被跳过")


def test_manager_loads_fertility_ml_agent():
    """_load_real_agents 加载 FertilityMLAgent"""
    from framework.agents.manager import AgentManager
    mgr = AgentManager()
    agent = mgr.agents["model-6"]
    assert agent.__class__.__name__ == "FertilityMLAgent"
    print("✓ AgentManager 加载 FertilityMLAgent")
```

**重要**：不要修改既有 5 个测试函数（包括 `test_manager_topological_sort_farmer`）。该测试的断言 `ordered[-1] == "model-6"` 在 Task 5 后会失败，这是 **plan-mandated 已知 break，将在 Task 7 修复**。你的新增测试 `test_topological_sort_model6_no_dep` 的断言 `ordered[-1] != "model-6"` 与既有测试冲突，这是预期行为。

#### Step 2: 运行测试确认失败（TDD RED）

```bash
python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"
```

Expected: FAIL（`_should_execute_agent` 方法不存在、`FERTILITY_KEYWORDS` 未导出、`dependencies` 仍为 `["model-4", "model-5"]`、model-6 仍是 `ComprehensiveImprovementAgent`）。

请把这一步的实际输出贴到 task-5-report.md 的 RED 证据区。

#### Step 3: 修改 `framework/agents/manager.py`

BASE 版本（当前 HEAD `af6fb2e` 的 `framework/agents/manager.py` 完整内容，197 行）：

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
            "evidence": [],
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
            "details": details,
            "summary": summary,
            "recommendations": recommendations,
        }


# 模块级单例
agent_manager = AgentManager()
```

**5 处必改点**：

1. **顶部 import 后新增 FERTILITY_KEYWORDS 常量**（在 `from .router import RoleRouter` 之后、`class _StubAgent` 之前）：

```python
# 肥力相关关键词（与 FertilityMLAgent.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]
```

2. **修改 `_register_agents` 中 model-6 spec 行**：

```python
("model-6", "FertilityMLAgent", "耕地肥力 SOC/Dose ML 预测", "fertility_ml"),
```

3. **修改依赖声明**：

```python
self.agents["model-6"].dependencies = []
```

4. **修改 `_load_real_agents` 中 model-6 加载逻辑**（替换原 `from .specialized.comprehensive_agent import ComprehensiveImprovementAgent` 块）：

```python
try:
    from .specialized.fertility_ml_agent import FertilityMLAgent
    real["model-6"] = FertilityMLAgent()
except ImportError:
    pass
```

5. **新增 `_should_execute_agent` 方法**（放在 `_topological_sort` 之后、`_summarize` 之前）：

```python
def _should_execute_agent(self, agent_id: str, question: str) -> bool:
    """问题感知过滤：model-6 仅在肥力相关问题时执行。"""
    if agent_id == "model-6":
        q_lower = (question or "").lower()
        return any(kw.lower() in q_lower for kw in FERTILITY_KEYWORDS)
    return True
```

6. **修改 `_execute_with_dependencies` 加入过滤逻辑**（在 `for agent_id in ordered:` 循环开头加入跳过分支）：

```python
for agent_id in ordered:
    # 按需过滤：非肥力问题跳过 model-6
    if not self._should_execute_agent(agent_id, question):
        results[agent_id] = {
            "status": "skipped",
            "reason": "question_not_related",
            "answer": "",
            "evidence": [],
            "confidence": 0.0,
            "simulated": True,
        }
        accumulated[agent_id] = results[agent_id]
        continue

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
```

#### Step 4: 运行新增测试确认通过（TDD GREEN）

```bash
python -m pytest tests/test_agent_manager.py -v -k "should_execute or should_skip or dependencies_empty or topological_sort_model6 or skipped_in_details or loads_fertility"
```

Expected: 7 个新测试全部 PASS。把实际输出贴到 task-5-report.md 的 GREEN 证据区。

#### Step 5: 运行既有 AgentManager 测试确认兼容

```bash
python -m pytest tests/test_agent_manager.py -v
```

Expected:
- `test_manager_topological_sort_farmer` **会 FAIL**（原断言 `ordered[-1] == "model-6"` 不再成立，因为 model-6.dependencies=[] 后拓扑排序不再强制 model-6 在末尾）。**这是 plan-mandated 已知 break，Task 7 修复，不阻塞 Task 5 验收**。
- 其他既有测试应 PASS。

把这一步的实际输出（含 FAIL 行）贴到 task-5-report.md 的"既有测试影响"区。

#### Step 6: 提交

```bash
git add framework/agents/manager.py tests/test_agent_manager.py
git commit -m "feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤"
```

## 关键约束

1. **TDD 必须先 RED 后 GREEN**：在 task-5-report.md 中提供两段实际命令输出（RED 证据 + GREEN 证据）。
2. **不要修改既有 5 个测试函数**，包括会 FAIL 的 `test_manager_topological_sort_farmer`。
3. **不要删除 `framework/agents/specialized/comprehensive_agent.py` 或修改 `__init__.py` 中的 comprehensive 导入**——这是 Task 6 的职责。
4. **`FERTILITY_KEYWORDS` 必须与 `FertilityMLAgent.FERTILITY_KEYWORDS` 完全一致**（见 framework/agents/specialized/fertility_ml_agent.py line 9-15）。该 agent 已存在，可直接 import 验证一致性；但 plan 要求 manager.py 在顶部独立定义此常量，不要 import 复用（避免循环依赖风险）。
5. **不要重写整个 manager.py**——使用 Edit 工具按 5 处必改点逐一精准修改。
6. **`_should_execute_agent` 必须是 public 方法**（无下划线前缀的等价形式 plan 也接受，但 plan 原文写的就是 `_should_execute_agent`，保持一致）。
7. **不要新增任何 plan 未提及的文件或功能**——遵循"do what's asked, nothing more"原则。
8. **commit message 必须使用 plan 提供的原话**：`feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤`。

## 风险信号自报（implementer 完成后必须填写到 task-5-report.md）

请在 task-5-report.md 末尾填写下列自报（每项写"是/否 + 简短说明"）：

- 跨模块/跨子系统协调改动？
- 安全敏感面（认证、授权、加解密、SQL、外部输入处理、密钥/凭证）？
- 并发、锁、共享可变状态？
- 数据或 schema 迁移？
- 公共 API 契约或对外接口变更？
- 是否返回 DONE_WITH_CONCERNS？
- 单任务 diff 超过 200 行？

如任一为"是"，coordinator 将派发 reviewer subagent。

## 交付物

1. 修改后的 `framework/agents/manager.py`（5 处必改点已落地）
2. 新增 7 个测试函数后的 `tests/test_agent_manager.py`
3. `openspec/changes/add-model-6-fertility-ml/.comet/task-5-report.md`（包含 RED 证据、GREEN 证据、既有测试影响、风险信号自报）
4. Git commit `feat(manager): AgentManager 集成 FertilityMLAgent 并新增按需过滤`（在 `feature/20260718/add-model-6-fertility-ml` 分支上）

## 验收标准

- [ ] 7 个新测试函数已落地到 `tests/test_agent_manager.py`
- [ ] RED 阶段实际输出已贴到 report
- [ ] GREEN 阶段 7 个新测试全部 PASS 的实际输出已贴到 report
- [ ] 既有测试影响（含 `test_manager_topological_sort_farmer` FAIL 的实际输出）已贴到 report
- [ ] `framework/agents/manager.py` 5 处必改点已落地
- [ ] commit 已创建（hash 记录到 report）
- [ ] 风险信号自报已填写
