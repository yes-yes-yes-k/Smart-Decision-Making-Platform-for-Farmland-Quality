"""Document-group sampling with explicit metadata strata and retained hard cases."""
from collections import defaultdict,Counter
import hashlib
import random
import re


def rank(seed,value):return hashlib.sha256((seed+':'+str(value)).encode()).hexdigest()


def select_groups(documents,count,seed):
    strata=defaultdict(list)
    for d in documents:
        key=(d['profile']['source_kind'],d['profile']['language'],d['profile']['body_profile'],tuple(d['topic_source_folders']))
        strata[key].append(d['isolation_group'])
    count=min(count,len(documents))
    if count<len(strata):raise ValueError('insufficient_slots_to_cover_declared_metadata_strata')
    quota={k:1 for k in strata};remaining=count-len(strata)
    capacity=sum(len(v)-1 for v in strata.values())
    if capacity:
        for k,v in strata.items():quota[k]+=remaining*(len(v)-1)//capacity
        residual=count-sum(quota.values())
        order=sorted(strata,key=lambda k:(-(remaining*(len(strata[k])-1)%capacity),k))
        for k in order:
            if residual and quota[k]<len(strata[k]):quota[k]+=1;residual-=1
    result=[]
    for k in sorted(strata):
        ids=sorted(strata[k],key=lambda i:rank(seed+':group',i))
        result.extend(dict(group=i,stratum=list(k[:3])+[list(k[3])],probability=quota[k]/len(ids)) for i in ids[:quota[k]])
    return sorted(result,key=lambda r:rank(seed+':partition',r['group']))


def sample(documents,chunks,seed):
    bygroup=defaultdict(list)
    for d in documents:bygroup[d['isolation_group']].append(d)
    # Duplicate copies do not earn extra slots; canonical document is ID based.
    canonical={g:min(ds,key=lambda d:d['document_id']) for g,ds in bygroup.items()}
    bydoc=defaultdict(list)
    for c in chunks:bydoc[c['document_id']].append(c)
    selected=select_groups(list(canonical.values()),100,seed+':representative')
    rows=[]
    for index,item in enumerate(selected):
        part='calibration' if index<20 else 'test';d=canonical[item['group']]
        buckets=defaultdict(list)
        for c in bydoc[d['document_id']]:buckets[c['position_quartile']].append(c)
        for q in buckets:buckets[q].sort(key=lambda c:rank(seed+':representative-chunk',c['sample_id']))
        omitted=(index+(1 if part=='calibration' else 2))%4
        order=[q for q in range(4) if q!=omitted]+[omitted];chosen=[]
        while len(chosen)<3 and any(buckets.values()):
            for q in order:
                if buckets[q] and len(chosen)<3:chosen.append(buckets[q].pop(0))
        for c in chosen:
            probability=item['probability'];cal_groups=min(20,len(selected))
            part_probability=(cal_groups if part=='calibration' else len(selected)-cal_groups)/len(selected)
            rows.append(dict(c,isolation_group=item['group'],track='representative',partition=part,
                stratum=item['stratum'],group_inclusion_probability=probability,group_design_weight=1/probability,
                group_partition_inclusion_probability=probability*part_probability,
                weight_scope='document_group_not_chunk_population',selection_rule='rotating_quartile_no_quality_filter'))
    used={r['group'] for r in selected}
    remaining=[d for g,d in canonical.items() if g not in used]
    challenge=select_groups(remaining,100,seed+':challenge')
    positive=re.compile(r'缓解|改善|修复|治理|降低|提高|规定|测定|适用|improv|remedi|amelior|reduc|increas|prescrib|determin',re.I)
    negative=re.compile(r'未|不能|无显著|不适用|并非|试剂|仪器|参考文献|not\b|no\b|insignificant|reagent|instrument|references',re.I)
    for index,item in enumerate(challenge):
        part='calibration' if index<20 else 'test';d=canonical[item['group']]
        available=list(bydoc[d['document_id']]);chosen=[]
        for rule,pattern in [('relation_lexical_candidate',positive),('difficult_negative_or_random_control',negative)]:
            if not available:break
            ordered=sorted(available,key=lambda c:(-len(pattern.findall(c['text'])),rank(seed+':'+rule,c['sample_id'])))
            c=ordered[0];available.remove(c);chosen.append(c)
            rows.append(dict(c,isolation_group=item['group'],track='challenge',partition=part,stratum=item['stratum'],
                group_inclusion_probability_conditional_on_remaining_pool=item['probability'],
                weight_scope='challenge_only_no_overall_quality_weight',selection_rule=rule,
                lexical_hint_present=bool(pattern.search(c['text'])),candidate_backend_predictions_used=False))
    counts=Counter((r['track'],r['partition']) for r in rows)
    return rows,dict(seed=seed,selected_groups=len(selected)+len(challenge),
        counts={t+':'+p:counts[t,p] for t in ['representative','challenge'] for p in ['calibration','test']},
        targets={'representative:calibration':60,'representative:test':240,'challenge:calibration':40,'challenge:test':160},
        short_documents_retained=True,quality_filter=False,reference_labels_not_used=True,
        challenge_relation_coverage_not_yet_verified=True,
        quartiles={p:dict(Counter(str(r['position_quartile']) for r in rows if r['track']=='representative' and r['partition']==p)) for p in ['calibration','test']})
