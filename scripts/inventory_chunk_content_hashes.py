"""Stream public metadata to inventory remaining migration work; no writes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.knowledge_graph.jobs import document_is_graph_eligible
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout": 5})
    with sessionmaker(bind=engine)() as session:
        sources = {row.id: dict(content_sha256=row.file_hash, expected_count=row.chunk_count)
            for row in session.query(Document).filter_by(status=Document.STATUS_COMPLETED,
                processing_stage="completed", review_status=Document.REVIEW_APPROVED,
                visibility_scope="public").yield_per(100) if document_is_graph_eligible(row)}
    engine.dispose()
    reader = WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR)
    counts, outside = {}, 0
    for item in reader.client.list_collections():
        collection = reader.client.get_collection(name=getattr(item, "name", str(item)), embedding_function=None)
        offset = 0
        while True:
            batch = collection.get(where={"visibility_scope": "public"}, include=["metadatas"], limit=500, offset=offset)
            for metadata in batch.get("metadatas") or []:
                did = metadata.get("document_id")
                if did not in sources:
                    outside += 1
                    continue
                tally = counts.setdefault(did, Counter())
                value = metadata.get("content_sha256")
                state = "missing" if not value else "matching" if value == sources[did]["content_sha256"] else "conflicting"
                tally[state] += 1
            size = len(batch["ids"])
            offset += size
            if size < 500:
                break
    report = dict(schema="chunk-hash-inventory-v1", read_only=True, inventory_is_not_source_verification=True,
        eligible_documents=len(sources), outside_eligible_snapshot_chunks=outside, documents=[])
    totals = Counter()
    for did, source in sorted(sources.items()):
        tally = counts.get(did, Counter())
        totals.update(tally)
        report["documents"].append(dict(document_id=did, expected_count=source["expected_count"],
            observed_count=sum(tally.values()), missing=tally["missing"], matching=tally["matching"], conflicting=tally["conflicting"]))
    report["totals"] = dict(totals)
    report["fully_bound_documents"] = sum(row["matching"] == row["expected_count"] and row["missing"] == 0 and row["conflicting"] == 0 for row in report["documents"])
    report["remaining_documents"] = sum(row["missing"] > 0 for row in report["documents"])
    report["count_mismatch_documents"] = [row["document_id"] for row in report["documents"] if row["expected_count"] != row["observed_count"]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "documents"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
