"""Source-bound proposal union, without votes, free-form reasons or old labels."""
import json


def union_proposals(proposals):
    decisions=[];relations=[];normalization=[];seen={};maps=[];relation_seen=set();norm_seen=set()
    for proposal in proposals:
        mapping={}
        for d in proposal.get('decisions',[]):
            key=(d['type'],json.dumps(d['fragment'],sort_keys=True,ensure_ascii=False))
            if key not in seen:
                eid='u'+str(len(decisions));seen[key]=eid
                decisions.append(dict(id=eid,type=d['type'],fragment=d['fragment']))
            mapping[d['id']]=seen[key]
        maps.append(mapping)
    for proposal,mapping in zip(proposals,maps):
        for raw in proposal.get('relations',[]):
            r=dict(raw,source_id=mapping[raw['source_id']],target_id=mapping[raw['target_id']])
            key=json.dumps(r,sort_keys=True,ensure_ascii=False)
            if key not in relation_seen:relations.append(r);relation_seen.add(key)
        for raw in proposal.get('normalization',[]):
            n=dict(raw,source_id=mapping[raw['source_id']],target_id=mapping[raw['target_id']])
            key=json.dumps(n,sort_keys=True,ensure_ascii=False)
            if key not in norm_seen:normalization.append(n);norm_seen.add(key)
    return dict(decisions=decisions,relations=relations,normalization=normalization)
