# Task 9: ComprehensiveImprovementAgent（模型6）

## 项目位置
这是 Comet Build 阶段 Task 9，在多智能体专业模型框架中实现第 6 个（最后一个）专业智能体。前序 Task 1-8 已完成 BaseAgent、MockDataLoader、RoleRouter、AgentManager 以及模型 1-5。当前 HEAD 提交为 `3617370`。

## 文件操作
- Create: `framework/agents/specialized/comprehensive_agent.py`
- Modify: `framework/agents/specialized/__init__.py`
- Test: `tests/test_agent_specialized.py`（追加模型6测试）

## 接口契约
- Consumes: `BaseAgent`、`MockDataLoader`；消费 context 中 `model-4`、`model-5` 的结果
- Produces: `ComprehensiveImprovementAgent` 类，注册为 `model-6`，`dependencies = ["model-4", "model-5"]`

## Step 1: 追加失败测试

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

## Step 2: 运行测试确认失败

Run: `python tests/test_agent_specialized.py`
Expected: FAIL，提示 `No module named 'framework.agents.specialized.comprehensive_agent'`

## Step 3: 实现 ComprehensiveImprovementAgent

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

## Step 4: 更新子包 __init__.py

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

## Step 5: 运行测试确认通过

Run: `python tests/test_agent_specialized.py`
Expected: PASS，输出 `所有专业智能体测试通过！`

## Step 6: 重新运行 Manager 测试以确认真实智能体被加载

Run: `python tests/test_agent_manager.py`
Expected: PASS（应仍通过，6 个真实智能体全部加载，`_StubAgent` 不再被使用）

## Step 7: Commit

```bash
git add framework/agents/specialized/comprehensive_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agents): 实现 ComprehensiveImprovementAgent（模型6）"
```

## Global Constraints

- 所有智能体输出 SHALL 包含 `simulated: True` 标记
- 所有智能体 SHALL 实现 `BaseAgent` 的 `execute(task)` 和 `answer_question(question, context)` 两个方法
- `execute` 返回 `{"status": "ok"|"error", "result": {...}, "metadata": {"simulated": True}}`
- `answer_question` 返回 `{"answer": str, "evidence": list, "confidence": float, "simulated": True}`
- 智能体注册键为 `model-6`，`dependencies = ["model-4", "model-5"]`
- 不引入新的第三方依赖
- 测试沿用"脚本式测试"风格（`assert` + `print` + `if __name__ == "__main__":`）
- 测试运行命令为 `python tests/test_agent_specialized.py` 和 `python tests/test_agent_manager.py`
- TDD 模式：先写失败测试，运行确认 RED，再写实现，运行确认 GREEN

## 参考实现

参考 `framework/agents/specialized/organic_matter_agent.py`（模型5，Task 8 产物）的实现模式。本任务不同点：
- 模型6 有 `dependencies = ["model-4", "model-5"]`，需消费上游结果
- 使用模块级 `IMPROVEMENT_MEASURES` 措施库和辅助函数 `_extract_upstream_summary`、`_match_measures`
- `answer_question` 在 evidence 中包含 `priority_measures` 字段
