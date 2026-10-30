"""Verify R1/R2 delivery artifacts offline; never opens the product application."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.upload.pdf_layout import map_old_chunks, versioned_chunks

DEFAULT_RUN = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(run):
    def load(name):
        return json.loads((run/name).read_text(encoding="utf-8"))

    audit = json.loads((run.parent/"r0-20261030/source-audit.json").read_text(encoding="utf-8"))
    originals = {d["document_id"]: d for d in audit["documents"]}
    parsed = []
    for folder in ("parsing", "parsing-additional"):
        for path in sorted((run/folder).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if "source_packet" not in data:
                continue
            document, chunk_set, packet = (data[k] for k in ("document", "chunk_set", "source_packet"))
            did = packet["document_id"]
            require(digest(Path(originals[did]["original_path"])) == document["document_sha256"], "Original source changed")
            require(versioned_chunks(document) == chunk_set, "Chunk set cannot be reconstructed")
            require(packet["parse_version"] == document["parse_version"] and packet["chunk_set_version"] == chunk_set["chunk_set_version"], "Source packet version mismatch")
            require(packet["chunks"] == chunk_set["chunks"], "Source packet chunks differ")
            require("review_status" not in packet and packet["derived_artifact_status"] == "unpublished_candidate_parse", "Parse status must not replace literature approval")
            old = json.loads(Path(originals[did]["corpus_path"]).read_text(encoding="utf-8"))
            require(map_old_chunks(old["chunks"], document, chunk_set) == data["legacy_mapping"], "Legacy mapping cannot be reconstructed")
            for page in document["pages"]:
                require(len(page["text"]) == len(page["char_bboxes"]), "Character map alignment failed")
                for block in page["blocks"]:
                    require(0 <= block["start"] < block["end"] <= len(page["text"]), "Invalid page block span")
            parsed.append({"document_id": did, "pages": len(document["pages"]), "chunks": len(chunk_set["chunks"])})
    require({d["document_id"] for d in parsed} == {449, 1149, 1141, 104, 308}, "Five repaired source versions required")
    require(sum(d["pages"] for d in parsed) == 69 and sum(d["chunks"] for d in parsed) == 666, "Unexpected repaired corpus size")
    paper449 = load("parsing/449.json")["document"]["pages"][6]["text"]
    require(paper449.index("SOC Content Under Long-Term Biochar Application") < paper449.index("application of biochar boosts SOC content by 52.5%") < paper449.index("Net GHG Mitigation Effect"), "SOC paragraph reading order regression")
    paper1141 = load("parsing/1141.json")["document"]["pages"]
    require("65.2%" in paper1141[3]["text"] and all("FOR PEER REVIEW" not in p["text"] for p in paper1141), "Off-page draft layer regression")
    require("BBlluuee" not in paper1141[4]["text"] and "Blue and red" in paper1141[4]["text"], "Duplicated glyph regression")
    paper308 = load("parsing-additional/308.json")["document"]["pages"][10]
    require("Soil biological indicators" in paper308["text"] and "rotated_text_requires_review" in paper308["warnings"], "Rotated table text or review warning lost")

    frozen = load("contract-freeze.json")
    for name in ("schema", "compiler"):
        require(digest(ROOT/frozen[name+"_file"]) == frozen[name+"_sha256"], "Frozen contract changed")
    baseline = load("baseline-results.json")
    require(baseline["snapshot_chunks"] == 112168 and baseline["query_vectors_used"] == 9, "Baseline snapshot or query count changed")
    require(all(r["status_code"] == 200 and r["response"]["retrieval"]["mode"] == "hybrid" for r in baseline["results"]), "Real hybrid HTTP baseline incomplete")
    require(baseline["current_source_metrics"]["metadata_queries"] == 18, "Two current-source lookups per query not observed")
    require(baseline["production_database_written"] is False and baseline["production_vector_index_written"] is False, "Baseline scope changed")
    manifest = load("embedding-request-manifest-v2.json")
    authorization = load("budget-authorization-v2.json")
    require(authorization["manifest_sha256"] == digest(run/"embedding-request-manifest-v2.json"), "Authorization manifest changed")
    require(authorization["caps"] == {"tokens": 20000, "attempts": 27, "concurrency": 2}, "Authorized caps changed")
    for item in manifest["requests"]:
        saved = load("embeddings/"+item["case_id"]+".json")
        require(saved["payload_sha256"] == item["payload_sha256"] and len(saved["embedding"]) == 1024, "Fresh query vector mismatch")
        require(saved["origin"] == "fresh_authorized_R1_query_embedding", "Corpus vector cannot replace real query vector")
    connection = sqlite3.connect((run/"execution/budget.sqlite3").as_uri()+"?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        attempts, charged, inflight = connection.execute("SELECT count(*),sum(coalesce(charged,reserved)),sum(state='inflight') FROM attempts").fetchone()
        failed = connection.execute("SELECT count(*),sum(charged) FROM attempts WHERE state='failed'").fetchone()
    finally:
        connection.close()
    require((attempts, charged, inflight) == (27, 11962, 0), "R1 ledger changed")
    require(failed == (18, 11628), "Initial failed attempts were not retained")
    tests = load("test-results-final.json")
    require(tests["state"] == "passed" and tests["tests_passed"] == 109, "Necessary regression tests incomplete")
    for result in tests["runs"]:
        require(digest(ROOT/result["log"]) == result["sha256"], "Test evidence changed")
    history = load("historical-integrity.json")
    require(history["state"] == "passed" and history["historical_file_references_checked"] == 2459, "Historical integrity failed")
    return {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "state": "passed", "parsing": parsed,
            "repaired_pages": 69, "repaired_chunks": 666, "real_hybrid_HTTP_queries": 9,
            "regression_tests": 109, "R1_budget": {"attempts": attempts, "charged_or_reserved_tokens": charged, "inflight": inflight},
            "additional_model_calls": 0, "published_claims_added": 0,
            "meaning": "Implementation and source-location validation; relevance, semantic support and deployment are not accepted here"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    result = validate(run)
    if args.write_report:
        path = run/"artifact-validation-v2.json"
        if path.exists():
            raise ValueError("Existing report must not be overwritten")
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
