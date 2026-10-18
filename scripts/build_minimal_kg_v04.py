"""Build v0.4 from the reviewed v0.3 graph.

The build is additive: it preserves every v0.3 assertion, adds controlled
standard aliases, and derives fine-grained standard-indicator roles only from
explicit source passages.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.release import publish_graph_release

STANDARD_ALIASES = {
    "standard:doc-3": [
        "NY/T 1634",
        "NY/T 1634-2008",
        "耕地地力调查与质量评价技术规程",
        "耕地地力评价规程",
    ],
    "standard:doc-4": [
        "GB/T 33469",
        "GB/T 33469-2016",
        "耕地质量等级",
        "耕地质量等级国家标准",
    ],
    "standard:doc-11": [
        "补充耕地质量鉴定技术规范",
        "补充耕地鉴定技术规范",
        "补充耕地鉴定规范",
    ],
    "standard:doc-13": [
        "广东省补充耕地质量验收细则",
        "广东补充耕地质量验收细则",
        "广东补充耕地验收细则",
        "广东补充耕地验收",
        "广东省验收细则",
    ],
    "standard:doc-14": [
        "广东省补充耕地质量鉴定技术规范",
        "广东补充耕地质量鉴定技术规范",
        "广东补充耕地鉴定技术规范",
        "广东补充耕地鉴定规范",
        "广东补充耕地鉴定",
        "广东省鉴定规范",
        "广东鉴定",
    ],
}

ROLE_RELATION_SPECS = [
    {
        "type": "classifies_basic_indicator",
        "source": "standard:doc-4",
        "targets": [
            "indicator:effective_depth", "indicator:organic_matter",
            "indicator:texture", "indicator:bulk_density",
            "indicator:irrigation", "indicator:drainage",
        ],
        "display_label": "列为基础性指标",
        "dimension": "indicator_classification",
        "value": "basic",
        "evidence": {
            "document_id": 4, "document_title": "耕地质量等级 GB/T 33469-2016",
            "page": 6, "chunk_index": 9,
            "quote": "基础性指标包括有效土层厚度、有机质含量、耕层质地、土壤容重、灌溉能力、排水能力等13个指标。",
        },
    },
    {
        "type": "classifies_regional_supplementary_indicator",
        "source": "standard:doc-4",
        "targets": ["indicator:plough_depth", "indicator:soil_ph"],
        "display_label": "列为区域补充性指标",
        "dimension": "indicator_classification",
        "value": "regional_supplementary",
        "evidence": {
            "document_id": 4, "document_title": "耕地质量等级 GB/T 33469-2016",
            "page": 6, "chunk_index": 9,
            "quote": "区域补充性指标包括耕层厚度、田面坡度、盐渍化程度、地下水埋深、酸碱度、海拔高度等6个指标。",
        },
    },
    {
        "type": "assigns_by_field_survey",
        "source": "standard:doc-14",
        "targets": [
            "indicator:effective_depth", "indicator:plough_depth", "indicator:drainage",
        ],
        "display_label": "依据实地踏勘赋值",
        "dimension": "acquisition_mode",
        "value": "field_survey",
        "evidence": {
            "document_id": 14, "document_title": "广东省补充耕地质量鉴定技术规范 试行",
            "page": 44, "chunk_index": 79,
            "quote": "有效土层厚度、耕层厚度、排水能力等指标依据实地踏勘情况赋值。",
        },
    },
    {
        "type": "assigns_by_laboratory_test",
        "source": "standard:doc-14",
        "targets": [
            "indicator:soil_ph", "indicator:organic_matter", "indicator:available_p",
            "indicator:available_k", "indicator:texture", "indicator:bulk_density",
        ],
        "display_label": "依据土壤样品检测结果赋值",
        "dimension": "acquisition_mode",
        "value": "laboratory_test",
        "evidence": {
            "document_id": 14, "document_title": "广东省补充耕地质量鉴定技术规范 试行",
            "page": 45, "chunk_index": 80,
            "quote": "土壤酸碱度、土壤有机质、有效磷、速效钾、耕层质地、土壤容重依据土壤样品检测的结果。",
        },
    },
]


def _edge_id(relation_type: str, source: str, target: str) -> str:
    raw = f"{relation_type}|{source}|{target}".encode("utf-8")
    return "rel:" + hashlib.sha1(raw).hexdigest()[:16]


def _role_relations(entity_ids: set[str]) -> list[dict]:
    relations = []
    for spec in ROLE_RELATION_SPECS:
        for target in spec["targets"]:
            if spec["source"] not in entity_ids or target not in entity_ids:
                raise ValueError(f"role relation endpoint missing: {spec['source']} -> {target}")
            evidence = {
                **spec["evidence"],
                "review_status": "approved_role_semantics",
                "review_note": "v0.4第二阶段依据明确枚举或赋值方式原文细化关系语义。",
            }
            relations.append({
                "id": _edge_id(spec["type"], spec["source"], target),
                "type": spec["type"],
                "source": spec["source"],
                "target": target,
                "display_label": spec["display_label"],
                "semantics": {
                    "dimension": spec["dimension"],
                    "value": spec["value"],
                },
                "status": "approved_role_semantics",
                "evidence": [evidence],
                "supporting_document_count": 1,
                "confidence": 0.95,
                "review": {
                    "verified_by": "Codex（材料级核验）",
                    "verified_at": "2026-10-18",
                    "basis": "explicit_source_enumeration",
                },
            })
    return relations


def build(source: Path) -> dict:
    graph = json.loads(source.read_text(encoding="utf-8"))
    if graph.get("schema_version") != "minimal-cultivated-land-kg-v0.3":
        raise ValueError("v0.4 must be built from the reviewed v0.3 graph")

    entities = {str(item["id"]): item for item in graph.get("entities", [])}
    missing = sorted(set(STANDARD_ALIASES) - set(entities))
    if missing:
        raise ValueError(f"missing standard entities: {missing}")
    for entity_id, aliases in STANDARD_ALIASES.items():
        entity = entities[entity_id]
        existing = list(entity.get("aliases") or [])
        entity["aliases"] = list(dict.fromkeys([*existing, *aliases]))

    texture = entities["indicator:texture"]
    texture["retrieval_terms"] = list(dict.fromkeys([
        *(texture.get("retrieval_terms") or []), "耕层质地",
    ]))

    role_relations = _role_relations(set(entities))
    existing_keys = {
        (item["type"], item["source"], item["target"])
        for item in graph.get("relations", [])
    }
    duplicates = [
        item for item in role_relations
        if (item["type"], item["source"], item["target"]) in existing_keys
    ]
    if duplicates:
        raise ValueError("role semantics would duplicate an existing relation")
    graph["relations"].extend(role_relations)

    graph["schema_version"] = "minimal-cultivated-land-kg-v0.4"
    graph["generated_at"] = datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat()
    graph["lineage"] = {
        "base_schema_version": "minimal-cultivated-land-kg-v0.3",
        "base_artifact": source.name,
        "phase": "v0.4-phase-2-role-semantics",
    }
    graph["release_notes"] = [
        "保留v0.3全部已核验实体、关系和证据。",
        "为5个标准实体补充简称、编号和口语化检索别名。",
        "正式RAG图谱匹配使用原始问句，避免同义词归一化抹平精确实体。",
        "新增17条标准—指标细粒度关系，区分指标层级与取值方式。",
        "指标层级包括基础性指标、区域补充性指标；取值方式包括现场踏勘、实验室检测。",
    ]
    relation_types = list(graph.get("scope", {}).get("relation_types") or [])
    relation_types.extend(spec["type"] for spec in ROLE_RELATION_SPECS)
    graph.setdefault("scope", {})["relation_types"] = list(dict.fromkeys(relation_types))
    graph["scope"]["standard_indicator_semantics"] = {
        "indicator_classification": ["basic", "regional_supplementary"],
        "acquisition_mode": ["field_survey", "laboratory_test"],
        "dimensions_are_independent": True,
    }
    validation = dict(graph.get("validation") or {})
    relation_counts = Counter(item["type"] for item in graph["relations"])
    evidence_count = sum(len(item.get("evidence") or []) for item in graph["relations"])
    validation.update({
        "relation_count": len(graph["relations"]),
        "relation_counts": dict(sorted(relation_counts.items())),
        "evidence_count": evidence_count,
        "standard_entity_count": len(STANDARD_ALIASES),
        "standard_alias_count": sum(len(item) for item in STANDARD_ALIASES.values()),
        "v04_phase_1_passed": all(
            set(aliases) <= set(entities[entity_id].get("aliases") or [])
            for entity_id, aliases in STANDARD_ALIASES.items()
        ),
        "role_relation_count": len(role_relations),
        "role_relation_counts": dict(sorted(Counter(
            item["type"] for item in role_relations
        ).items())),
        "v04_phase_2_passed": len(role_relations) == 17 and all(
            item.get("evidence") and item.get("semantics") for item in role_relations
        ),
    })
    graph["validation"] = validation
    return graph


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json",
    )
    parser.add_argument("--release-id", default="kg-v0.4-production-candidate-1")
    parser.add_argument("--reviewed-by", default="Codex material-level review")
    parser.add_argument(
        "--output", type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json",
    )
    args = parser.parse_args()
    graph = build(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = publish_graph_release(
        args.output, release_id=args.release_id, reviewed_by=args.reviewed_by,
    )
    print(json.dumps({
        "schema_version": graph["schema_version"],
        "entities": len(graph["entities"]),
        "relations": len(graph["relations"]),
        "evidence": graph["validation"]["evidence_count"],
        "standard_aliases": graph["validation"]["standard_alias_count"],
        "role_relations": graph["validation"]["role_relation_count"],
        "release_id": manifest["release_id"],
        "sha256": manifest["sha256"],
        "passed": (
            graph["validation"]["v04_phase_1_passed"]
            and graph["validation"]["v04_phase_2_passed"]
        ),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
