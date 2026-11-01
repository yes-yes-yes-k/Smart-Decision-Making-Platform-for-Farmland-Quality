"""Read-only inspection diagnostics. Flags never change labels or scoring masks."""
import json,re
from collections import Counter
from .evaluation_v4 import validate_input
from .evaluation_v4_r3 import align_fragment

def source_flags(text):
    flags=[]
    if '(cid:' in text:flags.append('unmapped_pdf_glyph')
    if '\ufffd' in text:flags.append('replacement_character')
    if len(''.join(text.split()))<80:flags.append('short_visible_text')
    if re.search(r'\b[A-Za-z]{35,}\b',text):flags.append('long_concatenated_english_token')
    if re.search(r'参考文献|\breferences\b|\bbibliography\b',text,re.I):flags.append('reference_marker')
    if re.search(r'copyright|Creative\s+Commons|All rights reserved|Downloaded\s+from|©',text,re.I):flags.append('publication_boilerplate_marker')
    if '| ---' in text or text.count('|')>=10:flags.append('table_layout')
    return flags

def inspect_entity_fragments(visible,raw):
    blocks=validate_input(visible);items=[];seen=set()
    for i,m in enumerate(raw.get('mentions',[])):
        entry=dict(index=i,type=m.get('type'),requested=m.get('fragment'))
        try:
            f,a=align_fragment(m['fragment'],blocks);key=(f['block_id'],a['span_start'],a['span_end'],m['type'])
            entry.update(bound=True,resolved_text=f['text'],span_start=a['span_start'],span_end=a['span_end'],method=a['method'],duplicate=key in seen)
            seen.add(key)
        except (ValueError,KeyError,TypeError) as exc:
            entry.update(bound=False,error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
            fragment=m.get('fragment',{})
            if isinstance(fragment,dict) and fragment.get('occurrence',0)!=0:
                try:
                    _,a=align_fragment(dict(fragment,occurrence=0),blocks)
                    entry['first_occurrence_is_bindable']=True
                except (ValueError,TypeError,KeyError):pass
        items.append(entry)
    return items

def inspect_relabel(visible,result):
    inspections=[];malformed=[];truncated=[]
    for trace in result.get('trace',[]):
        if trace.get('finish_reason')!='stop':truncated.append(dict(stage=trace['stage'],finish_reason=trace.get('finish_reason')))
        if trace['stage']=='entities':
            try:raw=json.loads(trace['content']);inspections=inspect_entity_fragments(visible,raw)
            except (ValueError,KeyError,TypeError):malformed.append('entities_json_not_parseable')
    return dict(index=result['index'],sample_id=result['sample_id'],state=result['state'],errors=result.get('errors',{}),
        entity_fragment_count=len(inspections),literal_bindable_count=sum(i['bound'] for i in inspections),
        unbound_fragment_count=sum(not i['bound'] for i in inspections),duplicate_fragment_count=sum(i.get('duplicate',False) for i in inspections),
        fragment_inspections=inspections,truncated_stages=truncated,malformed=malformed,
        diagnostic_only=True,semantic_validity_not_inferred_from_binding=True)
