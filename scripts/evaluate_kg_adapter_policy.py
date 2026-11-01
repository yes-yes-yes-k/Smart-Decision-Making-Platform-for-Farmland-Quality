"""Evaluate extraction adapter production policy from recorded reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.adapter_gate import evaluate_adapter_policy


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, action="append", default=[])
    parser.add_argument("--conformance", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_adapter_policy(
        _load(args.policy),
        [_load(path) for path in args.evaluation],
        [_load(path) for path in args.conformance],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["production_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
