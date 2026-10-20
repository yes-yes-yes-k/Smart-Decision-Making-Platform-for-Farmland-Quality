from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
GRAPH_V01 = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.1.json"
REVIEW_DATA = ROOT / "artifacts" / "minimal_kg" / "review_workbook_data.json"
GRAPH_V02 = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json"
REPORT_V02 = ROOT / "artifacts" / "minimal_kg" / "writeback_report_v0.2.md"

REVIEWED_AT = "2026-10-09"
VERIFIED_BY = "Codex（材料级核验）"

REJECTED_RELATION_SAMPLES = {
    "KG-038": "原文并列出现侵蚀、酸化和有机质下降，不能证明直接因果。",
    "KG-039": "原文仅并列养分缺乏、容重大和板结，不能证明影响关系。",
    "KG-040": "原文表达灌排改善可降低盐碱化，候选关系方向错误。",
    "KG-041": "原文表达灌排改善可降低盐碱化，候选关系方向错误。",
    "KG-042": "原文并列盐碱化治理与增加有机质，不能证明影响关系。",
    "KG-073": "原文说明容重过高影响养分分布，未证明本条候选方向。",
}
PASSED_RELATION_SAMPLES = {"KG-037"}

ENTITY_ALIASES: dict[str, list[str]] = {
    "indicator:texture": ["土壤质地", "耕层土壤质地"],
    "indicator:drainage": ["排水能力"],
    "indicator:irrigation": ["灌溉能力"],
    "indicator:plough_depth": ["耕层厚度"],
    "measure:conservation_tillage": ["保护性耕作"],
    "measure:guest_soil": ["客土改良"],
    "measure:soil_conditioner": ["施用土壤调理剂", "土壤调理剂"],
    "measure:formula_fertilization": ["测土配方施肥", "配方施肥"],
    "measure:deep_tillage": ["深松深耕"],
    "measure:straw_return": ["秸秆还田"],
    "measure:green_manure": ["绿肥种植", "种植绿肥"],
    "obstacle:nutrient_deficiency": ["养分缺乏", "养分不足"],
    "obstacle:erosion": ["土壤侵蚀"],
    "obstacle:compaction": ["土壤板结", "土壤紧实", "紧实化"],
    "obstacle:salinization": ["土壤盐渍化", "盐渍化"],
    "obstacle:acidification": ["土壤酸化", "酸化障碍"],
    "obstacle:poor_drainage": ["排水不良", "排涝困难"],
    "obstacle:shallow_plough": ["耕层变浅", "耕层浅薄"],
}

RELATED_TERMS: dict[str, list[dict[str, str]]] = {
    "indicator:texture": [{"term": "机械组成", "relation": "检测与表征概念"}],
    "indicator:drainage": [
        {"term": "排涝能力", "relation": "相关能力"},
        {"term": "排水条件", "relation": "条件描述"},
    ],
    "indicator:irrigation": [
        {"term": "灌溉保证率", "relation": "量化指标"},
        {"term": "灌溉保障率", "relation": "量化指标"},
    ],
    "indicator:plough_depth": [{"term": "有效耕层厚度", "relation": "限定指标"}],
    "measure:conservation_tillage": [
        {"term": "免耕", "relation": "下位措施"},
        {"term": "少耕", "relation": "下位措施"},
        {"term": "覆盖耕作", "relation": "下位措施"},
    ],
    "measure:guest_soil": [
        {"term": "客土置换", "relation": "具体实施方式"},
        {"term": "换土", "relation": "具体实施方式"},
    ],
    "measure:soil_conditioner": [
        {"term": "改土剂", "relation": "相关称谓"},
        {"term": "调理剂改良", "relation": "实施描述"},
    ],
    "measure:formula_fertilization": [{"term": "精准施肥", "relation": "相关上位技术"}],
    "measure:deep_tillage": [
        {"term": "深松", "relation": "组成措施"},
        {"term": "深耕", "relation": "组成措施"},
        {"term": "深翻", "relation": "深耕方式"},
    ],
    "measure:straw_return": [{"term": "腐熟还田", "relation": "实施方式"}],
    "measure:green_manure": [{"term": "绿肥还田", "relation": "后续工序"}],
    "obstacle:nutrient_deficiency": [
        {"term": "肥力不足", "relation": "更宽泛障碍"},
        {"term": "土壤贫瘠", "relation": "更宽泛障碍"},
    ],
    "obstacle:erosion": [
        {"term": "水土流失", "relation": "相关过程"},
        {"term": "表土流失", "relation": "表现"},
    ],
    "obstacle:compaction": [{"term": "容重过高", "relation": "表征指标"}],
    "obstacle:salinization": [
        {"term": "盐碱化", "relation": "组合概念"},
        {"term": "盐分障碍", "relation": "上位障碍"},
    ],
    "obstacle:acidification": [
        {"term": "pH偏低", "relation": "状态表现"},
        {"term": "酸性障碍", "relation": "障碍表现"},
    ],
    "obstacle:poor_drainage": [
        {"term": "渍害", "relation": "结果"},
        {"term": "涝害", "relation": "结果"},
    ],
    "obstacle:shallow_plough": [{"term": "有效土层不足", "relation": "相关但不同障碍"}],
}

