"""Read-only conversational adapter for annual flux queries and pure trials."""
import re
from contextvars import ContextVar

from sqlalchemy.exc import SQLAlchemyError

from framework.domain.other_models import cd_flux_v2 as flux

accepted = ContextVar('flux_defaults_accepted', default=())
DEFAULTS = {'bulk_density_g_cm3': {'value': 1., 'basis': 'legacy scenario assumption, not measured'},
            'soil_depth_m': {'value': .2, 'basis': 'legacy 0-20cm scenario'}}


def parse_acceptance(question):
    match = re.fullmatch(r'同意使用通量默认值[：:]\s*([a-z0-9_,，\s]+)[。！!]?', question.strip())
    if not match:
        return ()
    fields = tuple(x.strip() for x in re.split('[,，]', match[1]))
    return fields if fields and all(x in DEFAULTS for x in fields) else ()


def query(operation, previous, *, year=None, region_name=None, parameters=None, parcel_id=None,
          region_id=None, region_type=None, parameter_units=None, source=None, field=None, years=None,
          all_regions=False, limit=100, offset=0):
    from framework.config import Config
    if not Config.CD_FLUX_V2_ENABLED:
        return {'status': 'unavailable', 'message': '年度通量服务已关闭'}
    old = previous if (previous or {}).get('calculation_type') == 'flux' else {}
    if all_regions and (parcel_id or region_id):
        return {'status':'needs_analysis_object','message':'请先切换已验证分析范围，再查询全域。'}
    scope = {n: v if v is not None else old.get(n) for n, v in
             dict(year=year,region_name=region_name,parcel_id=parcel_id,region_id=region_id,region_type=region_type,source=source).items()}
    scope['source'] = scope['source'] or 'all'
    scope['all_regions'] = all_regions or old.get('all_regions', False)
    if parcel_id:
        scope.update(region_name=None,region_id=None,region_type=None,all_regions=False)
    elif region_id or region_name:
        scope.update(parcel_id=None,all_regions=False)
        if region_name and region_name != old.get('region_name') and not region_id:
            scope.update(region_id=None,region_type=region_type)
    if all_regions:
        scope.update(region_name=None,region_id=None,region_type=None,parcel_id=None)
    if scope['region_name'] and not scope['region_id']:
        from framework.models.thematic_model import SpatialRegionCatalog as Region
        rows = Region.query.filter_by(enabled=True,display_name=scope['region_name']).all()
        if len(rows) != 1:
            return {'status':'needs_analysis_object','candidates': [{'type':r.object_type,'id':r.object_id,'name':r.display_name} for r in rows]}
        scope.update(region_type=rows[0].object_type,region_id=rows[0].object_id)
    field = field or old.get('field') or 'net_cd'
    same = all(old.get(k) == v for k,v in scope.items())
    values = dict(old.get('parameters',{})) if same else {}
    units = dict(old.get('parameter_units',{})) if same else {}
    sources = dict(old.get('parameter_sources',{})) if same else {}
    draft = {**scope,'calculation_type':'flux','schema_version':2,'field':field,
             'parameters':values,'parameter_units':units,'parameter_sources':sources,
             'calculation_version':flux.VERSION}
    args = {k:scope[k] for k in ('source','year','parcel_id','region_type','region_id')}
    try:
        if operation == 'flux_parameters':
            result={'status':'ok','definitions':flux.UNITS,'default_options':DEFAULTS,
                    'missing_semantics':'未知不等于零；初始浓度需按容重与厚度换算储量','draft':draft}
            if scope['parcel_id'] and scope['year'] is not None:
                result['recorded_values'] = flux.select_inputs(**args)[0]
            return result
        if operation == 'flux_predict':
            if scope['year'] is None:
                return {'status':'needs_scenario_inputs','missing_fields':['year'],'draft':draft}
            if scope['parcel_id'] and (not same or not values):
                rows,_ = flux.select_inputs(**args)
                if len(rows)==1 and rows[0]['contract_version']==flux.VERSION:
                    row=rows[0]
                    known_units=(row['provenance'] or {}).get('units',{})
                    for name in flux.NUMBERS:
                        if row[name] is not None and known_units.get(name)==flux.UNITS[name]:
                            values[name]=row[name]; units[name]=known_units[name]
                            sources[name]={'source':'recorded_input','input_id':row['id'],'input_revision':row['input_revision']}
            for name,value in (parameters or {}).items():
                values[name]=value; units.pop(name,None); sources[name]={'source':'user_provided'}
            units.update(parameter_units or {})
            trial_units={**units,**{n:flux.UNITS[n] for n in accepted.get() if n in DEFAULTS}}
            result=flux.trial(values,trial_units,defaults=DEFAULTS,accepted_defaults=accepted.get())
            for name,entry in result['defaults'].items():
                values[name]=entry['value']; units[name]=flux.UNITS[name]
                sources[name]={'source':'explicitly_accepted_default',**entry}
            draft.update(parameters=values,parameter_units=units,parameter_sources=sources)
            return {**result,'calculation_type':'flux','schema_version':2,'draft':draft,
                    'missing_fields':result['coverage']['missing'],'default_options':DEFAULTS,
                    'scope':scope,'input_sources':sources}
        if not (scope['parcel_id'] or scope['region_id'] or scope['all_regions']):
            return {'status':'needs_analysis_object','draft':draft}
        if operation == 'flux_compare':
            args.pop('year')
            if years is None:
                return {'status':'needs_input','missing_fields':['years'],'draft':draft}
            result=flux.compare(years,field=field,**args)
        elif operation == 'flux_results':
            if not 1<=limit<=1000 or offset<0:
                raise ValueError('invalid_limit')
            result=flux.results(**args)
            result['total']=len(result['rows']);result['rows']=result['rows'][offset:offset+limit]
        else:
            result=flux.statistics(field=field,**args)
        artifact_scope = {**args, 'category': 'flux', 'field': field,
                          'calculation_version': flux.VERSION}
        if operation == 'flux_compare':
            artifact_scope['years'] = list(dict.fromkeys(years))
        return {**result,'status':'ok' if result.get('has_data',any(x['has_data'] for x in result.get('years',[]))) else 'no_data',
                'draft':draft, 'artifact_scope':artifact_scope}
    except ValueError as exc:
        return {'status':'needs_scenario_inputs','input_issues':str(exc),'draft':draft}
    except SQLAlchemyError:
        flux.session().rollback()
        return {'status':'service_unavailable','draft':draft}
