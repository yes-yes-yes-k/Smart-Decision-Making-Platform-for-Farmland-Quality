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
            acid_summary = (upstream.get("acidification") or {}).get("answer", "未触发酸化模型")
            organic_summary = (upstream.get("organic_matter") or {}).get("answer", "未触发有机质模型")
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
            acid_summary = (upstream.get("acidification") or {}).get("answer", "")
            organic_summary = (upstream.get("organic_matter") or {}).get("answer", "")
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
