"""Read-only M0 inventory. Never initializes the app, Chroma client or workers."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import sqlite3
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def database_snapshot(config):
    """Use server-enforced read-only transactions; never echo DSNs or errors."""
    from sqlalchemy.engine import make_url
    import psycopg2
    url = make_url(config.SQLALCHEMY_DATABASE_URI)
    report = {"driver": url.drivername, "endpoint_is_local": url.host in (None, "localhost", "127.0.0.1", "::1"),
              "state": "unavailable", "queries_are_aggregate_or_metadata_only": True}
    eligible = {}
    connection = None
    try:
        connection = psycopg2.connect(host=url.host, port=url.port, user=url.username, password=url.password,
             dbname=url.database, connect_timeout=4,
             options="-c default_transaction_read_only=on -c statement_timeout=8000 -c lock_timeout=1000 -c application_name=kg_recovery_m0_readonly")
        connection.set_session(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
        cur = connection.cursor()
        cur.execute("SHOW transaction_read_only")
        report["server_read_only"] = cur.fetchone()[0] == "on"
        if not report["server_read_only"]:
            raise RuntimeError("read_only_not_enforced")
        cur.execute("SELECT version()")
        report["server_version"] = cur.fetchone()[0].split(",")[0]
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")
        tables = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT current_schema()")
        report["inspected_schema"] = cur.fetchone()[0]
        cur.execute("SELECT schemaname,tablename FROM pg_tables WHERE tablename LIKE 'kg\\_%' ESCAPE '\\'")
        report["KG_tables_across_schemas"] = [{"schema": schema, "table": table} for schema, table in cur.fetchall()]
        report["document_table_present"] = "kb_document" in tables
        if "kb_document" in tables:
            cur.execute("SELECT count(*),coalesce(sum(chunk_count),0) FROM kb_document")
            total, chunks = cur.fetchone()
            report["documents_total"], report["declared_chunks_total"] = total, int(chunks)
            for name in ("status", "processing_stage", "review_status", "visibility_scope", "document_kind", "language"):
                cur.execute('SELECT "'+name+'",count(*) FROM kb_document GROUP BY "'+name+'"')
                report[name+"_counts"] = {str(k): n for k, n in cur.fetchall()}
            cur.execute("SELECT id,file_hash,chunk_count,file_path FROM kb_document WHERE status=1 AND processing_stage='completed' AND review_status='approved' AND visibility_scope='public' AND document_kind IN ('academic_paper','standard','policy','method_guideline') AND file_hash IS NOT NULL AND file_hash<>'' AND chunk_count>0")
            present = 0
            for did, digest, count, filename in cur.fetchall():
                eligible[did] = {"hash": digest, "expected": count}
                path = Path(filename)
                if not path.is_absolute():
                    path = Path(config.UPLOAD_FOLDER)/path
                present += path.is_file()
            report.update(eligible_public_documents=len(eligible), eligible_declared_chunks=sum(row["expected"] for row in eligible.values()),
                          eligible_source_files_present=present, eligible_source_files_missing=len(eligible)-present,
                          original_file_bytes_rehashed=False)
            cur.execute("SELECT document_kind,count(*),count(nullif(doi_normalized,'')),count(DISTINCT nullif(doi_normalized,'')) FROM kb_document GROUP BY document_kind")
            report["bibliographic_identity"] = [{"kind": kind, "documents": n, "nonempty_DOI": with_doi, "distinct_DOI": distinct}
                                                  for kind, n, with_doi, distinct in cur.fetchall()]
        grouped = {"kg_extraction_job": "state", "kg_outbox_event": "state", "kg_entity_candidate": "review_status",
                   "kg_relation_candidate": "review_status", "kg_claim_candidate": "review_status",
                   "kg_candidate_evidence": "review_status", "kg_claim_evidence": "review_status", "kg_release": "state"}
        report["workflow_tables"] = {}
        for table, column in grouped.items():
            if table not in tables:
                report["workflow_tables"][table] = {"present": False}
                continue
            cur.execute('SELECT "'+column+'",count(*) FROM "'+table+'" GROUP BY "'+column+'"')
            report["workflow_tables"][table] = {"present": True, "counts": {str(k): n for k, n in cur.fetchall()}}
        if "kg_control" in tables:
            cur.execute("SELECT active_release_id FROM kg_control")
            report["active_release_pointers"] = [row[0] for row in cur.fetchall()]
        cur.execute("SELECT extname,extversion FROM pg_extension WHERE extname='age'")
        report["age_extensions"] = [{"name": name, "version": version} for name, version in cur.fetchall()]
        cur.execute("SELECT name,default_version,installed_version FROM pg_available_extensions WHERE name='age'")
        report["age_available_extensions"] = [{"name": name, "available_version": available, "installed_version": installed}
                                               for name, available, installed in cur.fetchall()]
        if report["age_extensions"]:
            cur.execute("SELECT count(*) FROM ag_catalog.ag_graph")
            report["age_graph_count"] = cur.fetchone()[0]
        report["state"] = "observed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["sqlstate"] = getattr(exc, "pgcode", None)
        report["partial_results_only"] = True
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()
    return report, eligible


def vector_snapshot(config, eligible, database_observed):
    path = Path(config.CHROMA_PERSIST_DIR).resolve()/"chroma.sqlite3"
    report = {"state": "missing" if not path.is_file() else "unavailable", "method": "sqlite_metadata_diagnostic_only",
              "read_only": True, "Chroma_client_started": False, "proves_HNSW_or_query_health": False}
    if not path.is_file():
        return report
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=3)
        connection.execute("PRAGMA query_only=ON")
        report["query_only"] = connection.execute("PRAGMA query_only").fetchone()[0] == 1
        deadline = time.monotonic()+30
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        connection.execute("BEGIN")
        report["sqlite_bytes"] = path.stat().st_size
        report["collections"] = [{"name": name, "dimension": dimension, "rows": n} for name, dimension, n in connection.execute(
            "SELECT c.name,c.dimension,count(e.id) FROM collections c LEFT JOIN segments s ON s.collection=c.id AND s.scope='METADATA' LEFT JOIN embeddings e ON e.segment_id=s.id GROUP BY c.id,c.name,c.dimension")]
        report["embedding_rows"] = connection.execute("SELECT count(*) FROM embeddings").fetchone()[0]
        observed = defaultdict(Counter)
        visibility, seen = Counter(), 0
        def consume(meta):
            nonlocal seen
            if not meta:
                return
            seen += 1
            visibility[str(meta.get("visibility_scope", "missing"))] += 1
            did = meta.get("document_id")
            if database_observed and type(did) is int and meta.get("visibility_scope") == "public":
                if did in eligible:
                    digest = meta.get("content_sha256")
                    state = "missing" if not digest else "matching" if digest == eligible[did]["hash"] else "conflicting"
                    observed[did][state] += 1
                else:
                    report["public_chunks_outside_eligible_snapshot"] = report.get("public_chunks_outside_eligible_snapshot", 0)+1
        current, meta = None, {}
        cursor = connection.execute("SELECT m.id,m.key,m.string_value,m.int_value FROM embedding_metadata m JOIN embeddings e ON e.id=m.id WHERE m.key IN ('document_id','visibility_scope','content_sha256') ORDER BY m.id")
        for identifier, key, string, integer in cursor:
            if identifier != current:
                consume(meta)
                current, meta = identifier, {}
            meta[key] = integer if integer is not None else string
        consume(meta)
        report.update(state="observed", rows_with_selected_metadata=seen, visibility_counts=dict(visibility))
        report["source_position_metadata"] = {
            "positive_page_rows": connection.execute("SELECT count(*) FROM embedding_metadata m JOIN embeddings e ON e.id=m.id WHERE m.key='page' AND m.int_value>0").fetchone()[0],
            "nonnegative_chunk_index_rows": connection.execute("SELECT count(*) FROM embedding_metadata m JOIN embeddings e ON e.id=m.id WHERE m.key='chunk_index' AND m.int_value>=0").fetchone()[0]}
        if database_observed:
            totals = sum(observed.values(), Counter())
            discrepancies = [did for did, row in eligible.items() if sum(observed[did].values()) != row["expected"]]
            report["eligible_document_metadata_binding"] = {"documents": len(eligible), "counts": dict(totals),
                "fully_bound_documents": sum(observed[did]["matching"] == row["expected"] and not observed[did]["missing"] and not observed[did]["conflicting"] for did, row in eligible.items()),
                "chunk_count_discrepancy_documents": len(discrepancies), "discrepancy_document_ids_first_20": discrepancies[:20],
                "source_bytes_or_chunk_text_revalidated": False,
                "relational_and_vector_snapshots_are_not_cross_store_atomic": True}
        else:
            report["eligible_binding"] = "unknown_relational_snapshot_unavailable"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["partial_results_only"] = True
    finally:
        if connection is not None:
            connection.rollback()
            connection.close()
    return report


def graph_snapshot(config):
    path = Path(config.KG_GRAPH_PATH)
    report = {"configured_API_store": config.KG_GRAPH_STORE, "configured_file_exists": path.is_file(),
              "configured_graph_retrieval_enabled": config.KG_RETRIEVAL_ENABLED,
              "live_process_store_not_introspected": True, "chat_source_code_store": "file_KnowledgeGraphRetriever"}
    if path.is_file():
        blob = path.read_bytes()
        payload = json.loads(blob)
        report.update(file_sha256=hashlib.sha256(blob).hexdigest(), file_bytes=len(blob),
                      top_level_keys=list(payload), counts={key: len(payload[key]) for key in ("entities", "relations", "evidence", "evidences", "claims") if isinstance(payload.get(key), (list, dict))})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    database, eligible = database_snapshot(Config)
    report = {"schema": "knowledge-engineering-M0-inventory-v1", "client_date": "2026-10-30",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "model_calls": 0, "database_writes": 0, "app_or_worker_started": False,
              "hardware": {"os": platform.system(), "os_release": platform.release(), "architecture": platform.machine(), "logical_CPUs": os.cpu_count()},
              "database": database, "vector": vector_snapshot(Config, eligible, database["state"] == "observed"), "graph": graph_snapshot(Config)}
    source = Path(r"D:\17417\Documents\知识库文献")
    counts, size = Counter(), 0
    if source.is_dir():
        for path in source.rglob("*"):
            if path.is_file():
                counts[path.suffix.lower() or "no_extension"] += 1
                size += path.stat().st_size
    report["source_directory"] = {"exists": source.is_dir(), "files_by_extension": dict(counts), "total_bytes": size,
                                  "files_deduplicated_or_hash_verified": False, "not_equal_to_database_document_count": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output), "database_state": database["state"], "vector_state": report["vector"]["state"], "model_calls": 0}))


if __name__ == "__main__":
    main()
