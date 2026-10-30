"""Freeze ten real published papers and verify source bytes/chunks; no model."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO/"artifacts/knowledge_platform/evidence-m1-v1"
SEED = "research-M1-source-strata-20261030-v1"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode()
    if path.exists() and path.read_bytes() != data:
        raise ValueError("frozen_pilot_file_changed:"+path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def prepare():
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    from sqlalchemy.engine import make_url
    import psycopg2
    url = make_url(Config.SQLALCHEMY_DATABASE_URI)
    conn = psycopg2.connect(host=url.host, port=url.port, user=url.username, password=url.password, dbname=url.database,
        connect_timeout=4, options="-c default_transaction_read_only=on -c statement_timeout=8000")
    conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
    try:
        cur = conn.cursor()
        cur.execute("SELECT id,doc_name,title,file_type,file_path,file_hash,chunk_count,parse_metadata FROM kb_document WHERE status=1 AND processing_stage='completed' AND review_status='approved' AND visibility_scope='public' AND document_kind='academic_paper' AND file_hash IS NOT NULL AND chunk_count>0 ORDER BY id")
        docs = [dict(zip(("id", "name", "title", "file_type", "file_path", "file_hash", "chunk_count", "parse_metadata"), row)) for row in cur.fetchall()]
    finally:
        conn.rollback(); conn.close()
    chosen, used_hashes = [], set()
    def text(doc):
        return (str(doc["title"] or "")+" "+doc["name"]).casefold()
    def take(stratum, predicate):
        options = [doc for doc in docs if doc["file_hash"] not in used_hashes and predicate(doc)]
        if not options:
            raise ValueError("source_stratum_unavailable:"+stratum)
        doc = min(options, key=lambda row: digest(SEED+":"+stratum+":"+str(row["id"])))
        used_hashes.add(doc["file_hash"]); chosen.append((stratum, doc))
    for name, words in [("biochar", ("biochar", "生物炭")), ("lime", ("liming", "lime ", "石灰")),
                        ("organic_amendment", ("manure", "有机肥", "有机物")), ("straw", ("straw", "秸秆"))]:
        take(name, lambda doc, terms=words: any(word in text(doc) for word in terms))
    take("long_paper", lambda doc: doc["chunk_count"] >= 180)
    take("OCR_or_mixed_1", lambda doc: (doc["parse_metadata"] or {}).get("ocr_pages", 0) > 0)
    take("OCR_or_mixed_2", lambda doc: (doc["parse_metadata"] or {}).get("ocr_pages", 0) > 0)
    take("CAJ_conversion", lambda doc: (doc["parse_metadata"] or {}).get("conversion") == "caj_to_pdf")
    take("PDF_in_CAJ", lambda doc: (doc["parse_metadata"] or {}).get("conversion") == "pdf_payload")
    take("review_or_synthesis", lambda doc: any(word in text(doc) for word in ("review", "综述", "进展")))
    selection = {"seed": SEED, "model_performance_used": False, "reference_answers_used": False,
                 "document_count": 10, "scope": "representative_workflow_pilot_not_statistical_benchmark",
                 "documents": [{k: doc[k] for k in ("id", "name", "title", "file_type", "file_hash", "chunk_count", "parse_metadata")} | {"stratum": stratum} for stratum, doc in chosen]}
    write(OUT/"selection.json", selection)
    # Direct read-only SQLite is an export diagnostic only. Product retrieval
    # consumes the source contract, not Chroma's private SQL schema.
    connection = sqlite3.connect((Path(Config.CHROMA_PERSIST_DIR).resolve()/"chroma.sqlite3").as_uri()+"?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    try:
        for stratum, doc in chosen:
            path = Path(doc["file_path"])
            if not path.is_absolute():
                path = Path(Config.UPLOAD_FOLDER)/path
            file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if file_sha != doc["file_hash"]:
                raise ValueError("original_file_hash_changed:"+str(doc["id"]))
            metadata = {}
            cursor = connection.execute("SELECT m.id,m.key,m.string_value,m.int_value FROM embedding_metadata m JOIN embedding_metadata d ON d.id=m.id AND d.key='document_id' AND d.int_value=? JOIN embeddings e ON e.id=m.id WHERE m.key IN ('chroma:document','page','chunk_index','content_sha256','visibility_scope') ORDER BY m.id", (doc["id"],))
            for identifier, key, string, integer in cursor:
                metadata.setdefault(identifier, {})[key] = integer if integer is not None else string
            chunks = sorted(metadata.values(), key=lambda row: row["chunk_index"])
            if len(chunks) != doc["chunk_count"] or [row["chunk_index"] for row in chunks] != list(range(len(chunks))):
                raise ValueError("source_chunk_count_or_sequence_mismatch")
            for row in chunks:
                if row["visibility_scope"] != "public" or row["content_sha256"] != file_sha or type(row["page"]) is not int or row["page"] <= 0:
                    raise ValueError("source_metadata_binding_invalid")
            from framework.upload.document_parser import parse_document
            from framework.upload.chunker import split_text_with_pages
            print(json.dumps({"stage": "verify_original", "document_id": doc["id"], "stratum": stratum, "chunks": len(chunks)}), flush=True)
            report = {"document_id": doc["id"], "original_hash_verified": True, "stratum": stratum}
            try:
                pages = parse_document(str(path), doc["file_type"], page_aware=True)
                rebuilt = split_text_with_pages(pages)
                matching = len(rebuilt) == len(chunks) and all(value == row["chroma:document"] and page == row["page"] for (value, page), row in zip(rebuilt, chunks))
                report.update(reparsed_pages=len(pages), rebuilt_chunks=len(rebuilt), all_chunk_text_and_pages_match=matching,
                              state="verified" if matching else "reparse_mismatch")
            except Exception as exc:
                report.update(state="reparse_failed", error_type=type(exc).__name__, all_chunk_text_and_pages_match=False)
            # Preserve every selected document even when verification fails.
            write(OUT/"verification"/(str(doc["id"])+".json"), report)
            exported = {"document_id": doc["id"], "title": doc["title"] or doc["name"], "content_sha256": file_sha,
                        "document_kind": "academic_paper", "visibility_scope": "public", "review_status": "approved",
                        "verification": report, "chunks": [{"document_id": doc["id"], "content_sha256": file_sha,
                           "chunk_index": row["chunk_index"], "page": row["page"], "content": row["chroma:document"]} for row in chunks]}
            write(OUT/"corpus"/(str(doc["id"])+".json"), exported)
            print(json.dumps({"stage": "saved", "document_id": doc["id"], "state": report["state"]}), flush=True)
    finally:
        connection.rollback(); connection.close()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in (OUT/"verification").glob("*.json")]
    write(OUT/"source-verification.json", {"selected": len(chosen), "saved": len(reports), "verified": sum(row["state"] == "verified" for row in reports),
          "model_calls": 0, "unresolved_sources_retained": [row["document_id"] for row in reports if row["state"] != "verified"]})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prepare()
