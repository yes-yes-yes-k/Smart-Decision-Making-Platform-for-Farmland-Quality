"""Offline block-ranking probe over the existing 60-candidate pool.

Answers two questions without any model call: how many reference chunks are in
the pool at all, and can ranking heuristics lift them into the top 5?
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
TRANSFER = R1 / "span-transfer-20261031-v1/span-transfer.json"
SOURCE_RUN = R1 / "r1-r2-20261030-v1"
CLONE = SOURCE_RUN / "runtime/chroma"
FILTERS = {"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": ["academic_paper"]}}]}

SECTION_HINTS = {
    "abstract": 0.2, "introduction": 0.0, "material": -0.3, "method": -0.3,
    "result": 0.6, "discussion": 0.4, "conclusion": 0.5, "reference": -0.8,
}


def _norm(text: str) -> str:
    return "".join(character for character in text if not character.isspace())


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
                             "chunk_index": mapped.get("chunk_index", reference["chunk_index"]),
                             "old_chunk_index": reference["chunk_index"],
                             "quote": reference.get("quote", "")})
    return cases, rows


def section_prior(text: str) -> float:
    lowered = (text or "").casefold()
    score = 0.0
    for key, weight in SECTION_HINTS.items():
        if key in lowered:
            score += weight
    return round(score, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="block-ranking-20261031-v1")
    parser.add_argument("--pool", type=int, default=60)
    args = parser.parse_args()
    out = R1 / args.run_id
    out.mkdir(parents=True, exist_ok=True)
    temp = (out / ".tmp").resolve(); temp.mkdir(exist_ok=True)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(temp)

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = str(CLONE)
    Config.HYBRID_SEARCH_ENABLED = True
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    manifest = json.loads((SOURCE_RUN / "embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache = {}
    for item in manifest["requests"]:
        saved = json.loads((SOURCE_RUN / "embeddings" / (item["case_id"] + ".json")).read_text(encoding="utf-8"))
        cache[item["payload"]["input"][0]] = saved["embedding"]

    def embed_query(query):
        if query not in cache:
            raise RuntimeError("query_outside_frozen_manifest")
        return cache[query]

    stub = types.ModuleType("framework.embedding.service")
    stub.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=embed_query,
                                                   embed_documents=lambda *a, **k: None)
    sys.modules["framework.embedding.service"] = stub

    from framework.vector_store.chroma_store import vector_store
    from framework.knowledge_graph.answerability_rerank import rerank_values, score_chunk

    cases, rows = targets()
    per_case, ranks, records = {}, {}, []
    try:
        for case in cases["cases"]:
            if not case.get("subquestions"):
                continue
            result = vector_store.hybrid_search(case["query"], n_results=args.pool, filters=FILTERS, domain_expansion=True)
            candidates = result["results"][:args.pool]
            values = [{"document_id": item["metadata"].get("document_id"),
                       "chunk_index": item["metadata"].get("chunk_index"),
                       "text": item.get("content", "")} for item in candidates]
            def first_rank(sequence, quote):
                target = _norm(quote)
                for position, item in enumerate(sequence, start=1):
                    text = item.get("text", "")
                    if quote and (quote in text or (target and target in _norm(text))):
                        return position
                return None

            answerable, _ = rerank_values(case["query"], values)
            sectioned = sorted(values, key=lambda value: -(
                score_chunk(case["query"], value["text"])["score"] + section_prior(value["text"])))

            case_rows = [row for row in rows if row["case_id"] == case["id"]]
            base, answerable_rank, section_rank = {}, {}, {}
            for row in case_rows:
                key = (row["document_id"], row["old_chunk_index"])
                base[key] = first_rank(values, row["quote"])
                answerable_rank[key] = first_rank(answerable, row["quote"])
                section_rank[key] = first_rank(sectioned, row["quote"])

            per_case[case["id"]] = {"pool": len(values), "mode": result["retrieval"].get("mode")}
            ranks[case["id"]] = {"base": base, "answerable": answerable_rank, "section": section_rank}
    finally:
        vector_store.close()

    for row in rows:
        key = (row["document_id"], row["old_chunk_index"])
        case = ranks[row["case_id"]]
        records.append({**row, "in_pool": bool(case["base"].get(key)),
                        "baseline_rank": case["base"].get(key),
                        "answerable_rank": case["answerable"].get(key),
                        "section_rank": case["section"].get(key)})

    summary = {"references": len(records),
               "in_pool": sum(1 for r in records if r["in_pool"]),
               "baseline_top5": sum(1 for r in records if r["baseline_rank"] and r["baseline_rank"] <= 5),
               "answerable_top5": sum(1 for r in records if r["answerable_rank"] and r["answerable_rank"] <= 5),
               "section_top5": sum(1 for r in records if r["section_rank"] and r["section_rank"] <= 5),
               "in_pool_top20": {case: sum(1 for r in records
                                           if r["case_id"] == case and r["in_pool"]
                                           and r["baseline_rank"] and r["baseline_rank"] <= 20)
                                 for case in per_case}}
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "state": "offline_probe",
              "pool": args.pool, "model_calls": 0,
              "summary": summary, "cases": per_case, "references": records,
              "limits": ["single original query per case; no intent decomposition",
                         "ranking can only reorder candidates already in the pool"]}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# 块级排序离线探针", "",
             f"- 参考证据 {len(records)} 条；落在 60 候选池内 **{summary['in_pool']}** 条",
             f"- 池内前 5：基线 {summary['baseline_top5']} / 可答性 {summary['answerable_top5']} / 加章节先验 {summary['section_top5']}",
             "", "| 用例 | 子问题 | 文献 | 块 | 池内 | 基线 | 可答性 | 章节 |",
             "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |"]
    for r in records:
        lines.append(f"| {r['case_id']} | {r['subquestion_id']} | {r['document_id']} | {r['chunk_index']} | "
                     f"{'是' if r['in_pool'] else '否'} | {r['baseline_rank'] or '-'} | "
                     f"{r['answerable_rank'] or '-'} | {r['section_rank'] or '-'} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
