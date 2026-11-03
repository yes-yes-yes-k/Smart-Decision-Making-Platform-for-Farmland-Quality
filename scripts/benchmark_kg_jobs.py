"""Run or clean the isolated 100k extraction-job conservation benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--jobs", type=int, default=100_000)
    parser.add_argument("--worker-concurrency", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("--apply is required; use only an isolated benchmark database")
    # Loading the production ORM requires the complete spatial dependency
    # set. Keep --help side-effect free, but never substitute test shims for a
    # real benchmark execution.
    from sqlalchemy import create_engine

    from framework.knowledge_graph.job_benchmark import (
        cleanup_job_benchmark, run_job_conservation_benchmark,
    )

    engine = create_engine(args.dsn, pool_pre_ping=True)
    if args.cleanup:
        report = cleanup_job_benchmark(engine, namespace=args.namespace)
    else:
        if args.output is None:
            parser.error("--output is required for a benchmark run")
        report = run_job_conservation_benchmark(
            engine, namespace=args.namespace, job_count=args.jobs,
            worker_concurrency=args.worker_concurrency, batch_size=args.batch_size,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
