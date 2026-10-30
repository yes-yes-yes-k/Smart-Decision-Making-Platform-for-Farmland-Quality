from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.synthetic import (
    SyntheticScale, cleanup_synthetic_dataset, generate_synthetic_dataset,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--documents", type=int, default=100_000)
    parser.add_argument("--entities", type=int, default=100_000)
    parser.add_argument("--evidence", type=int, default=1_000_000)
    parser.add_argument("--jobs", type=int, default=100_000)
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        result = {"cleaned": cleanup_synthetic_dataset(
            args.output_root, namespace=args.namespace,
        )}
    else:
        result = generate_synthetic_dataset(
            args.output_root, namespace=args.namespace,
            scale=SyntheticScale(args.documents, args.entities, args.evidence, args.jobs),
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
