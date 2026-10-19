"""Build the evidence-complete v0.3 cultivated-land minimal graph.

v0.3 closes the reviewed v0.2 orphan entities with page-located evidence and
adds the missing measure -> indicator relation needed for precise modelling.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json"
OUTPUT = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
REPORT = ROOT / "artifacts" / "minimal_kg" / "design_hardening_report_v0.3.md"


def relation_id(relation_type: str, source: str, target: str) -> str:
    raw = f"{relation_type}|{source}|{target}".encode("utf-8")
    return "rel:" + hashlib.sha1(raw).hexdigest()[:16]


def evidence(document_id: int, page: int, chunk_index: int, quote: str) -> dict[str, Any]:
    titles = {
        15: "主要红壤区坡耕地土壤质量评价与障碍因子识别",
        29: "耕地质量等级提升的土地整治项目设计关键技术研究",
    }
    return {
        "document_id": document_id,
        "document_title": titles[document_id],
        "page": page,
        "chunk_index": chunk_index,
        "quote": quote,
        "review_status": "approved",
        "review_sample_id": None,
        "review_note": "v0.3孤立实体证据补强，按原文材料核验。",
    }


ADDITIONAL_ENTITY = {
    "id": "measure:drainage_project",
    "type": "measure",
    "name": "排灌工程改良",
    "aliases": ["排灌工程改良", "灌溉与排水工程"],
    "related_terms": [
        {"term": "排涝", "relation": "实施功能"},
        {"term": "完善排水", "relation": "实施描述"},
    ],
    "retrieval_terms": ["排水沟", "降低地下水位", "防止渍害", "内涝治理"],
    "status": "approved",
    "review": {
        "decision": "通过",
        "verified_by": "Codex（材料级核验）",
        "verified_at": "2026-10-15",
        "basis": "source_material",
    },
}


RELATION_ADDITIONS = [
    {
        "type": "characterized_by",
        "source": "obstacle:nutrient_deficiency",
        "target": "indicator:total_n",
        "evidence": [evidence(
            15, 7, 14,
            "采用障碍度诊断模型进一步分析发现，该区域坡耕地的障碍因素阈值为：土壤全氮、全磷和砾石含量分别小于1.15 g/kg、小于0.45 g/kg和大于2.62%时土壤存在障碍问题。",
        )],
        "review_note": "全氮低于材料阈值可表征养分障碍。",
    },
    {
        "type": "characterized_by",
        "source": "obstacle:nutrient_deficiency",
        "target": "indicator:cec",
        "evidence": [evidence(
            15, 7, 15,
            "坡耕地土壤养分障碍主要由全磷、阳离子交换量低下限制，主要分布于江西省、广东省和广西省。",
        )],
        "review_note": "阳离子交换量低下被原文直接列为养分障碍限制因素。",
    },
    {
        "type": "addresses",
        "source": "measure:green_manure",
        "target": "obstacle:low_organic_matter",
        "evidence": [evidence(
            29, 54, 115,
            "对于土壤有机质含量较低的问题，一般通过施用农家肥、秸秆还田、种植绿肥翻埋还田、施用土壤改良剂、测土培肥等技术可以有效提升土壤有机质含量。",
        )],
        "review_note": "绿肥种植直接对应有机质含量较低问题。",
    },
    {
        "type": "improves_indicator",
        "source": "measure:guest_soil",
        "target": "indicator:effective_depth",
        "evidence": [evidence(
            15, 59, 110,
            "通过深翻改土和引入客土等手段，改善土壤层次结构，提高土壤储水保肥能力，从而实质性增加有效土层厚度。",
        )],
        "review_note": "使用措施—指标改善关系，避免把客土强行绑定到单一障碍。",
    },
    {
        "type": "characterized_by",
        "source": "obstacle:shallow_plough",
        "target": "indicator:plough_depth",
        "evidence": [evidence(
            15, 59, 110,
            "可采用深松与深耕的耕作技术打破犁底层，从而提高土壤透气透水性能以及增加耕层厚度。",
        )],
        "review_note": "耕层浅薄以耕层厚度作为直接表征指标。",
    },
    {
        "type": "addresses",
        "source": "measure:formula_fertilization",
        "target": "obstacle:nutrient_imbalance",
        "evidence": [evidence(
            15, 59, 111,
            "采用测土配方施肥方法平衡施肥，无机肥与有机肥相结合，避免养分过剩或匮乏。",
        )],
        "review_note": "测土配方施肥通过避免养分过剩或匮乏来治理养分失衡。",
    },
    {
        "type": "addresses",
        "source": "measure:drainage_project",
        "target": "obstacle:poor_drainage",
        "evidence": [evidence(
            29, 57, 120,
            "灌溉与排水工程可改善灌溉条件、降低地下水位、排涝并防止农作物产生渍害。",
        )],
        "review_note": "排水工程的排涝、防渍功能直接对应排水不良。",
    },
    {
        "type": "characterized_by",
        "source": "obstacle:poor_drainage",
        "target": "indicator:drainage",
        "evidence": [evidence(
            29, 57, 120,
            "部分耕地因为平原地区地势低洼、排水不畅，导致土壤盐渍化和耕地内涝。",
        )],
        "review_note": "排水不畅和内涝用于识别排水不良障碍。",
    },
]


RETRIEVAL_TERM_ADDITIONS = {
    "obstacle:erosion": ["侵蚀退化", "坡地冲刷"],
    "measure:liming": ["调酸", "中和土壤酸性", "撒石灰"],
    "measure:no_till": ["少扰动耕作", "少扰动", "不翻耕"],
    "measure:soil_conditioner": ["调理剂", "调酸材料"],
    "measure:formula_fertilization": ["平衡施肥", "施肥管理", "按需施肥", "施肥怎么配"],
    "measure:deep_tillage": ["机械改土", "疏松耕层"],
    "measure:deep_loosening": ["破除犁底层", "机械松土"],
    "measure:organic_fertilizer": ["培肥", "补充肥力", "农家肥"],
    "measure:straw_return": ["提高缓冲能力", "农作物秸秆"],
    "measure:conservation_tillage": ["少耕", "减少有机质消耗"],
    "measure:green_manure": ["种绿肥", "绿肥翻埋", "绿肥"],
    "measure:guest_soil": ["引入客土", "掺土改良", "外面运土", "外来土掺入"],
    "measure:drainage_project": ["排灌工程", "排水工程"],
    "obstacle:compaction": ["板结", "土发硬", "地发硬", "硬邦邦", "犁底层太硬"],
    "obstacle:low_organic_matter": ["有机质消耗", "有机质少", "地力差"],
    "obstacle:nutrient_imbalance": ["肥料配比不合理", "施肥比例不合理", "养分过剩或匮乏", "施肥乱", "有的过量有的不足"],
    "obstacle:poor_drainage": ["排水不畅", "田里积水", "田里老积水", "容易内涝", "水排不出去"],
    "obstacle:shallow_plough": ["土层太薄", "耕层太薄", "耕层不够厚"],
    "indicator:cec": ["保肥能力", "交换容量"],
    "indicator:total_n": ["氮素水平", "氮含量"],
}


ALLOWED_DIRECTIONS = {
    "addresses": ("measure", "obstacle"),
    "improves_indicator": ("measure", "indicator"),
    "characterized_by": ("obstacle", "indicator"),
    "includes_indicator": ("standard", "indicator"),
    "prescribes_measurement": ("standard", "indicator"),
    "assessment_basis": ("standard", "obstacle"),
}


def build() -> dict[str, Any]:
    graph = json.loads(SOURCE.read_text(encoding="utf-8"))
    graph["schema_version"] = "minimal-cultivated-land-kg-v0.3"
    graph["generated_at"] = datetime.now(timezone.utc).isoformat()
    graph["source_graph"] = SOURCE.relative_to(ROOT).as_posix()
    graph["scope"]["relation_types"] = list(ALLOWED_DIRECTIONS)
    graph["scope"]["formal_entity_policy"] = (
        "正式实体必须至少参与一条带页码证据的正式关系；否则进入candidate_entities。"
    )

    entities = {entity["id"]: entity for entity in graph["entities"]}
    entities[ADDITIONAL_ENTITY["id"]] = dict(ADDITIONAL_ENTITY)
    for entity_id, terms in RETRIEVAL_TERM_ADDITIONS.items():
        entity = entities[entity_id]
        entity["retrieval_terms"] = list(dict.fromkeys([
            *(entity.get("retrieval_terms") or []), *terms,
        ]))
    graph["entities"] = sorted(entities.values(), key=lambda item: item["id"])

    relations = {
        (relation["type"], relation["source"], relation["target"]): relation
        for relation in graph["relations"]
    }
    audit = []
    for index, addition in enumerate(RELATION_ADDITIONS, 1):
        key = (addition["type"], addition["source"], addition["target"])
        review_id = f"V03-E{index:03d}"
        for item in addition["evidence"]:
            item["review_sample_id"] = review_id
        relation = {
            "id": relation_id(*key),
            "type": addition["type"],
            "source": addition["source"],
            "target": addition["target"],
            "status": "approved",
            "review_sample_ids": [review_id],
            "evidence": addition["evidence"],
            "supporting_document_count": len({
                item["document_id"] for item in addition["evidence"]
            }),
            "confidence": 0.9,
            "review": {
                "verified_by": "Codex（材料级核验）",
                "verified_at": "2026-10-15",
                "basis": "source_material",
                "note": addition["review_note"],
            },
        }
        relations[key] = relation
        audit.append({
            "sample_id": review_id,
            "relation_id": relation["id"],
            "decision": "通过",
            "note": addition["review_note"],
        })
    graph["relations"] = sorted(
        relations.values(), key=lambda item: (item["type"], item["source"], item["target"]),
    )
    graph.setdefault("review_audit", {})["v03_evidence_additions"] = audit
    graph["candidate_entities"] = []
    graph["validation"] = validate(graph)
    return graph


def validate(graph: dict[str, Any]) -> dict[str, Any]:
    entities = {entity["id"]: entity for entity in graph["entities"]}
    linked = set()
    invalid_endpoints = []
    invalid_directions = []
    relations_without_evidence = []
    relation_keys = []
    evidence_keys = []
    evidence_count = 0
    page_count = 0
    for relation in graph["relations"]:
        source = entities.get(relation["source"])
        target = entities.get(relation["target"])
        if source is None or target is None:
            invalid_endpoints.append(relation["id"])
            continue
        linked.update((relation["source"], relation["target"]))
        expected = ALLOWED_DIRECTIONS.get(relation["type"])
        if expected != (source["type"], target["type"]):
            invalid_directions.append(relation["id"])
        if not relation.get("evidence"):
            relations_without_evidence.append(relation["id"])
        relation_keys.append((relation["type"], relation["source"], relation["target"]))
        for item in relation.get("evidence") or []:
            evidence_count += 1
            page_count += item.get("page") is not None
            evidence_keys.append((
                relation["id"], item.get("document_id"), item.get("page"), item.get("quote"),
            ))
    orphan_entities = sorted(set(entities) - linked)
    duplicate_relation_count = len(relation_keys) - len(set(relation_keys))
    duplicate_evidence_count = len(evidence_keys) - len(set(evidence_keys))
    passed = not any((
        invalid_endpoints, invalid_directions, relations_without_evidence,
        orphan_entities, duplicate_relation_count, duplicate_evidence_count,
    ))
    return {
        "entity_count": len(entities),
        "entity_counts": dict(sorted(Counter(e["type"] for e in entities.values()).items())),
        "relation_count": len(graph["relations"]),
        "relation_counts": dict(sorted(Counter(r["type"] for r in graph["relations"]).items())),
        "evidence_count": evidence_count,
        "evidence_with_page_ratio": round(page_count / evidence_count, 4) if evidence_count else 0.0,
        "relations_without_evidence": relations_without_evidence,
        "invalid_endpoint_relations": invalid_endpoints,
        "invalid_direction_relations": invalid_directions,
        "duplicate_relation_count": duplicate_relation_count,
        "duplicate_evidence_count": duplicate_evidence_count,
        "orphan_entity_count": len(orphan_entities),
        "orphan_entities": orphan_entities,
        "passed": passed,
    }


def render_report(graph: dict[str, Any]) -> str:
    validation = graph["validation"]
    additions = graph["review_audit"]["v03_evidence_additions"]
    entities = {entity["id"]: entity for entity in graph["entities"]}
    lines = [
        "# 耕地质量最小知识图谱 v0.3 设计加固报告",
        "",
        "## 结论",
        "",
        f"- 正式实体：{validation['entity_count']} 个",
        f"- 正式关系：{validation['relation_count']} 条",
        f"- 页码证据：{validation['evidence_count']} 条，定位率 {validation['evidence_with_page_ratio']:.1%}",
        f"- 孤立正式实体：{validation['orphan_entity_count']} 个",
        f"- 自动校验：{'通过' if validation['passed'] else '未通过'}",
        "",
        "v0.3规定：没有证据关系的术语不得留在正式实体集合，应降级到 `candidate_entities`。本次7个v0.2孤立实体均找到可核验关系，因此未发生降级。",
        "",
        "## 新增关系",
        "",
        "| 关系 | 主体 | 客体 | 核验编号 |",
        "|---|---|---|---|",
    ]
    relation_index = {relation["id"]: relation for relation in graph["relations"]}
    labels = {
        "addresses": "治理/缓解",
        "characterized_by": "由指标表征",
        "improves_indicator": "改善指标",
    }
    for item in additions:
        relation = relation_index[item["relation_id"]]
        lines.append(
            f"| {labels.get(relation['type'], relation['type'])} | "
            f"{entities[relation['source']]['name']} | {entities[relation['target']]['name']} | "
            f"{item['sample_id']} |"
        )
    lines.extend([
        "",
        "## 设计调整",
        "",
        "- 新增 `improves_indicator`，表达措施直接改善指标，避免将措施强行挂接到不精确障碍。",
        "- 实体增加 `retrieval_terms`，仅用于口语问法召回，不作为同义词或事实关系。",
        "- 正式图谱增加无孤点约束、关系方向约束、证据页码约束和重复检查。",
        "- 新增排灌工程改良实体，用于区分排水不良与盐渍化、酸化等相近障碍。",
        "",
        "## 输出",
        "",
        f"- 图谱：`{OUTPUT.relative_to(ROOT).as_posix()}`",
        f"- 本报告：`{REPORT.relative_to(ROOT).as_posix()}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    graph = build()
    OUTPUT.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(render_report(graph), encoding="utf-8")
    print(json.dumps({
        "graph": str(OUTPUT),
        "report": str(REPORT),
        "validation": graph["validation"],
    }, ensure_ascii=False))
    return 0 if graph["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
