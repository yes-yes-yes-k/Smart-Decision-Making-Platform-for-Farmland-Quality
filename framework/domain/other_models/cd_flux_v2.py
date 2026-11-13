"""Annual, provenance-aware flux services; trial() has no database dependency."""
import csv
import io
import json
import math

from sqlalchemy import text

INPUTS = ('atmospheric_deposition', 'irrigation_input', 'agro_chemicals_input', 'enterprise_input')
OUTPUTS = ('groundwater_leaching', 'surface_runoff', 'grain_removal', 'straw_removal')
NUMBERS = (*INPUTS, *OUTPUTS, 'initial_cd', 'bulk_density_g_cm3', 'soil_depth_m')
VERSION = 'cd_flux_mass_balance_v2'
UNITS = {**dict.fromkeys((*INPUTS, *OUTPUTS), 'g/ha/a'), 'initial_cd': 'g/ha',
         'bulk_density_g_cm3': 'g/cm3', 'soil_depth_m': 'm'}


def number(value, name):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('invalid_number:' + name)
    result = float(value)
    if not math.isfinite(result) or result < 0 or (name in ('bulk_density_g_cm3', 'soil_depth_m') and result == 0):
        raise ValueError('invalid_number:' + name)
    return result


def trial(parameters, units, *, defaults=None, accepted_defaults=()):
    values = dict(parameters)
    concentration = number(values.pop('initial_concentration', None), 'initial_concentration')
    used_defaults = {}
    for name, entry in (defaults or {}).items():
        if name not in NUMBERS or name == 'enterprise_input' or not isinstance(entry, dict) or not entry.get('basis'):
            raise ValueError('invalid_default')
        if values.get(name) is None and name in accepted_defaults:
            values[name] = entry['value']
            used_defaults[name] = entry
    unknown = set(values) - set(NUMBERS)
    if unknown:
        raise ValueError('unknown_parameters:' + ','.join(sorted(unknown)))
    values = {n: number(values.get(n), n) for n in NUMBERS}
    for name, value in values.items():
        if value is not None and units.get(name) != UNITS[name]:
            raise ValueError('unverified_unit:' + name)
    if concentration is not None:
        if units.get('initial_concentration') != 'mg/kg':
            raise ValueError('unverified_unit:initial_concentration')
        if values['soil_depth_m'] is None or values['bulk_density_g_cm3'] is None:
            raise ValueError('initial_concentration_requires_soil_mass')
        stock = concentration * 10000 * values['soil_depth_m'] * values['bulk_density_g_cm3']
        if not math.isfinite(stock):
            raise ValueError('numeric_overflow')
        if values['initial_cd'] is not None and not math.isclose(values['initial_cd'], stock, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('conflicting_initial_stock_and_concentration')
        values['initial_cd'] = stock
    missing = [n for n in (*INPUTS, *OUTPUTS) if values[n] is None]
    incoming = sum(values[n] or 0 for n in INPUTS)
    outgoing = sum(values[n] or 0 for n in OUTPUTS)
    if not all(math.isfinite(v) for v in (incoming, outgoing)):
        raise ValueError('numeric_overflow')
    result = {'status': 'partial' if missing else 'success', 'calculation_version': VERSION,
              'coverage': {'missing': missing, 'covered': [n for n in (*INPUTS, *OUTPUTS) if n not in missing]},
              'subtotals': {'in_cd': incoming, 'out_cd': outgoing}, 'in_cd': None,
              'out_cd': None, 'net_cd': None, 'end_cd': None, 'inputs': values,
              'defaults': used_defaults, 'unit_status': {'status': 'verified_explicit_contract'}, 'duration_years': 1}
    if missing:
        return result
    net = incoming - outgoing
    if not all(math.isfinite(v) for v in (incoming, outgoing, net)):
        raise ValueError('numeric_overflow')
    result.update(in_cd=incoming, out_cd=outgoing, net_cd=net)
    concentration_missing = [n for n in ('initial_cd', 'bulk_density_g_cm3', 'soil_depth_m') if values[n] is None]
    result['concentration_missing'] = concentration_missing
    if not concentration_missing:
        remaining = values['initial_cd'] + net
        if remaining < 0:
            raise ValueError('negative_end_stock')
        mass = 10000000 * values['soil_depth_m'] * values['bulk_density_g_cm3']
        if not math.isfinite(mass) or mass <= 0:
            raise ValueError('invalid_soil_mass')
        result['end_cd'] = 1000 * remaining / mass
    return result


def session():
    from framework.models.user import db
    return db.session


def mapping(source, region_type):
    from framework.domain.other_models import heavy_metal_cd_spatial as spatial
    if source == 'native':
        return spatial.parcel_region_map(region_type), {}
    if source != 'ported':
        return {}, {'unknown_source': True}
    base = spatial.ported_region_map()
    rows = session().execute(text('SELECT object_type,object_id,parent_object_type,parent_object_id,enabled FROM spatial_region_catalog')).all()
    nodes = {(r[0], r[1]): r for r in rows}
    result, errors = {}, {}
    expected = {'township': 'county', 'county': 'city', 'city': 'province'}
    for parcel, township in base.items():
        current, seen = ('township', township), set()
        target = None
        valid_chain = False
        while current in nodes and current not in seen:
            seen.add(current)
            row = nodes[current]
            if not row[4]:
                break
            if current[0] == region_type:
                target = current[1]
            if current[0] == 'province' and not row[2] and not row[3]:
                valid_chain = True
                break
            if expected.get(current[0]) != row[2]:
                break
            current = (row[2], row[3])
        if valid_chain and target is not None:
            result[parcel] = target
        if parcel not in result:
            errors[parcel] = 'invalid_or_missing_parent_chain'
    return result, errors


def select_inputs(*, source='all', year=None, parcel_id=None, region_type=None, region_id=None):
    if source not in ('all', 'native', 'ported', 'unknown'):
        raise ValueError('invalid_source')
    if year is not None and (isinstance(year, bool) or not str(year).isdigit() or not 1 <= int(year) <= 9999):
        raise ValueError('invalid_year')
    if bool(region_type) != bool(region_id) or (parcel_id and region_type):
        raise ValueError('invalid_region')
    if region_type:
        if region_type not in ('province', 'city', 'county', 'township'):
            raise ValueError('invalid_region_type')
        valid = session().execute(text('SELECT 1 FROM spatial_region_catalog WHERE object_type=:t AND object_id=:i AND enabled'), {'t': region_type, 'i': region_id}).first()
        if not valid:
            raise ValueError('region_not_found')
    clauses, params = [], {}
    if source != 'all':
        clauses.append('source=:source')
        params['source'] = source
    if year is not None:
        clauses.append('accounting_year=:year')
        params['year'] = int(year)
    if parcel_id:
        clauses.append('parcel_id=:pid')
        params['pid'] = str(parcel_id)
    query = 'SELECT * FROM cd_flux_input_v2' + (' WHERE ' + ' AND '.join(clauses) if clauses else '') + ' ORDER BY id'
    rows = [dict(r) for r in session().execute(text(query), params).mappings()]
    unmapped = 0
    if region_type:
        maps = {s: mapping(s, region_type)[0] for s in {r['source'] for r in rows}}
        unmapped = sum(r['parcel_id'] not in maps[r['source']] for r in rows)
        rows = [r for r in rows if maps[r['source']].get(r['parcel_id']) == str(region_id)]
    return rows, {'unmapped_records': unmapped, 'source': source, 'year': year,
                  'region_type': region_type, 'region_id': region_id, 'parcel_id': parcel_id}


def import_csv(content, *, legacy=False):
    from framework.domain.other_models.cd_flux import CSV_TO_ATTR, REQUIRED_COLUMNS
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    fields = set(reader.fieldnames or ())
    required = set(REQUIRED_COLUMNS) if legacy else {'source', 'accounting_year', 'parcel_id', 'sample_id', *NUMBERS}
    if not required <= fields:
        raise ValueError('missing_columns:' + ','.join(sorted(required - fields)))
    records = []
    for raw in reader:
        if legacy:
            data = {target: raw.get(col) for col, target in CSV_TO_ATTR.items() if target != 'bd020_90'}
            data.update(source='unknown', accounting_year=None)
            provenance = {'unit_status': 'unverified', 'legacy_bulk_density': raw.get('bd020_90')}
        else:
            data = {n: raw.get(n) for n in NUMBERS}
            data.update(source=raw['source'], accounting_year=raw['accounting_year'])
            provenance = {'units': UNITS, 'basis': 'explicit_v2_csv_contract'}
        if data['source'] not in ('native', 'ported', 'unknown'):
            raise ValueError('invalid_source')
        if not legacy:
            year = str(data['accounting_year'])
            if not year.isdigit() or not 1 <= int(year) <= 9999:
                raise ValueError('invalid_year')
            data['accounting_year'] = int(year)
        for n in NUMBERS:
            data[n] = number(data.get(n), n)
        data.update(parcel_id=(raw.get('parcel_id') or '').strip(), sample_id=(raw.get('sample_id') or '').strip(),
                    contract_version='legacy_v1' if legacy else VERSION, provenance=json.dumps(provenance))
        if not data['parcel_id'] or not data['sample_id']:
            raise ValueError('invalid_identity')
        records.append(data)
    keys = [(r['source'], r['parcel_id'], r['sample_id'], r['accounting_year']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate_batch_keys')
    fields = ['source', 'parcel_id', 'sample_id', 'accounting_year', *NUMBERS, 'contract_version', 'provenance']
    values = [f'CAST(:{n} AS jsonb)' if n == 'provenance' else ':' + n for n in fields]
    updates = ','.join(f'{n}=EXCLUDED.{n}' for n in fields if n not in ('source', 'parcel_id', 'sample_id', 'accounting_year'))
    query = f"INSERT INTO cd_flux_input_v2 ({','.join(fields)}) VALUES ({','.join(values)}) ON CONFLICT (source,parcel_id,sample_id,accounting_year) DO UPDATE SET {updates}, input_revision=cd_flux_input_v2.input_revision+1"
    try:
        for record in records:
            session().execute(text(query), record)
        session().commit()
    except Exception:
        session().rollback()
        raise
    return {'imported': len(records), 'contract_version': 'legacy_v1' if legacy else VERSION}


def calculate(**scope):
    rows, coverage = select_inputs(**scope)
    calculated = 0
    try:
        for row in rows:
            if row['contract_version'] == 'legacy_v1':
                continue
            result = trial({n: row[n] for n in NUMBERS}, (row['provenance'] or {}).get('units', {}))
            params = {**{n: result[n] for n in ('in_cd', 'out_cd', 'net_cd', 'end_cd', 'status')},
                      'id': row['id'], 'revision': row['input_revision'], 'version': VERSION,
                      'coverage': json.dumps(result['coverage']), 'units': json.dumps(result['unit_status'])}
            session().execute(text('''INSERT INTO cd_flux_output_v2
                (input_id,input_revision,calculation_version,in_cd,out_cd,net_cd,end_cd,status,coverage,unit_status)
                VALUES (:id,:revision,:version,:in_cd,:out_cd,:net_cd,:end_cd,:status,CAST(:coverage AS jsonb),CAST(:units AS jsonb))
                ON CONFLICT (input_id,input_revision,calculation_version) DO NOTHING'''), params)
            calculated += 1
        session().commit()
    except Exception:
        session().rollback()
        raise
    return {'has_data': bool(rows), 'calculated': calculated, 'coverage': coverage}


def results(*, calculation_version=VERSION, **scope):
    rows, coverage = select_inputs(**scope)
    outputs = {r['input_id']: dict(r) for r in session().execute(text('''SELECT o.* FROM cd_flux_output_v2 o
        JOIN cd_flux_input_v2 i ON i.id=o.input_id AND i.input_revision=o.input_revision
        WHERE o.calculation_version=:v'''), {'v': calculation_version}).mappings()}
    result = [{**r, 'output': outputs.get(r['id'])} for r in rows]
    return {'has_data': bool(result), 'rows': result, 'coverage': coverage, 'calculation_version': calculation_version}


def statistics(field='net_cd', **scope):
    from framework.domain.other_models.cd_flux import FIELDS
    from framework.domain.other_models.heavy_metal_cd_statistics import basic_statistics
    if field not in FIELDS:
        raise ValueError('unknown_field')
    payload = results(**scope)
    groups = {}
    for row in payload.pop('rows'):
        key = (row['source'], row['accounting_year'])
        group = groups.setdefault(key, {'source': key[0], 'year': key[1], 'records': 0, 'parcel_ids': set(), 'values': [],
                                        'unit_status': 'unverified' if calculation_version_is_legacy(scope) else 'explicit_v2_contract',
                                        'incomplete_records': 0})
        group['records'] += 1
        group['parcel_ids'].add(row['parcel_id'])
        value = (row['output'] or {}).get(field)
        if not row['output'] or row['output']['status'] in ('partial', 'legacy'):
            group['incomplete_records'] += 1
        if value is not None:
            group['values'].append(value)
    summaries = []
    for group in groups.values():
        values = group.pop('values')
        group['parcel_count'] = len(group.pop('parcel_ids'))
        group.update(valid_records=len(values), statistics=basic_statistics(values) if values else {},
                     distribution=distribution(field, values), parcel_ids_scope='covered_only')
        summaries.append(group)
    return {**payload, 'has_data':any(g['valid_records'] for g in summaries),
            'field': field, 'unit': FIELDS[field]['unit'], 'groups': summaries,
            'statistics_method': 'record_arithmetic', 'regional_total_supported': False}


def calculation_version_is_legacy(scope):
    return scope.get('calculation_version') == 'legacy_v1'


def distribution(field, values):
    if not values:
        return {'count': 0, 'buckets': []}
    if field == 'net_cd':
        boundaries = (-5,5)
        indices = [0 if v < -5 else 1 if v <= 5 else 2 for v in values]
        labels = ['<-5','[-5,5]','>5']
    else:
        if field == 'end_cd':
            boundaries = (.3,.6)
        else:
            mean = sum(values) / len(values)
            boundaries = (.5 * mean,1.5 * mean)
        indices = [0 if v < boundaries[0] else 1 if v < boundaries[1] else 2 for v in values]
        labels = [f'<{boundaries[0]}',f'[{boundaries[0]},{boundaries[1]})',f'>={boundaries[1]}']
    return {'count': len(values), 'boundaries': boundaries, 'display_only': True,
            'relative': field in ('in_cd','out_cd'),
            'buckets': [{'range': label,'count': indices.count(i),'percent':100*indices.count(i)/len(values)} for i,label in enumerate(labels)]}


def compare(years, **scope):
    if not isinstance(years, list) or not years or len(years) > 20:
        raise ValueError('invalid_years')
    return {'years': [statistics(year=y, **scope) for y in years],
            'warning': '各年度覆盖可能不同，均值差异不代表同批地块变化'}
