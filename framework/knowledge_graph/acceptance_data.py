"""Pure isolation, deterministic sampling and answerability validation primitives."""
from collections import defaultdict
import hashlib
import re

def digest(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def normalized(s):return ''.join(c.casefold() for c in (s or '') if c.isalnum())
def standard_family(s):return re.sub(r'[-—–]?\s*(?:19|20)\d{2}$','',normalized(s))

class Groups:
    def __init__(self,ids):self.parent={i:i for i in ids}
    def find(self,x):
        while self.parent[x]!=x:self.parent[x]=self.parent[self.parent[x]];x=self.parent[x]
        return x
    def union(self,a,b):
        a,b=self.find(a),self.find(b);self.parent[max(a,b)]=min(a,b)

def identity_groups(documents):
    g=Groups([d['id'] for d in documents]);seen={}
    for d in documents:
        identities=[('file',d.get('file_sha256')),('doi',(d.get('doi') or '').casefold()),('standard',standard_family(d.get('standard_number')))]
        title=normalized(d.get('title'))
        if len(title)>12:identities.append(('title',title))
        for kind,value in identities:
            if not value:continue
            if (kind,value) in seen:g.union(d['id'],seen[kind,value])
            else:seen[kind,value]=d['id']
    return g

def assert_isolation(rows):
    groups={};samples=set()
    for r in rows:
        if r['sample_id'] in samples:raise ValueError('duplicate_sample')
        samples.add(r['sample_id']);key=r['isolation_group'];partition=(r['track'],r['partition'])
        if key in groups and groups[key]!=partition:raise ValueError('document_group_crosses_track_or_partition')
        groups[key]=partition

def deterministic_selection(documents,chunks,seed):
    # Three representative chunks per group imply >=100 groups for 300 samples.
    bygroup=defaultdict(list);bydoc={d['id']:d for d in documents}
    for c in chunks:bygroup[c['isolation_group']].append(c)
    strata=defaultdict(list)
    for group,cs in bygroup.items():
        d=bydoc[cs[0]['document_id']]
        strata[d['kind'],d.get('language') or 'unknown',d.get('parse_quality') or 'unknown'].append(group)
    for key in strata:strata[key].sort(key=lambda g:digest(seed+':group:'+str(g)))
    ordered=[]
    while any(strata.values()):
        for key in sorted(strata):
            if strata[key]:ordered.append(strata[key].pop(0))
    representative=[];used=set();group_no=0
    for group in ordered:
        cs=sorted(bygroup[group],key=lambda c:(c['position_quartile'],digest(seed+':chunk:'+c['sample_id'])))
        # Round robin position buckets; never filter short/OCR content out.
        buckets=defaultdict(list)
        for c in cs:buckets[c['position_quartile']].append(c)
        chosen=[]
        while len(chosen)<3 and any(buckets.values()):
            for k in sorted(buckets):
                if buckets[k] and len(chosen)<3:chosen.append(buckets[k].pop(0))
        if len(chosen)<3:continue  # recorded eligibility constraint, not a quality replacement
        partition='calibration' if group_no%5==0 else 'test';group_no+=1;used.add(group)
        representative.extend(dict(c,track='representative',partition=partition) for c in chosen)
        if len(representative)==300:break
    patterns=re.compile(r'改善|提高|降低|治理|修复|测定|评价指标|规定|improv|remedi|increas|decreas|soil.*measur',re.I)
    candidates=[]
    for group in ordered:
        if group in used:continue
        cs=[c for c in bygroup[group] if patterns.search(c['text'])]
        cs.sort(key=lambda c:digest(seed+':challenge:'+c['sample_id']))
        candidates.extend((group,c) for c in cs[:5])
    challenge=[];assignment={};cal=test=0
    for group,c in candidates:
        if group not in assignment:assignment[group]='calibration' if len(assignment)%5==0 else 'test'
        partition=assignment[group]
        if (partition=='calibration' and cal>=40) or (partition=='test' and test>=160):continue
        challenge.append(dict(c,track='challenge',partition=partition));cal+=partition=='calibration';test+=partition=='test'
        if len(challenge)==200:break
    rows=representative+challenge;assert_isolation(rows)
    return rows

def validate_qa(item,blocks,partition_groups):
    if item['answerability'] not in ('answerable','insufficient','false_premise','beyond_evidence'):raise ValueError('invalid_answerability')
    if not item.get('question') or not item.get('rationale'):raise ValueError('missing_qa_reason')
    evidence=item['evidence'];part=item['partition']
    groups=set()
    for ev in evidence:
        b=blocks[ev['sample_id']];groups.add(b['isolation_group'])
        if b['partition']!=part:raise ValueError('qa_cross_partition')
        if not ev['text'] or b['text'][ev['span_start']:ev['span_end']]!=ev['text']:raise ValueError('qa_unbound_evidence')
    if not groups or any(partition_groups[g]!=part for g in groups):raise ValueError('qa_missing_source_scope')
    if item['answerability']=='answerable' and not item.get('answer_points'):raise ValueError('answerable_without_points')
    if item.get('multihop') and len({e['sample_id'] for e in evidence})<2:raise ValueError('multihop_needs_two_blocks')
    if item['answerability']!='answerable' and not item.get('missing_or_invalid_premise'):raise ValueError('abstention_needs_reason')
    return dict(item,isolation_groups=sorted(groups))
