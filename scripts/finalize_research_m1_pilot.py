"""Audit M1 requirement evidence and freeze reproducible nonproduction results."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT
from framework.knowledge_graph.contracts import SourceChunk
from framework.knowledge_graph.research_records import validate_record


def read(name):
    return json.loads((OUT/name).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = OUT/"completion-manifest-v1.json"
    if manifest.exists():
        existing = read(manifest.name)
        for name, expected in existing["files"].items():
            if sha(OUT/name) != expected:
                raise ValueError("frozen_M1_artifact_changed:"+name)
        print(json.dumps({"state": "already_frozen_unchanged", "files": len(existing["files"])}))
        return
    selected = read("selection.json")["documents"]
    verification = read("source-verification.json")
    pilot = read("product-pilot-v2.json")
    validation = read("validation-v1.json")
    compilation = read("record-compilation-v1.json")
    if len(selected) != 10 or verification["verified"] != 10 or len(pilot["documents"]) != 10 or len(pilot["sources"]["sources"]) != 10:
        raise ValueError("ten_real_paper_scope_incomplete")
    if not validation["exit_code"] == 0 or validation["tests_sha256"] != sha(REPO/"tests/test_research_evidence.py"):
        raise ValueError("current_tests_not_verified")
    if pilot["search_while_comparison_running"] != {"comparison_state": "running", "search_sources": 2} or not pilot["reuse"]:
        raise ValueError("asynchronous_or_reuse_evidence_missing")
    if pilot["published_claims_added"] != 0 or len(pilot["combined_comparison"]["result"]["rows"]) != compilation["source_grounded_records"]:
        raise ValueError("M1_trust_or_combined_output_mismatch")
    count = 0
    for item, result in zip(selected, pilot["documents"]):
        if item["id"] != result["document_id"] or result["comparison"]["state"] != "completed" or not result["context_matches"] or not result["search"]["sources"]:
            raise ValueError("real_product_route_evidence_missing")
        source = read("corpus/"+str(item["id"])+".json")
        if source["content_sha256"] != item["file_hash"] or source["verification"]["state"] != "verified":
            raise ValueError("source_verification_missing")
        chunks = {row["chunk_index"]: SourceChunk(**row) for row in source["chunks"]}
        for record in read("records/"+str(item["id"])+".json"):
            validate_record(record, chunks); count += 1
    if count != compilation["source_grounded_records"]:
        raise ValueError("pending_record_count_changed")
    post = read("source-store-postcheck-v1.json")
    if post["database"]["documents_total"] != 1173 or post["vector"]["embedding_rows"] != 112168 or post["database"]["KG_tables_across_schemas"]:
        raise ValueError("original_source_store_checkpoint_changed_requires_review")
    budget = read("execution/run-state.json")["budget"]
    if budget["requests"] != 10 or budget["tokens_charged_or_reserved"] > 500000 or budget["inflight"]:
        raise ValueError("M1_budget_or_terminal_state_invalid")
    external = REPO/"artifacts/knowledge_platform/external-benchmark-v1"
    connection = sqlite3.connect((external/"execution/budget.sqlite3").resolve().as_uri()+"?mode=ro", uri=True)
    try:
        old_budget = connection.execute("SELECT count(*),sum(coalesce(charged,reserved)),sum(CASE WHEN state='inflight' THEN 1 ELSE 0 END) FROM attempts").fetchone()
    finally:
        connection.close()
    if old_budget != (1361, 4093959, 0):
        raise ValueError("external_budget_changed_requires_scope_review")
    old_count = 0
    for name in ("calibration-result-manifest-v1.json", "qa-pilot-result-manifest-v1.json", "qa-pilot-result-manifest-v2.json"):
        data = json.loads((external/"reports"/name).read_text(encoding="utf-8"))
        for relative, expected in data["files"].items():
            if sha(external/relative) != expected:
                raise ValueError("historical_frozen_asset_changed")
            old_count += 1
    # Live queues stay mutable; archive transactionally consistent SQLite copies.
    for name, database in (("product-v1.sqlite3", OUT/"runtime/product.sqlite3"), ("M1-budget-v1.sqlite3", OUT/"execution/budget.sqlite3")):
        target = OUT/"frozen-runtime"/name
        target.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(database.resolve().as_uri()+"?mode=ro", uri=True)
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close(); source.close()
    code = [REPO/"framework/knowledge_graph"/(name+".py") for name in ("research_records", "research_extraction", "research_store", "research_service", "research_sources", "contracts")]
    code += [REPO/name for name in ("framework/api/routes/literature_evidence.py", "framework/api/app.py", "framework/config.py", "tests/test_research_evidence.py")]
    code += list((REPO/"scripts").glob("*research*m1*.py"))
    code += [REPO/"scripts/migrate_research_evidence.py", REPO/"scripts/run_research_comparison_worker.py"]
    for source in dict.fromkeys(code):
        target = OUT/"frozen-code"/source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
    paths = [path for path in OUT.rglob("*") if path.is_file() and "runtime" not in path.relative_to(OUT).parts and not path.name.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm"))]
    paths += list((OUT/"frozen-runtime").glob("*.sqlite3"))
    files = {str(path.relative_to(OUT)): sha(path) for path in paths}
    result = {"state": "M1_isolated_functional_workflow_complete", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
              "papers": 10, "source_chunks": 1306, "source_grounded_pending_records": count, "published_claims_added": 0,
              "quality_status": "extraction_coverage_insufficient_not_certified", "product_deployed": False,
              "tests_passed": validation["passed"], "M1_budget": budget,
              "historical_frozen_files_verified": old_count, "external_budget_unchanged": True,
              "API_and_workers_not_left_running": True, "files": files}
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("state", "papers", "source_grounded_pending_records", "tests_passed", "historical_frozen_files_verified")}))


if __name__ == "__main__":
    main()
