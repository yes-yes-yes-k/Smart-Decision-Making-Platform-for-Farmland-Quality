"""Canonicalize literal duplicate entities, preserving conditions and evidence."""
import copy
import json
from .benchmark_protocol import validate_proposal


def compile_reference_v2(packet,validated,schema):
    result=copy.deepcopy(validated);p=result['materialized_proposal'];seen={};mapping={};entities=[]
    for e in p['entities']:
        key=(e['type'],e['block_id'],e['start'],e['end'],e['text'])
        if key not in seen:seen[key]=e['id'];entities.append(e)
        mapping[e['id']]=seen[key]
    p['entities']=entities
    def remap(value):
        if isinstance(value,list):return [remap(v) for v in value]
        if isinstance(value,dict):return {k:(mapping.get(v,v) if k in ['source_id','target_id','entity_id'] and isinstance(v,str) else remap(v)) for k,v in value.items()}
        return value
    p['relations']=remap(p['relations']);p['normalization']=remap(p['normalization'])
    facts={}
    for r in p['relations']:
        key=(r['type'],r['source_id'],r['target_id'],r['modality'],json.dumps(r.get('conditions',[]),sort_keys=True,ensure_ascii=False))
        if key not in facts:facts[key]=r
        else:
            known={json.dumps(e,sort_keys=True,ensure_ascii=False) for e in facts[key]['evidence']}
            for e in r['evidence']:
                k=json.dumps(e,sort_keys=True,ensure_ascii=False)
                if k not in known:facts[key]['evidence'].append(e);known.add(k)
    p['relations']=list(facts.values())
    checked=validate_proposal(packet,p,schema)
    # Legacy duplicate detection omits conditions. All evidence, types, spans,
    # modalities and endpoint checks still run before that legacy check.
    new_errors=[e for e in checked['errors'] if e['error']!='duplicate_relation']
    old_errors=[e for e in validated.get('errors',[]) if e['error'] not in ['duplicate_relation','duplicate_entity_span']]
    result.update(materialized_proposal=p,errors=old_errors+new_errors,
        protocol_complete=not old_errors and not new_errors,
        reference_ready=not old_errors and not new_errors and not result.get('unresolved'),
        raw_entity_to_canonical=mapping,conditions_preserved=True,semantic_facts_modified=False,
        canonicalization_version='literal_entities_and_condition_aware_facts_v2')
    return result
