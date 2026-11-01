"""Trace the unchanged nine-query baseline with cached real query vectors.

Capture each retrieval leg BEFORE fusion/truncation. Known target IDs are only
applied after retrieval, never passed as retrieval filters or query expansion.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.retrieval_diagnostics import pointer, signature, target_summary, valid_paper

BASE = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"
OUT = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/candidate-trace-20261030-v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise ValueError("trace_output_exists_use_new_run_version")
    code_files = ["framework/vector_store/chroma_store.py", "framework/knowledge_graph/research_retrieval.py",
                  "framework/knowledge_graph/research_sources.py", "framework/knowledge_graph/research_service.py",
                  "framework/api/routes/literature_evidence.py"]
    for name in code_files:
        if digest(ROOT/name) != digest(BASE/"frozen-code"/name):
            raise ValueError("baseline_code_changed_do_not_attribute_old_results:"+name)
    baseline = json.loads((BASE/"baseline-results.json").read_text(encoding="utf-8"))
    inputs = json.loads((BASE.parent/"r0-20261030/query-inputs.json").read_text(encoding="utf-8"))
    manifest = json.loads((BASE/"embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache, input_hashes = {}, {}
    for item in manifest["requests"]:
        path = BASE/"embeddings"/(item["case_id"]+".json")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved["payload_sha256"] != item["payload_sha256"] or saved["origin"] != "fresh_authorized_R1_query_embedding":
            raise ValueError("query_embedding_identity_changed")
        cache[item["payload"]["input"][0]] = saved["embedding"]
        input_hashes[path.relative_to(ROOT).as_posix()] = digest(path)
    def embed_query(query):
        return cache[query]  # Missing query fails; there is no API fallback.
    def forbidden(*args, **kwargs):
        raise RuntimeError("candidate_trace_no_model_or_new_embeddings")
    embedding = types.ModuleType("framework.embedding.service")
    embedding.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=embed_query, embed_documents=forbidden)
    sys.modules["framework.embedding.service"] = embedding
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = str((BASE/"runtime/chroma").resolve())
    Config.HYBRID_SEARCH_ENABLED = True
    Config.RRF_K = baseline["hybrid_configuration"]["k"]
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    from framework.vector_store.chroma_store import vector_store as store
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_service import ResearchService
    from framework.knowledge_graph.research_store import ResearchStore, migrate
    from framework.api.routes.literature_evidence import create_evidence_app
    import sqlalchemy as sa
    from flask_jwt_extended import create_access_token
    if store.get_collection_stats()["count"] != baseline["snapshot_chunks"]:
        raise ValueError("baseline_snapshot_count_changed")
    source = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    engine = sa.create_engine("sqlite:///:memory:")
    migrate(engine, apply=True)
    OUT.mkdir(parents=True)
    capture = {}
    original_vector, original_lexical, original_fuse, original_collection = store.search, store._bm25_search, store._rrf_fuse, store._search_in
    original_lookup = source.lookup_many

    def vector(*args, **kwargs):
        result = original_vector(*args, **kwargs)
        capture["vector"] = result["results"]
        capture["vector_state"] = result.get("retrieval")
        return result
    def lexical(*args, **kwargs):
        result = original_lexical(*args, **kwargs)
        capture["lexical"] = result
        return result
    def fuse(*args, **kwargs):
        result = original_fuse(*args, **kwargs)
        capture["fused_full"] = result
        return result
    def collection(collection, *args, **kwargs):
        result = original_collection(collection, *args, **kwargs)
        capture.setdefault("vector_collections", {})[collection.name] = result
        return result
    def lookup(*args, **kwargs):
        result = original_lookup(*args, **kwargs)
        capture.setdefault("lookups", []).append(result)
        return result
    store.search, store._bm25_search, store._rrf_fuse, store._search_in = vector, lexical, fuse, collection
    source.lookup_many = lookup
    service = ResearchService(ResearchStore(engine), source, corpus_search=PublishedCorpusSearch(store, source))
    app = create_evidence_app(service, source.actor, jwt_secret=os.urandom(48).hex())
    results = []
    try:
        with source.engine.connect() as connection:
            actor_id = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
        with app.app_context():
            token = create_access_token(identity=str(actor_id))
        client = app.test_client()
        for case in inputs["cases"]:
            capture.clear()
            began = time.perf_counter()
            response = client.post("/api/v1/literature-evidence/search", json={"query": case["query"], "limit": 20},
                                   headers={"Authorization": "Bearer "+token})
            payload = response.get_json()
            full = capture.get("fused_full", [])
            top60 = full[:60]
            lookups = capture.get("lookups", [])
            after = []
            if len(lookups) == 2:
                after = [item for item in top60 if all(valid_paper(item, live.get(item["metadata"].get("document_id"))) for live in lookups)]
            returned = [pointer(i) for i in payload.get("sources", [])]
            phases_verified = (response.status_code == 200 and len(lookups) == 2
                               and [signature(pointer(i)) for i in after[:20]] == [signature(i) for i in returned]
                               and payload["filtered_unverified_or_stale"] == len(top60)-len(after))
            old = next(r for r in baseline["results"] if r["case_id"] == case["id"])
            stages = {"vector": [pointer(i) for i in capture.get("vector", [])],
                      "lexical": [pointer(i) for i in capture.get("lexical", [])],
                      "fused_full": [pointer(i) for i in full], "fused_top60": [pointer(i) for i in top60],
                      "after_source_checks": [pointer(i) for i in after], "returned": returned}
            safe_live = [{str(k): {field: v.get(field) for field in ("content_sha256", "review_status", "visibility_scope", "completed", "source_bytes_valid", "document_kind")} for k, v in live.items()} for live in lookups]
            result = {"case_id": case["id"], "query": case["query"], "HTTP_status": response.status_code,
                      "seconds": time.perf_counter()-began, "stages": stages,
                      "vector_collections": {name: [pointer(i) for i in items] for name, items in capture.get("vector_collections", {}).items()},
                      "current_source_checks": safe_live, "source_phases_verified_against_product_response": phases_verified,
                      "returned_order_matches_previous_baseline": [signature(i) for i in returned] == [signature(pointer(i)) for i in old["response"].get("sources", [])],
                      "actual_retrieval": payload.get("retrieval"), "error_code": payload.get("error_code")}
            results.append(result)
            print(json.dumps({"case_id": case["id"], "vector": len(stages["vector"]), "lexical": len(stages["lexical"]),
                              "fused_full": len(full), "same_previous_top20": result["returned_order_matches_previous_baseline"]}), flush=True)
        # Apply known targets only AFTER every retrieval has finished.
        references = json.loads((BASE.parent/"r0-20261030/query-cases.json").read_text(encoding="utf-8"))
        target_ids = sorted({did for c in references["cases"] for did in c["reference_document_ids"]})
        target_authority = original_lookup(target_ids, actor_id, require_academic=True)
        inventory = {}
        for did in target_ids:
            values = []
            for collection in store._collections.values():
                found = collection.get(where={"document_id": did}, include=["metadatas"])
                values.extend(found.get("metadatas") or [])
            inventory[did] = {"indexed_chunks": len(values), "public_academic_chunks": sum(m.get("visibility_scope") == "public" and m.get("document_kind") == "academic_paper" for m in values),
                              "current_source": {k: target_authority.get(did, {}).get(k) for k in ("content_sha256", "review_status", "visibility_scope", "completed", "source_bytes_valid", "document_kind")}}
        for result in results:
            case = next(c for c in references["cases"] if c["id"] == result["case_id"])
            result["targets"] = [target_summary(did, result["stages"], source_checks_verified=result["source_phases_verified_against_product_response"]) | {"inventory": inventory[did]} for did in case["reference_document_ids"]]
        report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "state": "completed_candidate_attribution",
                  "candidate_limit_per_leg": 60, "fusion_k": Config.RRF_K, "fused_limit": 60, "return_limit": 20,
                  "ranker_or_filters_modified": False, "target_ids_used_in_retrieval": False, "model_calls": 0,
                  "baseline_snapshot_chunks": baseline["snapshot_chunks"], "isolated_mutable_runtime_reused": True,
                  "input_hashes": input_hashes | {"baseline-results.json": digest(BASE/"baseline-results.json")},
                  "product_code_sha256": {name: digest(ROOT/name) for name in code_files},
                  "chroma_version": importlib.metadata.version("chromadb"),
                  "results": results, "all_source_stages_verified": all(r["source_phases_verified_against_product_response"] for r in results),
                  "all_previous_top20_reproduced": all(r["returned_order_matches_previous_baseline"] for r in results),
                  "limits": ["Not in top60 means only that window was missed, not absent from whole corpus.", "Ranks are chunk ranks. First-seen paper order is a diagnostic projection, not a new ranking.", "Title-bearing variants change more than language; they do not isolate a causal translation benefit."]}
        (OUT/"candidate-trace.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    finally:
        store.search, store._bm25_search, store._rrf_fuse, store._search_in = original_vector, original_lexical, original_fuse, original_collection
        source.lookup_many = original_lookup
        source.close()
        engine.dispose()
        store.close()


if __name__ == "__main__":
    main()
