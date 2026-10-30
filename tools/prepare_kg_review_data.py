from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import chromadb

from framework.knowledge_graph.minimal_graph import MEASURES, OBSTACLES

GRAPH_PATH = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.1.json"
OUT_PATH = ROOT / "artifacts" / "minimal_kg" / "review_workbook_data.json"

RELATION_LABELS = {
    "affects": "影响",
    "addresses": "治理",
    "defines": "定义",
    "supports": "支持",
}
TYPE_LABELS = {
    "indicator": "耕地质量指标",
    "obstacle": "障碍因素",
    "measure": "改良措施",
    "standard": "标准依据",
}
ADDRESS_CUES = ("针对", "改良", "治理", "调控", "施用", "防治", "缓解", "改善", "提升", "采取", "措施", "修复")
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；;])|\n+")
SPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    return SPACE.sub(" ", text or "").strip()


def term_positions(text: str, spec) -> list[int]:
    lowered = text.lower()
    positions = []
    for alias in spec.aliases:
        start = 0
        needle = alias.lower()
        while True:
            pos = lowered.find(needle, start)
            if pos < 0:
                break
            positions.append(pos)
            start = pos + max(1, len(needle))
    return positions


def best_context(text: str, measure, obstacle):
    m_pos = term_positions(text, measure)
    o_pos = term_positions(text, obstacle)
    if not m_pos or not o_pos:
        return None
    distance, mp, op = min((abs(m - o), m, o) for m in m_pos for o in o_pos)
    if distance > 450:
        return None
    left = max(0, min(mp, op) - 130)
    right = min(len(text), max(mp, op) + 260)
    context = normalise(text[left:right])
    same_sentence = False
    for sentence in SENTENCE_SPLIT.split(text):
        if any(a.lower() in sentence.lower() for a in measure.aliases) and any(
            a.lower() in sentence.lower() for a in obstacle.aliases
        ):
            same_sentence = True
            context = normalise(sentence)[:420]
            break
    has_cue = any(cue in context for cue in ADDRESS_CUES)
    if same_sentence and has_cue:
        strength, rank = "强", 3
    elif distance <= 220 and has_cue:
        strength, rank = "中", 2
    else:
        strength, rank = "弱", 1
    if "[J]" in context or "参考文献" in context:
        strength, rank = "弱", 1
    return distance, context, strength, rank


def entity_rows(graph):
    relations_by_entity = defaultdict(list)
    for relation in graph["relations"]:
        relations_by_entity[relation["source"]].append(relation)
        relations_by_entity[relation["target"]].append(relation)
    rows = []
    for entity in sorted(graph["entities"], key=lambda x: (x["type"], x["name"])):
        evidence = None
        for relation in relations_by_entity.get(entity["id"], []):
            if relation.get("evidence"):
                evidence = relation["evidence"][0]
                break
        evidence = evidence or {}
        aliases = "、".join(entity.get("aliases") or [])
        rows.append({
            "sample_type": "实体",
            "fact_type": TYPE_LABELS[entity["type"]],
            "subject": entity["name"],
            "predicate": "规范名称与别名",
            "object": aliases or "无别名",
            "source": evidence.get("document_title", "图谱标准实体"),
            "page": evidence.get("page"),
            "quote": evidence.get("quote", "请确认规范名称、概念边界及允许别名。"),
            "system_suggestion": "确认规范名称及别名",
        })
    return rows


