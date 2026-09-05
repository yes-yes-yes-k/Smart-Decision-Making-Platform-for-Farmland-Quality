"""Print a password-free summary of the configured PostgreSQL parcel table."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[3] / ".env",override=True)
from framework.config import Config
from framework.agents.workflows.comprehensive.checkpointing import normalize_postgres_uri
import psycopg

with psycopg.connect(normalize_postgres_uri(Config.SQLALCHEMY_DATABASE_URI)) as conn:
    with conn.cursor() as cur:
        cur.execute("select column_name,data_type from information_schema.columns where table_schema=current_schema() and table_name='parcel_info' order by ordinal_position")
        columns=cur.fetchall()
        cur.execute("select * from parcel_info limit 3")
        names=[item.name for item in cur.description]
        rows=[dict(zip(names,row)) for row in cur.fetchall()]
        cur.execute("select table_name from information_schema.columns where table_schema=current_schema() and column_name='parcel_id' order by table_name")
        parcel_tables=[row[0] for row in cur.fetchall()]
        verify_counts={}
        for table in parcel_tables:
            cur.execute(f'SELECT count(*) FROM "{table}" WHERE parcel_id = ANY(%s)',(["P-VERIFY-001","P-VERIFY-002","P-VERIFY-003"],))
            count=cur.fetchone()[0]
            if count: verify_counts[table]=count
        cur.execute("select column_name from information_schema.columns where table_schema=current_schema() and table_name='model_execution_log' order by ordinal_position")
        execution_columns=[row[0] for row in cur.fetchall()]
print(json.dumps({"columns":columns,"samples":rows,"verify_counts":verify_counts,"execution_columns":execution_columns},ensure_ascii=False,indent=2,default=str))
