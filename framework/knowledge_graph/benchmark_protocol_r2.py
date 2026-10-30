"""Explicit inclusion decisions with deterministic exact-literal coordinates.

No OCR repair, whitespace folding, boundary trimming, or alias substitution.
Only include decisions become entity proposals; other decisions stay auditable.
"""
import copy
from .benchmark_protocol import validate_proposal


def locate(fragment,blocks):
    text=blocks[fragment['block_id']]
    quote=fragment['text'];occ=fragment['occurrence']
    if not isinstance(quote,str) or not quote or type(occ) is not int or occ<0:
        raise ValueError('invalid_literal_fragment')
    start=-len(quote)
    for _ in range(occ+1):
        start=text.find(quote,start+len(quote))
        if start<0:
            raise ValueError('fragment_occurrence_not_in_source')
    return dict(block_id=fragment['block_id'],text=quote,occurrence=occ,
                start=start,end=start+len(quote))


def ground(packet,raw,schema):
    blocks={b['block_id']:b['text'] for b in packet['blocks']}
    decisions=raw.get('decisions')
    if not isinstance(decisions,list):
        raise ValueError('explicit_decisions_list_required')
    proposal=dict(entities=[],relations=[],normalization=copy.deepcopy(raw.get('normalization',[])),
        task_masks=copy.deepcopy(raw.get('task_masks',{})),notes=copy.deepcopy(raw.get('notes',[])))
    records=[];errors=[];seen_ids=set()
    for index,d in enumerate(decisions):
        try:
            if not isinstance(d.get('id'),str) or not d['id'] or d['id'] in seen_ids:
                raise ValueError('missing_or_duplicate_decision_id')
            seen_ids.add(d['id'])
            if d['decision'] not in {'include','exclude','uncertain'}:
                raise ValueError('invalid_inclusion_decision')
            if not isinstance(d.get('reason'),str) or not d['reason'].strip():
                raise ValueError('decision_reason_required')
            fragment=locate(d['fragment'],blocks)
            records.append(dict(d,resolved_fragment=fragment))
            if d['decision']=='include':
                proposal['entities'].append(dict(id=d['id'],type=d['type'],**fragment))
        except (ValueError,KeyError,TypeError) as exc:
            errors.append(dict(task='decision',index=index,error=str(exc)))
    relations=raw.get('relations')
    if not isinstance(relations,list):
        errors.append(dict(task='relations',error='relations_list_required'))
    else:
        for index,r in enumerate(relations):
            try:
                relation=copy.deepcopy(r)
                relation['evidence']=[dict(**locate(f,blocks),role=f['role']) for f in r['evidence']]
                proposal['relations'].append(relation)
            except (ValueError,KeyError,TypeError) as exc:
                errors.append(dict(task='relation',index=index,error=str(exc)))
    check=validate_proposal(packet,proposal,schema)
    check['errors']=errors+check['errors']
    check['protocol_complete']=not check['errors']
    return dict(proposal=proposal,decisions=records,protocol=check,
        coordinates='program_exact_literal_nonoverlapping_occurrence',
        semantic_support_not_certified=True)
