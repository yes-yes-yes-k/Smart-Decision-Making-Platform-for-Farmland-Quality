"""JSON/AGE dual-read comparison and primary-read promotion gate."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from .contracts import GraphQuery, GraphStore


@dataclass(frozen=True, slots=True)
class DualReadCase:
    query: GraphQuery
    entity_match: bool
    relation_match: bool
    evidence_match: bool
    json_counts: Mapping[str, int]
    age_counts: Mapping[str, int]


def _identity(result) -> tuple[set[str], set[tuple[str, str, str]], set[str]]:
    entities = {str(item.get("id") or item.get("entity_id")) for item in result.entities}
    relations = {
        (
            str(item.get("type") or item.get("relation_type")),
            str(item.get("source") or item.get("source_entity_id")),
            str(item.get("target") or item.get("target_entity_id")),
        )
        for item in result.relations
    }
    evidence = {
        str(item.get("evidence_id") or "") for item in result.evidence_references
        if item.get("evidence_id")
    }
    return entities, relations, evidence


def compare_graph_stores(
    json_store: GraphStore,
    age_store: GraphStore,
    queries: Sequence[GraphQuery],
    *,
    minimum_match_ratio: float = 1.0,
) -> dict[str, Any]:
    if not queries:
        raise ValueError("at least one representative query is required")
    if not 0.0 <= minimum_match_ratio <= 1.0:
        raise ValueError("minimum_match_ratio must be between zero and one")
    cases = []
    matched = 0
    for query in queries:
        json_result = json_store.neighbors(query)
        age_result = age_store.neighbors(query)
        json_identity = _identity(json_result)
        age_identity = _identity(age_result)
        flags = tuple(left == right for left, right in zip(json_identity, age_identity))
        matched += int(all(flags))
        cases.append(DualReadCase(
            query=query,
            entity_match=flags[0], relation_match=flags[1], evidence_match=flags[2],
            json_counts={
                "entities": len(json_identity[0]), "relations": len(json_identity[1]),
                "evidence": len(json_identity[2]),
            },
            age_counts={
                "entities": len(age_identity[0]), "relations": len(age_identity[1]),
                "evidence": len(age_identity[2]),
            },
        ))
    ratio = matched / len(queries)
    health = dict(age_store.health())
    passed = ratio >= minimum_match_ratio and bool(health.get("ready"))
    return {
        "schema": "knowledge-graph-dual-read-report-v1",
        "passed": passed,
        "eligible_for_primary": passed,
        "minimum_match_ratio": minimum_match_ratio,
        "match_ratio": ratio,
        "matched_queries": matched,
        "query_count": len(queries),
        "age_health": health,
        "cases": [asdict(item) for item in cases],
    }
