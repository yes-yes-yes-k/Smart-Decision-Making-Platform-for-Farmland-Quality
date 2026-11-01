"""Real full-corpus HTTP retrieval and existing-record queue, isolated writes only."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import sys
import time
import types
import statistics

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_knowledge_m2_snapshot import OUT
from framework.knowledge_graph.research_store import ResearchStore, migrate, jobs, records
from framework.knowledge_graph.research_service import ResearchService
from framework.knowledge_graph.research_sources import PublishedResearchSources
from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
from framework.api.routes.literature_evidence import create_evidence_app
from framework.knowledge_graph.operational_measurements import process_memory
import sqlalchemy as sa


def main():
    target = OUT/"product-v1.json"
    database = OUT/"runtime/research-m2.sqlite3"
    if target.exists() or database.exists():
        raise ValueError("isolated_measurement_exists_use_new_version")
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    os.environ["CHROMA_PERSIST_DIR"] = str((OUT/"runtime/chroma-clone").resolve())
    from framework.config import Config
    Config.CHROMA_PERSIST_DIR = os.environ["CHROMA_PERSIST_DIR"]
    fake = types.ModuleType("framework.embedding.service")
    def forbidden(*args, **kwargs):
        raise RuntimeError("M2_no_model_calls")
    fake.embedding_service = types.SimpleNamespace(is_available=lambda: False, embed_documents=forbidden, embed_query=forbidden)
    sys.modules["framework.embedding.service"] = fake
    from framework.vector_store.chroma_store import vector_store
    from flask_jwt_extended import create_access_token
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(database)))
    migrate(engine, apply=True)
    store = ResearchStore(engine)
    m1 = REPO/"artifacts/knowledge_platform/evidence-m1-v1"
    selected = json.loads((m1/"selection.json").read_text(encoding="utf-8"))["documents"]
    for item in selected:
        store.import_source(json.loads((m1/"corpus"/(str(item["id"])+".json")).read_text(encoding="utf-8")))
        for record in json.loads((m1/"records"/(str(item["id"])+".json")).read_text(encoding="utf-8")):
            store.add_record(record)
    current = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    with current.engine.connect() as connection:
        actor = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
        total = connection.execute(sa.text("SELECT count(*),sum(chunk_count) FROM kb_document")).one()
    service = ResearchService(store, current, corpus_search=PublishedCorpusSearch(vector_store, current))
    app = create_evidence_app(service, current.actor, jwt_secret=secrets.token_hex(32))
    with app.app_context():
        token = create_access_token(identity=str(actor))
    client = app.test_client()
    headers = {"Authorization": "Bearer "+token}
    prefix = "/api/v1/literature-evidence"
    def call(method, route, body=None):
        response = client.open(prefix+route, method=method, json=body, headers=headers)
        if response.status_code not in (200, 202):
            raise ValueError("product_route_failed:"+route+":"+str(response.status_code))
        return response.json
    searches = []
    for query in ("石灰", "soil organic carbon", "交换性氢", "有效钾", "生物炭", "cadmium soil", "秸秆", "有机质"):
        before = dict(current.metrics); started = time.perf_counter(); cpu = time.process_time()
        result = call("POST", "/search", {"query": query, "limit": 5})
        latency = time.perf_counter()-started
        searches.append({"query": query, "seconds": latency, "cpu_seconds": time.process_time()-cpu,
            "sources": [{key: item[key] for key in ("document_id", "content_sha256", "chunk_index", "page")} for item in result["sources"]],
            "state": result["state"], "candidate_budget": result["candidate_budget"], "candidates_read": result["candidates_read"],
            "verification": {key: current.metrics[key]-before[key] for key in before}})
        print(json.dumps({"query": query, "seconds": latency, "hits": len(result["sources"])}), flush=True)
    unregistered = next(item for search in searches for item in search["sources"] if item["document_id"] not in {item["id"] for item in selected})
    started = time.perf_counter()
    chunk = call("GET", f"/sources/{unregistered['document_id']}/chunks/{unregistered['chunk_index']}?content_sha256={unregistered['content_sha256']}")
    context_seconds = time.perf_counter()-started
    assert chunk["text"] and chunk["page"] == unregistered["page"]
    # Ten real source jobs; no extraction or model generation. Include durable
    # restart, queued/running cancellation, worker failure and stale-reference rejection.
    pending = []
    for index, item in enumerate(selected):
        response = call("POST", "/comparisons", {"query": "soil 土壤 lime biochar " + str(index), "document_ids": [item["id"]]})
        pending.append(response["id"])
    assert call("POST", "/comparisons", {"query": "soil 土壤 lime biochar 0", "document_ids": [selected[0]["id"]]})["reused"]
    service.cancel(actor, pending[0])
    # The next queued item is held at commit and cancelled while running.
    running_cancel = service.run_once(before_commit=lambda: service.cancel(actor, pending[1]))
    assert running_cancel["state"] == "lease_lost_or_cancelled"
    def fail():
        raise RuntimeError("injected_worker_failure")
    assert service.run_once(before_commit=fail)["state"] == "failed"
    with engine.begin() as connection:
        connection.execute(jobs.update().where(jobs.c.id == pending[3]).values(state="running", attempts=1, lease="expired-test-lease", lease_until=time.time()-1))
    service = ResearchService(store, current, corpus_search=PublishedCorpusSearch(vector_store, current))
    queue_samples = []
    while True:
        started = time.perf_counter(); cpu = time.process_time()
        value = service.run_once()
        if value["state"] == "idle":
            break
        queue_samples.append({"seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu, "state": value["state"]})
    assert store.job(pending[3], actor)["attempts"] == 2
    # Reject one pending candidate in this isolated store, then exercise normal
    # read-time invalidation. Original M1 labels and production rows stay intact.
    with engine.connect() as connection:
        candidate = connection.execute(sa.select(records.c.id, records.c.document_id).limit(1)).first()
    affected = next(identifier for identifier, item in zip(pending, selected) if item["id"] == candidate.document_id)
    if store.job(affected, actor)["state"] == "completed":
        store.reject_record(candidate.id)
        assert service.get(actor, affected)["state"] == "invalidated"
    else:
        # Always make one completed reference for explicit invalidation, even if
        # its document happened to be in a cancellation/failure scenario above.
        extra, _ = service.submit(actor, {"query": "soil 土壤 explicit invalidation", "document_ids": [candidate.document_id]})
        assert service.run_once()["state"] == "completed"
        store.reject_record(candidate.id)
        assert service.get(actor, extra["id"])["state"] == "invalidated"
    with engine.connect() as connection:
        counts = dict(connection.execute(sa.select(jobs.c.state, sa.func.count()).group_by(jobs.c.state)).all())
        all_jobs = connection.execute(sa.select(sa.func.count()).select_from(jobs)).scalar_one()
        record_count = connection.execute(sa.select(sa.func.count()).select_from(records)).scalar_one()
    assert sum(counts.values()) == all_jobs and counts.get("queued", 0) == counts.get("running", 0) == 0
    assert record_count == 2
    times = sorted(item["seconds"] for item in searches)
    report = {"state": "completed", "captured_at_utc": datetime.now(timezone.utc).isoformat(), "network_service_deployed": False,
        "source_database_readonly": True, "source_documents": total[0], "source_declared_chunks": total[1],
        "searches": searches, "search_median_seconds": statistics.median(times), "search_p95_seconds": times[-1],
        "unregistered_source_context": {"verified": True, "document_id": unregistered["document_id"], "seconds": context_seconds},
        "queue_processing_samples": queue_samples, "queue_counts": counts, "total_jobs": all_jobs, "backlog": 0,
        "recovered_job_attempts": 2, "pending_source_records_available_before_rejection": record_count,
        "queue_limits": {"pending_per_owner": 20, "pending_total": 100},
        "source_verification": current.metrics, "model_calls": 0, "published_claims_added": 0,
        "extraction_repeated": False, "memory": process_memory(),
        "limits": ["comparison_is_only_ten_registered_sources_two_existing_pending_records", "no_extraction_throughput_claim", "lightweight_blueprint_not_full_app_deployment"]}
    vector_store.close(); current.close(); engine.dispose()
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"state": "completed", "search_median_seconds": report["search_median_seconds"], "queue_counts": counts, "model_calls": 0}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); main()
