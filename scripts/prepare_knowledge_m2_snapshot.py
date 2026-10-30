"""Stream a consistent read-only Chroma metadata snapshot for M2 measurements."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO/"artifacts/knowledge_platform/operations-m2-v1"


def main():
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    target = OUT/"corpus/source.sqlite3"
    if target.exists():
        raise ValueError("M2_source_snapshot_already_exists_verify_do_not_replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    for name in ("bm25_store.py", "chroma_store.py"):
        path = REPO/"framework/vector_store"/name
        backup = OUT/"baseline-code"/name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, backup)
    origin = sqlite3.connect((Path(Config.CHROMA_PERSIST_DIR).resolve()/"chroma.sqlite3").as_uri()+"?mode=ro", uri=True)
    origin.execute("PRAGMA query_only=ON"); origin.execute("BEGIN")
    output = sqlite3.connect(target)
    output.execute("CREATE TABLE chunks (collection TEXT,id TEXT,content TEXT,metadata TEXT,PRIMARY KEY(collection,id))")
    counts, last, maximum = Counter(), 0, 0
    try:
        while True:
            rows = origin.execute("SELECT e.id,e.embedding_id,c.name FROM embeddings e JOIN segments s ON s.id=e.segment_id JOIN collections c ON c.id=s.collection WHERE e.id>? ORDER BY e.id LIMIT 500", (last,)).fetchall()
            if not rows:
                break
            identifiers = [row[0] for row in rows]
            meta = {identifier: {} for identifier in identifiers}
            query = "SELECT id,key,string_value,int_value,float_value,bool_value FROM embedding_metadata WHERE id IN ("+",".join("?" for _ in identifiers)+")"
            for identifier,key,string,integer,floating,boolean in origin.execute(query, identifiers):
                value = string if string is not None else bool(boolean) if boolean is not None else integer if integer is not None else floating
                meta[identifier][key] = value
            inserts = []
            for identifier, chunk_id, collection in rows:
                values = meta[identifier]
                content = values.pop("chroma:document", None)
                if not isinstance(content, str) or not content:
                    raise ValueError("M2_missing_source_text")
                values = {key: value for key,value in values.items() if not key.startswith("chroma:")}
                inserts.append((collection, chunk_id, content, json.dumps(values, ensure_ascii=False)))
                counts[collection] += 1
            output.executemany("INSERT INTO chunks VALUES (?,?,?,?)", inserts)
            output.commit()
            maximum = max(maximum, len(rows)); last = rows[-1][0]
            if sum(counts.values()) % 10000 == 0:
                print(json.dumps({"snapshot_rows": sum(counts.values())}), flush=True)
        total = origin.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        if sum(counts.values()) != total:
            raise ValueError("M2_source_snapshot_count_mismatch")
        output.execute("CREATE INDEX idx_M2_document ON chunks(json_extract(metadata,'$.document_id'))")
        output.commit()
    finally:
        origin.rollback(); origin.close(); output.close()
    report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "source_read_only": True,
        "Chroma_client_started": False, "model_calls": 0, "rows": sum(counts.values()), "collections": dict(counts),
        "max_export_page": maximum, "snapshot_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source_original_bytes_revalidated": False, "method": "consistent_metadata_text_export_not_vector_or_HNSW_health",
        "baseline_code_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (OUT/"baseline-code").glob("*.py")}}
    (OUT/"source-snapshot-v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"rows": report["rows"], "collections": dict(counts), "model_calls": 0}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); main()
