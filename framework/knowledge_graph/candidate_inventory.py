"""Source-bound candidate retention, with a document-isolated learned vocabulary."""
import re
from .candidate_selection import candidates as seed_candidates


def literal_matches(name,text):
    pattern=r'\s+'.join(re.escape(p) for p in name.split())
    if not pattern:return []
    hits=[]
    for m in re.finditer(pattern,text,re.IGNORECASE):
        if any(x in m.group() for x in ('\n','\r','##','<|>')):continue
        if m.group()[0].isascii() and m.group()[0].isalnum() and m.start() and text[m.start()-1].isascii() and text[m.start()-1].isalnum():continue
        if m.group()[-1].isascii() and m.group()[-1].isalnum() and m.end()<len(text) and text[m.end()].isascii() and text[m.end()].isalnum():continue
        hits.append(m)
    return hits


def build_vocabulary(training_rows,excluded_groups):
    terms={}
    for row in training_rows:
        group=row['source']['leakage_group']
        if row['source']['split']!='development' or group in excluded_groups:
            raise ValueError('training_document_leakage')
        if not row['evaluation_eligible']:continue
        for e in row['entities']:
            if not literal_matches(e['name'],row['source']['text']):continue
            key=(e['type'],e['name'].casefold())
            item=terms.setdefault(key,dict(name=e['name'],type=e['type'],training_groups=set(),training_samples=set()))
            item['training_groups'].add(group);item['training_samples'].add(row['sample_id'])
    return [dict(name=v['name'],type=v['type'],training_groups=sorted(v['training_groups']),
        training_samples=sorted(v['training_samples']),document_support=len(v['training_groups'])) for _,v in sorted(terms.items())]


def inventory(text,vocabulary):
    indexed={}
    def add(name,kind,lo,hi,origin,support):
        key=(lo,hi,kind)
        row=indexed.setdefault(key,dict(name=name,type=kind,span_start=lo,span_end=hi,
            origins=[],document_support=0,review_status='retained',confirmed_entity=False))
        if origin not in row['origins']:row['origins'].append(origin)
        row['document_support']=max(support,row['document_support'])
    for row in seed_candidates(text):add(row['name'],row['type'],row['span_start'],row['span_end'],'seed_patterns',0)
    for term in vocabulary:
        for m in literal_matches(term['name'],text):
            add(m.group(),term['type'],m.start(),m.end(),'training_vocabulary',term['document_support'])
    rows=sorted(indexed.values(),key=lambda r:(r['span_start'],r['span_end'],r['type']))
    for i,row in enumerate(rows):
        row['id']=i
        if len({r['type'] for r in rows if r['name'].casefold()==row['name'].casefold()})>1:
            row['review_status']='needs_review'
    return rows


def apply_review(rows,decisions):
    """Keep every source candidate; missing decisions remain pending, never disappear."""
    by_id={r['id']:r for r in rows};seen=set();result=[dict(r) for r in rows]
    for decision in decisions:
        cid=decision['id']
        if type(cid) is not int or cid not in by_id or cid in seen:raise ValueError('invalid_candidate_id')
        if decision['status'] not in ('retained','needs_review') or not isinstance(decision.get('reason'),str) or not decision['reason'].strip():
            raise ValueError('invalid_review_decision')
        seen.add(cid)
        result[cid].update(review_status=decision['status'],review_reason=decision['reason'])
    for row in result:
        if row['id'] not in seen:row.update(review_status='needs_review',review_reason='no explicit review decision; candidate preserved')
    return result
