"""Dry-run or advance one resumable historical graph backfill batch."""
from __future__ import annotations

import argparse
import json

from framework.api.app import create_app
from framework.knowledge_graph.backfill import HistoricalGraphBackfill
from framework.models.user import db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-key")
    parser.add_argument("--actor-id", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--after-document-id", type=int, default=0)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        service = HistoricalGraphBackfill(db.session)
        if args.dry_run:
            report = service.dry_run(
                after_document_id=args.after_document_id, limit=args.batch_size,
            )
        else:
            if not args.run_key:
                parser.error("--run-key is required unless --dry-run is used")
            run, counts = service.run_batch(
                run_key=args.run_key, created_by=args.actor_id,
                batch_size=args.batch_size,
            )
            db.session.commit()
            report = {
                **counts, "run_key": run.run_key, "state": run.state,
                "checkpoint_document_id": run.checkpoint_document_id,
                "totals": {
                    "eligible": run.eligible_count, "created": run.created_count,
                    "reused": run.reused_count, "skipped": run.skipped_count,
                },
            }
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
