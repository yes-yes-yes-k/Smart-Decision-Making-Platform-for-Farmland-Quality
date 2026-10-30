"""Run vector retrieval against the configured store while graph retrieval fails."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph.resilience_probe import probe_vector_availability


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", action="append", dest="queries", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Delay Chroma/model initialization until after argparse handles --help.
    from framework.rag.chain import RAGChain

    report = probe_vector_availability(RAGChain(), args.queries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["available_during_graph_failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
