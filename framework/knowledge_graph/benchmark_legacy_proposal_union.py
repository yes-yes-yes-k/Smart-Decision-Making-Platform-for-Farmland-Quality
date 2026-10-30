"""Full-ID candidate union preserving older normalization proposal schemas."""
import copy
import json
from .benchmark_proposal_union import union_proposals


def union_legacy_proposals(proposals):
    stripped=[dict(p,normalization=[]) for p in proposals]
    result=union_proposals(stripped)
    keys={(d['type'],json.dumps(d['fragment'],sort_keys=True,ensure_ascii=False)):d['id'] for d in result['decisions']}
    seen=set()
    for proposal in proposals:
        mapping={d['id']:keys[d['type'],json.dumps(d['fragment'],sort_keys=True,ensure_ascii=False)] for d in proposal['decisions']}
        def remap(value):
            if isinstance(value,dict):
                return {k:(mapping[v] if k in {'entity_id','source_id','target_id'} and isinstance(v,str) and v in mapping else remap(v)) for k,v in value.items()}
            if isinstance(value,list):return [remap(v) for v in value]
            return value
        for item in proposal.get('normalization',[]):
            normalized=remap(copy.deepcopy(item))
            key=json.dumps(normalized,sort_keys=True,ensure_ascii=False)
            if key not in seen:result['normalization'].append(normalized);seen.add(key)
    return result
