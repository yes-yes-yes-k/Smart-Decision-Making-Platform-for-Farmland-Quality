"""Read-only audit of historical freezes, budgets and original source metadata."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO/"artifacts/knowledge_platform/operations-m2-v1"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    target = OUT/"integrity-v1.json"
    if target.exists():
        raise ValueError("integrity_result_exists_use_new_version")
    roots = REPO/"artifacts/knowledge_platform"
    verified = {}
    for relative in ["evidence-m1-v1/completion-manifest-v1.json", *["external-benchmark-v1/reports/"+name for name in
        ("calibration-result-manifest-v1.json", "qa-pilot-result-manifest-v1.json", "qa-pilot-result-manifest-v2.json")]]:
        manifest = json.loads((roots/relative).read_text(encoding="utf-8"))
        base = roots/("evidence-m1-v1" if relative.startswith("evidence") else "external-benchmark-v1")
        for name, expected in manifest["files"].items():
            if digest(base/name) != expected:
                raise ValueError("historical_asset_changed:"+name)
        verified[relative] = len(manifest["files"])
    budgets = {}
    for name, expected in (("evidence-m1-v1", (10, 35395, 0)), ("external-benchmark-v1", (1361, 4093959, 0))):
        with sqlite3.connect((roots/name/"execution/budget.sqlite3").resolve().as_uri()+"?mode=ro", uri=True) as connection:
            found = connection.execute("SELECT count(*),sum(coalesce(charged,reserved)),sum(CASE WHEN state='inflight' THEN 1 ELSE 0 END) FROM attempts").fetchone()
        if tuple(found) != expected:
            raise ValueError("historical_budget_changed")
        budgets[name] = {"attempts": found[0], "tokens_charged_or_reserved": found[1], "inflight": found[2]}
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    original = sqlite3.connect((Path(Config.CHROMA_PERSIST_DIR).resolve()/"chroma.sqlite3").as_uri()+"?mode=ro", uri=True)
    original.execute("PRAGMA query_only=ON"); original.execute("BEGIN")
    snapshot = sqlite3.connect((OUT/"corpus/source.sqlite3").resolve().as_uri()+"?mode=ro", uri=True)
    snapshot.execute("PRAGMA query_only=ON")
    last, count = 0, 0
    try:
        while True:
            rows = original.execute("SELECT e.id,e.embedding_id,c.name FROM embeddings e JOIN segments s ON s.id=e.segment_id JOIN collections c ON c.id=s.collection WHERE e.id>? ORDER BY e.id LIMIT 500", (last,)).fetchall()
            if not rows:
                break
            identifiers = [row[0] for row in rows]
            metas = {identifier: {} for identifier in identifiers}
            sql = "SELECT id,key,string_value,int_value,float_value,bool_value FROM embedding_metadata WHERE id IN ("+",".join("?" for _ in identifiers)+")"
            for identifier, key, string, integer, floating, boolean in original.execute(sql, identifiers):
                metas[identifier][key] = string if string is not None else bool(boolean) if boolean is not None else integer if integer is not None else floating
            for identifier, chunk_id, collection in rows:
                meta = metas[identifier]
                text = meta.pop("chroma:document", None)
                meta = {key: value for key,value in meta.items() if not key.startswith("chroma:")}
                saved = snapshot.execute("SELECT content,metadata FROM chunks WHERE collection=? AND id=?", (collection, chunk_id)).fetchone()
                if not saved or text != saved[0] or meta != json.loads(saved[1]):
                    raise ValueError("original_source_text_or_metadata_changed")
                count += 1
            last = rows[-1][0]
        if count != 112168 or snapshot.execute("SELECT count(*) FROM chunks").fetchone()[0] != count:
            raise ValueError("original_source_count_changed")
    finally:
        original.rollback(); original.close(); snapshot.close()
    report = {"state": "verified", "captured_at_utc": datetime.now(timezone.utc).isoformat(), "historical_manifests": verified,
        "budgets_unchanged": budgets, "original_chroma_rows_text_and_metadata_equal_snapshot": count,
        "max_read_page": 500, "original_chroma_client_started": False, "model_calls": 0,
        "limits": ["does_not_rehash_every_original_PDF_or_compare_vector_float_bytes", "PostgreSQL_aggregate_postcheck_is_separate"]}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "historical_files": sum(verified.values()), "source_rows": count, "budgets_unchanged": True}))


if __name__ == "__main__":
    main()
