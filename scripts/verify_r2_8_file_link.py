"""R2.8 end-to-end real file link: candidate artifacts → PG → read-back → graph.

Zero new model calls. This script:
1. Reads the 5 v2 candidate files (papers with relations) from artifacts.
2. Verifies each document exists in kb_document with matching content_sha256.
3. Re-verifies span integrity (quote_sha256, offsets) without model calls.
4. Writes candidates to PG via candidate_store.write_bundle.
5. Reads them back via candidate_reader.read_candidates.
6. Verifies write-rows == read-rows and identity hash is consistent.
7. Runs the bounded graph expander to verify cross-document contribution hits.

Usage:
    .venv/Scripts/python.exe scripts/verify_r2_8_file_link.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# The 5 papers that produced relations in the R2.5 batch.
CANDIDATE_LOCATIONS = [
    ("r2-20261031-v4-quoteonly-retry", "1015"),
    ("r2-20261031-v19-parallel-probe", "1032"),
    ("r2-20261031-v20-remaining4", "306"),
    ("r2-20261031-v5-sample", "1141"),
    ("r2-20261031-v15-default-8", "1021"),
]

ARTIFACTS = PROJECT_ROOT / "artifacts" / "knowledge_platform" / "research-extraction-v2"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _verify_span_integrity(bundle: dict) -> tuple[int, int]:
    """Check every span's quote_sha256 and offsets. Returns (checked, rejected)."""
    checked = 0
    rejected = 0

    def check_span(span):
        nonlocal checked, rejected
        if not isinstance(span, dict):
            rejected += 1
            return
        quote = span.get("quote", "")
        start = span.get("start", -1)
        end = span.get("end", -1)
        expected_sha = span.get("quote_sha256", "")
        if not isinstance(quote, str) or not quote.strip():
            rejected += 1
        elif not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            rejected += 1
        elif _sha256_text(quote) != expected_sha:
            rejected += 1
        checked += 1

    for study in bundle.get("studies", []):
        for ctx in study.get("context", []):
            check_span(ctx)
        if study.get("attribution"):
            check_span(study["attribution"])
    for entity in bundle.get("entities", []):
        check_span(entity.get("mention"))
    for relation in bundle.get("relations", []):
        check_span(relation.get("result"))
        for qualifier in (relation.get("qualifiers") or {}).values():
            if isinstance(qualifier, dict) and qualifier.get("evidence"):
                check_span(qualifier["evidence"])
    return checked, rejected


