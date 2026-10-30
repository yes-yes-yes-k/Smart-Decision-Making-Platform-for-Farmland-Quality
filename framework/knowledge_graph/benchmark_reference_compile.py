"""Canonical reference facts retain all independently supported evidence."""
import copy
import json
from .benchmark_protocol import validate_proposal


def compile_reference(packet,validated,schema):
    result=copy.deepcopy(validated)
    proposal=result['materialized_proposal'];facts={};groups=[]
    for index,relation in enumerate(proposal['relations']):
        key=(relation['type'],relation['source_id'],relation['target_id'],relation['modality'],
             json.dumps(relation.get('conditions',[]),ensure_ascii=False,sort_keys=True))
        if key not in facts:
            facts[key]=copy.deepcopy(relation);groups.append(dict(validated_relation_indices=[index],key=key))
        else:
            n=list(facts).index(key);groups[n]['validated_relation_indices'].append(index)
            present={json.dumps(e,sort_keys=True,ensure_ascii=False) for e in facts[key]['evidence']}
            for e in relation['evidence']:
                if json.dumps(e,sort_keys=True,ensure_ascii=False) not in present:
                    facts[key]['evidence'].append(copy.deepcopy(e));present.add(json.dumps(e,sort_keys=True,ensure_ascii=False))
    proposal['relations']=list(facts.values())
    check=validate_proposal(packet,proposal,schema)
    other_errors=[e for e in validated.get('errors',[]) if e.get('error')!='duplicate_relation']
    result.update(protocol_complete=check['protocol_complete'] and not other_errors,
        errors=other_errors+check['errors'],reference_ready=check['protocol_complete'] and not other_errors and not result.get('unresolved'),
        canonical_fact_groups=groups,normalization='identical_facts_merge_evidence_only',
        original_model_decisions_changed=False)
    return result
