"""Build isolated layout-v2 text and mappings for explicitly selected audited PDFs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from framework.upload.pdf_layout import PROFILE, map_old_chunks, parse_layout_pdf, versioned_chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1/parsing")
    parser.add_argument("--document-ids", nargs="+", type=int, default=[449, 1149, 1141])
    args = parser.parse_args()
    target = args.output_dir.resolve()
    if target.exists():
        raise SystemExit("Choose a new output directory; existing versions cannot be overwritten")
    audit = json.loads((ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030/source-audit.json").read_text(encoding="utf-8"))
    if not set(args.document_ids) <= {d["document_id"] for d in audit["documents"]}:
        raise ValueError("document_outside_original_ten_source_audit")
    target.mkdir(parents=True)
    summary = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "profile": PROFILE,
               "model_calls": 0, "production_indexes_changed": False, "documents": []}
    for item in audit["documents"]:
        did = item["document_id"]
        if did not in set(args.document_ids):
            continue
        path = Path(item["original_path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["file_sha256_frozen"]:
            raise ValueError("source_changed_since_audit")
        old = json.loads(Path(item["corpus_path"]).read_text(encoding="utf-8"))
        document = parse_layout_pdf(path)
        chunks = versioned_chunks(document)
        mapping = map_old_chunks(old["chunks"], document, chunks)
        packet = {"document_id": did, "document_sha256": document["document_sha256"],
                  "parse_version": document["parse_version"], "chunk_set_version": chunks["chunk_set_version"],
                  "title": old["title"], "parser_profile": PROFILE, "chunks": chunks["chunks"],
                  "derived_artifact_status": "unpublished_candidate_parse",
                  "current_PG_qualification": "not_verified_for_new_parse"}
        payload = {"document": document, "chunk_set": chunks, "source_packet": packet,
                   "old_corpus_file_sha256": hashlib.sha256(Path(item["corpus_path"]).read_bytes()).hexdigest(),
                   "legacy_mapping": mapping}
        (target/f"{did}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        (target/f"{did}.txt").write_text("\n\n".join(f"PAGE {p['page']}\n{p['text']}" for p in document["pages"]), encoding="utf-8")
        summary["documents"].append({"document_id": did, "pages": len(document["pages"]),
                                     "old_chunks": len(old["chunks"]), "new_chunks": len(chunks["chunks"]),
                                     "parse_version": document["parse_version"], "chunk_set_version": chunks["chunk_set_version"],
                                     "exact_legacy_chunks": sum(m["state"] == "exact_unique" for m in mapping),
                                     "unreadable_pages": [p["page"] for p in document["pages"] if p["status"] == "unreadable"],
                                     "page_reading_order": {p["page"]: p["reading_order"] for p in document["pages"]}})
        print(json.dumps(summary["documents"][-1]), flush=True)
    (target/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
