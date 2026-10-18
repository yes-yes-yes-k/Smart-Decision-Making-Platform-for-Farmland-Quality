"""Build realistic role-semantics acceptance questions for graph v0.4."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SUPPORTED_CASES = [
    ("角色-基础-01", "基础性指标", "按 GB/T 33469 做耕地质量评价时，有效土层厚度算全国都要看的基础指标吗？", "classifies_basic_indicator", "standard:doc-4", "indicator:effective_depth", "算。GB/T 33469 将有效土层厚度列为基础性指标。"),
    ("角色-基础-02", "基础性指标", "国标耕地质量等级里，有机质到底是基础项还是地方补充项？", "classifies_basic_indicator", "standard:doc-4", "indicator:organic_matter", "土壤有机质属于基础性指标，不是区域补充性指标。"),
    ("角色-基础-03", "基础性指标", "耕层质地在 GB/T 33469 中属于基础性指标吗？", "classifies_basic_indicator", "standard:doc-4", "indicator:texture", "属于。耕层质地被列入基础性指标。"),
    ("角色-基础-04", "基础性指标", "土壤容重是不是 GB/T 33469 的基础指标，还是只有部分地区才用？", "classifies_basic_indicator", "standard:doc-4", "indicator:bulk_density", "土壤容重是基础性指标。"),
    ("角色-基础-05", "基础性指标", "按耕地质量等级国标，灌溉能力是基础性指标吗？", "classifies_basic_indicator", "standard:doc-4", "indicator:irrigation", "是。灌溉能力属于基础性指标。"),
    ("角色-基础-06", "基础性指标", "排水能力在 GB/T 33469 里是基础指标还是区域补充指标？", "classifies_basic_indicator", "standard:doc-4", "indicator:drainage", "排水能力属于基础性指标。"),
    ("角色-区域-01", "区域补充性指标", "耕层厚度在 GB/T 33469 里属于区域补充性指标，对吗？", "classifies_regional_supplementary_indicator", "standard:doc-4", "indicator:plough_depth", "对。耕层厚度属于区域补充性指标。"),
    ("角色-区域-02", "区域补充性指标", "酸碱度在耕地质量等级国标里是不是按区域选用的补充指标？", "classifies_regional_supplementary_indicator", "standard:doc-4", "indicator:soil_ph", "是。酸碱度属于区域补充性指标。"),
    ("角色-踏勘-01", "现场踏勘指标", "广东补充耕地鉴定时，有效土层厚度要现场量还是送实验室？", "assigns_by_field_survey", "standard:doc-14", "indicator:effective_depth", "有效土层厚度依据实地踏勘情况赋值。"),
    ("角色-踏勘-02", "现场踏勘指标", "按广东补充耕地鉴定规范，耕层厚度的数据是现场踏勘赋值的吗？", "assigns_by_field_survey", "standard:doc-14", "indicator:plough_depth", "是。耕层厚度依据实地踏勘情况赋值。"),
    ("角色-踏勘-03", "现场踏勘指标", "广东鉴定时排水能力怎么取值，是看现场排水情况还是化验土样？", "assigns_by_field_survey", "standard:doc-14", "indicator:drainage", "排水能力依据实地踏勘情况赋值，不属于土样化验指标。"),
    ("角色-检测-01", "实验室检测指标", "广东鉴定规范里的土壤 pH，要靠实验室检测结果赋值吗？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:soil_ph", "需要。土壤酸碱度依据土壤样品检测结果赋值。"),
    ("角色-检测-02", "实验室检测指标", "广东补充耕地鉴定中，有机质是不是送样检测后再赋值？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:organic_matter", "是。土壤有机质依据土壤样品检测结果赋值。"),
    ("角色-检测-03", "实验室检测指标", "广东补充耕地鉴定的有效磷能现场看出来吗，规范要求怎么取值？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:available_p", "有效磷依据土壤样品检测结果赋值。"),
    ("角色-检测-04", "实验室检测指标", "广东鉴定规范对速效钾是现场估值，还是要求做土样检测？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:available_k", "速效钾依据土壤样品检测结果赋值。"),
    ("角色-检测-05", "实验室检测指标", "广东补充耕地鉴定里的耕层质地，最终赋值看实验室结果吗？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:texture", "耕层质地依据土壤样品检测结果赋值。"),
    ("角色-检测-06", "实验室检测指标", "土壤容重在广东补充耕地鉴定中是不是实验室检测指标？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:bulk_density", "是。土壤容重依据土壤样品检测结果赋值。"),
]

COUNTERFACTUAL_CASES = [
    ("角色-反事实-01", "GB/T 33469 把耕层厚度列为全国统一的基础性指标，对吗？", "classifies_basic_indicator", "standard:doc-4", "indicator:plough_depth", "不对。现有证据将耕层厚度列为区域补充性指标。"),
    ("角色-反事实-02", "耕地质量等级国标中，土壤酸碱度属于基础性指标吧？", "classifies_basic_indicator", "standard:doc-4", "indicator:soil_ph", "不是。土壤酸碱度属于区域补充性指标。"),
    ("角色-反事实-03", "GB/T 33469 里的排水能力是区域补充性指标吗？", "classifies_regional_supplementary_indicator", "standard:doc-4", "indicator:drainage", "不是。排水能力属于基础性指标。"),
    ("角色-反事实-04", "灌溉能力在耕地质量等级国标里只算区域补充项，对不对？", "classifies_regional_supplementary_indicator", "standard:doc-4", "indicator:irrigation", "不对。灌溉能力属于基础性指标。"),
    ("角色-反事实-05", "广东补充耕地鉴定的有效土层厚度要送实验室化验后赋值，对吗？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:effective_depth", "不对。有效土层厚度依据实地踏勘情况赋值。"),
    ("角色-反事实-06", "广东鉴定中的排水能力是实验室检测指标吗？", "assigns_by_laboratory_test", "standard:doc-14", "indicator:drainage", "不是。排水能力依据实地踏勘情况赋值。"),
    ("角色-反事实-07", "广东补充耕地鉴定时，土壤 pH 主要靠现场目测赋值吗？", "assigns_by_field_survey", "standard:doc-14", "indicator:soil_ph", "不是。土壤酸碱度依据土壤样品检测结果赋值。"),
    ("角色-反事实-08", "有效磷在广东补充耕地鉴定里可以靠现场踏勘直接赋值吗？", "assigns_by_field_survey", "standard:doc-14", "indicator:available_p", "不可以。有效磷依据土壤样品检测结果赋值。"),
]


def build(graph: dict) -> dict:
    relation_index = {
        (item["type"], item["source"], item["target"]): item
        for item in graph["relations"]
    }
    entity_index = {item["id"]: item for item in graph["entities"]}
    questions = []
    for item_id, category, question, relation_type, source, target, answer in SUPPORTED_CASES:
        relation = relation_index[(relation_type, source, target)]
        questions.append({
            "id": item_id,
            "category": category,
            "question": question,
            "question_style": "realistic_user_wording",
            "provenance": "designed_not_user_log",
            "expected_status": "supported",
            "expected_answer": answer,
            "expected_relation_id": relation["id"],
            "expected_relation_type": relation_type,
            "expected_source_entity": {"id": source, "name": entity_index[source]["name"]},
            "expected_target_entity": {"id": target, "name": entity_index[target]["name"]},
            "expected_semantics": relation["semantics"],
            "answer_keywords": [entity_index[target]["name"], relation["display_label"]],
        })
    for item_id, question, relation_type, source, target, answer in COUNTERFACTUAL_CASES:
        questions.append({
            "id": item_id,
            "category": "角色反事实",
            "question": question,
            "question_style": "realistic_user_wording",
            "provenance": "designed_not_user_log",
            "expected_status": "unsupported",
            "expected_answer": answer,
            "expected_relation_id": None,
            "expected_relation_type": relation_type,
            "expected_source_entity": {"id": source, "name": entity_index[source]["name"]},
            "expected_target_entity": {"id": target, "name": entity_index[target]["name"]},
            "answer_keywords": ["不", entity_index[target]["name"]],
        })
    return {
        "schema_version": "kg-v0.4-role-semantics-acceptance-v0.1",
        "generated_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "source_graph": "cultivated_land_minimal_graph_v0.4.json",
        "provenance_note": "问句为模拟真实用户表达，不冒充生产日志或真实用户历史记录。",
        "summary": {
            "question_count": len(questions),
            "supported_count": len(SUPPORTED_CASES),
            "counterfactual_count": len(COUNTERFACTUAL_CASES),
            "category_counts": dict(sorted(Counter(item["category"] for item in questions).items())),
        },
        "questions": questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "role_semantics_acceptance_v0.4.json")
    args = parser.parse_args()
    payload = build(json.loads(args.graph.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
