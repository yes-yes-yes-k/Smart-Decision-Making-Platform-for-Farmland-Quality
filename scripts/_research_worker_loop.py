"""Background worker loop for research evidence comparison.

Launched by ``scripts/manage_research_worker.py``. Runs either the
extraction worker (GraphExtractionWorker.run_forever) or the comparison
worker (ResearchService.run_once in a poll loop) depending on --mode.

This script is intentionally minimal: it sets up the Flask app context
to reuse the existing service wiring, then enters the appropriate loop.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

LOG = logging.getLogger("research-worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

stop_event = threading.Event()


def _handle_signal(signum, frame):
    LOG.info("received signal %d, shutting down", signum)
    stop_event.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run_comparison_worker() -> None:
    """Poll the comparison queue and process jobs."""
    from framework.api.app import create_app
    app = create_app()
    with app.app_context():
        service = app.extensions.get("literature_evidence_service")
        if service is None:
            LOG.error("literature_evidence_service not configured; exiting")
            return
        LOG.info("comparison worker started (pid=%d)", os.getpid())
        while not stop_event.is_set():
            try:
                report = service.run_once(timeout=30)
                state = report.get("state", "unknown")
                if state == "idle":
                    stop_event.wait(5)
                else:
                    LOG.info("comparison job: %s", report)
            except Exception:
                LOG.error("comparison worker iteration failed", exc_info=True)
                stop_event.wait(5)
    LOG.info("comparison worker stopped")


def run_extraction_worker() -> None:
    """Run the graph extraction worker forever."""
    from framework.api.app import create_app
    from framework.models.user import db
    from framework.knowledge_graph.worker import GraphExtractionWorker

    app = create_app()
    with app.app_context():
        # The extraction worker needs a backend and chunk reader.
        # In the local environment, these may not be fully configured.
        # This mode is provided for completeness; the comparison mode
        # is the primary local use case.
        try:
            from framework.knowledge_graph.adapters.live_graphrag import LiveGraphRagProvider
            from framework.knowledge_graph.chunk_reader import ChunkReader
            backend = LiveGraphRagProvider().backend()
            reader = ChunkReader(db.engine)
        except Exception:
            LOG.error("extraction backend not available; use comparison mode")
            return

        worker_id = f"{socket.gethostname()}:{os.getpid()}"
        worker = GraphExtractionWorker(
            session_factory=lambda: db.session,
            backend=backend,
            chunk_reader=reader,
            worker_id=worker_id,
        )
        LOG.info("extraction worker started (worker_id=%s)", worker_id)
        worker.run_forever(stop_event, poll_seconds=5)
    LOG.info("extraction worker stopped")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["extraction", "comparison"], default="comparison")
    args = parser.parse_args()

    if args.mode == "extraction":
        run_extraction_worker()
    else:
        run_comparison_worker()


if __name__ == "__main__":
    main()