def relation_rows(graph, required_count=65):
    entities = {entity["id"]: entity for entity in graph["entities"]}
    candidates = []
    for relation in graph["relations"]:
        for evidence_index, evidence in enumerate(relation.get("evidence") or []):
            candidates.append({
                "sample_type": "关系",
                "fact_type": RELATION_LABELS[relation["type"]],
                "subject": entities[relation["source"]]["name"],
                "predicate": RELATION_LABELS[relation["type"]],
                "object": entities[relation["target"]]["name"],
                "source": evidence["document_title"],
                "page": evidence.get("page"),
                "quote": evidence["quote"],
                "system_suggestion": "保留候选关系",
                "_priority": (
                    relation["supporting_document_count"],
                    relation["confidence"],
                    -evidence_index,
                ),
                "_relation_id": relation["id"],
            })
    candidates.sort(key=lambda row: row["_priority"], reverse=True)
    chosen, used = [], set()
    # First ensure every relationship is represented once.
    for row in candidates:
        if row["_relation_id"] in used:
            continue
        chosen.append(row)
        used.add(row["_relation_id"])
    # Then add independent evidence samples for the strongest relationships.
    chosen_keys = {(r["_relation_id"], r["source"], r["page"], r["quote"]) for r in chosen}
    for row in candidates:
        key = (row["_relation_id"], row["source"], row["page"], row["quote"])
        if key in chosen_keys:
            continue
        chosen.append(row)
        chosen_keys.add(key)
        if len(chosen) >= required_count:
            break
    if len(chosen) < required_count:
        raise RuntimeError(f"可用关系证据不足: {len(chosen)} < {required_count}")
    for row in chosen[:required_count]:
        row.pop("_priority", None)
        row.pop("_relation_id", None)
    return chosen[:required_count]


def supplemental_evidence(graph):
    corpus_ids = {int(doc["document_id"]) for doc in graph["corpus"]}
    client = chromadb.PersistentClient(path=str(ROOT / "chroma_db"))
    collection = client.get_collection("kb_cultivated_land_quality")
    data = collection.get(include=["documents", "metadatas"])
    candidates = []
    seen = set()
    for text, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
        document_id = int(metadata.get("document_id") or 0)
        if document_id not in corpus_ids:
            continue
        for obstacle in OBSTACLES:
            if not term_positions(text, obstacle):
                continue
            for measure in MEASURES:
                context_data = best_context(text, measure, obstacle)
                if not context_data:
                    continue
                distance, context, strength, rank = context_data
                key = (obstacle.code, measure.code, document_id, metadata.get("page"), context)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "obstacle": obstacle.name,
                    "measure": measure.name,
                    "strength": strength,
                    "source": metadata.get("doc_name") or metadata.get("source"),
                    "page": metadata.get("page"),
                    "quote": context,
                    "machine_judgment": "建议核验治理关系" if rank >= 2 else "仅共现，需谨慎核验",
                    "_rank": rank,
                    "_distance": distance,
                })
    candidates.sort(key=lambda r: (-r["_rank"], r["_distance"], r["obstacle"], r["measure"]))
    # Keep variety across obstacle-measure pairs before adding extra evidence.
    selected, pairs = [], set()
    for row in candidates:
        pair = (row["obstacle"], row["measure"])
        if pair in pairs:
            continue
        selected.append(row)
        pairs.add(pair)
        if len(selected) >= 30:
            break
    if len(selected) < 30:
        for row in candidates:
            key = (row["obstacle"], row["measure"], row["source"], row["page"], row["quote"])
            if any((x["obstacle"], x["measure"], x["source"], x["page"], x["quote"]) == key for x in selected):
                continue
            selected.append(row)
            if len(selected) >= 30:
                break
    for row in selected:
        row.pop("_rank", None)
        row.pop("_distance", None)
    return selected


def main():
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    entities = entity_rows(graph)
    relations = relation_rows(graph, 65)
    samples = entities + relations
    if len(samples) != 100:
        raise RuntimeError(f"核验样本数量错误: {len(samples)}")
    for index, row in enumerate(samples, 1):
        row["sample_id"] = f"KG-{index:03d}"
    evidence = supplemental_evidence(graph)
    for index, row in enumerate(evidence, 1):
        row["evidence_id"] = f"OM-{index:03d}"
    payload = {
        "summary": {
            "sample_count": len(samples),
            "entity_sample_count": len(entities),
            "relation_sample_count": len(relations),
            "supplemental_evidence_count": len(evidence),
            "corpus_document_count": len(graph["corpus"]),
        },
        "samples": samples,
        "obstacle_measure_evidence": evidence,
        "corpus": graph["corpus"],
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
