"""Opt-in PostgreSQL rehearsal; all schema/data changes are rolled back."""
import importlib.util
import os
from pathlib import Path
import uuid

import psycopg2
from psycopg2 import sql
import pytest
from dotenv import load_dotenv

spec = importlib.util.spec_from_file_location('flux_migration', Path(__file__).parents[1] / 'scripts/migrate_cd_flux_v2.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


@pytest.fixture
def connection():
    database = os.getenv('CD_MIGRATION_TEST_DB')
    if not database:
        pytest.skip('set CD_MIGRATION_TEST_DB for PostgreSQL migration rehearsal')
    load_dotenv(os.environ['CD_MIGRATION_ENV_FILE'])
    conn = psycopg2.connect(host=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
                            user=os.getenv('DB_USER', 'postgres'), password=os.getenv('DB_PASSWORD'), dbname=database)
    name = 'cd_migration_test_' + uuid.uuid4().hex
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
            cur.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(name)))
        yield conn
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute('SELECT to_regnamespace(%s)', (name,))
            assert cur.fetchone()[0] is None
        conn.rollback()
        conn.close()


def test_unknown_year_uniqueness_and_multiple_years(connection):
    assert migration.migrate(connection) == {'inputs': 0, 'outputs': 0}
    assert migration.migrate(connection) == {'inputs': 0, 'outputs': 0}
    with connection.cursor() as cur:
        statement = '''INSERT INTO cd_flux_input_v2(source,parcel_id,sample_id,accounting_year,contract_version)
                       VALUES ('unknown','p','s',%s,'legacy_v1')'''
        cur.execute(statement, (None,))
        cur.execute('SAVEPOINT duplicate_check')
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(statement, (None,))
        cur.execute('ROLLBACK TO SAVEPOINT duplicate_check')
        cur.execute(statement, (2023,))
        cur.execute(statement, (2024,))
        cur.execute('SELECT count(*) FROM cd_flux_input_v2')
        assert cur.fetchone()[0] == 3


def test_legacy_copy_preserves_unknowns_and_idempotence(connection):
    with connection.cursor() as cur:
        cur.execute('''CREATE TABLE cd_flux_input (id bigint,parcel_id text,sample_id text,
            initial_cd float,atmospheric_deposition float,irrigation_input float,agro_chemicals_input float,
            groundwater_leaching float,surface_runoff float,grain_removal float,straw_removal float,bd020_90 float);
            INSERT INTO cd_flux_input VALUES(1,'p','s',600,10,5,3,1,2,3,4,1.3);
            CREATE TABLE cd_flux_output (parcel_id text,sample_id text,in_cd float,out_cd float,net_cd float,end_cd float);
            INSERT INTO cd_flux_output VALUES('p','s',18,10,8,0.233846);''')
    assert migration.migrate(connection) == {'inputs': 1, 'outputs': 1}
    assert migration.migrate(connection) == {'inputs': 0, 'outputs': 0}
    with connection.cursor() as cur:
        cur.execute('SELECT source,accounting_year,enterprise_input,bulk_density_g_cm3 FROM cd_flux_input_v2')
        assert cur.fetchone() == ('unknown', None, None, None)
        cur.execute('SELECT in_cd,calculation_version FROM cd_flux_output_v2')
        assert cur.fetchone() == (18, 'legacy_v1')
        cur.execute('SELECT count(*) FROM cd_flux_input')
        assert cur.fetchone()[0] == 1


def test_incompatible_schema_refuses_and_rollback_recovers(connection):
    with connection.cursor() as cur:
        cur.execute('SAVEPOINT before_failure')
        cur.execute('CREATE TABLE cd_flux_input_v2 (id bigint)')
    with pytest.raises(ValueError,match='partial_v2_schema'):
        migration.migrate(connection)
    with connection.cursor() as cur:
        cur.execute('ROLLBACK TO SAVEPOINT before_failure')
    assert migration.migrate(connection)=={'inputs':0,'outputs':0}


def test_new_year_data_survives_repeated_migration(connection):
    migration.migrate(connection)
    with connection.cursor() as cur:
        cur.execute("INSERT INTO cd_flux_input_v2(source,parcel_id,sample_id,accounting_year,enterprise_input,contract_version) VALUES('ported','p','s',2024,3,'v2'),('ported','p','s',2023,2,'v2')")
    migration.migrate(connection)
    with connection.cursor() as cur:
        cur.execute('SELECT accounting_year,enterprise_input FROM cd_flux_input_v2 ORDER BY accounting_year')
        assert cur.fetchall()==[(2023,2),(2024,3)]
