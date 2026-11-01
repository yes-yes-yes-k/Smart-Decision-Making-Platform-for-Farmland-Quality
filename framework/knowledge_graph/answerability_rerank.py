"""Deterministic answerability reranking for retrieved evidence chunks.

R1.4 showed the failure mode "right paper, wrong chunk": document ranking was
fine while the passages that actually answer the sub-question stayed outside
the returned window. This reranker scores a chunk by how much of the question
it can answer — concept coverage, reported results, effect directions and
condition cues — without a model call, without the evaluator's reference
answers, and without changing recall.

It only reorders candidates that retrieval already returned; nothing is added,
dropped, or re-embedded.
"""
from __future__ import annotations

import re

from framework.vector_store.retrieval_policy import (
    CONTEXT, INDICATORS, MEASURES, _mentions, lexical_concept_groups)

VERSION = "answerability-rerank-v1"

_RESULT = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|mg/kg|g/kg|kg/ha|t/ha|cm|d\b|天|年|percent)", re.I)
_DIRECTION = ("增加", "提高", "上升", "降低", "下降", "减少", "显著", "无显著", "分别",
              "increase", "decrease", "reduc", "improv", "higher", "lower", "significant")
_CONDITION = ("土壤", "红壤", "酸性", "稻田", "水稻", "小麦", "玉米", "ph", "施用量", "用量",
              "年限", "长期", "处理", "试验", "小区", "盆栽", "田间")
_NOISE = ("参考文献", "references", "目录", "致谢", "acknowledg", "作者简介", "基金项目")
_WEIGHTS = {"concept": 1.5, "result": 0.8, "direction": 0.6, "condition": 0.4}


def _concept_groups(query: str) -> list[tuple[str, ...]]:
    groups = lexical_concept_groups(query)
    if not groups:
        # Queries without a recognized measure still need concept coverage.
        groups = [list(aliases) for aliases in INDICATORS if _mentions(query, aliases)]
        groups += [list(aliases) for aliases in CONTEXT if _mentions(query, aliases)]
    return [tuple(group) for group in groups]


def _present(text: str, aliases) -> bool:
    folded = text.casefold()
    return any(alias.casefold() in folded for alias in aliases)


def score_chunk(query: str, text: str, groups=None) -> dict:
    """Score one chunk and expose the individual signals for audit."""
    groups = groups if groups is not None else _concept_groups(query)
    lowered = (text or "").casefold()
    covered = sum(1 for group in groups if _present(lowered, group))
    coverage = covered / len(groups) if groups else 0.0
    results = len(_RESULT.findall(text or ""))
    directions = sum(1 for word in _DIRECTION if word in lowered)
    conditions = sum(1 for word in _CONDITION if word in lowered)
    noise = sum(1 for word in _NOISE if word.casefold() in lowered)
    length_penalty = 0.5 if len(text or "") < 300 else 0.0
    score = (_WEIGHTS["concept"] * coverage
             + _WEIGHTS["result"] * min(results, 3) / 3
             + _WEIGHTS["direction"] * min(directions, 3) / 3
             + _WEIGHTS["condition"] * min(conditions, 3) / 3
             - 0.8 * noise - length_penalty)
    return {"score": round(score, 6), "concept_coverage": round(coverage, 4),
            "concepts_covered": covered, "concepts_total": len(groups),
            "result_mentions": results, "direction_cues": directions,
            "condition_cues": conditions, "noise_markers": noise,
            "short_chunk_penalty": length_penalty}


def rerank_values(query: str, values: list[dict]) -> tuple[list[dict], dict]:
    """Stable reorder by answerability; original order breaks ties."""
    groups = _concept_groups(query)
    scored = []
    for position, value in enumerate(values):
        signals = score_chunk(query, value.get("text", ""), groups)
        scored.append((signals["score"], -position, value, signals))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    ordered = [item[2] for item in scored]
    trace = {"version": VERSION, "candidates": len(values), "concepts": [list(g) for g in groups],
             "scores": [{"document_id": item[2].get("document_id"),
                         "chunk_index": item[2].get("chunk_index"),
                         "original_rank": -item[1] + 1, **item[3]} for item in scored]}
    return ordered, trace
