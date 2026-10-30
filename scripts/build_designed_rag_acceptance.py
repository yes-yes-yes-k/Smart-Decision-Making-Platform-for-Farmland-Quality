"""Build a frozen, designed RAG acceptance set from reviewed v0.3 relations."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph import assess_graph_claim  # noqa: E402


# Questions and answers are manually phrased. Relation IDs are resolved against
# the reviewed graph so a stale or mistyped label fails the build.
SUPPORTED = (
    # 障碍因素—改良措施（13）
    ("措施-01", "改良措施", "地块土壤有机质持续下降，保护性耕作是否有材料依据？", "有。现有材料支持用保护性耕作应对有机质不足。", "rel:c091fea7959dbdf2", ("保护性耕作", "有机质不足")),
    ("措施-02", "改良措施", "土体紧实、耕作阻力明显增大时，深松能否作为针对性措施？", "可以。经核验关系支持深松用于改善土壤板结问题。", "rel:0fa82c25f87b948b", ("深松", "土壤板结")),
    ("措施-03", "改良措施", "坡耕地表土流失明显，资料是否支持采用深松深耕进行改良？", "支持。材料把深松深耕作为土壤侵蚀治理相关措施。", "rel:c00808f7cccaa063", ("深松深耕", "土壤侵蚀")),
    ("措施-04", "改良措施", "低洼田块排水不畅并出现渍害，应优先考虑哪类工程改良？", "应优先考虑排灌工程改良，用于改善排水不良和渍害风险。", "rel:0f4be5e25d694ab8", ("排灌工程改良", "排水不良")),
    ("措施-05", "改良措施", "配方施肥除了平衡养分，对酸化土壤是否也有调控依据？", "有。当前核验材料支持测土配方施肥用于土壤酸化调控。", "rel:30f42f9a2778f4fb", ("测土配方施肥", "土壤酸化")),
    ("措施-06", "改良措施", "检测显示土壤养分不足时，测土配方施肥是否属于有据可查的措施？", "是。图谱中的正式关系支持用测土配方施肥应对养分缺乏。", "rel:e2259384941ce3ea", ("测土配方施肥", "养分缺乏")),
    ("措施-07", "改良措施", "氮磷钾比例不协调的田块，为什么建议采用测土配方施肥？", "因为核验材料支持测土配方施肥针对养分失衡，通过平衡施肥避免养分过剩或匮乏。", "rel:fe3116ba788a3738", ("测土配方施肥", "养分失衡")),
    ("措施-08", "改良措施", "有机质偏低的耕地能否通过种植并翻压绿肥来培肥？", "可以。现有证据支持绿肥种植用于改善有机质不足。", "rel:f3690c33ee8dc897", ("绿肥种植", "有机质不足")),
    ("措施-09", "改良措施", "红壤酸化地块最常见且有正式证据支持的调酸措施是什么？", "施用石灰是当前材料明确支持的土壤酸化调控措施。", "rel:058b3641c36a3a8c", ("施用石灰", "土壤酸化")),
    ("措施-10", "改良措施", "对于已经出现板结和退化的地块，免耕是否被材料列为可选措施？", "是。核验材料支持免耕用于土壤板结和退化问题。", "rel:810e8d511a70cd3e", ("免耕", "土壤板结")),
    ("措施-11", "改良措施", "土壤肥力不足时，增施有机肥与养分缺乏之间有什么正式关系？", "正式关系表明增施有机肥可用于应对养分缺乏。", "rel:33ff419a3c78e3ed", ("增施有机肥", "养分缺乏")),
    ("措施-12", "改良措施", "酸化问题较重时，土壤调理剂能否作为改良选项？", "可以。当前资料支持施用土壤调理剂作为土壤酸化的改良选项。", "rel:e97eb40d2da004f3", ("施用土壤调理剂", "土壤酸化")),
    ("措施-13", "改良措施", "秸秆还田与缓解土壤酸化之间是否存在已核验关系？", "存在。v0.3 中有秸秆还田针对土壤酸化的正式证据关系。", "rel:369ee758119f6ca4", ("秸秆还田", "土壤酸化")),

    # 障碍—指标（5）
    ("诊断-01", "障碍诊断", "怀疑耕层板结时，应重点查看哪个土壤物理指标？", "应重点查看土壤容重；现有材料用容重表征土壤板结。", "rel:a7fa385a7d0a486a", ("土壤板结", "土壤容重")),
    ("诊断-02", "障碍诊断", "保肥能力差并伴随养分不足时，阳离子交换量能否用于辅助判断？", "可以。阳离子交换量偏低可作为养分缺乏的表征指标之一。", "rel:2f13738db223ce87", ("养分缺乏", "阳离子交换量")),
    ("诊断-03", "障碍诊断", "判断耕地是否存在养分缺乏，为什么需要关注全氮？", "因为材料将全氮列为养分缺乏的表征指标，并给出了相关障碍阈值证据。", "rel:849ac8d18ab20557", ("养分缺乏", "全氮")),
    ("诊断-04", "障碍诊断", "田块经常积水时，哪个能力指标可直接反映排水不良？", "排水能力可用于表征排水不良。", "rel:3d1f6d884a25aa5a", ("排水不良", "排水能力")),
    ("诊断-05", "障碍诊断", "耕作层越来越薄，应以哪个厚度指标判断耕层变浅？", "应关注耕层厚度；该指标用于表征耕层变浅。", "rel:e29748d3e2d538e9", ("耕层变浅", "耕层厚度")),

    # 措施—指标（1）
    ("指标改善-01", "指标改善", "采用客土改良后，最直接改善的土层厚度指标是什么？", "现有证据支持客土改良增加有效土层厚度。", "rel:5607979760e1c0f4", ("客土改良", "有效土层厚度")),

    # 标准纳入指标（9）
    ("标准指标-01", "标准指标", "《补充耕地质量鉴定技术规范（试行）》是否要求关注有效土层厚度？", "是。该规范把有效土层厚度列入农业生产符合性指标。", "rel:7b6bc685264abbf9", ("补充耕地质量鉴定技术规范", "有效土层厚度")),
    ("标准指标-02", "标准指标", "广东补充耕地验收时，有效土层厚度是不是农业生产符合性评价指标？", "是。广东省补充耕地质量验收细则将有效土层厚度列为符合性评价指标。", "rel:99e721a06ccf4433", ("广东省验收细则", "有效土层厚度")),
    ("标准指标-03", "标准指标", "广东补充耕地验收细则是否把土壤有机质纳入评价？", "是。该验收细则将土壤有机质纳入农业生产符合性评价。", "rel:f9c88c11bd6694ff", ("广东省验收细则", "土壤有机质")),
    ("标准指标-04", "标准指标", "广东补充耕地鉴定规范中是否包含有效土层厚度这一项？", "包含。有效土层厚度属于该规范的农业生产符合性指标。", "rel:86c8fa5cc3cd0353", ("广东省鉴定规范", "有效土层厚度")),
    ("标准指标-05", "标准指标", "按广东补充耕地鉴定规范开展评价时，需要纳入土壤有机质吗？", "需要。规范将土壤有机质含量列入农业生产符合性指标。", "rel:a25189da93c4f527", ("广东省鉴定规范", "土壤有机质")),
    ("标准指标-06", "标准指标", "广东补充耕地鉴定的检测指标里有没有土壤酸碱度？", "有。土壤pH（酸碱度）被列入相关检测指标。", "rel:f1d13520fe4de90e", ("广东省鉴定规范", "土壤pH")),
    ("标准指标-07", "标准指标", "依据 GB/T 33469 评价耕地质量时，要不要考虑排水能力？", "要。排水能力属于 GB/T 33469 的耕地质量评价指标。", "rel:044127b8e4d59456", ("GB/T 33469", "排水能力")),
    ("标准指标-08", "标准指标", "GB/T 33469 的指标体系是否覆盖农田灌溉能力？", "覆盖。灌溉能力被纳入 GB/T 33469 的评价指标体系。", "rel:81b176bb7989c3eb", ("GB/T 33469", "灌溉能力")),
    ("标准指标-09", "标准指标", "耕层厚度在 GB/T 33469 中属于需要考虑的补充指标吗？", "是。耕层厚度被列为 GB/T 33469 的区域补充性指标。", "rel:5e88a7f9ebc436e2", ("GB/T 33469", "耕层厚度")),

    # 检测方法（8）
    ("检测-01", "检测方法", "补充耕地质量鉴定时，速效钾检测应追溯哪项农业行业标准？", "规范引用 NY/T 889 作为土壤速效钾和缓效钾含量的测定依据。", "rel:b5915f818902e6ad", ("速效钾", "NY/T 889")),
    ("检测-02", "检测方法", "补充耕地鉴定中的有效磷测定应查哪个标准分册？", "应查 NY/T 1121.7，即土壤检测第7部分：土壤有效磷的测定。", "rel:bb6e93083cdb2f35", ("有效磷", "NY/T 1121.7")),
    ("检测-03", "检测方法", "补充耕地质量鉴定采用什么标准测定土壤容重？", "规范引用 NY/T 1121.4 作为土壤容重测定依据。", "rel:e72f5987e2b800d8", ("土壤容重", "NY/T 1121.4")),
    ("检测-04", "检测方法", "补充耕地鉴定材料中，土壤有机质测定对应哪一部分标准？", "对应 NY/T 1121.6，即土壤检测第6部分：土壤有机质的测定。", "rel:c5c26498c75036d1", ("土壤有机质", "NY/T 1121.6")),
    ("检测-05", "检测方法", "需要测定耕层土壤机械组成时，规范引用哪项方法？", "规范引用 NY/T 1121.3，即土壤检测第3部分：土壤机械组成的测定。", "rel:587379790746229b", ("土壤质地", "NY/T 1121.3")),
    ("检测-06", "检测方法", "广东补充耕地鉴定中的土壤pH应按哪项标准测定？", "应按 NY/T 1121.2（土壤检测第2部分：土壤pH的测定）执行。", "rel:6b90980691d544af", ("土壤pH", "NY/T 1121.2")),
    ("检测-07", "检测方法", "GB/T 33469 是否提供土壤容重的规范性测定依据？", "是。GB/T 33469 的规范性附录包含土壤容重测定内容。", "rel:e2168ef49d3eccd5", ("GB/T 33469", "土壤容重")),
    ("检测-08", "检测方法", "广东补充耕地鉴定中，排水能力是实验室检测还是现场赋值？", "材料说明排水能力等指标依据实地踏勘情况赋值。", "rel:41e5eb61530d038c", ("排水能力", "实地踏勘")),

    # 标准判定依据（1）
    ("依据-01", "标准依据", "按照 NY/T 1634 判断盐碱化程度时，应以什么信息作为依据？", "应依据土样检测结果判断盐碱化程度。", "rel:d557f9945967ab07", ("NY/T 1634", "土样检测")),
)


COUNTERFACTUAL = (
    ("反事实-01", "施用石灰能直接作为土壤盐渍化治理措施吗？", "当前核验图谱不支持“施用石灰—土壤盐渍化”关系；材料明确支持的是施用石灰用于土壤酸化调控。", ("施用石灰", "土壤盐渍化")),
    ("反事实-02", "现场想用绿肥种植处理土壤板结，这种措施与障碍的对应关系成立吗？", "当前核验材料不支持“绿肥种植—土壤板结”关系；绿肥种植已有证据支持的用途是改善有机质不足。", ("绿肥种植", "土壤板结")),
    ("反事实-03", "排灌工程改良是否用于解决养分缺乏？", "当前图谱不支持“排灌工程改良—养分缺乏”关系；排灌工程已有正式证据支持的是改善排水不良。", ("排灌工程改良", "养分缺乏")),
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _max_similarity(question: str, gold_questions: list[str]) -> float:
    source = _normalise(question)
    return max(
        (SequenceMatcher(None, source, _normalise(item)).ratio() for item in gold_questions),
        default=0.0,
    )


def build(graph: dict, gold: dict) -> dict:
    relations = {item["id"]: item for item in graph["relations"]}
    entities = {item["id"]: item for item in graph["entities"]}
    gold_questions = [item.get("question", "") for item in gold.get("questions", [])]
    questions = []

    for item_id, category, question, answer, relation_id, keywords in SUPPORTED:
        relation = relations.get(relation_id)
        if relation is None:
            raise ValueError(f"关系不存在: {relation_id}")
        similarity = _max_similarity(question, gold_questions)
        if similarity >= 0.85:
            raise ValueError(f"问题与旧金标准近重复: {item_id} similarity={similarity:.3f}")
        evidence = [{
            "document_id": row.get("document_id"),
            "document_title": row.get("document_title"),
            "page": row.get("page"),
            "chunk_index": row.get("chunk_index"),
        } for row in relation.get("evidence") or []]
        questions.append({
            "id": item_id,
            "category": category,
            "question": question,
            "expected_answer": answer,
            "answer_keywords": list(keywords),
            "expected_status": "supported",
            "expected_retrieval_mode": "graph_augmented",
            "expected_relation_id": relation_id,
            "expected_relation_type": relation["type"],
            "expected_source_entity": {
                "id": relation["source"], "name": entities[relation["source"]]["name"],
            },
            "expected_target_entity": {
                "id": relation["target"], "name": entities[relation["target"]]["name"],
            },
            "expected_evidence": evidence,
            "max_similarity_to_gold_v03": round(similarity, 4),
            "acceptance": {
                "relation_hit_at_5": None,
                "evidence_hit_at_5": None,
                "answer_grounded": None,
                "citation_correct": None,
                "review_note": "",
            },
        })

    for item_id, question, answer, keywords in COUNTERFACTUAL:
        assessment = assess_graph_claim(graph, question)
        if assessment.get("status") != "unsupported":
            raise ValueError(f"反事实未被判为 unsupported: {item_id} {assessment.get('status')}")
        similarity = _max_similarity(question, gold_questions)
        if similarity >= 0.85:
            raise ValueError(f"反事实与旧金标准近重复: {item_id} similarity={similarity:.3f}")
        alternatives = []
        for row in assessment.get("alternatives") or []:
            if row["relation_id"] not in alternatives:
                alternatives.append(row["relation_id"])
        questions.append({
            "id": item_id,
            "category": "反事实",
            "question": question,
            "expected_answer": answer,
            "answer_keywords": list(keywords),
            "expected_status": "unsupported",
            "expected_retrieval_mode": "graph_augmented",
            "expected_relation_id": None,
            "expected_relation_type": assessment.get("relation_type"),
            "expected_source_entity": {
                "id": assessment.get("source_entity_id"),
                "name": entities[assessment.get("source_entity_id")]["name"],
            },
            "expected_target_entity": {
                "id": assessment.get("target_entity_id"),
                "name": entities[assessment.get("target_entity_id")]["name"],
            },
            "expected_alternative_relation_ids": alternatives[:3],
            "expected_evidence": [],
            "max_similarity_to_gold_v03": round(similarity, 4),
            "acceptance": {
                "unsupported_detected": None,
                "false_affirmation_absent": None,
                "supported_alternative_cited": None,
                "review_note": "",
            },
        })

    return {
        "schema_version": "cultivated-land-designed-rag-acceptance-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": "cultivated_land_minimal_graph_v0.3.json",
        "provenance": "synthetic_questions_manually_designed_from_material_confirmed_relations",
        "independent_question_text_from": "gold_qa_v0.3.json",
        "question_count": len(questions),
        "status_counts": dict(sorted(Counter(q["expected_status"] for q in questions).items())),
        "category_counts": dict(sorted(Counter(q["category"] for q in questions).items())),
        "relation_type_counts": dict(sorted(Counter(q["expected_relation_type"] for q in questions).items())),
        "acceptance_rules": {
            "supported": "Top 5 命中预期关系和至少一条预期证据；答案包含关键词且引用位置正确。",
            "unsupported": "不得肯定不存在的关系；应说明当前核验材料不支持，并优先给出有证据的替代关系。",
            "pass_threshold": "supported 关系命中率>=90%，证据命中率>=90%，反事实无错误肯定率=100%。",
        },
        "questions": questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json")
    parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "gold_qa_v0.3.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "rag_acceptance_designed_v0.1.json")
    args = parser.parse_args()
    payload = build(
        json.loads(args.graph.read_text(encoding="utf-8")),
        json.loads(args.gold.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "question_count": payload["question_count"],
        "status_counts": payload["status_counts"],
        "category_counts": payload["category_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
