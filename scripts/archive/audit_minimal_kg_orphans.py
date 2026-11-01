"""Audit evidence for entities that are disconnected in the reviewed graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
VENV_SITE = ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))

import chromadb


def evidence_window(content: str, terms: list[str], radius: int = 320) -> str:
    lowered = content.lower()
    positions = [lowered.find(term.lower()) for term in terms if term]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - radius)
    end = min(len(content), center + radius)
    return content[start:end]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--graph",
        type=Path,
        default=ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json",
    )
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--entity", action="append", dest="entities")
    parser.add_argument("--document-id", action="append", type=int, dest="document_ids")
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    corpus_ids = {int(item["document_id"]) for item in graph["corpus"]}
    entities = {item["id"]: item for item in graph["entities"]}
    orphan_ids = args.entities or graph.get("validation", {}).get("orphan_entities", [])

    collection = chromadb.PersistentClient(
        path=str(ROOT / "chroma_db"),
    ).get_collection("kb_cultivated_land_quality")
    data = collection.get(include=["documents", "metadatas"])

    output = {}
    for entity_id in orphan_ids:
        entity = entities[entity_id]
        terms = [entity.get("name", ""), *(entity.get("aliases") or [])]
        terms.extend(item.get("term", "") for item in entity.get("related_terms") or [])
        terms = list(dict.fromkeys(term for term in terms if term))
        hits = []
        for content, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
            metadata = metadata or {}
            try:
                document_id = int(metadata.get("document_id"))
            except (TypeError, ValueError):
                continue
            if document_id not in corpus_ids:
                continue
            if args.document_ids and document_id not in set(args.document_ids):
                continue
            matched = [term for term in terms if term.lower() in (content or "").lower()]
            if not matched:
                continue
            hits.append({
                "matched_terms": matched,
                "document_id": document_id,
                "page": metadata.get("page"),
                "chunk_index": metadata.get("chunk_index"),
                "source": metadata.get("source"),
                "content": evidence_window(content or "", matched),
            })
        output[entity_id] = {
            "name": entity["name"],
            "hit_count": len(hits),
            "hits": hits[: args.limit],
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
