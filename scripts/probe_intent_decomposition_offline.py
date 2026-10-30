"""Offline intent-decomposition probe (no model calls, lexical path only).

Question: are the evidence chunks that R1.4 could not return reachable in the
lexical ranking at all, and can splitting one question into sub-intents lift
them into the top 60?

Vector sub-intents would need new embeddings, so this probe deliberately stays
on the lexical leg and reports that limit explicitly.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from framework.vector_store.bm25_store import BM25Store
from framework.vector_store.retrieval_policy import (
    INDICATORS, MEASURES, lexical_concept_groups)

R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
TRANSFER = R1 / "span-transfer-20261031-v1/span-transfer.json"
LEXICAL = R1 / "r1-r2-20261030-v1/runtime/chroma/lexical-index.sqlite3"
FILTERS = {"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": ["academic_paper"]}}]}


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
                chunk = mapped.get("chunk_index", reference["chunk_index"])
                rows.append({"case_id": case["id"], "subquestion_id": subquestion["id"],
                             "document_id": reference["document_id"], "chunk_index": chunk,
                             "old_chunk_index": reference["chunk_index"],
                             "mapped": mapped.get("mapped", False)})
    return cases, rows


def clauses(query: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[，。？；、,?;]", query)]
    return [part for part in parts if len(part) >= 4]


def concept_subsets(query: str):
    groups = lexical_concept_groups(query)
    measure_names = {alias for aliases in MEASURES for alias in aliases}
    indicator_names = {alias for aliases in INDICATORS for alias in aliases}

    def named(group, names):
        return any(alias in names for alias in group)

    return {
        "concept_and": groups,
        "measure_indicator": [g for g in groups if named(g, measure_names) or named(g, indicator_names)],
        "indicator_only": [g for g in groups if named(g, indicator_names)],
    }


def ranks(rows):
    return {(row["metadata"].get("document_id"), row["metadata"].get("chunk_index")): position
            for position, row in enumerate(rows, start=1)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="intent-probe-20261031-v1")
    parser.add_argument("--baseline-limit", type=int, default=200)
    parser.add_argument("--variant-limit", type=int, default=60)
    args = parser.parse_args()
    out = R1 / args.run_id
    if out.exists():
        raise SystemExit("run id already exists")
    out.mkdir(parents=True)
    if not LEXICAL.exists():
        raise SystemExit("lexical index missing; run the R1.1 clone step first")

    cases, rows = targets()
    store = BM25Store(path=LEXICAL, collection="enterprise_kb")
    try:
        per_case = {}
        for case in cases["cases"]:
            if not case.get("subquestions"):
                continue
            query = case["query"]
            baseline = ranks(store.search(query, min(200, args.baseline_limit), FILTERS))
            variants = {}
            for name, groups in concept_subsets(query).items():
                if groups:
                    variants[name] = ranks(store.search(query, args.variant_limit, FILTERS,
                                                        concept_groups=groups))
            variants["keyword_or"] = ranks(store.search(query, args.variant_limit, FILTERS))
            merged = {}
            for name, table in variants.items():
                for key, position in table.items():
                    merged.setdefault(key, []).append((position, name))
            union = {}
            for key, hits in merged.items():
                position, name = min(hits)
                union[key] = {"rank": position, "variant": name}
            per_case[case["id"]] = {"baseline": baseline, "variants": {k: len(v) for k, v in variants.items()},
                                    "union": union}
    finally:
        store.close()

    results = []
    for row in rows:
        key = (row["document_id"], row["chunk_index"])
        case = per_case[row["case_id"]]
        base = case["baseline"].get(key)
        union = case["union"].get(key)
        results.append({**row,
                        "baseline_rank": base,
                        "baseline_top60": bool(base and base <= 60),
                        "best_variant_rank": union["rank"] if union else None,
                        "best_variant": union["variant"] if union else None,
                        "recovered_top60": bool(union and union["rank"] <= 60)})

    summary = {
        "references": len(results),
        "baseline_top60": sum(1 for r in results if r["baseline_top60"]),
        "baseline_top200": sum(1 for r in results if r["baseline_rank"]),
        "recovered_top60": sum(1 for r in results if r["recovered_top60"]),
        "unreachable_in_top200": sum(1 for r in results if not r["baseline_rank"]),
        "by_variant": {name: sum(1 for r in results if r["best_variant"] == name)
                       for name in ("concept_and", "measure_indicator", "indicator_only", "keyword_or")},
    }
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "state": "offline_lexical_probe", "run_id": args.run_id,
              "inputs": {"query_cases_sha256": sha256(CASES), "span_transfer_sha256": sha256(TRANSFER),
                         "lexical_index": LEXICAL.relative_to(ROOT).as_posix(),
                         "lexical_index_sha256": sha256(LEXICAL)},
              "limits": {"model_calls": 0,
                         "vector_leg": "not decomposed: sub-intent vectors would need new embeddings",
                         "scope": "enterprise_kb lexical collection only",
                         "meaning": "lexical reachability bound, not end-to-end hybrid recall"},
              "baseline_limit": args.baseline_limit, "variant_limit": args.variant_limit,
              "summary": summary, "references": results}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# R1.4 意图拆解离线探针（词法）", "",
             f"- 参考证据：{len(results)} 条；原查询词法前 60：{summary['baseline_top60']} 条",
             f"- 原查询词法前 200 内可达：{summary['baseline_top200']} 条；200 名外不可达：{summary['unreachable_in_top200']} 条",
             f"- 拆解后进入前 60：**{summary['recovered_top60']}** 条",
             f"- 各变体命中：{summary['by_variant']}", "",
             "| 用例 | 子问题 | 文献 | 块 | 原查询排名 | 拆解最佳 | 变体 | 前60 |",
             "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |"]
    for row in results:
        lines.append(f"| {row['case_id']} | {row['subquestion_id']} | {row['document_id']} | {row['chunk_index']} | "
                     f"{row['baseline_rank'] or '-'} | {row['best_variant_rank'] or '-'} | "
                     f"{row['best_variant'] or '-'} | {'是' if row['recovered_top60'] else '否'} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