NEW_ENTITIES = [
    {
        "id": "measure:deep_loosening",
        "type": "measure",
        "name": "深松",
        "aliases": ["深松"],
        "related_terms": [{"term": "深松深耕", "relation": "组合措施"}],
        "status": "approved_with_revision",
    },
    {
        "id": "measure:no_till",
        "type": "measure",
        "name": "免耕",
        "aliases": ["免耕"],
        "related_terms": [{"term": "保护性耕作", "relation": "上位措施"}],
        "status": "approved_with_revision",
    },
]

EVIDENCE_DECISIONS: dict[str, tuple[str, str]] = {
    "OM-001": ("通过", "原文直接说明施用石灰是耕地酸化治理手段。"),
    "OM-002": ("修改后通过", "收窄为土壤板结—深松。"),
    "OM-003": ("驳回", "秸秆还田针对养分类障碍，不是土壤侵蚀。"),
    "OM-004": ("通过", "原文明确深松深耕可减轻侵蚀退化。"),
    "OM-005": ("驳回", "绿肥针对有机质偏低，板结对应免耕和深松。"),
    "OM-006": ("驳回", "调理剂针对酸化，水土流失对应水利与防护林。"),
    "OM-007": ("驳回", "秸秆还田用于提高有机质，不直接对应板结。"),
    "OM-008": ("驳回", "摘要未出现保护性耕作治理盐渍化证据。"),
    "OM-009": ("驳回", "绿肥用于提高保肥性能，未直接对应酸化治理。"),
    "OM-010": ("驳回", "秸秆还田对应贫瘠化，未明确对应盐渍化。"),
    "OM-011": ("通过", "酸化限制型措施段明确支持秸秆还田。"),
    "OM-012": ("驳回", "增施有机肥对应酸化治理，不是侵蚀治理。"),
    "OM-013": ("驳回", "增施有机肥对应贫瘠化，未明确对应盐渍化。"),
    "OM-014": ("驳回", "有机肥用于改善保水性能，未直接证明治理酸化。"),
    "OM-015": ("通过", "酸化限制型措施段明确支持测土配方施肥。"),
    "OM-016": ("驳回", "深松深耕属于前一段薄化/侵蚀措施。"),
    "OM-017": ("驳回", "未直接形成保护性耕作治理侵蚀结论。"),
    "OM-018": ("通过", "原文直接表述土壤调理剂治理酸化。"),
    "OM-019": ("驳回", "秸秆还田出现在土壤薄化措施段。"),
    "OM-020": ("驳回", "测土配方施肥对应养分管理，不是侵蚀治理。"),
    "OM-021": ("驳回", "测土配方施肥属于养分限制措施。"),
    "OM-022": ("驳回", "原文明确石灰用于酸性土壤，候选关系错误。"),
    "OM-023": ("驳回", "石灰对应酸化治理，与侵蚀仅相邻。"),
    "OM-024": ("修改后通过", "收窄为土壤板结—免耕。"),
    "OM-025": ("驳回", "仅为参考文献条目。"),
    "OM-026": ("驳回", "绿肥位于酸化治理段，不能证明治理侵蚀。"),
    "OM-027": ("修改后通过", "改为保护性耕作有助于缓解有机质不足。"),
    "OM-028": ("通过", "原文将肥力障碍与测土配方施肥直接对应。"),
    "OM-029": ("通过", "原文将肥力障碍与增施有机肥直接对应。"),
    "OM-030": ("修改后通过", "收窄为土壤板结—深松。"),
}

SUPPLEMENT_EDGE_OVERRIDES = {
    "OM-002": ("measure:deep_loosening", "obstacle:compaction"),
    "OM-024": ("measure:no_till", "obstacle:compaction"),
    "OM-027": ("measure:conservation_tillage", "obstacle:low_organic_matter"),
    "OM-030": ("measure:deep_loosening", "obstacle:compaction"),
}

