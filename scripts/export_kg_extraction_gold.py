"""Export the reviewed v0.4 graph as a deterministic extraction gold set."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT
    / "artifacts"
    / "minimal_kg"
    / "cultivated_land_minimal_graph_v0.4.json"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "artifacts" / "minimal_kg" / "extraction_gold_v1.jsonl"
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_gold_rows(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    entities = {str(item["id"]): item for item in graph.get("entities") or []}
    rows: list[dict[str, Any]] = []
    for relation in graph.get("relations") or []:
        source = entities.get(str(relation.get("source")))
        target = entities.get(str(relation.get("target")))
        if source is None or target is None:
            raise ValueError(f"relation endpoint missing: {relation.get('id')}")
        for evidence in relation.get("evidence") or []:
            quote = str(evidence.get("quote") or "")
            if not quote:
                raise ValueError(f"evidence quote missing: {relation.get('id')}")
            quote_hash = str(evidence.get("quote_sha256") or sha256_text(quote))
            if quote_hash != sha256_text(quote):
                raise ValueError(f"evidence quote hash mismatch: {relation.get('id')}")
            if evidence.get("page") is None:
                raise ValueError(f"evidence page missing: {relation.get('id')}")
            rows.append({
                "gold_version": "cultivated-land-extraction-gold-v1",
                "graph_schema_version": graph.get("schema_version"),
                "relation": {
                    "id": relation.get("id"),
                    "type": relation.get("type"),
                    "source": {
                        "id": source.get("id"),
                        "type": source.get("type"),
                        "name": source.get("name"),
                    },
                    "target": {
                        "id": target.get("id"),
                        "type": target.get("type"),
                        "name": target.get("name"),
                    },
                    "review_status": relation.get("status"),
                },
                "evidence": {
                    "evidence_id": evidence.get("evidence_id"),
                    "document_id": evidence.get("document_id"),
                    "document_title": evidence.get("document_title"),
                    "page": evidence.get("page"),
                    "chunk_index": evidence.get("chunk_index"),
                    "quote": quote,
                    "quote_sha256": quote_hash,
                    "review_status": evidence.get("review_status"),
                },
            })
    return sorted(rows, key=lambda row: (
        str(row["relation"]["id"]),
        str(row["evidence"].get("evidence_id") or ""),
        int(row["evidence"].get("document_id") or 0),
        int(row["evidence"].get("page") or 0),
    ))


def export_gold(source: Path, output: Path) -> dict[str, Any]:
    graph_bytes = source.read_bytes()
    graph = json.loads(graph_bytes.decode("utf-8"))
    if graph.get("schema_version") != "minimal-cultivated-land-kg-v0.4":
        raise ValueError("gold v1 must be exported from the reviewed v0.4 graph")
    rows = build_gold_rows(graph)
    serialized = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8", newline="\n")
    manifest = {
        "gold_version": "cultivated-land-extraction-gold-v1",
        "source": source.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": hashlib.sha256(graph_bytes).hexdigest(),
        "output": output.relative_to(PROJECT_ROOT).as_posix(),
        "output_sha256": sha256_text(serialized),
        "entity_count": len(graph.get("entities") or []),
        "relation_count": len(graph.get("relations") or []),
        "evidence_count": len(rows),
        "relation_counts": dict(sorted(Counter(
            row["relation"]["type"] for row in rows
        ).items())),
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(export_gold(args.source, args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
