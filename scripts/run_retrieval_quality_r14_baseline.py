"""R1.4 real-interface baseline: per-subquestion evidence rank on the frozen corpus.

Reuses the verified isolated Chroma snapshot and the nine authorized query
vectors from the R1.1 run. No embedding or generation call is made: any query
outside the frozen manifest aborts the run. PostgreSQL is read-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
INPUTS = R1 / "r0-20261030/query-inputs.json"
SOURCE_RUN = R1 / "r1-r2-20261030-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_vectors():
    manifest = json.loads((SOURCE_RUN / "embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache = {}
    for item in manifest["requests"]:
        saved = json.loads((SOURCE_RUN / "embeddings" / (item["case_id"] + ".json")).read_text(encoding="utf-8"))
        if (saved["payload_sha256"] != item["payload_sha256"]
                or saved["origin"] != "fresh_authorized_R1_query_embedding"):
            raise ValueError("query_vector_version_mismatch")
        cache[item["payload"]["input"][0]] = saved["embedding"]
    return manifest, cache


def load_parse_index() -> dict:
    """Current chunk texts per document, from the R2.1 re-parse where available."""
    index = {}
    for folder in ("parsing", "parsing-additional"):
        for path in sorted((SOURCE_RUN / folder).glob("*.json")):
            if path.name == "summary.json":
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            document = data.get("document", {})
            document_id = document.get("document_id") or int(path.stem)
            chunks = [(chunk["chunk_index"], chunk["content"])
                      for chunk in data.get("chunk_set", {}).get("chunks", [])]
            if chunks:
                index[int(document_id)] = chunks
    return index


def _collapse(text: str):
    """Drop whitespace, keep an index map back to original codepoints."""
    kept, index = [], []
    for position, character in enumerate(text):
        if not character.isspace():
            kept.append(character)
            index.append(position)
    return "".join(kept), index


def locate(text: str, quote: str):
    """Exact first, then whitespace-insensitive; returns original offsets."""
    if not text or not quote:
        return None
    position = text.find(quote)
    if position >= 0:
        return {"start": position, "end": position + len(quote), "normalized": False}
    collapsed_text, index = _collapse(text)
    collapsed_quote, _ = _collapse(quote)
    if not collapsed_quote:
        return None
    hit = collapsed_text.find(collapsed_quote)
    if hit < 0:
        return None
    return {"start": index[hit], "end": index[hit + len(collapsed_quote) - 1] + 1,
            "normalized": True}


def evaluate_case(case, response, limit, parse_index=None):
    """Locate each reference quote in the returned window.

    R2.1 re-parsed part of the corpus, so the frozen M1 chunk indexes no longer
    address the current chunks. Evidence is therefore located by its exact
    quote text and then mapped to the current chunk and offset; a matching
    (chunk, start) pair is reported as an unchanged position, not assumed.
    """
    sources = response.get("sources", [])
    documents = response.get("documents", [])
    doc_rank = {}
    for position, document in enumerate(documents, start=1):
        doc_rank.setdefault(document.get("document_id"), position)

    subquestions = []
    reference_docs = set(case.get("reference_document_ids", []))
    for item in case.get("subquestions", []):
        rows, best = [], None
        for reference in item.get("reference_evidence", []):
            quote = reference.get("quote", "")
            document_id = reference["document_id"]
            mapped_document = document_id in (parse_index or {})
            current, current_match = None, None
            for chunk_index, content in (parse_index or {}).get(document_id, []):
                match = locate(content, quote)
                if match:
                    current, current_match = chunk_index, match
                    break
            if not mapped_document:
                # No re-parse for this document: the frozen chunk index still applies.
                current = reference["chunk_index"]
                current_match = {"start": reference.get("start", 0), "normalized": False}
            hits = []
            for rank, source in enumerate(sources, start=1):
                if source.get("document_id") != document_id:
                    continue
                match = locate(source.get("text") or "", quote)
                if current is not None and source.get("chunk_index") == current:
                    hits.append((rank, source, [current_match["start"]], current_match["normalized"]))
                elif match:
                    hits.append((rank, source, [match["start"]], match["normalized"]))
            if not hits:
                if mapped_document and current is None:
                    status = "quote_absent_from_current_parse"
                else:
                    status = "current_chunk_not_returned"
                rows.append({"document_id": document_id, "chunk_index": reference["chunk_index"],
                             "page": reference.get("page_one_based"), "rank": None,
                             "status": status, "quote_present": False,
                             "current_chunk_index": current, "role": reference.get("role")})
                continue
            rank, source, positions, normalized = hits[0]
            unchanged = (source.get("chunk_index") == reference["chunk_index"]
                         and positions[0] == reference.get("start"))
            status = "in_top5" if rank <= 5 else "returned_after_top5"
            if len(positions) > 1 and not unchanged:
                status += "_ambiguous_quote"
            best = rank if best is None else min(best, rank)
            rows.append({"document_id": reference["document_id"],
                         "chunk_index": reference["chunk_index"], "page": reference.get("page_one_based"),
                         "rank": rank, "status": status, "quote_present": True,
                         "current_chunk_index": source.get("chunk_index"),
                         "current_start": positions[0],
                         "position_unchanged": unchanged,
                         "whitespace_normalized_match": normalized,
                         "chunk_sha_changed": (source.get("publication") or {}).get("content_sha256") != reference.get("content_sha256"),
                         "role": reference.get("role")})
        passed = any(row["status"].startswith("in_top5") for row in rows)
        subquestions.append({"id": item["id"], "question": item["question"],
                             "answerability": item.get("answerability"),
                             "best_rank": best, "passed": passed, "references": rows})

    return {"case_id": case["id"], "query": case["query"],
            "status_code": response.get("_status_code", 200),
            "seconds": response.get("_seconds"),
            "documents": [{"rank": i + 1, "document_id": d.get("document_id"), "title": d.get("title"),
                           "version": (d.get("publication") or {}).get("version")}
                          for i, d in enumerate(documents)],
            "reference_document_ranks": {str(doc): doc_rank.get(doc) for doc in sorted(reference_docs)},
            "sources_returned": len(sources),
            "returned_sources": [{"rank": i + 1, "document_id": s.get("document_id"),
                                  "chunk_index": s.get("chunk_index"), "page": s.get("page"),
                                  "text_length": len(s.get("text") or "")}
                                 for i, s in enumerate(sources)],
            "subquestions": subquestions}


def ensure_writable_temp(preferred: Path) -> str:
    """Force a writable temp dir before Chroma starts.

    The sandbox exposes %TEMP% as an unwritable location while Python's
    ``tempfile`` silently falls back to the working directory. Chroma's Rust
    SQLite layer does not fall back, so the env vars are pinned explicitly.
    """
    preferred.mkdir(parents=True, exist_ok=True)
    for key in ("TMPDIR", "TEMP", "TMP"):
        os.environ[key] = str(preferred)
    return str(preferred)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="r14-20261031-v1")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    out = R1 / args.run_id
    if out.exists():
        raise SystemExit("run id already exists; choose a new one")
    out.mkdir(parents=True)
    temp_dir = ensure_writable_temp(out / ".tmp")
    clone = (SOURCE_RUN / "runtime/chroma").resolve()
    if not (clone / "chroma.sqlite3").exists():
        raise SystemExit("verified isolated clone missing; rerun R1.1 clone first")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    gates = cases["gates"]
    manifest, cache = load_vectors()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = str(clone)
    Config.HYBRID_SEARCH_ENABLED = True
    Config.SQLALCHEMY_DATABASE_URI = Config.SQLALCHEMY_DATABASE_URI.replace("+psycopg2", "+psycopg")
    os.environ["ANONYMIZED_TELEMETRY"] = "False"

    used = []

    def embed_query(query):
        if query not in cache:
            raise RuntimeError("query_outside_frozen_manifest_no_API_fallback")
        used.append(query)
        return cache[query]

    def forbidden(*a, **k):
        raise RuntimeError("r14_must_not_embed_documents")

    stub = types.ModuleType("framework.embedding.service")
    stub.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=embed_query,
                                                   embed_documents=forbidden)
    sys.modules["framework.embedding.service"] = stub

    started = time.perf_counter()
    from framework.vector_store.chroma_store import vector_store
    index_seconds = time.perf_counter() - started

    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_service import ResearchService
    from framework.knowledge_graph.research_store import ResearchStore, migrate
    from framework.api.routes.literature_evidence import create_evidence_app
    import sqlalchemy as sa
    from flask_jwt_extended import create_access_token

    source = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    engine = sa.create_engine("sqlite:///:memory:")
    migrate(engine, apply=True)
    with source.engine.connect() as connection:
        actor_id = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
    service = ResearchService(ResearchStore(engine), source,
                              corpus_search=PublishedCorpusSearch(vector_store, source))
    app = create_evidence_app(service, source.actor, jwt_secret=os.urandom(48).hex())
    with app.app_context():
        token = create_access_token(identity=str(actor_id))
    client = app.test_client()

    results = []
    try:
        for case in inputs["cases"]:
            began = time.perf_counter()
            response = client.post("/api/v1/literature-evidence/search",
                                   json={"query": case["query"], "limit": args.limit},
                                   headers={"Authorization": "Bearer " + token})
            payload = response.get_json() or {}
            payload["_status_code"] = response.status_code
            payload["_seconds"] = round(time.perf_counter() - began, 4)
            results.append(payload)
            print(json.dumps({"case_id": case["id"], "status": response.status_code,
                              "sources": len(payload.get("sources", [])),
                              "documents": len(payload.get("documents", [])),
                              "seconds": payload["_seconds"]}), flush=True)

        by_id = {c["id"]: c for c in cases["cases"]}
        parse_index = load_parse_index()
        evaluated = [evaluate_case(by_id[case["id"]], payload, args.limit, parse_index)
                     for case, payload in zip(inputs["cases"], results)]
    finally:
        source.close()
        engine.dispose()
        vector_store.close()

    subquestions = [s for case in evaluated for s in case["subquestions"]]
    passed = [s for s in subquestions if s["passed"]]
    doc_gate = {case["case_id"]: all(rank is not None and rank <= gates["distinct_paper_rank_max"]
                                     for rank in case["reference_document_ranks"].values())
                for case in evaluated}
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "state": "completed_real_interface_baseline",
              "run_id": args.run_id, "limit": args.limit,
              "inputs": {"query_cases_sha256": sha256(CASES), "query_inputs_sha256": sha256(INPUTS),
                         "embedding_manifest_sha256": sha256(SOURCE_RUN / "embedding-request-manifest-v2.json"),
                         "isolated_clone": clone.relative_to(ROOT).as_posix()},
              "index_load_seconds": round(index_seconds, 3),
              "query_vectors_used": len(set(used)), "additional_model_calls": 0,
              "writable_temp": temp_dir,
              "retrieval_mode_note": "hybrid requires vector and lexical legs; both are recorded per case",
              "http_instance": "isolated_product_blueprint_ephemeral_jwt_live_actor",
              "gates": gates,
              "summary": {"subquestions": len(subquestions), "passed": len(passed),
                          "pass_rate": round(len(passed) / len(subquestions), 4) if subquestions else None,
                          "document_gate_passed": doc_gate},
              "cases": evaluated,
              "limitations": ["semantic support unreviewed: rank is location evidence only",
                              "variants without subquestions are judged at document level only",
                              "no answer generation and no new embedding requests"]}
    (out / "baseline-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["# R1.4 真实接口基线", "",
             f"- 运行：`{args.run_id}`，返回上限 {args.limit}",
             f"- 子问题：{len(subquestions)} 个，支持前5通过 {len(passed)} 个",
             f"- 文档门槛（每篇参考文献进入前{gates['distinct_paper_rank_max']}）：{doc_gate}", "",
             "| 用例 | 子问题 | 最佳排名 | 前5 |", "| --- | --- | ---: | --- |"]
    for case in evaluated:
        for item in case["subquestions"]:
            lines.append(f"| {case['case_id']} | {item['id']} | {item['best_rank']} | "
                         f"{'通过' if item['passed'] else '未通过'} |")
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
