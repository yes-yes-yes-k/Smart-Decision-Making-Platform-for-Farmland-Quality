"""Measure whether intent-level vectors recover the evidence R1.4 missed.

Unions three already-paid-for signals per case: sub-question vectors, one
condition variant, and the lexical concept variants. Reports how deep each
reference span sits and whether 60 candidates would have been enough.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
TRANSFER = R1 / "span-transfer-20261031-v1/span-transfer.json"
EMBEDDINGS = R1 / "r14-intent-embeddings-20261031-v1"
CLONE = R1 / "r1-r2-20261030-v1/runtime/chroma"
LEXICAL = R1 / "r1-r2-20261030-v1/runtime/chroma/lexical-index.sqlite3"
FILTERS = {"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": ["academic_paper"]}}]}
LIMIT = 200


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    transfer = {(row["document_id"], row["old_chunk_index"]): row
                for row in json.loads(TRANSFER.read_text(encoding="utf-8"))["rows"]}
    rows = []
    for case in cases["cases"]:
        for subquestion in case.get("subquestions", []):
            for reference in subquestion.get("reference_evidence", []):
                mapped = transfer.get((reference["document_id"], reference["chunk_index"])) or {}
                rows.append({"case_id": case["id"], "subquestion_id": subquestion["id"],
                             "document_id": reference["document_id"],
                             "chunk_index": mapped.get("chunk_index", reference["chunk_index"])})
    return cases, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="intent-recall-20261031-v1")
    args = parser.parse_args()
    out = R1 / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    print("temp", out / ".tmp")
    temp = (out / ".tmp").resolve()
    temp.mkdir(exist_ok=True)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(temp)

    import chromadb
    client = chromadb.PersistentClient(path=str(CLONE))
    collection = client.get_collection("enterprise_kb")

    vectors = {}
    for path in sorted((EMBEDDINGS / "embeddings").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        vectors.setdefault(data["case_id"], []).append((data["kind"], data["embedding"]))

    cases, rows = targets()
    vector_ranks, vector_meta = {}, {}
    for case in cases["cases"]:
        for kind, vector in vectors.get(case["id"], []):
            result = collection.query(query_embeddings=[vector], n_results=LIMIT,
                                      where=FILTERS, include=["metadatas"])
            for position, meta in enumerate(result["metadatas"][0], start=1):
                key = (meta.get("document_id"), meta.get("chunk_index"))
                vector_meta.setdefault(key, []).append({"rank": position, "query_kind": kind})
    for key, hits in vector_meta.items():
        vector_ranks[key] = min(hit["rank"] for hit in hits)

    from framework.vector_store.bm25_store import BM25Store
    from framework.vector_store.retrieval_policy import (
        INDICATORS, MEASURES, lexical_concept_groups)
    store = BM25Store(path=LEXICAL, collection="enterprise_kb")
    lexical_ranks = {}
    try:
        for case in cases["cases"]:
            if not case.get("subquestions"):
                continue
            groups = lexical_concept_groups(case["query"])
            measures = {alias for aliases in MEASURES for alias in aliases}
            indicators = {alias for aliases in INDICATORS for alias in aliases}

            def named(group, names):
                return any(alias in names for alias in group)

            subsets = [groups,
                       [g for g in groups if named(g, measures) or named(g, indicators)]]
            searches = [store.search(case["query"], LIMIT, FILTERS)]
            for subset in subsets:
                if subset:
                    searches.append(store.search(case["query"], LIMIT, FILTERS, concept_groups=subset))
            for rows_found in searches:
                for position, row in enumerate(rows_found, start=1):
                    key = (row["metadata"].get("document_id"), row["metadata"].get("chunk_index"))
                    lexical_ranks[key] = min(lexical_ranks.get(key, position), position)
    finally:
        store.close()

    union = {}
    for key, rank in vector_ranks.items():
        union[key] = min(union.get(key, rank), rank)
    for key, rank in lexical_ranks.items():
        union[key] = min(union.get(key, rank), rank)

    results = []
    for row in rows:
        key = (row["document_id"], row["chunk_index"])
        v = vector_ranks.get(key)
        l = lexical_ranks.get(key)
        combined = min([rank for rank in (v, l) if rank], default=None)
        neighbours = [union.get((row["document_id"], row["chunk_index"] + delta)) for delta in (-2, -1, 1, 2)]
        near = min([rank for rank in neighbours if rank], default=None)
        results.append({**row, "vector_rank": v, "lexical_rank": l, "combined_rank": combined,
                        "neighbour_rank": near})

    def coverage(kind, limit):
        field = {"vector": "vector_rank", "lexical": "lexical_rank", "combined": "combined_rank"}[kind]
        return sum(1 for r in results if r[field] and r[field] <= limit)

    summary = {
        "references": len(results),
        "vector": {str(limit): coverage("vector", limit) for limit in (60, 100, 200)},
        "lexical": {str(limit): coverage("lexical", limit) for limit in (60, 100, 200)},
        "combined": {str(limit): coverage("combined", limit) for limit in (60, 100, 200)},
        "never_in_either": sum(1 for r in results if not r["combined_rank"]),
        "neighbour_window": 2,
        "covered_with_neighbours": sum(1 for r in results
                                       if (r["combined_rank"] or 10**9) <= 60
                                       or (r["neighbour_rank"] and r["neighbour_rank"] <= 60)),
    }
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "state": "measured",
              "inputs": {"query_cases_sha256": sha256(CASES), "span_transfer_sha256": sha256(TRANSFER),
                         "embedding_manifest_sha256": sha256(EMBEDDINGS / "manifest.json"),
                         "lexical_index_sha256": sha256(LEXICAL)},
              "cost": {"embedding_attempts": 17, "additional_attempts": 0,
                       "estimated_tokens": 182},
              "limit": LIMIT, "summary": summary, "references": results}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")

    lines = ["# 意图级召回的 60 候选覆盖率", "",
             f"- 参考证据：{len(results)} 条（深度上限 {LIMIT}）",
             f"- 向量：前60 {summary['vector']['60']} / 前100 {summary['vector']['100']} / 前200 {summary['vector']['200']}",
             f"- 词法：前60 {summary['lexical']['60']} / 前100 {summary['lexical']['100']} / 前200 {summary['lexical']['200']}",
             f"- 两者并集：前60 {summary['combined']['60']} / 前100 {summary['combined']['100']} / 前200 {summary['combined']['200']}",
             f"- 两路都没有：{summary['never_in_either']} 条",
             f"- 允许±2邻块时前60覆盖：{summary['covered_with_neighbours']} 条", "",
             "| 用例 | 子问题 | 文献 | 块 | 向量 | 词法 | 并集 |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in results:
        lines.append(f"| {row['case_id']} | {row['subquestion_id']} | {row['document_id']} | {row['chunk_index']} | "
                     f"{row['vector_rank'] or '-'} | {row['lexical_rank'] or '-'} | {row['combined_rank'] or '-'} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
