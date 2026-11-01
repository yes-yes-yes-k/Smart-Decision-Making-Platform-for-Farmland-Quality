"""Compose and gate the five evidence reports from a full capacity run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.capacity_report import compose_capacity_report


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--target", type=Path,
        default=Path("benchmarks/knowledge_platform/target-v1.json"),
    )
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--load-report", type=Path, required=True)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--job-report", type=Path, required=True)
    parser.add_argument("--vector-report", type=Path, required=True)
    parser.add_argument("--backup-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compose_capacity_report(
        target=_load(args.target), metadata=_load(args.metadata),
        load_report=_load(args.load_report), runtime_report=_load(args.runtime_report),
        job_report=_load(args.job_report), vector_report=_load(args.vector_report),
        backup_report=_load(args.backup_report), run_id=args.run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(report["acceptance"], ensure_ascii=False, sort_keys=True))
    return 0 if report["acceptance"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
