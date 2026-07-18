# Task 4 Brief — FertilityMLAgent 智能体

> **来源**：`docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md` 第 883-1270 行
> **OpenSpec 对应**：`openspec/changes/add-model-6-fertility-ml/tasks.md` 第 4.1-4.6 节
> **BASE commit**：`ddd374e`（Task 3 完成后的最新提交）

## Files

- Create: `framework/agents/specialized/fertility_ml_agent.py`
- Modify: `framework/agents/specialized/__init__.py`（新增 FertilityMLAgent 导入，保留 comprehensive_agent 导入——Task 6 会移除）
- Modify: `tests/test_agent_specialized.py`（在 `if __name__` 块之前新增 6 个测试函数）

## Interfaces

- **Consumes**: 
  - `model_6_execution`（Task 3 产物，from `framework.domain.other_models.model_6`）
  - `BaseAgent`（既有，`framework/agents/base.py`）
  - `MockDataLoader.mark_simulated`（既有，`framework/agents/mock_data.py`，签名 `mark_simulated(payload: Dict) -> Dict` 添加 `simulated: True` 标记）
- **Produces**: `FertilityMLAgent(BaseAgent)` 类，`model_id="model-6"`，`domain="fertility_ml"`，`dependencies=[]`。`execute(task)` 返回 `{status, result, metadata}` 结构；`answer_question(question, context)` 返回 `{answer, evidence, sources}` 结构，按 Dose/SOC/综合 三分支格式化。Task 5 `AgentManager._load_real_agents` 导入并实例化此类。

## 现有代码状态

### `framework/agents/specialized/__init__.py`（当前内容）

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

### `BaseAgent` 接口（`framework/agents/base.py`）

```python
class BaseAgent(ABC):
    def __init__(self, name: str, description: str, model_id: str, domain: str):
        self.name = name
        self.description = description
        self.model_id = model_id
        self.domain = domain
        self.dependencies: List[str] = []

    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]: ...

    @abstractmethod
    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]: ...
```

### `MockDataLoader.mark_simulated`（`framework/agents/mock_data.py`）

```python
@staticmethod
def mark_simulated(payload: Dict[str, Any]) -> Dict[str, Any]:
    """返回 payload 的副本并添加 simulated: True 标记。"""
    out = dict(payload)
    out["simulated"] = True
    return out
```

### `tests/test_agent_specialized.py` 结构

- 文件头部有 `sys.path.insert(0, ...)` 确保 `framework` 模块可导入
- 已有 18 个测试函数（覆盖 model-1 ~ model-6 的 ComprehensiveImprovementAgent）
- 第 216 行有 `if __name__ == "__main__":` 块，调用所有现有测试函数（含 comprehensive 测试，**这些将在 Task 6/7 中移除**）
- **新增的 FertilityMLAgent 测试不加入 `if __name__` 块**，仅通过 pytest 运行（因为 `monkeypatch` 参数在直接调用时会报错）

## 步骤

### Step 1: 在 `tests/test_agent_specialized.py` 末尾（`if __name__` 之前）新增 6 个 FertilityMLAgent 测试

