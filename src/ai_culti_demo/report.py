from __future__ import annotations

from typing import Any


DEFAULT_ACTIONS = [
    "核验核心字段映射和数据来源",
    "确认推荐图层是否可用于当前汇报场景",
    "在真实模型接入后复核诊断结论",
]


def build_report_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """将诊断结果整理为稳定、可拆解的汇报摘要。"""

    if diagnosis.get("status") != "ok":
        return {
            "status": "error",
            "error": {
                "code": "MISSING_DIAGNOSIS",
                "message": "需要传入成功的诊断结果",
            },
        }

    topic = diagnosis["topic"]
    findings = [
        {
            "title": "诊断主题",
            "content": f"{topic['name']} 已形成结构化结果。",
        },
        {
            "title": "来源追溯",
            "content": "结果包含数据目录、参考资产和运行时依赖说明。",
        },
    ]
    findings.extend(
        {"title": "判定依据", "content": item}
        for item in diagnosis.get("evidence", [])
    )

    return {
        "status": "ok",
        "diagnosis_id": diagnosis["diagnosis_id"],
        "area": diagnosis["area"],
        "summary": diagnosis["summary"],
        "findings": findings,
        "recommendations": diagnosis.get("recommendations", []),
        "actions": DEFAULT_ACTIONS,
        "source": {
            "diagnosis_topic": topic["id"],
            "recommended_layers": diagnosis.get("recommended_layers", []),
            "reliability": diagnosis.get("reliability", {}),
        },
    }
