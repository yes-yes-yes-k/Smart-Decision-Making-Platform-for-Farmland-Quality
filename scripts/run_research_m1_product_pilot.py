"""Exercise ten real papers through the product blueprint in an isolated instance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import threading

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT
from framework.knowledge_graph.research_store import ResearchStore
from framework.knowledge_graph.research_service import ResearchService
from framework.knowledge_graph.research_sources import PublishedResearchSources
from framework.api.routes.literature_evidence import create_evidence_app
import sqlalchemy as sa


def main():
    if (OUT/"completion-manifest-v1.json").exists():
        raise ValueError("M1_product_results_frozen_use_a_new_run_version")
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    from flask_jwt_extended import create_access_token
    path = OUT/"runtime/product.sqlite3"
    if not path.is_file():
        raise ValueError("explicit_pilot_migration_required_first")
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(path)), connect_args={"check_same_thread": False})
    store = ResearchStore(engine); store.require_schema()
    current = PublishedResearchSources(Config.SQLALCHEMY_DATABASE_URI, Config.UPLOAD_FOLDER)
    compilation = json.loads((OUT/"record-compilation-v1.json").read_text(encoding="utf-8"))
    diagnostics = {row["document_id"]: row for row in compilation["documents"]}
    selection = json.loads((OUT/"selection.json").read_text(encoding="utf-8"))
    for item in selection["documents"]:
        document = json.loads((OUT/"corpus"/(str(item["id"])+".json")).read_text(encoding="utf-8"))
        live = current(item["id"], 0)
        if not live or not live["source_bytes_valid"] or live["content_sha256"] != document["content_sha256"]:
            raise ValueError("real_pilot_source_no_longer_current")
        diagnostic = diagnostics[item["id"]]
        document["extraction_summary"] = {"request_state": diagnostic["request_state"], "valid_records": diagnostic["valid_records"],
            "rejected_selections": len(diagnostic["invalid_selections"]), "empty_output": diagnostic["empty_output"],
            "selected_chunks": 8, "total_chunks": len(document["chunks"]), "coverage": "partial_task_selection"}
        store.import_source(document)
        for record in json.loads((OUT/"records"/(str(item["id"])+".json")).read_text(encoding="utf-8")):
            store.add_record(record)
    # Read an existing active identity; no password, token or username is saved.
    with current.engine.connect() as connection:
        actor_id = connection.execute(sa.text("SELECT id FROM sys_user WHERE status=1 ORDER BY id LIMIT 1")).scalar_one()
    service = ResearchService(store, current)
    app = create_evidence_app(service, current.actor, jwt_secret=secrets.token_hex(32))
    with app.app_context():
        token = create_access_token(identity=str(actor_id))
    headers = {"Authorization": "Bearer "+token}
    client = app.test_client()
    prefix = "/api/v1/literature-evidence"
    def call(method, route, data=None):
        response = client.open(prefix+route, method=method, json=data, headers=headers)
        if response.status_code not in (200, 202):
            raise ValueError("product_route_failed:"+route+":"+str(response.status_code)+":"+str(response.json))
        return response.json
    report = {"state": "running", "scope": "ten_real_papers_through_product_blueprint_isolated_instance",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(), "network_service_deployed": False,
        "source_database_mode": "live_readonly_PostgreSQL_and_original_hash_recheck",
        "product_store": "isolated_SQLite_not_capacity_proof", "graph": "not_configured_source_retrieval_independent",
        "model_calls_during_product_pilot": 0, "published_claims_added": 0,
        "sources": call("GET", "/sources"), "documents": []}
    for item in selection["documents"]:
        document_id = item["id"]
        search = call("POST", "/search", {"query": "soil 土壤", "document_ids": [document_id], "limit": 3})
        if not search["sources"] or any(row["document_id"] != document_id for row in search["sources"]):
            raise ValueError("real_paper_not_retrievable:"+str(document_id))
        hit = search["sources"][0]
        context = call("GET", f"/sources/{document_id}/chunks/{hit['chunk_index']}?content_sha256={hit['content_sha256']}")
        if context["text"] != hit["text"] or context["page"] != hit["page"]:
            raise ValueError("product_source_context_changed")
        job = call("POST", "/comparisons", {"query": "soil 土壤 yield SOC biochar lime 石灰 生物炭", "document_ids": [document_id]})
        if job["state"] == "queued":
            service.run_once()
        result = call("GET", "/comparisons/"+job["id"])
        if result["state"] != "completed":
            raise ValueError("product_comparison_not_completed")
        report["documents"].append({"document_id": document_id, "stratum": item["stratum"], "search": search,
                                    "context_matches": True, "comparison": result})
        print(json.dumps({"document_id": document_id, "product_state": result["state"], "rows": len(result["result"]["rows"])}), flush=True)
    # Deliberately hold only this worker before commit: normal search must remain usable.
    combined_request = {"query": "soil 土壤 yield SOC biochar lime 石灰 生物炭", "limit": 30}
    combined = call("POST", "/comparisons", combined_request)
    entered, release = threading.Event(), threading.Event()
    if combined["state"] == "queued":
        def hold():
            entered.set()
            if not release.wait(20):
                raise RuntimeError("pilot_release_timed_out")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(service.run_once, before_commit=hold)
            if not entered.wait(20):
                raise ValueError("comparison_worker_not_running")
            try:
                while_running = call("GET", "/comparisons/"+combined["id"])
                independent_search = call("POST", "/search", {"query": "soil 土壤", "limit": 2})
                report["search_while_comparison_running"] = {"comparison_state": while_running["state"], "search_sources": len(independent_search["sources"])}
            finally:
                release.set()
            future.result(timeout=30)
    else:
        report["search_while_comparison_running"] = {"state": "previous_completed_run_reused_not_remeasured"}
    report["combined_comparison"] = call("GET", "/comparisons/"+combined["id"])
    report["reuse"] = call("POST", "/comparisons", combined_request)["reused"]
    report["state"] = "product_workflow_completed_extraction_coverage_limited"
    report["record_compilation"] = compilation
    (OUT/"product-pilot-v2.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    current.close(); engine.dispose()
    print(json.dumps({"papers": len(report["documents"]), "current_sources": len(report["sources"]["sources"]),
                      "pending_research_records": compilation["source_grounded_records"], "published_claims_added": 0}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
