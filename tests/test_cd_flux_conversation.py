from framework.agents.cd_conversation import query_cd, _draft_context
from framework.agents.cd_flux_conversation import accepted,parse_acceptance
from framework.domain.other_models import cd_flux_v2 as flux


def parameters():
    return dict(zip(flux.INPUTS+flux.OUTPUTS,[10,5,3,2,1,2,3,4]),initial_cd=600,bulk_density_g_cm3=1.3,soil_depth_m=.2)


def test_multiturn_scope_defaults_and_units(monkeypatch):
    monkeypatch.setattr(flux,'select_inputs',lambda **kwargs:([],{}))
    first=query_cd('flux_predict',year=2024,parameters={'enterprise_input':2},parameter_units={'enterprise_input':'g/ha/a'})
    assert first['status']=='partial'
    token=_draft_context.set(first['draft'])
    try:
        complete=query_cd('flux_predict',parameters={k:v for k,v in parameters().items() if k!='enterprise_input'},parameter_units=flux.UNITS)
        assert complete['net_cd']==10 and complete['end_cd']>0
        changed=query_cd('flux_predict',year=2025,parameters={'enterprise_input':3},parameter_units={'enterprise_input':'g/ha/a'})
        assert set(changed['draft']['parameters'])=={'enterprise_input'}
        bad=query_cd('flux_predict',parameters={'enterprise_input':3},parameter_units={'enterprise_input':'mg/kg'})
        assert bad['status']=='needs_scenario_inputs'
    finally:
        _draft_context.reset(token)


def test_no_scope_and_no_year_do_not_scan_database(monkeypatch):
    monkeypatch.setattr(flux,'statistics',lambda **kwargs:(_ for _ in ()).throw(AssertionError('no scan')))
    assert query_cd('flux')['status']=='needs_analysis_object'
    assert query_cd('flux_predict',parameters=parameters(),parameter_units=flux.UNITS)['missing_fields']==['year']
    assert query_cd('flux',parcel_id='locked',all_regions=True)['status']=='needs_analysis_object'


def test_explicit_default_acceptance():
    p=parameters();p.pop('bulk_density_g_cm3')
    first=query_cd('flux_predict',year=2024,parameters=p,parameter_units=flux.UNITS)
    assert first['end_cd'] is None
    token=_draft_context.set(first['draft'])
    fields=parse_acceptance('同意使用通量默认值：bulk_density_g_cm3')
    default_token=accepted.set(fields)
    try:
        result=query_cd('flux_predict')
        assert result['end_cd'] is not None
        assert result['draft']['parameter_sources']['bulk_density_g_cm3']['source']=='explicitly_accepted_default'
    finally:
        accepted.reset(default_token);_draft_context.reset(token)
    assert not parse_acceptance('同意使用通量默认值：enterprise_input')


def test_flux_source_and_year_queries(monkeypatch):
    calls=[]
    monkeypatch.setattr(flux,'statistics',lambda **kwargs:(calls.append(kwargs) or {'has_data':False,'groups':[]}))
    result=query_cd('flux',all_regions=True,year=2024,source='ported')
    assert result['status']=='no_data' and calls[0]['year']==2024 and calls[0]['source']=='ported'
    monkeypatch.setattr(flux,'compare',lambda years,**kwargs:{'years':[{'has_data':True,'year':y} for y in years]})
    result=query_cd('flux_compare',all_regions=True,years=[2023,2024])
    assert len(result['years'])==2
