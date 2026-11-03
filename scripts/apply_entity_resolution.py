"""Apply entity resolution to persisted candidates.

R3 follow-up. Updates kg_entity_candidate.canonical_entity_id,
canonical_name, and resolution_status for all 31 entities based on the
surface alias table in entity_catalog.py.

Zero model calls.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from framework.knowledge_graph.entity_catalog import resolve_surface


def main() -> None:
    url = (
        f"postgresql+psycopg://{os.getenv('DB_USER', 'postgres')}:"
        f"{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"
    )
    engine = create_engine(url, connect_args={"connect_timeout": 8})

    rows = engine.connect().execute(text(
        "SELECT id, mention FROM kg_entity_candidate ORDER BY id"
    )).mappings().all()
    print(f"Resolving {len(rows)} entity candidates...")

    resolved = 0
    unresolved = 0
    deduped = 0
    canonical_counts: dict[str, int] = {}

    with engine.begin() as conn:
        for row in rows:
            cid, cname, status = resolve_surface(row["mention"])
            if cid:
                canonical_counts[cid] = canonical_counts.get(cid, 0) + 1
                conn.execute(text(
                    "UPDATE kg_entity_candidate "
                    "SET canonical_entity_id = :cid, canonical_name = :cname, "
                    "    resolution_status = :status "
                    "WHERE id = :id"
                ), {"cid": cid, "cname": cname, "status": status, "id": row["id"]})
                resolved += 1
            else:
                unresolved += 1

    # Report duplicates (canonical_ids shared by multiple entity candidates)
    for cid, count in sorted(canonical_counts.items()):
        if count > 1:
            deduped += count - 1
            print(f"  dedup: {cid} shared by {count} entity candidates")

    print(f"\nResults: resolved={resolved} unresolved={unresolved} deduped={deduped}")
    print(f"Unique canonical entities: {len(canonical_counts)}")

    # Check cross-document matches
    cross = engine.connect().execute(text("""
        SELECT canonical_entity_id, array_agg(DISTINCT j.document_id) AS docs
        FROM kg_entity_candidate e
        JOIN kg_extraction_job j ON e.job_id = j.id
        WHERE e.canonical_entity_id IS NOT NULL
        GROUP BY canonical_entity_id
        HAVING array_length(array_agg(DISTINCT j.document_id), 1) > 1
    """)).mappings().all()
    if cross:
        print(f"\nCross-document canonical matches: {len(cross)}")
        for r in cross:
            print(f"  {r['canonical_entity_id']}: docs={r['docs']}")
    else:
        print("\nCross-document canonical matches: 0 (papers study different topics)")

    engine.dispose()


if __name__ == "__main__":
    main()
