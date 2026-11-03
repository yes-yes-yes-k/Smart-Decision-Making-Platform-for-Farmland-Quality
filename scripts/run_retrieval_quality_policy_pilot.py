"""Nine frozen natural queries through real HTTP retrieval, zero model calls.

Reuse only exact cached query vectors and the existing mutable isolated runtime.
Never import the production app or migrate the configured database. Source
checks use the existing read-only adapter; research tables are in memory only.
"""
import copy
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
BASE = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"
TRACE = BASE.parent/"candidate-trace-20261030-v1/candidate-trace.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in {".", ".."}:
        raise ValueError("invalid_run_id")
    out = BASE.parent/args.run_id
    out.mkdir(exist_ok=False)
    code_files = ["framework/vector_store/retrieval_policy.py", "framework/vector_store/lexical_index.py",
                  "framework/vector_store/bm25_store.py", "framework/vector_store/chroma_store.py",
                  "framework/knowledge_graph/research_retrieval.py", "framework/api/routes/literature_evidence.py",
                  "scripts/run_retrieval_quality_policy_pilot.py"]
    code_hashes = {name: digest(ROOT/name) for name in code_files}
    for name in code_files:
        target = out/"frozen-code"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT/name).read_bytes())
    frozen = json.loads((BASE/"manifest.json").read_text(encoding="utf-8"))["files"]
    for name, expected in frozen.items():
        if digest(BASE/name) != expected:
            raise ValueError("frozen_input_changed:"+name)
    trace_hash = digest(TRACE)
    manifest = json.loads((BASE/"embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache = {}
    for request in manifest["requests"]:
        saved = json.loads((BASE/"embeddings"/(request["case_id"]+".json")).read_text(encoding="utf-8"))
        if saved["payload_sha256"] != request["payload_sha256"]:
            raise ValueError("embedding_identity_changed")
        cache[request["payload"]["input"][0]] = saved["embedding"]
    def forbidden(*args, **kwargs):
        raise RuntimeError("pilot_new_model_calls_forbidden")
    embedding = types.ModuleType("framework.embedding.service")
    embedding.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=lambda q: cache[q], embed_documents=forbidden)
    sys.modules["framework.embedding.service"] = embedding
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = str((BASE/"runtime/chroma").resolve())
    Config.HYBRID_SEARCH_ENABLED, Config.RRF_K = True, 60
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    from framework.vector_store.chroma_store import vector_store as store
    from framework.vector_store.retrieval_policy import rank_documents, VERSION, MEASURES, INDICATORS, CONTEXT
    from framework.knowledge_graph.retrieval_diagnostics import pointer, signature, valid_paper
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_store import ResearchStore, migrate
    from framework.knowledge_graph.research_service import ResearchService
    from framework.api.routes.literature_evidence import create_evidence_app
    import sqlalchemy as sa
    from flask_jwt_extended import create_access_token
    source = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    engine = sa.create_engine("sqlite:///:memory:")
    migrate(engine, apply=True)
    search = PublishedCorpusSearch(store, source)
    service = ResearchService(ResearchStore(engine), source, corpus_search=search)
    app = create_evidence_app(service, source.actor, jwt_secret=os.urandom(48).hex())
    baseline = json.loads(TRACE.read_text(encoding="utf-8"))
    cases = json.loads((BASE.parent/"r0-20261030/query-inputs.json").read_text(encoding="utf-8"))["cases"]
    original_search, original_fuse = store.search, store._rrf_fuse
    capture = {}
    def fuse(vector, lexical, k=60):
        result = original_fuse(vector, lexical, k)
        capture.update(vector=[pointer(i) for i in vector], lexical=[pointer(i) for i in lexical],
                       fused_full=[pointer(i) for i in result])
        return result
    store._rrf_fuse = fuse
    results = []
    try:
        with source.engine.connect() as connection:
            actor = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
        with app.app_context():
            token = create_access_token(identity=str(actor))
        client = app.test_client()
        for case in cases:
            query = case["query"]
            # One exact cached vector lookup, same realized ANN candidates in both arms.
            vector = original_search(query, 60, {"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": ["academic_paper"]}}]})
            if vector.get("retrieval", {}).get("state") != "completed":
                raise ValueError("cached_vector_search_failed")
            def fixed_vector(q, *args, **kwargs):
                if q != query:
                    raise ValueError("query_changed_under_cached_vector")
                return copy.deepcopy(vector)
            store.search = fixed_vector
            row = {"case_id": case["id"], "query": query}
            for profile in ("baseline", "concepts"):
                search.enhance_recall = profile == "concepts"
                capture.clear()
                started = time.perf_counter()
                response = client.post("/api/v1/literature-evidence/search", json={"query": query, "limit": 20},
                                       headers={"Authorization": "Bearer "+token})
                body = response.get_json()
                if response.status_code != 200:
                    raise ValueError("pilot_HTTP_failed:"+str(body.get("error_code")))
                row[profile] = {"HTTP_status": response.status_code, "seconds": time.perf_counter()-started,
                                "stages": copy.deepcopy(capture), "response": body}
            old = next(r for r in baseline["results"] if r["case_id"] == case["id"])
            row["baseline_top20_matches_frozen"] = [signature(pointer(i)) for i in row["baseline"]["response"]["sources"]] == [signature(i) for i in old["stages"]["returned"]]
            # Fusion-only ablation on unchanged legs; weights are experiment arms,
            # not production settings. Keep every full rank and resulting cutoff.
            ablations = []
            legs = row["baseline"]["stages"]
            for vector_weight, vector_limit, lexical_limit in ((1, 60, 60), (1.5, 60, 60), (2, 60, 60), (1, 60, 30), (1, 30, 60)):
                scores, items = {}, {}
                for leg, weight, leg_limit in (("vector", vector_weight, vector_limit), ("lexical", 1, lexical_limit)):
                    for rank, item in enumerate(legs[leg][:leg_limit], 1):
                        key = signature(item)
                        scores[key] = scores.get(key, 0)+weight/(60+rank)
                        items.setdefault(key, item)
                ordered = [items[key] for key in sorted(scores, key=lambda key: -scores[key])]
                ablations.append({"vector_weight": vector_weight, "lexical_weight": 1, "k": 60,
                                  "vector_limit": vector_limit, "lexical_limit": lexical_limit,
                                  "fused_full": ordered, "fused_top60": ordered[:60], "top20_before_live_checks": ordered[:20],
                                  "current_source_revalidated": False})
            ids = sorted({item["document_id"] for arm in ablations for item in arm["fused_top60"]})
            checks = [source.lookup_many(ids, actor, require_academic=True) for _ in range(2)]
            for arm in ablations:
                arm["after_source_checks"] = [item for item in arm["fused_top60"] if all(
                    valid_paper({"metadata": item | {"document_kind": "academic_paper"}}, live.get(item["document_id"])) for live in checks)]
                arm["returned"] = arm["after_source_checks"][:20]
                arm["current_source_revalidated"] = True
            row["fusion_only_ablations"] = ablations
            row["changes"] = {}
            for unit in ("sources", "documents"):
                before = row["baseline"]["response"][unit]
                after = row["concepts"]["response"][unit]
                identity = ((lambda item: (item["document_id"], item["content_sha256"])) if unit == "documents" else
                            (lambda item: (item["document_id"], item["content_sha256"], item["chunk_index"])))
                old_keys, new_keys = {identity(item) for item in before}, {identity(item) for item in after}
                row["changes"][unit] = {"entered": [identity(item) for item in after if identity(item) not in old_keys],
                                        "exited": [identity(item) for item in before if identity(item) not in new_keys]}
            results.append(row)
            print(json.dumps({"case_id": case["id"], "HTTP_profiles_passed": 2, "frozen_top20": row["baseline_top20_matches_frozen"]}), flush=True)
        # Target labels enter only after all retrieval has completed.
        refs = json.loads((BASE.parent/"r0-20261030/query-cases.json").read_text(encoding="utf-8"))
        for row in results:
            reference = next(c for c in refs["cases"] if c["id"] == row["case_id"])
            row["target_ranks"] = {}
            for profile in ("baseline", "concepts"):
                data = row[profile]
                sequences = data["stages"] | {"sources": data["response"]["sources"], "documents": data["response"]["documents"]}
                row["target_ranks"][profile] = {str(did): {name: [i for i, item in enumerate(items, 1) if item["document_id"] == did]
                    for name, items in sequences.items()} for did in reference["reference_document_ids"]}
        for name, expected in frozen.items():
            if digest(BASE/name) != expected:
                raise ValueError("frozen_artifact_changed:"+name)
        if digest(TRACE) != trace_hash:
            raise ValueError("trace_changed")
        if any(digest(ROOT/name) != expected for name, expected in code_hashes.items()):
            raise ValueError("pilot_code_changed_during_run")
        metadata = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
                    "new_query_vectors": 0, "target_labels_used_in_retrieval": False,
                    "lexical_vocabulary_version": VERSION, "measures": MEASURES, "indicators": INDICATORS, "context": CONTEXT,
                    "candidate_budget_per_leg": 60, "lexical_split": [30, 30], "fused_budget": 60,
                    "evidence_limit": 20, "document_limit": 20, "frozen_files_unchanged": len(frozen),
                    "mutable_isolated_runtime_reused": True, "production_app_started": False,
                    "production_DB_migrated": False, "semantic_support_evaluated": False,
                    "trace_input_sha256": trace_hash, "all_frozen_top20_reproduced": all(r["baseline_top20_matches_frozen"] for r in results)}
        metadata["code_sha256"] = code_hashes
        outputs = {"candidate-recall-results.json": metadata | {"results": results},
                   "fusion-ranking-results.json": metadata | {"results": [{key: row[key] for key in ("case_id", "fusion_only_ablations", "target_ranks")} for row in results]},
                   "document-evidence-ranking-results.json": metadata | {"results": [{"case_id": row["case_id"], "target_ranks": row["target_ranks"],
                       "documents": row["concepts"]["response"]["documents"], "sources": row["concepts"]["response"]["sources"]} for row in results]}}
        for name, value in outputs.items():
            (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        files = {p.relative_to(out).as_posix(): digest(p) for p in out.rglob("*") if p.is_file()}
        (out/"manifest.json").write_text(json.dumps(metadata | {"files": files}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"output": str(out), "model_calls": 0, "frozen_files_unchanged": len(frozen)}))
    finally:
        store.search, store._rrf_fuse = original_search, original_fuse
        source.close()
        engine.dispose()
        store.close()


if __name__ == "__main__":
    main()