```python
def test_fertility_ml_agent_execute_structure(monkeypatch):
    """execute 返回结构包含 status/result/metadata 三层"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    from framework.domain.other_models import model_6
    # mock model_6_execution 返回 success
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47，预测结果仅供参考",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    assert agent.model_id == "model-6"
    assert agent.dependencies == []
    result = agent.execute({"pH": 6.5})
    assert "status" in result
    assert "result" in result
    assert "metadata" in result
    assert result["result"]["soc_prediction"] == 12.5
    print("✓ FertilityMLAgent.execute 返回三层结构")


def test_fertility_ml_agent_answer_dose_keywords(monkeypatch):
    """问'施用量' → 仅返回 Dose 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我这块地需要施多少肥？", {"data": {"pH": 6.5}})
    assert "施肥" in out["answer"] or "t/ha" in out["answer"]
    # evidence 应包含 dose_prediction 但不应包含 soc_prediction
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "dose_prediction" in metrics
    assert "soc_prediction" not in metrics
    print("✓ FertilityMLAgent 施用量问题返回 Dose 预测")


def test_fertility_ml_agent_answer_soc_keywords(monkeypatch):
    """问'有机碳' → 仅返回 SOC 预测"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田有机碳含量多少？", {"data": {"pH": 6.5}})
    assert "SOC" in out["answer"] or "有机碳" in out["answer"]
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" not in metrics
    print("✓ FertilityMLAgent 有机碳问题返回 SOC 预测")


def test_fertility_ml_agent_answer_fertility_keywords(monkeypatch):
    """问'肥力' → 返回 SOC + Dose 综合诊断"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "success",
            "soc_prediction": 12.5,
            "soc_confidence": 0.91,
            "dose_prediction": 150.0,
            "dose_confidence": 0.47,
            "dose_warning": "Dose 模型 R²=0.47",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 6.5}})
    metrics = [e.get("metric") for e in out["evidence"]]
    assert "soc_prediction" in metrics
    assert "dose_prediction" in metrics
    print("✓ FertilityMLAgent 肥力问题返回综合诊断")


def test_fertility_ml_agent_answer_fallback_status(monkeypatch):
    """status=fallback → answer 标注'模型不可用'"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "fallback",
            "soc_prediction": 12.0,
            "soc_confidence": 0.3,
            "dose_prediction": 100.0,
            "dose_confidence": 0.3,
            "dose_warning": "模型不可用，返回训练集均值估算",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
            "fallback_reason": "model_file_missing",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {}})
    assert "模型不可用" in out["answer"] or "训练集均值" in out["answer"]
    print("✓ FertilityMLAgent fallback 时标注模型不可用")


def test_fertility_ml_agent_answer_rejected_status(monkeypatch):
    """status=rejected → answer 标注越界特征"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent
    monkeypatch.setattr(
        "framework.agents.specialized.fertility_ml_agent.model_6_execution",
        lambda data: {
            "status": "rejected",
            "reason": "input_out_of_range",
            "out_of_range_features": [
                {"feature": "pH", "value": 99.0, "valid_range": [3.0, 11.0]}
            ],
            "soc_prediction": None,
            "soc_confidence": 0.0,
            "dose_prediction": None,
            "dose_confidence": 0.0,
            "dose_warning": "输入值越界，未执行预测",
            "imputed_features": [],
            "imputation_applied": False,
            "model_version": "ETR_v1_20260713",
        }
    )
    agent = FertilityMLAgent()
    out = agent.answer_question("我的田肥力怎么样？", {"data": {"pH": 99.0}})
    assert "越界" in out["answer"] or "异常" in out["answer"]
    assert "pH" in out["answer"]
    assert out["evidence"] == []
    print("✓ FertilityMLAgent rejected 时标注越界特征")
```

**注意**：不要修改 `if __name__ == "__main__":` 块——新增测试仅通过 pytest 运行（monkeypatch 参数在直接调用时会报错）。

### Step 2: 运行测试确认失败

```bash
python -m pytest tests/test_agent_specialized.py -v -k "fertility_ml"
```

Expected: FAIL，`ModuleNotFoundError: No module named 'framework.agents.specialized.fertility_ml_agent'`。

### Step 3: 创建 `framework/agents/specialized/fertility_ml_agent.py`

