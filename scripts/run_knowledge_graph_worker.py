"""Run as a separate service; never start extraction inside a web worker."""
import argparse
import json
import logging
import os
from pathlib import Path
import signal
import socket
import sys
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check", action="store_true", help="check runtime/config without consuming jobs")
    parser.add_argument("--shadow", action="store_true", help="explicit candidate-only pilot before backend qualification")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--heartbeat-seconds", type=float, default=30)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    python = os.environ.get("KG_GRAPHRAG_PYTHON")
    if not python or not Path(python).is_file() or not os.environ.get("KG_EXTRACTION_MODEL"):
        parser.error("Configure KG_GRAPHRAG_PYTHON and KG_EXTRACTION_MODEL first")
    if args.poll_seconds <= 0 or args.timeout <= 0:
        parser.error("poll interval and timeout must be positive")
    if not 0 < args.heartbeat_seconds < args.lease_seconds:
        parser.error("heartbeat must be positive and shorter than lease")
    from framework.knowledge_graph.extraction_config import model_endpoint
    if model_endpoint().rstrip("/") == "https://api.siliconflow.cn/v1" and not (
            os.environ.get("KG_EXTRACTION_API_KEY") or os.environ.get("SILICONFLOW_API_KEY")):
        parser.error("SiliconFlow model credentials are not configured")
    from flask import Flask
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.user import db
    from framework.knowledge_graph.adapters.live_graphrag import LiveMicrosoftGraphRagBackend
    backend = LiveMicrosoftGraphRagBackend(python, timeout=args.timeout)
    backend.provider.check_runtime()
    from framework.knowledge_graph.adapter_gate import evaluate_adapter_policy
    def read_report(path):
        try:
            return json.loads((ROOT / path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    gate = evaluate_adapter_policy(
        read_report("governance/knowledge-platform/adapter-policy-v1.json"),
        [read_report(f"artifacts/knowledge_platform/{name}-evaluation-v1.json") for name in ("graphrag", "openspg")],
        [read_report(f"artifacts/knowledge_platform/{name}-conformance-v1.json") for name in ("graphrag", "openspg")])
    production_ready = (gate.get("production_ready") is True and
                        gate.get("selected", {}).get("primary") == f"{backend.name}@{backend.version}")
    if args.check:
        print(json.dumps(dict(runtime_ready=True, model_configured=True, production_ready=production_ready)))
        return 0
    if not args.shadow and not production_ready:
        parser.error("backend qualification pending; use --shadow for an explicit candidate-only pilot")
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    from framework.knowledge_graph.worker import GraphExtractionWorker

    # Minimal app: no web routes, automatic migrations or chat model startup.
    app = Flask("knowledge-graph-worker")
    app.config.from_object(Config)
    db.init_app(app)
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    with app.app_context():
        worker = GraphExtractionWorker(
            sessionmaker(bind=db.engine), backend,
            WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR),
            worker_id=f"{socket.gethostname()[:40]}:{os.getpid()}:{uuid.uuid4().hex[:12]}",
            lease_seconds=args.lease_seconds, heartbeat_seconds=args.heartbeat_seconds)
        if args.once:
            report = worker.run_once()
            print(json.dumps(report))
            return int(report.get("state") in {"failed", "lease_lost"})
        worker.run_forever(stop, poll_seconds=args.poll_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
