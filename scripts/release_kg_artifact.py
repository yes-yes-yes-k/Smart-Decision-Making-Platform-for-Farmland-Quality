"""Publish a reviewed graph with stable evidence IDs and a checksum manifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.release import publish_graph_release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--graph", type=Path,
        default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--release-id", default="kg-v0.4-production-candidate-1")
    parser.add_argument("--reviewed-by", default="Codex material-level review")
    args = parser.parse_args()
    payload = publish_graph_release(
        args.graph, output_path=args.output, manifest_path=args.manifest,
        release_id=args.release_id, reviewed_by=args.reviewed_by,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
