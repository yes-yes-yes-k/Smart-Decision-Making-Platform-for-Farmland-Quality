# Task 8: OrganicMatterAgent（模型5）

## 项目位置
这是 Comet Build 阶段 Task 8，在多智能体专业模型框架中实现第 5 个专业智能体。前序 Task 1-7 已完成 BaseAgent 基类、MockDataLoader、RoleRouter、AgentManager 以及模型 1-4 的专业智能体。

## 文件操作
- Create: `framework/agents/specialized/organic_matter_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型5测试）

## 接口契约
- Consumes: `BaseAgent`、`MockDataLoader`
- Produces: `OrganicMatterAgent` 类，注册为 `model-5`，`dependencies = []`

## Step 1: 追加失败测试

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

## Step 2: 运行测试确认失败

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.organic_matter_agent'`

## Step 3: 实现 OrganicMatterAgent

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

## Step 4: 更新子包 __init__.py

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

## Step 5: 运行测试确认通过

Run: `python tests/test_agent_specialized.py`
Expected: PASS

## Step 6: Commit

```bash
git add framework/agents/specialized/organic_matter_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 OrganicMatterAgent（模型5）"
```

## Global Constraints

- 所有智能体输出 SHALL 包含 `simulated: True` 标记
- 所有智能体 SHALL 实现 `BaseAgent` 的 `execute(task)` 和 `answer_question(question, context)` 两个方法
- `execute` 返回 `{"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}`
- `answer_question` 返回 `{"answer": str, "evidence": list, "confidence": float, "simulated": True}`
- 智能体注册键为 `model-5`，`dependencies = []`
- 不引入新的第三方依赖
- 测试沿用"脚本式测试"风格（`assert` + `print` + `if __name__ == "__main__":`）
- 测试运行命令为 `python tests/test_agent_specialized.py`
- TDD 模式：先写失败测试，运行确认 RED，再写实现，运行确认 GREEN

## 参考实现

参考 `framework/agents/specialized/acidification_agent.py`（模型4，Task 7 产物）的实现模式：
- 使用模块级 MOCK_INPUTS、规则常量
- `_compute(inputs)` 方法统一计算逻辑
- `execute` 和 `answer_question` 共用 `_compute`
- `answer_question` 按关键词分支返回不同 answer/evidence/confidence