_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def normalise(text: str) -> str:
    return _SPACE.sub(" ", text or "").strip()


def compact(text: str) -> str:
    return _PUNCT.sub("", text or "").lower()


def edge_id(relation_type: str, source: str, target: str) -> str:
    raw = f"{relation_type}|{source}|{target}".encode("utf-8")
    return "rel:" + hashlib.sha1(raw).hexdigest()[:16]


def evidence_key(evidence: dict[str, Any]) -> tuple[Any, Any, str]:
    return (
        evidence.get("document_id") or evidence.get("document_title"),
        evidence.get("page"),
        normalise(evidence.get("quote", "")),
    )


def reconstructed_relation_samples(graph: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for relation in graph["relations"]:
        for evidence_index, evidence in enumerate(relation.get("evidence") or []):
            candidates.append({
                "relation_id": relation["id"],
                "relation": relation,
                "evidence": evidence,
                "priority": (
                    relation["supporting_document_count"],
                    relation["confidence"],
                    -evidence_index,
                ),
            })
    candidates.sort(key=lambda row: row["priority"], reverse=True)
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for row in candidates:
        if row["relation_id"] in used:
            continue
        selected.append(row)
        used.add(row["relation_id"])
    chosen_keys = {
        (row["relation_id"], *evidence_key(row["evidence"])) for row in selected
    }
    for row in candidates:
        key = (row["relation_id"], *evidence_key(row["evidence"]))
        if key in chosen_keys:
            continue
        selected.append(row)
        chosen_keys.add(key)
        if len(selected) >= 65:
            break
    if len(selected) != 65:
        raise RuntimeError(f"关系核验样本重建失败: {len(selected)}")
    return selected


def classify_standard_relation(quote: str) -> str:
    if re.search(r"指标包括|评价检测指标|灌溉能力.*排水能力", quote):
        return "includes_indicator"
    return "prescribes_measurement"


def add_relation_evidence(
    grouped: dict[tuple[str, str, str], dict[str, Any]],
    relation_type: str,
    source: str,
    target: str,
    evidence: dict[str, Any],
    *,
    decision: str,
    sample_id: str,
    note: str,
) -> None:
    key = (relation_type, source, target)
    relation = grouped.setdefault(key, {
        "id": edge_id(*key),
        "type": relation_type,
        "source": source,
        "target": target,
        "status": "approved" if decision == "通过" else "approved_with_revision",
        "review_sample_ids": [],
        "evidence": [],
    })
    if decision != "通过":
        relation["status"] = "approved_with_revision"
    if sample_id not in relation["review_sample_ids"]:
        relation["review_sample_ids"].append(sample_id)
    item = deepcopy(evidence)
    item["quote"] = normalise(item.get("quote", ""))
    item["review_status"] = "approved" if decision == "通过" else "approved_with_revision"
    item["review_sample_id"] = sample_id
    item["review_note"] = note
    if evidence_key(item) not in {evidence_key(existing) for existing in relation["evidence"]}:
        relation["evidence"].append(item)


def document_id_for_source(source: str, corpus: Iterable[dict[str, Any]]) -> int | None:
    source_key = compact(Path(source).stem)
    matches = []
    for document in corpus:
        title_key = compact(document["title"])
        if title_key in source_key or source_key.startswith(title_key):
            matches.append((len(title_key), int(document["document_id"])))
    return max(matches, default=(0, None))[1]


def build_graph_v02(graph: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    entities = deepcopy(graph["entities"])
    entity_by_id = {entity["id"]: entity for entity in entities}
    sorted_entities = sorted(entities, key=lambda item: (item["type"], item["name"]))
    if len(sorted_entities) != 35:
        raise RuntimeError("实体样本基线不是35条")

    entity_audit = []
    modified_entity_ids = set(ENTITY_ALIASES)
    for index, entity in enumerate(sorted_entities, 1):
        sample_id = f"KG-{index:03d}"
        review_row = review["samples"][index - 1]
        if review_row["sample_id"] != sample_id or review_row["subject"] != entity["name"]:
            raise RuntimeError(f"实体样本错位: {sample_id}")
        decision = "修改后通过" if entity["id"] in modified_entity_ids else "通过"
        if entity["id"] in ENTITY_ALIASES:
            entity["aliases"] = ENTITY_ALIASES[entity["id"]]
            entity["related_terms"] = RELATED_TERMS.get(entity["id"], [])
        entity["status"] = "approved_with_revision" if decision == "修改后通过" else "approved"
        entity["review"] = {
            "sample_id": sample_id,
            "decision": decision,
            "verified_by": VERIFIED_BY,
            "verified_at": REVIEWED_AT,
        }
        entity_audit.append({
            "sample_id": sample_id,
            "entity_id": entity["id"],
            "decision": decision,
        })

    for entity in NEW_ENTITIES:
        item = deepcopy(entity)
        item["review"] = {
            "decision": "修改后通过",
            "derived_from": "术语边界修订",
            "verified_by": VERIFIED_BY,
            "verified_at": REVIEWED_AT,
        }
        entities.append(item)
        entity_by_id[item["id"]] = item

    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    relation_audit = []
    samples = reconstructed_relation_samples(graph)
    for offset, mapped in enumerate(samples, 36):
        sample_id = f"KG-{offset:03d}"
        review_row = review["samples"][offset - 1]
        evidence = mapped["evidence"]
        if (
            review_row["sample_id"] != sample_id
            or normalise(review_row["quote"]) != normalise(evidence["quote"])
            or review_row.get("page") != evidence.get("page")
        ):
            raise RuntimeError(f"关系样本错位: {sample_id}")
        original = mapped["relation"]
        if sample_id in REJECTED_RELATION_SAMPLES:
            relation_audit.append({
                "sample_id": sample_id,
                "original_relation_id": original["id"],
                "decision": "驳回",
                "reason": REJECTED_RELATION_SAMPLES[sample_id],
                "evidence": evidence,
            })
            continue
        decision = "通过" if sample_id in PASSED_RELATION_SAMPLES else "修改后通过"
        if original["type"] == "addresses":
            relation_type = "addresses"
            note = "原文直接支持改良措施治理障碍因素。"
        elif original["type"] == "affects":
            relation_type = "characterized_by"
            note = "将宽泛的影响关系收窄为土壤板结表现为/伴随土壤容重升高。"
        elif original["type"] == "defines":
            relation_type = classify_standard_relation(evidence["quote"])
            note = "标准关系由定义改为纳入评价指标或规定检测方法。"
        elif original["type"] == "supports":
            relation_type = "assessment_basis"
            note = "将笼统支持关系改为盐碱化程度判定依据。"
        else:
            raise RuntimeError(f"未知关系类型: {original['type']}")
        add_relation_evidence(
            grouped,
            relation_type,
            original["source"],
            original["target"],
            evidence,
            decision=decision,
            sample_id=sample_id,
            note=note,
        )
        relation_audit.append({
            "sample_id": sample_id,
            "original_relation_id": original["id"],
            "new_relation_id": edge_id(relation_type, original["source"], original["target"]),
            "decision": decision,
        })

    name_to_id = {entity["name"]: entity["id"] for entity in entities}
    evidence_audit = []
    for row in review["obstacle_measure_evidence"]:
        evidence_id = row["evidence_id"]
        decision, note = EVIDENCE_DECISIONS[evidence_id]
        audit_item = {
            "evidence_id": evidence_id,
            "decision": decision,
            "obstacle": row["obstacle"],
            "measure": row["measure"],
            "reason": note,
        }
        if decision == "驳回":
            evidence_audit.append(audit_item)
            continue
        source, target = SUPPLEMENT_EDGE_OVERRIDES.get(
            evidence_id,
            (name_to_id[row["measure"]], name_to_id[row["obstacle"]]),
        )
        document_id = document_id_for_source(row["source"], graph["corpus"])
        evidence = {
            "document_id": document_id,
            "document_title": next(
                (doc["title"] for doc in graph["corpus"] if int(doc["document_id"]) == document_id),
                Path(row["source"]).stem,
            ),
            "page": row.get("page"),
            "chunk_index": None,
            "quote": row["quote"],
        }
        add_relation_evidence(
            grouped,
            "addresses",
            source,
            target,
            evidence,
            decision=decision,
            sample_id=evidence_id,
            note=note,
        )
        audit_item["new_relation_id"] = edge_id("addresses", source, target)
        evidence_audit.append(audit_item)

    relations = sorted(grouped.values(), key=lambda item: (item["type"], item["source"], item["target"]))
    for relation in relations:
        relation["review_sample_ids"].sort()
        relation["supporting_document_count"] = len({
            evidence.get("document_id") or evidence.get("document_title")
            for evidence in relation["evidence"]
        })
        relation["confidence"] = 0.95 if relation["status"] == "approved" else 0.85
        relation["review"] = {
            "verified_by": VERIFIED_BY,
            "verified_at": REVIEWED_AT,
            "basis": "source_material",
        }

    output = {
        "schema_version": "minimal-cultivated-land-kg-v0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": GRAPH_V01.relative_to(ROOT).as_posix(),
        "scope": {
            "entity_types": ["indicator", "obstacle", "measure", "standard"],
            "relation_types": [
                "addresses",
                "characterized_by",
                "includes_indicator",
                "prescribes_measurement",
                "assessment_basis",
            ],
            "review_status": "material_confirmed",
            "note": "仅纳入通过或修改后通过的关系证据；驳回项保留在review_audit中。",
        },
        "corpus": deepcopy(graph["corpus"]),
        "entities": sorted(entities, key=lambda item: (item["type"], item["name"])),
        "relations": relations,
        "review_audit": {
            "verified_by": VERIFIED_BY,
            "verified_at": REVIEWED_AT,
            "source_review_data": REVIEW_DATA.relative_to(ROOT).as_posix(),
            "entity_samples": entity_audit,
            "relation_samples": relation_audit,
            "obstacle_measure_evidence": evidence_audit,
        },
    }
    output["validation"] = validate_graph(output)
    return output


def validate_graph(graph: dict[str, Any]) -> dict[str, Any]:
    entities = {entity["id"]: entity for entity in graph["entities"]}
    allowed_directions = {
        "addresses": ("measure", "obstacle"),
        "characterized_by": ("obstacle", "indicator"),
        "includes_indicator": ("standard", "indicator"),
        "prescribes_measurement": ("standard", "indicator"),
        "assessment_basis": ("standard", "obstacle"),
    }
    endpoint_errors = []
    direction_errors = []
    empty_evidence = []
    duplicate_evidence = []
    linked: set[str] = set()
    evidence_count = 0
    page_count = 0
    relation_keys = []
    for relation in graph["relations"]:
        relation_keys.append((relation["type"], relation["source"], relation["target"]))
        if relation["source"] not in entities or relation["target"] not in entities:
            endpoint_errors.append(relation["id"])
            continue
        linked.update((relation["source"], relation["target"]))
        expected = allowed_directions.get(relation["type"])
        actual = (entities[relation["source"]]["type"], entities[relation["target"]]["type"])
        if expected != actual:
            direction_errors.append({"relation_id": relation["id"], "expected": expected, "actual": actual})
        evidence = relation.get("evidence") or []
        if not evidence:
            empty_evidence.append(relation["id"])
        keys = [evidence_key(item) for item in evidence]
        if len(keys) != len(set(keys)):
            duplicate_evidence.append(relation["id"])
        evidence_count += len(evidence)
        page_count += sum(1 for item in evidence if item.get("page") is not None)
    duplicate_relations = len(relation_keys) - len(set(relation_keys))
    orphan_entities = sorted(set(entities) - linked)
    relation_counts = Counter(relation["type"] for relation in graph["relations"])
    entity_counts = Counter(entity["type"] for entity in graph["entities"])
    return {
        "entity_count": len(entities),
        "entity_counts": dict(sorted(entity_counts.items())),
        "relation_count": len(graph["relations"]),
        "relation_counts": dict(sorted(relation_counts.items())),
        "evidence_count": evidence_count,
        "evidence_with_page_ratio": round(page_count / evidence_count, 4) if evidence_count else 0.0,
        "relations_without_evidence": empty_evidence,
        "invalid_endpoint_relations": endpoint_errors,
        "invalid_direction_relations": direction_errors,
        "duplicate_relation_count": duplicate_relations,
        "duplicate_evidence_relations": duplicate_evidence,
        "orphan_entity_count": len(orphan_entities),
        "orphan_entities": orphan_entities,
        "passed": not any([
            endpoint_errors,
            direction_errors,
            empty_evidence,
            duplicate_relations,
            duplicate_evidence,
        ]),
    }


def render_report(graph: dict[str, Any]) -> str:
    validation = graph["validation"]
    audit = graph["review_audit"]
    entity_decisions = Counter(item["decision"] for item in audit["entity_samples"])
    relation_decisions = Counter(item["decision"] for item in audit["relation_samples"])
    evidence_decisions = Counter(item["decision"] for item in audit["obstacle_measure_evidence"])
    entities = {entity["id"]: entity for entity in graph["entities"]}

    accepted_addresses = [relation for relation in graph["relations"] if relation["type"] == "addresses"]
    rejected_relations = [item for item in audit["relation_samples"] if item["decision"] == "驳回"]

    lines = [
        "# 耕地质量最小知识图谱 v0.2 回写报告",
        "",
        "## 回写结论",
        "",
        f"- 回写日期：{REVIEWED_AT}",
        f"- 核验方式：{VERIFIED_BY}",
        f"- 实体样本：通过 {entity_decisions['通过']} 条，修改后通过 {entity_decisions['修改后通过']} 条",
        f"- 关系证据样本：通过 {relation_decisions['通过']} 条，修改后通过 {relation_decisions['修改后通过']} 条，驳回 {relation_decisions['驳回']} 条",
        f"- 障碍—措施补充证据：通过 {evidence_decisions['通过']} 条，修改后通过 {evidence_decisions['修改后通过']} 条，驳回 {evidence_decisions['驳回']} 条",
        "",
        "## 实体术语回写",
        "",
        "18 组实体完成别名边界修订。严格别名保留在 `aliases`，上下位概念、相关指标、实施方式和结果术语移入 `related_terms`。根据已核验措施证据新增“深松”和“免耕”两个措施实体。",
        "",
        "## 关系回写",
        "",
        f"- 正式关系：{validation['relation_count']} 条",
        f"- 正式证据：{validation['evidence_count']} 条",
        "- 原 `defines` 关系已改为 `includes_indicator` 或 `prescribes_measurement`。",
        "- 土壤板结—土壤容重关系已收窄为 `characterized_by`。",
        "- 标准—盐碱化关系已改为 `assessment_basis`。",
        "- 仅通过或修改后通过的证据进入正式关系；驳回项仅保留在审计记录。",
        "",
        "### 已纳入的障碍—改良措施关系",
        "",
        "| 改良措施 | 关系 | 障碍因素 | 证据条数 | 状态 |",
        "|---|---|---|---:|---|",
    ]
    for relation in accepted_addresses:
        lines.append(
            f"| {entities[relation['source']]['name']} | 治理/缓解 | {entities[relation['target']]['name']} | {len(relation['evidence'])} | {relation['status']} |"
        )

    lines.extend([
        "",
        "### 驳回的原关系证据",
        "",
        "| 样本 | 原关系ID | 原因 |",
        "|---|---|---|",
    ])
    for item in rejected_relations:
        lines.append(f"| {item['sample_id']} | {item['original_relation_id']} | {item['reason']} |")

    lines.extend([
        "",
        "## 自动校验",
        "",
        "| 校验项 | 结果 |",
        "|---|---|",
        f"| 实体端点完整 | {'通过' if not validation['invalid_endpoint_relations'] else '失败'} |",
        f"| 关系方向合法 | {'通过' if not validation['invalid_direction_relations'] else '失败'} |",
        f"| 每条关系均有证据 | {'通过' if not validation['relations_without_evidence'] else '失败'} |",
        f"| 重复关系 | {validation['duplicate_relation_count']} |",
        f"| 重复证据关系 | {len(validation['duplicate_evidence_relations'])} |",
        f"| 证据页码定位率 | {validation['evidence_with_page_ratio']:.1%} |",
        f"| 总体验证 | {'通过' if validation['passed'] else '失败'} |",
        "",
        "## 待补证实体",
        "",
        f"当前有 {validation['orphan_entity_count']} 个已确认实体尚无通过核验的正式关系证据。为避免臆造关系，v0.2 保留这些实体并标记为后续补证对象：",
        "",
    ])
    for entity_id in validation["orphan_entities"]:
        lines.append(f"- {entities[entity_id]['name']}（`{entity_id}`）")

    lines.extend([
        "",
        "## 输出",
        "",
        f"- 图谱：`{GRAPH_V02.relative_to(ROOT).as_posix()}`",
        f"- 报告：`{REPORT_V02.relative_to(ROOT).as_posix()}`",
        "",
        "## 后续建议",
        "",
        "以 v0.2 为检索基线建立 30～50 道金标准问答，分别测试指标解释、障碍诊断、改良措施及标准依据，并与纯向量检索进行对比。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    graph = json.loads(GRAPH_V01.read_text(encoding="utf-8"))
    review = json.loads(REVIEW_DATA.read_text(encoding="utf-8"))
    output = build_graph_v02(graph, review)
    GRAPH_V02.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_V02.write_text(render_report(output), encoding="utf-8")
    print(json.dumps({
        "graph": str(GRAPH_V02),
        "report": str(REPORT_V02),
        "validation": output["validation"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
