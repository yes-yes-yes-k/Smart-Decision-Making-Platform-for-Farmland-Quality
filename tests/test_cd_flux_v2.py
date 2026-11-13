import csv
import io
import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from framework.domain.other_models import cd_flux_v2 as flux


def parameters():
    return dict(zip(flux.INPUTS + flux.OUTPUTS, [10, 5, 3, 2, 1, 2, 3, 4]),
                initial_cd=600, bulk_density_g_cm3=1.3, soil_depth_m=.2)


def test_independent_mass_balance_and_unknown_enterprise():
    p = parameters()
    result = flux.trial(p, flux.UNITS)
    assert (result['in_cd'], result['out_cd'], result['net_cd']) == (20,10,10)
    assert result['end_cd'] == pytest.approx(.2346153846153846)
    p.pop('enterprise_input')
    result = flux.trial(p, flux.UNITS)
    assert result['net_cd'] is None and result['end_cd'] is None
    assert result['subtotals']['in_cd'] == 18
    p['enterprise_input'] = 0
    assert flux.trial(p, flux.UNITS)['net_cd'] == 8
    p=parameters(); p.pop('initial_cd'); p['initial_concentration']=.3
    value=flux.trial(p,{**flux.UNITS,'initial_concentration':'mg/kg'})
    assert value['inputs']['initial_cd']==pytest.approx(780)
    assert value['end_cd']==pytest.approx(.3038461538461538)
    bins=flux.distribution('net_cd',[-6,-5,0,5,6])
    assert [b['count'] for b in bins['buckets']]==[1,3,1]
    assert sum(b['percent'] for b in bins['buckets'])==100


@pytest.mark.parametrize('field,value', [('initial_cd',float('nan')),('soil_depth_m',0),('bulk_density_g_cm3',-1),('enterprise_input',True)])
def test_invalid_inputs(field,value):
    p=parameters(); p[field]=value
    with pytest.raises(ValueError):
        flux.trial(p,flux.UNITS)


def test_defaults_require_acceptance_and_explicit_units():
    p=parameters(); p.pop('bulk_density_g_cm3')
    defaults={'bulk_density_g_cm3':{'value':1.3,'basis':'scenario assumption'}}
    assert flux.trial(p,flux.UNITS,defaults=defaults)['end_cd'] is None
    assert flux.trial(p,flux.UNITS,defaults=defaults,accepted_defaults=['bulk_density_g_cm3'])['end_cd'] is not None
    with pytest.raises(ValueError,match='unverified_unit'):
        flux.trial(parameters(),{**flux.UNITS,'initial_cd':'mg/kg'})
    with pytest.raises(ValueError,match='negative_end_stock'):
        flux.trial({**parameters(),'initial_cd':0,'grain_removal':100},flux.UNITS)


@pytest.fixture
def pg(monkeypatch):
    if not os.getenv('CD_MIGRATION_TEST_DB'):
        pytest.skip('PostgreSQL integration environment not enabled')
    load_dotenv(os.environ['CD_MIGRATION_ENV_FILE'])
    engine=create_engine(URL.create('postgresql+psycopg2',username=os.getenv('DB_USER','postgres'),password=os.getenv('DB_PASSWORD'),host=os.getenv('DB_HOST','localhost'),port=int(os.getenv('DB_PORT','5432')),database=os.environ['CD_MIGRATION_TEST_DB']))
    with engine.connect() as conn:
        outer=conn.begin()
        name='cd_v2_test_'+uuid.uuid4().hex
        conn.execute(text('CREATE SCHEMA '+name))
        conn.execute(text('SET LOCAL search_path TO '+name))
        raw=conn.connection.cursor()
        raw.execute((Path(__file__).parents[1]/'scripts/sql/cd_flux_v2.sql').read_text(encoding='utf-8'))
        raw.close()
        db=Session(bind=conn,join_transaction_mode='create_savepoint')
        monkeypatch.setattr(flux,'session',lambda:db)
        try:
            yield db
        finally:
            db.close(); outer.rollback()
            assert conn.execute(text('SELECT to_regnamespace(:n)'),{'n':name}).scalar() is None
    engine.dispose()


def csv_data(rows):
    out=io.StringIO(); writer=csv.DictWriter(out,fieldnames=['source','accounting_year','parcel_id','sample_id',*flux.NUMBERS])
    writer.writeheader(); writer.writerows(rows)
    return out.getvalue().encode()


def row(year=2024,source='ported'):
    return {**parameters(),'source':source,'accounting_year':year,'parcel_id':'p','sample_id':'s'}


def test_atomic_import_revision_and_year_comparison(pg):
    with pytest.raises(ValueError):
        flux.import_csv(csv_data([row(),{**row(2023),'enterprise_input':'bad'}]))
    assert pg.execute(text('SELECT count(*) FROM cd_flux_input_v2')).scalar()==0
    flux.import_csv(csv_data([row(),row(2023),row(2024,'native')]))
    flux.calculate()
    assert len(flux.results(source='ported')['rows'])==2
    assert len(flux.results(year=2024)['rows'])==2
    comparison=flux.compare([2023,2024],source='ported')
    assert len(comparison['years'])==2
    flux.import_csv(csv_data([{**row(),'enterprise_input':3}]))
    assert flux.results(source='ported',year=2024)['rows'][0]['output'] is None
    flux.calculate(source='ported',year=2024)
    flux.calculate(source='ported',year=2024)
    assert flux.results(source='ported',year=2024)['rows'][0]['output']['net_cd']==11
    assert pg.execute(text('SELECT count(*) FROM cd_flux_output_v2')).scalar()==4