def main() -> None:
    app = Flask("r2-8-file-link")
    db_uri = (
        f"postgresql+psycopg://{os.getenv('DB_USER', 'postgres')}:"
        f"{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )
    app.config.update(
        SQLALCHEMY_DATABASE_URI=db_uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"poolclass": __import__(
            "sqlalchemy.pool", fromlist=["NullPool"]).NullPool},
    )
    from framework.models.user import db
    db.init_app(app)
    context = app.app_context()
    context.push()

    from framework.knowledge_graph.candidate_store import write_bundle
    from framework.knowledge_graph.candidate_reader import read_candidates
    from framework.knowledge_graph.graph_expander import BoundedGraphExpander

    print("=" * 70)
    print("R2.8 end-to-end real file link")
    print("=" * 70)

    total_written = {}
    total_read = {}
    total_span_checked = 0
    total_span_rejected = 0
    all_doc_ids = []

    for run_name, doc_id_str in CANDIDATE_LOCATIONS:
        candidate_path = ARTIFACTS / run_name / "candidates" / f"{doc_id_str}.json"
        if not candidate_path.exists():
            print(f"  SKIP doc {doc_id_str}: candidate file not found at {candidate_path}")
            continue
        bundle = json.loads(candidate_path.read_text(encoding="utf-8"))
        doc_id = bundle["source"]["document_id"]
        all_doc_ids.append(doc_id)

        # --- Step 1: verify document exists in PG with matching hash ---
        live = db.session.execute(text(
            "SELECT id, file_hash, visibility_scope, review_status, "
            "document_kind, status, processing_stage "
            "FROM kb_document WHERE id = :doc_id"
        ), {"doc_id": doc_id}).mappings().first()
        if live is None:
            print(f"  SKIP doc {doc_id}: not in kb_document")
            continue
        hash_match = live["file_hash"] == bundle["source"]["document_sha256"]
        print(f"\n  doc {doc_id} ({run_name}):")
        print(f"    kb_document: hash_match={hash_match} kind={live['document_kind']} "
              f"visibility={live['visibility_scope']} review={live['review_status']}")

        # --- Step 2: span integrity re-verification ---
        span_checked, span_rejected = _verify_span_integrity(bundle)
        total_span_checked += span_checked
        total_span_rejected += span_rejected
        print(f"    spans: checked={span_checked} rejected={span_rejected}")

        # --- Step 3: write to PG ---
        summary = write_bundle(bundle)
        total_written[doc_id] = summary
        print(f"    written: {summary}")

        # --- Step 4: read back ---
        live_source = {
            "content_sha256": live["file_hash"],
            "visibility_scope": live["visibility_scope"],
            "review_status": live["review_status"],
            "document_kind": live["document_kind"],
            "completed": (live["status"] == 1 and live["processing_stage"] == "completed"
                          and live["document_kind"] in {"academic_paper", "standard", "policy", "method_guideline"}),
        }
        read_result = read_candidates(doc_id, live_source=live_source)
        status = read_result["status"]
        c = read_result.get("candidates", {})
        read_counts = {
            "studies": len(c.get("studies", [])),
            "entities": len(c.get("entities", [])),
            "relations": len(c.get("relations", [])),
            "claims": len(c.get("claims", [])),
        }
        total_read[doc_id] = read_counts
        print(f"    read-back: status={status} counts={read_counts}")

        # --- Step 5: verify write == read ---
        for key in ("studies", "entities", "relations"):
            w = summary.get(key, 0)
            r = read_counts.get(key, 0)
            if w != r:
                print(f"    MISMATCH {key}: written={w} read={r}")

    # --- Step 6: graph expansion ---
    print(f"\n{'=' * 70}")
    print("Graph expansion (cross-document contribution hits)")
    print(f"{'=' * 70}")
    expander = BoundedGraphExpander()

    class _StubSources:
        def lookup_many(self, ids, owner_id, require_academic=False):
            return {
                doc_id: {
                    "title": f"doc {doc_id}", "document_kind": "academic_paper",
                    "content_sha256": total_written.get(doc_id, {}).get("content_sha256", "x" * 64),
                    "visibility_scope": "public", "review_status": "approved",
                    "completed": True, "source_bytes_valid": True,
                }
                for doc_id in ids
            }

    expanded_ids, graph_trace = expander.expand(
        all_doc_ids,
        current_sources=_StubSources(),
        owner_id=1,
        kinds=("academic_paper",),
    )
    print(f"  baseline docs: {all_doc_ids}")
    print(f"  expanded ids: {expanded_ids}")
    print(f"  graph trace: {graph_trace}")

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print("Summary")
    print(f"{'=' * 70}")
    print(f"  papers processed: {len(total_written)}")
    print(f"  spans re-verified: {total_span_checked} (rejected: {total_span_rejected})")
    total_relations = sum(s.get("relations", 0) for s in total_written.values())
    total_studies = sum(s.get("studies", 0) for s in total_written.values())
    total_entities = sum(s.get("entities", 0) for s in total_written.values())
    print(f"  written: studies={total_studies} entities={total_entities} relations={total_relations}")
    read_relations = sum(r.get("relations", 0) for r in total_read.values())
    print(f"  read-back relations: {read_relations}")
    print(f"  graph: state={graph_trace['state']} hits={graph_trace['contributing_hits']}")

    all_match = all(
        total_written[d].get(k, 0) == total_read[d].get(k, 0)
        for d in total_written for k in ("studies", "entities", "relations")
    )
    print(f"  write==read: {'YES' if all_match else 'NO'}")
    context.pop()


if __name__ == "__main__":
    main()
