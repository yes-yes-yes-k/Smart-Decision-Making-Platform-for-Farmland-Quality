"""Read-only PostgreSQL inventory for the Cd chat integration baseline."""
import argparse
import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    load_dotenv(args.env_file)
    report = {'database': args.database, 'audited_at': datetime.now(timezone.utc).isoformat(), 'dependencies': {}, 'tables': {}}
    for package in ('pytest', 'matplotlib', 'rasterio', 'seaborn', 'psycopg2-binary'):
        try:
            report['dependencies'][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report['dependencies'][package] = 'missing'
    conn = psycopg2.connect(host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
                            user=os.getenv('DB_USER', 'postgres'), password=os.getenv('DB_PASSWORD'),
                            dbname=args.database, connect_timeout=10)
    conn.set_session(readonly=True, autocommit=False)
    with conn, conn.cursor() as cur:
        cur.execute('SHOW server_version')
        report['postgresql'] = cur.fetchone()[0]
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = {r[0] for r in cur.fetchall()}
        for name in sorted(tables):
            if name.startswith('cd_') or name in ('parcel_info', 'parcel_history_snapshot', 'spatial_region_catalog', 'farmland_region_parcel_area'):
                cur.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name)))
                item = {'count': cur.fetchone()[0]}
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (name,))
                item['columns'] = [r[0] for r in cur.fetchall()]
                report['tables'][name] = item
                if {'parcel_id', 'sample_id'} <= set(item['columns']):
                    cur.execute(sql.SQL('SELECT count(*) FROM (SELECT parcel_id,sample_id FROM {} GROUP BY 1,2 HAVING count(*)>1) d').format(sql.Identifier(name)))
                    item['duplicate_parcel_sample_keys'] = cur.fetchone()[0]
        for name in ('cd_flux_input', 'cd_flux_output', 'cd_conversation_trial'):
            report['tables'].setdefault(name, {'exists': False})
        if 'spatial_region_catalog' in tables:
            cur.execute('SELECT object_type,object_id,parent_object_type,parent_object_id,enabled FROM spatial_region_catalog')
            rows = cur.fetchall()
            nodes = {(r[0], r[1]): r for r in rows}
            enabled = {k: r for k, r in nodes.items() if r[4]}
            anomalies = {'missing_parent': [], 'disabled_parent': [], 'cycles': [], 'invalid_parent_type': []}
            counts = {}
            expected = {'township': 'county', 'county': 'city', 'city': 'province'}
            for key, row in enabled.items():
                counts[key[0]] = counts.get(key[0], 0) + 1
                parent = (row[2], row[3])
                if key[0] in expected and row[2] != expected[key[0]]:
                    anomalies['invalid_parent_type'].append(key)
                if row[2] or row[3]:
                    if parent not in nodes:
                        anomalies['missing_parent'].append(key)
                    elif not nodes[parent][4]:
                        anomalies['disabled_parent'].append(key)
                seen = set()
                current = key
                while current in nodes:
                    if current in seen:
                        anomalies['cycles'].append(key)
                        break
                    seen.add(current)
                    node = nodes[current]
                    current = (node[2], node[3])
            report['regions'] = {'enabled_counts': counts, 'anomalies': anomalies}
        mapping = next((n for n in tables if n == 'cd_ported_parcel_township'), None)
        if mapping:
            cur.execute(sql.SQL('SELECT township_id,count(*),count(DISTINCT parcel_id) FROM {} GROUP BY 1 ORDER BY 1').format(sql.Identifier(mapping)))
            report['ported_townships'] = cur.fetchall()
            cur.execute(sql.SQL('SELECT count(*) FROM {} m LEFT JOIN parcel_info p ON p.parcel_id=m.parcel_id WHERE p.parcel_id IS NULL').format(sql.Identifier(mapping)))
            report['ported_missing_parcels'] = cur.fetchone()[0]
            cur.execute(sql.SQL("SELECT count(*) FROM {} m LEFT JOIN spatial_region_catalog r ON r.object_type='township' AND r.object_id=m.township_id AND r.enabled WHERE r.id IS NULL").format(sql.Identifier(mapping)))
            report['ported_missing_enabled_townships'] = cur.fetchone()[0]
        if 'farmland_region_parcel_area' in tables:
            cur.execute('SELECT region_type,count(*),count(DISTINCT parcel_id) FROM farmland_region_parcel_area GROUP BY 1')
            report['native_area_mapping'] = cur.fetchall()
            cur.execute('SELECT count(*) FROM farmland_region_parcel_area a LEFT JOIN parcel_info p ON p.parcel_id=a.parcel_id WHERE p.parcel_id IS NULL')
            report['native_missing_parcels'] = cur.fetchone()[0]
    conn.close()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
