"""Real hybrid/HTTP baseline on a new isolated Chroma clone and read-only PG.

Only fresh, authorized R1 query vectors are accepted. No embedding API calls,
full application initialization, production writes or answer generation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"


def clone(source, target):
    if target.exists() or OUT.resolve() not in target.parents or source in target.parents:
        raise ValueError("clone_must_use_new_isolated_target")
    files = [p for p in source.rglob("*") if p.is_file() and p.name not in {"chroma.sqlite3", "chroma.sqlite3-wal", "chroma.sqlite3-shm"}
             and not p.name.startswith("lexical-index")]
    if any(source not in p.resolve().parents for p in files):
        raise ValueError("outside_source_file_link")
    before = {p.relative_to(source).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    total = sum(v[0] for v in before.values())+(source/"chroma.sqlite3").stat().st_size
    if shutil.disk_usage(OUT).free < total*2:
        raise ValueError("clone_disk_headroom_insufficient")
    target.mkdir(parents=True)
    origin = sqlite3.connect((source/"chroma.sqlite3").as_uri()+"?mode=ro", uri=True)
    origin.execute("PRAGMA query_only=ON")
    version = origin.execute("PRAGMA data_version").fetchone()[0]
    destination = sqlite3.connect(target/"chroma.sqlite3")
    try:
        origin.backup(destination)
        for p in files:
            copy = target/p.relative_to(source)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, copy)
        after = {p.relative_to(source).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
        if before != after or version != origin.execute("PRAGMA data_version").fetchone()[0]:
            raise ValueError("source_changed_during_clone_do_not_use")
    finally:
        destination.close()
        origin.close()
    return {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "source_not_written": True,
            "sqlite_transactional_backup": True, "source_vector_file_stats_unchanged": True,
            "copied_bytes": total, "target": target.relative_to(ROOT).as_posix(),
            "limits": "Isolated query snapshot, not a production backup/restore certificate"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("clone", "run"))
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    from framework.config import Config
    target = (OUT/"runtime/chroma").resolve()
    if args.phase == "clone":
        report = clone(Path(Config.CHROMA_PERSIST_DIR).resolve(), target)
        (OUT/"clone.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(report))
        return
    if not (OUT/"clone.json").exists() or not (target/"chroma.sqlite3").exists() or (OUT/"baseline-results.json").exists():
        raise ValueError("new_verified_clone_and_new_run_required")
    inputs = json.loads((ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030/query-inputs.json").read_text(encoding="utf-8"))
    manifest = json.loads((OUT/"embedding-request-manifest-v2.json").read_text(encoding="utf-8"))
    cache = {}
    for item in manifest["requests"]:
        saved = json.loads((OUT/"embeddings"/(item["case_id"]+".json")).read_text(encoding="utf-8"))
        if (saved["payload_sha256"] != item["payload_sha256"] or saved["origin"] != "fresh_authorized_R1_query_embedding"
                or saved["model"] != Config.SILICONFLOW_EMBED_MODEL):
            raise ValueError("query_vector_version_or_model_mismatch")
        cache[item["payload"]["input"][0]] = saved["embedding"]
    query_vectors_used = []
    def embed_query(query):
        if query not in cache:
            raise ValueError("query_outside_frozen_R1_manifest_no_API_fallback")
        query_vectors_used.append(query)
        return cache[query]
    def forbidden(*args, **kwargs):
        raise RuntimeError("baseline_must_not_generate_new_document_embeddings")
    embedding = types.ModuleType("framework.embedding.service")
    embedding.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=embed_query, embed_documents=forbidden)
    sys.modules["framework.embedding.service"] = embedding
    Config.CHROMA_PERSIST_DIR = str(target)
    Config.HYBRID_SEARCH_ENABLED = True
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    started = time.perf_counter()
    from framework.vector_store.chroma_store import vector_store
    print(json.dumps({"phase": "index_ready", "seconds": time.perf_counter()-started}), flush=True)
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
    from framework.knowledge_graph.research_service import ResearchService
    from framework.knowledge_graph.research_store import ResearchStore, migrate
    from framework.api.routes.literature_evidence import create_evidence_app
    import sqlalchemy as sa
    from flask_jwt_extended import create_access_token
    source = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    # Only an ephemeral test store is migrated; all authority checks use PG RO.
    engine = sa.create_engine("sqlite:///:memory:")
    migrate(engine, apply=True)
    with source.engine.connect() as connection:
        actor_id = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
    service = ResearchService(ResearchStore(engine), source, corpus_search=PublishedCorpusSearch(vector_store, source))
    app = create_evidence_app(service, source.actor, jwt_secret=os.urandom(48).hex())
    with app.app_context():
        token = create_access_token(identity=str(actor_id))
    client = app.test_client()
    results = []
    try:
        for case in inputs["cases"]:
            began = time.perf_counter()
            response = client.post("/api/v1/literature-evidence/search", json={"query": case["query"], "limit": 20},
                                   headers={"Authorization": "Bearer "+token})
            payload = response.get_json()
            result = {"case_id": case["id"], "query": case["query"], "status_code": response.status_code,
                      "seconds": time.perf_counter()-began, "response": payload}
            results.append(result)
            print(json.dumps({"case_id": case["id"], "status_code": response.status_code,
                              "hits": len(payload.get("sources", [])), "mode": payload.get("retrieval", {}).get("mode"),
                              "seconds": result["seconds"]}), flush=True)
        report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
                  "state": "completed_baseline_path_verification" if all(r["status_code"] == 200 and r["response"].get("retrieval", {}).get("mode") == "hybrid" for r in results) else "incomplete",
                  "results": results, "query_vectors_used": len(query_vectors_used), "additional_model_calls": 0,
                  "vector_origin": "fresh_authorized_R1_query_embeddings_exact_query_cache_not_corpus_vectors",
                  "hybrid_configuration": {"fusion": "rrf", "k": Config.RRF_K, "candidate_budget": 60, "returned_evidence_limit": 20, "reranking": "not_applied"},
                  "current_source_metrics": source.metrics, "snapshot_chunks": vector_store.get_collection_stats()["count"],
                  "source_authority": "live_read_only_PG_and_original_file_SHA256_revalidated_twice",
                  "HTTP_instance": "isolated_same_product_blueprint_ephemeral_JWT_live_active_actor_not_deployed_server",
                  "production_database_written": False, "production_vector_index_written": False,
                  "retrieval_quality_acceptance": "not_R1.2_or_R1.4_paper_dedup_or_support_acceptance"}
        (OUT/"baseline-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    finally:
        source.close()
        engine.dispose()
        vector_store.close()


if __name__ == "__main__":
    main()
