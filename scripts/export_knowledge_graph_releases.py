"""Process non-blocking JSON/Parquet audit exports for published graph releases."""
from __future__ import annotations

import argparse
import json

from framework.api.app import create_app
from framework.knowledge_graph.release_platform import ReleaseAuditExporter
from framework.models.user import db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        store = app.extensions.get("knowledge_graph_store")
        if store is None or not callable(getattr(store, "export_snapshot", None)):
            print(json.dumps({
                "status": "error", "error_code": "graph_store_unavailable",
            }))
            return 2
        counts = ReleaseAuditExporter(
            db.session, store, app.config["KG_AUDIT_EXPORT_DIR"],
        ).process_pending(limit=args.limit)
        db.session.commit()
        print(json.dumps({"status": "ok", **counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
