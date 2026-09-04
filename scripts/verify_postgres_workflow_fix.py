"""Verify production PostgreSQL cleanup and workflow audit migration."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT.parents[1]/".env",override=True)
import psycopg
from framework.config import Config
from framework.agents.workflows.comprehensive.checkpointing import normalize_postgres_uri

required={"analysis_object_type","analysis_object_id","area_code","context_version","analysis_context_snapshot","model_version","data_as_of","data_version"}
with psycopg.connect(normalize_postgres_uri(Config.SQLALCHEMY_DATABASE_URI)) as conn,conn.cursor() as cur:
    cur.execute("select count(*) from parcel_info where parcel_id=any(%s)",(["P-VERIFY-001","P-VERIFY-002","P-VERIFY-003"],)); fake=cur.fetchone()[0]
    cur.execute("select column_name from information_schema.columns where table_schema=current_schema() and table_name='model_execution_log'"); columns={row[0] for row in cur.fetchall()}
    cur.execute("select count(*) from information_schema.table_constraints where table_schema=current_schema() and table_name='model_execution_log' and constraint_type='UNIQUE' and constraint_name='uk_model_execution_log_trace_id'"); unique_trace=cur.fetchone()[0]
    cur.execute("select indexname,indexdef from pg_indexes where schemaname=current_schema() and tablename='model_execution_log' and indexname='idx_model_execution_log_trace_id'"); trace_index=cur.fetchone()
    cur.execute("select trace_id,parcel_id,count(*),count(*) filter (where analysis_object_type='parcel' and analysis_object_id=parcel_id) from model_execution_log where trace_id like 'postgres-%%' and parcel_id=any(%s) group by trace_id,parcel_id order by max(created_at) desc limit 3",(["4190","1","1593"],)); traces=[{"trace_id":r[0],"parcel_id":r[1],"agent_logs":r[2],"provenance_bound":r[3]} for r in cur.fetchall()]
result={"fake_parcels_remaining":fake,"missing_provenance_columns":sorted(required-columns),"trace_unique_constraint_present":bool(unique_trace),"trace_index_present":bool(trace_index),"latest_comprehensive_traces":traces}
print(json.dumps(result,ensure_ascii=False,indent=2)); raise SystemExit(0 if fake==0 and required<=columns and not unique_trace and trace_index and all(x["agent_logs"]==4 and x["provenance_bound"]==4 for x in traces) else 1)