def test_legacy_and_enterprise_unknown_are_isolated(pg):
    from framework.domain.other_models.cd_flux import REQUIRED_COLUMNS
    old=dict(zip(REQUIRED_COLUMNS,['p','s',600,10,5,3,1,2,3,4]))
    buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=REQUIRED_COLUMNS); w.writeheader(); w.writerow(old)
    flux.import_csv(buf.getvalue().encode(),legacy=True)
    flux.import_csv(csv_data([{**row(),'enterprise_input':''}]))
    flux.calculate()
    assert len(flux.results(year=2024)['rows'])==1
    value=flux.results(year=2024)['rows'][0]['output']
    assert value['status']=='partial' and value['net_cd'] is None
    assert flux.results(source='unknown')['rows'][0]['accounting_year'] is None


def test_parent_mapping_and_invalid_chains(pg,monkeypatch):
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial
    monkeypatch.setattr(spatial,'ported_region_map',lambda:{'p':'t','bad':'broken'})
    pg.execute(text('CREATE TABLE spatial_region_catalog (object_type text,object_id text,parent_object_type text,parent_object_id text,enabled boolean)'))
    for t,i,pt,pi in [('township','t','county','c'),('county','c','city','s'),('city','s','province','p'),('province','p',None,None),('township','broken','township','broken')]:
        pg.execute(text('INSERT INTO spatial_region_catalog VALUES (:t,:i,:pt,:pi,true)'),dict(t=t,i=i,pt=pt,pi=pi))
    for t,i in [('township','t'),('county','c'),('city','s'),('province','p')]:
        m,errors=flux.mapping('ported',t)
        assert m.get('p')==i
        if t!='township':
            assert 'bad' in errors
    flux.import_csv(csv_data([row()]))
    assert len(flux.results(source='ported',region_type='county',region_id='c')['rows'])==1
    from framework.agents.cd_conversation import query_cd
    flux.calculate()
    for t,i in [('township','t'),('county','c'),('city','s'),('province','p')]:
        assert query_cd('flux',region_type=t,region_id=i,year=2024)['status']=='ok'
    with pytest.raises(ValueError,match='invalid_source'):
        flux.results(source='invalid')


def test_authenticated_management_api(pg):
    from flask import Flask
    from flask_jwt_extended import JWTManager,create_access_token
    from framework.api.routes.cd_flux import cd_flux_bp
    app=Flask(__name__); app.config['JWT_SECRET_KEY']='integration-secret-more-than-32-characters'
    JWTManager(app); app.register_blueprint(cd_flux_bp,url_prefix='/api/v1/cd-flux')
    client=app.test_client()
    assert client.get('/api/v1/cd-flux/v2/results').status_code==401
    with app.app_context():
        token=create_access_token(identity='1')
    headers={'Authorization':'Bearer '+token}
    response=client.post('/api/v1/cd-flux/v2/inputs/import',headers=headers,
                         data={'file':(io.BytesIO(csv_data([row()])),'inputs.csv')})
    assert response.status_code==200
    assert client.post('/api/v1/cd-flux/v2/calculate',headers=headers,json={'year':2024}).status_code==200
    result=client.get('/api/v1/cd-flux/v2/results?year=2024',headers=headers).get_json()['data']
    assert result['rows'][0]['output']['net_cd']==10
    assert client.get('/api/v1/cd-flux/v2/statistics?year=2024',headers=headers).status_code==200
    assert client.get('/api/v1/cd-flux/v2/compare?years=2023&years=2024',headers=headers).status_code==200
    assert client.get('/api/v1/cd-flux/v2/results?year=unknown',headers=headers).status_code==400
    app.config['CD_FLUX_V2_ENABLED']=False
    assert client.get('/api/v1/cd-flux/v2/results',headers=headers).status_code==503
    assert pg.execute(text('SELECT count(*) FROM cd_flux_input_v2 WHERE accounting_year=2024')).scalar()==1


def test_conversation_reads_matching_parameters_and_does_not_write_business(pg):
    from framework.agents.cd_conversation import query_cd,_draft_context
    flux.import_csv(csv_data([row(),{**row(2023),'enterprise_input':9}]))
    before=pg.execute(text('SELECT count(*) FROM cd_flux_output_v2')).scalar()
    result=query_cd('flux_predict',parcel_id='p',year=2024,source='ported')
    assert result['net_cd']==10
    assert result['draft']['parameter_sources']['enterprise_input']['source']=='recorded_input'
    assert pg.execute(text('SELECT count(*) FROM cd_flux_output_v2')).scalar()==before
    token=_draft_context.set(result['draft'])
    try:
        changed=query_cd('flux_predict',year=2023)
        assert changed['net_cd']==17
    finally:
        _draft_context.reset(token)