```python
from __future__ import annotations
from typing import Any, Dict, List

from ..base import BaseAgent
from ..mock_data import MockDataLoader
from ...domain.other_models.model_6 import model_6_execution


# 肥力相关关键词（与 AgentManager.FERTILITY_KEYWORDS 保持一致）
FERTILITY_KEYWORDS = [
    "有机碳", "SOC", "soc",
    "施用量", "施肥量", "施肥", "Dose", "dose", "剂量", "施多少肥",
    "肥力", "综合肥力",
    "秸秆", "有机肥", "培肥",
]

# Dose 关键词（优先级 1）
DOSE_KEYWORDS = ["施用量", "施肥量", "Dose", "剂量", "施多少肥", "施肥"]

# SOC 关键词（优先级 2）
SOC_KEYWORDS = ["有机碳", "SOC"]


class FertilityMLAgent(BaseAgent):
    """模型6：基于 ML 的耕地肥力 SOC/Dose 预测。"""

    def __init__(self):
        super().__init__(
            name="FertilityMLAgent",
            description="基于 ML 的耕地肥力 SOC/Dose 预测",
            model_id="model-6",
            domain="fertility_ml",
        )
        self.dependencies = []  # 独立 ML 模型，不依赖 model-4/5

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """调用 model_6_execution 执行 ML 预测，包装为三层结构。"""
        result = model_6_execution(task or {})
        return MockDataLoader.mark_simulated({
            "status": result["status"],
            "result": {
                "soc_prediction": result["soc_prediction"],
                "soc_confidence": result["soc_confidence"],
                "dose_prediction": result["dose_prediction"],
                "dose_confidence": result["dose_confidence"],
                "dose_warning": result["dose_warning"],
                "imputed_features": result["imputed_features"],
                "imputation_applied": result["imputation_applied"],
            },
            "metadata": {
                "model_version": result["model_version"],
                "fallback_reason": result.get("fallback_reason"),
                "reason": result.get("reason"),
                "out_of_range_features": result.get("out_of_range_features"),
            },
        })

    def answer_question(self, question: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """按关键词优先级处理问答：Dose > SOC > 综合/默认。"""
        exec_result = self.execute(
            context.get("data", {}) or context.get("task", {}) or {}
        )
        pred = exec_result["result"]

        q_lower = question.lower()

        # 优先级 1：明确问 Dose / 施用量
        if any(kw.lower() in q_lower for kw in DOSE_KEYWORDS):
            return self._format_dose_only(pred, exec_result)

        # 优先级 2：明确问 SOC / 有机碳
        if any(kw.lower() in q_lower for kw in SOC_KEYWORDS):
            return self._format_soc_only(pred, exec_result)

        # 优先级 3：肥力 / 综合 / 其他
        return self._format_both(pred, exec_result)

    def _format_rejected(self, exec_result: Dict[str, Any]) -> Dict[str, Any]:
        """越界拒绝的统一格式化"""
        oor = exec_result["metadata"].get("out_of_range_features", [])
        oor_text = "; ".join([
            f"{f['feature']}={f['value']}（合法范围 {f['valid_range'][0]}-{f['valid_range'][1]}）"
            for f in oor
        ])
        return MockDataLoader.mark_simulated({
            "answer": f"输入值异常，无法预测。越界特征：{oor_text}。请检查输入后重试。",
            "evidence": [],
            "sources": [],
        })

    def _format_soc_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['soc_confidence']:.0%}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，您的土壤有机碳（SOC）预测值约 {pred['soc_prediction']:.2f} g/kg{confidence_text}",
            "evidence": [
                {"metric": "soc_prediction", "value": pred["soc_prediction"], "unit": "g/kg"},
                {"metric": "soc_confidence", "value": pred["soc_confidence"]},
            ],
            "sources": [],
        })

    def _format_dose_only(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        if exec_result["status"] == "fallback":
            confidence_text = "（模型不可用，返回训练集均值估算）"
        else:
            confidence_text = f"（置信度 {pred['dose_confidence']:.0%}，{pred['dose_warning']}）"

        return MockDataLoader.mark_simulated({
            "answer": f"基于 ML 预测，建议施肥量约 {pred['dose_prediction']:.2f} t/ha{confidence_text}",
            "evidence": [
                {"metric": "dose_prediction", "value": pred["dose_prediction"], "unit": "t/ha"},
                {"metric": "dose_confidence", "value": pred["dose_confidence"]},
            ],
            "sources": [],
        })

    def _format_both(self, pred: Dict[str, Any], exec_result: Dict[str, Any]) -> Dict[str, Any]:
        if exec_result["status"] == "rejected":
            return self._format_rejected(exec_result)

        imputation_note = (
            "\n（注：部分特征用训练集均值填充，已标注于 imputed_features）"
            if pred["imputation_applied"] else ""
        )
        fallback_note = (
            "\n（模型不可用，以上为训练集均值估算）"
            if exec_result["status"] == "fallback" else ""
        )

        return MockDataLoader.mark_simulated({
            "answer": (
                f"基于 ML 预测的综合肥力诊断：\n"
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

### Step 4: 更新 `framework/agents/specialized/__init__.py`

将文件内容替换为（在 `comprehensive_agent` 导入保留的情况下新增 `fertility_ml_agent` 导入——Task 6 会移除 comprehensive）：

```python
from .stability_risk_agent import StabilityRiskAgent
from .potential_agent import PotentialAssessmentAgent
from .problem_agent import ProblemIdentificationAgent
from .acidification_agent import AcidificationRemediationAgent
from .organic_matter_agent import OrganicMatterAgent
from .comprehensive_agent import ComprehensiveImprovementAgent
from .fertility_ml_agent import FertilityMLAgent

