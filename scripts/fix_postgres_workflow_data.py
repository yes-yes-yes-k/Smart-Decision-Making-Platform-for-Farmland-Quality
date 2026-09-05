"""Back up and remove verification parcels, then migrate workflow provenance."""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT.parents[1]/".env",override=True)
import psycopg
import sqlalchemy as sa
from psycopg import sql
from framework.config import Config
from framework.agents.workflows.comprehensive.checkpointing import normalize_postgres_uri
from scripts.migrate_analysis_context import (
    ensure_execution_log_provenance, ensure_legacy_parcel_index,
    replace_unique_trace_constraint_with_index, _add_columns,
)

TARGETS=("P-VERIFY-001","P-VERIFY-002","P-VERIFY-003")


def fetch_dicts(cur,query,params=()):
    cur.execute(query,params); names=[item.name for item in cur.description]
    return [dict(zip(names,row)) for row in cur.fetchall()]


def main(argv=None):
    parser=argparse.ArgumentParser(); parser.add_argument("--apply",action="store_true"); args=parser.parse_args(argv)
    uri=normalize_postgres_uri(Config.SQLALCHEMY_DATABASE_URI)
    backup={"created_at":datetime.now(timezone.utc).isoformat(),"targets":TARGETS,"tables":{}}
    deleted={}
    with psycopg.connect(uri) as conn, conn.cursor() as cur:
        cur.execute("select id from model_execution_log where parcel_id=any(%s)",(list(TARGETS),)); execution_ids=[row[0] for row in cur.fetchall()]
        cur.execute("select distinct tc.table_name,kcu.column_name from information_schema.table_constraints tc join information_schema.key_column_usage kcu on tc.constraint_name=kcu.constraint_name and tc.table_schema=kcu.table_schema join information_schema.constraint_column_usage ccu on ccu.constraint_name=tc.constraint_name and ccu.table_schema=tc.table_schema where tc.constraint_type='FOREIGN KEY' and ccu.table_name='model_execution_log' and tc.table_schema=current_schema() order by tc.table_name")
        children=cur.fetchall()
        cur.execute("select c.table_name from information_schema.columns c join information_schema.tables t on t.table_schema=c.table_schema and t.table_name=c.table_name where c.table_schema=current_schema() and c.column_name='parcel_id' and t.table_type='BASE TABLE' order by c.table_name")
        parcel_tables=[row[0] for row in cur.fetchall()]
        for table,column in children:
            rows=fetch_dicts(cur,sql.SQL("select * from {} where {}=any(%s)").format(sql.Identifier(table),sql.Identifier(column)),(execution_ids,)) if execution_ids else []
            if rows: backup["tables"][table]=rows
        for table in parcel_tables:
            rows=fetch_dicts(cur,sql.SQL("select * from {} where parcel_id=any(%s)").format(sql.Identifier(table)),(list(TARGETS),))
            if rows: backup["tables"][table]=rows
        out=ROOT/"artifacts"/"postgres_cleanup"; out.mkdir(parents=True,exist_ok=True)
        path=out/f"verify-parcels-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(backup,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        if not args.apply:
            conn.rollback(); print(json.dumps({"mode":"dry-run","backup":str(path),"counts":{k:len(v) for k,v in backup["tables"].items()}},ensure_ascii=False)); return 0
        # Child rows first, then any non-FK parcel-indexed rows, execution logs,
        # and finally the three exact parcel records.
        for table,column in children:
            if execution_ids:
                cur.execute(sql.SQL("delete from {} where {}=any(%s)").format(sql.Identifier(table),sql.Identifier(column)),(execution_ids,)); deleted[table]=deleted.get(table,0)+cur.rowcount
        for table in parcel_tables:
            if table in {"model_execution_log","parcel_info"}: continue
            cur.execute(sql.SQL("delete from {} where parcel_id=any(%s)").format(sql.Identifier(table)),(list(TARGETS),)); deleted[table]=deleted.get(table,0)+cur.rowcount
        cur.execute("delete from model_execution_log where parcel_id=any(%s)",(list(TARGETS),)); deleted["model_execution_log"]=cur.rowcount
        cur.execute("delete from parcel_info where parcel_id=any(%s)",(list(TARGETS),)); deleted["parcel_info"]=cur.rowcount
        conn.commit()
    engine=sa.create_engine(Config.SQLALCHEMY_DATABASE_URI)
    with engine.begin() as connection:
        _add_columns(connection,"parcel_info",{"legacy_parcel_code":"VARCHAR(64)"})
        ensure_legacy_parcel_index(connection)
        ensure_execution_log_provenance(connection)
        replace_unique_trace_constraint_with_index(connection)
    with engine.connect() as connection:
        columns={item["name"] for item in sa.inspect(connection).get_columns("model_execution_log")}
        remaining=connection.execute(sa.text("select count(*) from parcel_info where parcel_id in ('P-VERIFY-001','P-VERIFY-002','P-VERIFY-003')")).scalar_one()
    print(json.dumps({"mode":"applied","backup":str(path),"deleted":deleted,"remaining_verify_parcels":remaining,"provenance_columns_present":sorted(columns & {"analysis_object_type","analysis_object_id","area_code","context_version","analysis_context_snapshot","model_version","data_as_of","data_version"})},ensure_ascii=False)); return 0

if __name__=="__main__": raise SystemExit(main())
