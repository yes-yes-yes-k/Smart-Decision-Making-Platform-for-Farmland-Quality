"""Diagnose baseline misses with stored terms and a SEPARATE vector@600 probe.

Never changes baseline budget/ranks and never calls an embedding API. Expanded
HNSW ranks are probe ranks, not claims of an exact exhaustive corpus ranking.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.retrieval_diagnostics import pointer, signature
from framework.vector_store.lexical_index import tokenize

BASE = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"
OUT = BASE.parent/"candidate-trace-20261030-v1"


def main():
    destination = OUT/"miss-probes.json"
    if destination.exists():
        raise ValueError("diagnostic_probe_exists_use_new_version")
    trace = json.loads((OUT/"candidate-trace.json").read_text(encoding="utf-8"))
    manifest = json.loads((BASE/"embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache = {}
    for item in manifest["requests"]:
        value = json.loads((BASE/"embeddings"/(item["case_id"]+".json")).read_text(encoding="utf-8"))
        if value["payload_sha256"] != item["payload_sha256"]:
            raise ValueError("query_cache_changed")
        cache[item["payload"]["input"][0]] = value["embedding"]
    def forbidden(*args, **kwargs):
        raise RuntimeError("offline_probe_no_model_calls")
    module = types.ModuleType("framework.embedding.service")
    module.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=lambda query: cache[query], embed_documents=forbidden)
    sys.modules["framework.embedding.service"] = module
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = str((BASE/"runtime/chroma").resolve())
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    from framework.vector_store.chroma_store import vector_store as store
    connection = sqlite3.connect((BASE/"runtime/chroma/lexical-index.sqlite3").resolve().as_uri()+"?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    results = []
    try:
        for case in trace["results"][:5]:
            target = case["targets"][0]
            did = target["document_id"]
            query_terms = sorted(set(tokenize(case["query"])))
            terms = set()
            rows = 0
            for collection in store._collections:
                values = connection.execute("SELECT t.terms FROM lexical_document d JOIN lexical_terms t ON t.rowid=d.rowid WHERE d.collection=? AND json_extract(d.metadata,'$.document_id')=?", (collection, did))
                for (text,) in values:
                    terms.update(text.split())
                    rows += 1
            result = {"case_id": case["case_id"], "document_id": did, "stored_lexical_chunks_checked": rows,
                      "query_terms": query_terms, "query_terms_found_in_target_stored_terms": sorted(set(query_terms) & terms),
                      "baseline_vector_best_rank_at60": target["stages"]["vector"]["best_chunk_rank"]}
            if result["baseline_vector_best_rank_at60"] is None:
                # A different n_results may change HNSW search effort. Keep this
                # separate and explicitly compare its prefix to the baseline.
                vector = store.search(case["query"], n_results=600,
                                      filters={"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": ["academic_paper"]}}]})
                candidates = [pointer(i) for i in vector["results"]]
                positions = [i for i, c in enumerate(candidates, 1) if c["document_id"] == did]
                result["separate_vector600_probe"] = {"best_rank": positions[0] if positions else None,
                                                       "target_chunk_ranks": positions, "candidates": candidates,
                                                       "state": vector.get("retrieval"),
                                                       "top60_matches_original_vector60": [signature(i) for i in candidates[:60]] == [signature(i) for i in case["stages"]["vector"]],
                                                       "ranking_is_exact_full_corpus": False}
            results.append(result)
            print(json.dumps({"case_id": case["case_id"], "lexical_overlap": result["query_terms_found_in_target_stored_terms"],
                              "vector600_best": result.get("separate_vector600_probe", {}).get("best_rank")}), flush=True)
        report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
                  "baseline_parameters_modified": False, "source_trace_sha256": hashlib.sha256((OUT/"candidate-trace.json").read_bytes()).hexdigest(),
                  "probe_only": True, "results": results,
                  "limits": ["Token intersection is a stored-token diagnostic, not semantic relevance judgment.",
                             "Vector@600 is a separate bounded ANN probe; it does not redefine original vector@60 or fused ranks.",
                             "No new corpus vectors or repaired parser versions were indexed."]}
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    finally:
        connection.close()
        store.close()


if __name__ == "__main__":
    main()