__all__ = [
    "StabilityRiskAgent",
    "PotentialAssessmentAgent",
    "ProblemIdentificationAgent",
    "AcidificationRemediationAgent",
    "OrganicMatterAgent",
    "ComprehensiveImprovementAgent",
    "FertilityMLAgent",
]
```

### Step 5: 运行 FertilityMLAgent 测试确认通过

```bash
python -m pytest tests/test_agent_specialized.py -v -k "fertility_ml"
```

Expected: 6 个测试全部 PASS。

### Step 6: 提交

```bash
git add framework/agents/specialized/fertility_ml_agent.py framework/agents/specialized/__init__.py tests/test_agent_specialized.py
git commit -m "feat(agent): 实现 FertilityMLAgent（Dose/SOC/综合三分支问答+fallback/rejected 格式化）"
```

## Global Constraints（摘自 plan）

- `FertilityMLAgent` 是薄包装，调用 `model_6_execution` 并处理结果格式化（不实现业务逻辑）
- `model_id="model-6"`、`domain="fertility_ml"`、`dependencies=[]`（独立 ML 模型，不依赖 model-4/5）
- 关键词优先级：Dose > SOC > 综合/默认
- fallback 时 answer 标注"模型不可用，返回训练集均值估算"
- rejected 时 answer 标注越界特征列表，evidence 为空
- Dose 单位 t/ha，SOC 单位 g/kg
- `execute` 返回三层结构 `{status, result, metadata}`，metadata 含 `model_version` + `fallback_reason`/`reason`/`out_of_range_features`
- `answer_question` 返回 `{answer, evidence, sources}`，evidence 含 metric/value/unit 字段
- 所有返回都通过 `MockDataLoader.mark_simulated` 添加 `simulated: True` 标记

## 注意事项

- **不删除 `comprehensive_agent` 导入**：Task 6 才会删除。本任务保留 `ComprehensiveImprovementAgent` 导入，确保既有测试不破坏
- **不修改 `if __name__` 块**：新增的 6 个 FertilityMLAgent 测试不加入 `if __name__` 块（monkeypatch 参数在直接调用时报错）。仅通过 pytest 运行
- **既有测试不破坏**：运行 `python -m pytest tests/test_agent_specialized.py -v`（全部测试）应仍 PASS（含 18 个既有 comprehensive 测试 + 6 个新 fertility_ml 测试 = 24 个 PASS）。如果既有测试有 FAIL，需要分析原因
- **import 路径**：`from ..base import BaseAgent`、`from ..mock_data import MockDataLoader`、`from ...domain.other_models.model_6 import model_6_execution`。注意 `...` 是三级相对路径（`fertility_ml_agent.py` → `specialized` → `agents` → `framework`，再 `framework.domain.other_models.model_6`）

## 风险信号预估（主会话预判，implementer 仍需自报）

- **跨模块协调**：弱命中（修改 `__init__.py` 影响 `manager.py` 的 import 路径，但本任务不修改 `manager.py`——Task 5 才修改）
- **API 变更**：弱命中（新增 public 类 `FertilityMLAgent`，但 `manager.py` 的 `_load_real_agents` 仍导入旧的 `ComprehensiveImprovementAgent`——Task 5 才切换）
- 其他信号（diff>200/并发/安全/数据迁移/DONE_WITH_CONCERNS）：不命中（diff 估约 250 行，但不超过 200 阈值——实际计数后可能命中）

按 `review_mode: standard`，如果 implementer 自报 diff>200 或跨模块命中 → 主会话将派发 reviewer。

## 报告契约

implementer 完成后写入 `openspec/changes/add-model-6-fertility-ml/.comet/subagent-reports/task-4-report.md`，包含：
1. **Status**: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED
2. **Commits**: commit hash + 简短描述
3. **测试摘要**: 
   - RED 阶段：N 个测试 FAIL（错误信息）
   - GREEN 阶段：6 个 fertility_ml 测试 PASS
   - 全量测试：24 个测试 PASS（18 既有 + 6 新增，确保不破坏既有测试）
4. **Concerns**: 任何顾虑
5. **风险信号自报**: 命中的风险信号列表
