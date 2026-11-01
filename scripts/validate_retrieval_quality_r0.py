"""Validate R0 audit evidence offline, without application/database initialization."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(run: Path) -> dict:
    def load(name: str) -> dict:
        return json.loads((run / name).read_text(encoding="utf-8"))

    source = load("source-audit.json")
    coverage = load("coverage-audit.json")
    cases = load("query-cases.json")
    inputs = load("query-inputs.json")
    history = load("historical-integrity.json")
    database = load("database-readonly-audit.json")
    documents = source["documents"]
    ids = {d["document_id"] for d in documents}
    require(len(documents) == len(ids) == 10, "Expected ten distinct sources")
    require(sum(d["chunk_count"] for d in documents) == 1306, "Chunk count changed")
    for d in documents:
        require(digest(Path(d["original_path"])) == d["file_sha256_frozen"], "Original source changed")
        require(digest(Path(d["corpus_path"])) == d["corpus_file_sha256"], "Frozen corpus changed")
        require(d["current_chroma_comparison"]["text_page_index_source_hash_match"], "Source comparison failed")

    require(coverage["record_count"] == len(coverage["records"]) == 29, "Record audit incomplete")
    statuses = Counter(r["historical_status"] for r in coverage["records"])
    require(statuses["rejected"] == 27, "Rejected historical records must remain rejected")
    require(coverage["accepted_pending_count"] == 2, "Pending record count changed")
    fields = [f for r in coverage["records"] for f in r["fields"].values()]
    require(len(fields) == 348, "All twelve fields per record must be audited")
    nonempty = [f for f in fields if f.get("quote") is not None]
    require(len(nonempty) == 104, "Nonempty field count changed")
    require(len(coverage["empty_documents"]) == 6, "Empty outputs must remain in audit")
    for d in coverage["empty_documents"]:
        require(d["all_chunks_structurally_inventoried"], "Document structure audit incomplete")
        require(bool(d["major_task_sections_review"]), "Missing task-section review")
        read = set(d["semantically_read_chunk_indexes"])
        unread = set(d["not_semantically_read_chunk_indexes"])
        frozen = json.loads((ROOT / f"artifacts/knowledge_platform/evidence-m1-v1/corpus/{d['document_id']}.json").read_text(encoding="utf-8"))
        all_indexes = {c["chunk_index"] for c in frozen["chunks"]}
        require(not (read & unread) and read | unread == all_indexes, "Read/unread coverage must partition document")
    for item in coverage["input_hashes"]:
        require(digest(ROOT / item["path"]) == item["sha256"], "Audit input changed")

    require(len(cases["cases"]) == 9, "Expected five primary cases and four variants")
    primary = [c for c in cases["cases"] if c["kind"] == "primary"]
    require({c["id"] for c in primary} == {"U1", "U2", "U3", "U4", "U5"}, "Primary cases changed")
    require(inputs["cases"] == [{"id": c["id"], "query": c["query"]} for c in cases["cases"]], "Query-only input diverged")
    parts = [p for c in primary for p in c["subquestions"]]
    references = [e for p in parts for e in p["reference_evidence"]]
    require(len(parts) == 12 and len(references) == 24, "Reference coverage changed")
    for e in references:
        require(e["document_id"] in ids, "Reference uses unselected source")
        path = ROOT / e["corpus_file"]
        require(digest(path) == e["corpus_file_sha256"], "Reference corpus hash changed")
        corpus = json.loads(path.read_text(encoding="utf-8"))
        chunk = next(c for c in corpus["chunks"] if c["chunk_index"] == e["chunk_index"])
        text = chunk["content"]
        require(chunk["page"] == e["page_one_based"], "Reference page changed")
        require(corpus["content_sha256"] == e["content_sha256"], "Reference source version changed")
        require(hashlib.sha256(text.encode("utf-8")).hexdigest() == e["chunk_text_sha256"], "Reference chunk changed")
        require(text[e["start"]:e["end"]] == e["quote"] and text.count(e["quote"]) == 1, "Invalid or ambiguous reference span")

    require(history["historical_manifest_state"] == "pass" and not history["mismatches"], "Historical freeze mismatch")
    require(history["model_calls_this_run"] == 0 and cases["model_api_calls"] == 0, "Unexpected model calls")
    require(database["state"] == "unavailable", "Runtime state changed; re-audit before describing it")
    for name in ["runtime-paths.md", "migration-runbook.md", "source-audit.md", "coverage-audit.md", "query-cases.md"]:
        require(bool((run / name).read_text(encoding="utf-8").strip()), "Missing readable audit document")
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(), "state": "pass",
        "meaning": "audit_artifact_integrity_only_not_retrieval_or_deployment_acceptance",
        "sources": len(documents), "chunks": 1306, "records": 29, "fields": len(fields),
        "cases": 9, "subquestions": len(parts), "reference_spans": len(references),
        "historical_file_references_checked": history["historical_file_references_checked"],
        "unresolved": ["PG current qualification/workflow/release state unavailable",
                       "Process visibility insufficient for service readiness",
                       "Two native CAJ page mappings not independently reverified",
                       "Layout, tables, source contradictions and unread ranges explicitly retained"],
        "model_api_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    result = validate(args.run_dir.resolve())
    if args.write_report:
        output = args.run_dir.resolve() / "validation.json"
        if output.exists():
            raise SystemExit("Refusing to overwrite existing validation report")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
