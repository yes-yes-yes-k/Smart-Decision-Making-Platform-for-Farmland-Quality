"""Reference release checks enforce frozen evidence rules without deleting facts."""
from .benchmark_protocol import literal_span


def check_reference(reference):
    blocks={b['block_id']:b['text'] for b in reference['visible_input']['blocks']}
    errors=[]
    for i,e in enumerate(reference['reference']['entities']):
        try:literal_span(e,blocks)
        except (ValueError,KeyError,TypeError) as exc:errors.append(dict(item='entity',index=i,error=str(exc)))
    for i,r in enumerate(reference['reference']['relations']):
        for evidence in r['evidence']:
            try:literal_span(evidence,blocks)
            except (ValueError,KeyError,TypeError) as exc:errors.append(dict(item='relation',index=i,error=str(exc)))
            if evidence.get('role')=='assertion' and evidence['block_id']!='chunk':
                errors.append(dict(item='relation',index=i,error='title_cannot_assert_relation'))
        if not any(e.get('role')=='assertion' and e['block_id']=='chunk' for e in r['evidence']):
            errors.append(dict(item='relation',index=i,error='relation_requires_body_assertion'))
    return dict(reference_ready=not errors,errors=errors,labels_modified=False,
        mask_expansion=False,scope='necessary_source_evidence_checks_not_expert_certification')
