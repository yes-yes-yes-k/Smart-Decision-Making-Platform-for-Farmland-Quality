"""Transactional PostgreSQL migration. Defaults to rehearsal with rollback.

An explicit --apply is required to persist the new parallel tables. Existing
legacy rows remain untouched; copied values retain unknown year and units.
"""
import argparse
import json
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('cd_flux_input_v2', 'cd_flux_output_v2')


def migrate(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext('cd_flux_v2_migration'))")
        cur.execute('SHOW server_version_num')
        if int(cur.fetchone()[0]) < 150000:
            raise ValueError('PostgreSQL 15+ required for NULLS NOT DISTINCT')
        cur.execute('SELECT to_regclass(%s),to_regclass(%s)', TABLES)
        present = cur.fetchone()
        if any(present) and not all(present):
            raise ValueError('partial_v2_schema: inspect manually before retry')
        if not any(present):
            cur.execute((ROOT / 'scripts/sql/cd_flux_v2.sql').read_text(encoding='utf-8'))
        for table, required in (
            ('cd_flux_input_v2', {'id','source','parcel_id','sample_id','accounting_year','input_revision',
                                 'enterprise_input','provenance','contract_version','soil_depth_m','bulk_density_g_cm3'}),
            ('cd_flux_output_v2', {'id','input_id','input_revision','calculation_version','coverage','unit_status','end_cd'}),
        ):
            cur.execute('SELECT attname FROM pg_attribute WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped', (table,))
            if not required <= {r[0] for r in cur.fetchall()}:
                raise ValueError('incompatible_existing_schema:' + table)
        cur.execute("SELECT count(*) FROM pg_index WHERE indrelid='cd_flux_input_v2'::regclass AND indisunique AND indnullsnotdistinct")
        if cur.fetchone()[0] != 1:
            raise ValueError('missing_unknown_year_unique_constraint')
        cur.execute("""SELECT array_agg(a.attname ORDER BY k.ord) FROM pg_index ix
            CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY k(attnum,ord)
            JOIN pg_attribute a ON a.attrelid=ix.indrelid AND a.attnum=k.attnum
            WHERE ix.indrelid='cd_flux_input_v2'::regclass AND ix.indisunique AND ix.indnullsnotdistinct
            GROUP BY ix.indexrelid""")
        if cur.fetchone()[0] != ['source','parcel_id','sample_id','accounting_year']:
            raise ValueError('incompatible_annual_unique_key')
        cur.execute("SELECT to_regclass('cd_flux_input'),to_regclass('cd_flux_output')")
        legacy_input, legacy_output = cur.fetchone()
        copied = {'inputs': 0, 'outputs': 0}
        if legacy_input:
            cur.execute('SELECT parcel_id,sample_id FROM cd_flux_input GROUP BY 1,2 HAVING count(*)>1 LIMIT 1')
            if cur.fetchone():
                raise ValueError('duplicate_legacy_input_keys')
            cur.execute('''INSERT INTO cd_flux_input_v2
                (source,parcel_id,sample_id,accounting_year,initial_cd,
                 atmospheric_deposition,irrigation_input,agro_chemicals_input,
                 groundwater_leaching,surface_runoff,grain_removal,straw_removal,
                 contract_version,provenance)
                SELECT 'unknown',parcel_id,sample_id,NULL,initial_cd,
                    atmospheric_deposition,irrigation_input,agro_chemicals_input,
                    groundwater_leaching,surface_runoff,grain_removal,straw_removal,
                    'legacy_v1',jsonb_build_object('legacy_input_id',id,
                      'legacy_bulk_density',bd020_90,'unit_status','unverified')
                FROM cd_flux_input ON CONFLICT DO NOTHING''')
            copied['inputs'] = cur.rowcount
        if legacy_output:
            cur.execute('SELECT parcel_id,sample_id FROM cd_flux_output GROUP BY 1,2 HAVING count(*)>1 LIMIT 1')
            if cur.fetchone():
                raise ValueError('duplicate_legacy_output_keys')
            cur.execute('''SELECT count(*) FROM cd_flux_output o LEFT JOIN
                cd_flux_input_v2 i ON i.source='unknown' AND i.accounting_year IS NULL
                AND i.contract_version='legacy_v1' AND i.parcel_id=o.parcel_id
                AND i.sample_id=o.sample_id WHERE i.id IS NULL''')
            if cur.fetchone()[0]:
                raise ValueError('orphan_legacy_output: migration stopped without changing legacy')
            cur.execute('''INSERT INTO cd_flux_output_v2
                (input_id,input_revision,calculation_version,in_cd,out_cd,net_cd,end_cd,
                 status,coverage,unit_status)
                SELECT i.id,1,'legacy_v1',o.in_cd,o.out_cd,o.net_cd,o.end_cd,
                    'legacy', '{"enterprise_input":"unknown","components":7}'::jsonb,
                    '{"status":"unverified"}'::jsonb
                FROM cd_flux_output o JOIN cd_flux_input_v2 i
                ON i.source='unknown' AND i.accounting_year IS NULL
                AND i.contract_version='legacy_v1' AND i.parcel_id=o.parcel_id
                AND i.sample_id=o.sample_id ON CONFLICT DO NOTHING''')
            copied['outputs'] = cur.rowcount
        return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_dotenv(args.env_file)
    conn = psycopg2.connect(host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
                            user=os.getenv('DB_USER', 'postgres'), password=os.getenv('DB_PASSWORD'),
                            dbname=args.database, connect_timeout=10)
    try:
        result = migrate(conn)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps({'mode': 'applied' if args.apply else 'rehearsal_rolled_back', **result}))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
