"""r3 calibration guards; historical v4.0/r2 validators remain unchanged."""
import copy
from .evaluation_v4 import validate_annotation,validate_input,mention_key


def align_fragment(fragment,blocks):
    """Recover original whitespace only; never fix letters, OCR, case or punctuation."""
    if set(fragment)!={'block_id','text','occurrence'}:raise ValueError('invalid_fragment_fields')
    bid,quote,occ=fragment['block_id'],fragment['text'],fragment['occurrence']
    if bid not in blocks or not isinstance(quote,str) or not quote.strip() or type(occ) is not int or occ<0:raise ValueError('invalid_fragment')
    source=blocks[bid]['text']
    compact='';offsets=[]
    for i,c in enumerate(source):
        if not c.isspace():compact+=c;offsets.append(i)
    target=''.join(c for c in quote if not c.isspace())
    if not target:raise ValueError('invalid_fragment')
    start=-1
    for _ in range(occ+1):
        start=compact.find(target,start+1)
        if start<0:raise ValueError('fragment_not_in_visible_input')
    lo,hi=offsets[start],offsets[start+len(target)-1]+1
    original=source[lo:hi]
    # Determine the occurrence index of the actual original slice for the legacy binder.
    index=-1;count=-1
    while index<lo:
        index=source.find(original,index+1);count+=1
        if index<0:raise ValueError('fragment_not_in_visible_input')
    return dict(block_id=bid,text=original,occurrence=count),dict(block_id=bid,requested_text=quote,resolved_text=original,
        span_start=lo,span_end=hi,method='exact' if original==quote else 'whitespace_only_alignment')


def validate_r3(visible,answer):
    blocks=validate_input(visible);clean=copy.deepcopy(answer);audit=[]
    for i,m in enumerate(clean.get('mentions',[])):
        m['fragment'],entry=align_fragment(m['fragment'],blocks);audit.append(dict(path=f'mentions/{i}',**entry))
    for i,r in enumerate(clean.get('relations',[])):
        for j,e in enumerate(r['evidence']):
            r['evidence'][j],entry=align_fragment(e,blocks);audit.append(dict(path=f'relations/{i}/evidence/{j}',**entry))
    annotation=validate_annotation(visible,clean)
    q=annotation['quality']
    if q['grade']=='A' and (not q['entity_eligible'] or not q['relation_eligible']):raise ValueError('grade_A_tasks_must_be_evaluable_even_if_empty')
    by_id={m['id']:m for m in annotation['mentions']};seen=set()
    for m in annotation['mentions']:
        text=m['fragment']['text']
        if m['type']=='indicator' and text in ('土壤肥沃','肥沃'):raise ValueError('generic_description_not_measurable_indicator')
        if m['type']=='measure' and text in ('沸水提取','分光光度法','PCR'):raise ValueError('laboratory_method_not_field_intervention')
    for r in annotation['relations']:
        key=(mention_key(by_id[r['source']]),r['relation_type'],mention_key(by_id[r['target']]),r['modality'])
        if key in seen:raise ValueError('duplicate_fact_merge_evidence_instead')
        seen.add(key)
        if r['modality'] in ('asserted','normative'):
            if not q['relation_eligible']:raise ValueError('positive_fact_conflicts_with_relation_ineligibility')
            if not any(e['block_id']=='chunk' for e in r['evidence']):raise ValueError('title_alone_cannot_establish_positive_relation')
    annotation.update(contract_revision='v4-r3',binding_audit=audit)
    return annotation
