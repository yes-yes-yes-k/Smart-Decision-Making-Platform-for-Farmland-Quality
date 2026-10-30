"""Recover only fully emitted source-bound objects, never complete missing JSON."""
import json
import re
from .benchmark_cells import materialize


def complete_array_objects(content,key):
    match=re.search(r'"'+re.escape(key)+r'"\s*:\s*\[',content)
    if not match:return [],False
    cursor=match.end();decoder=json.JSONDecoder();objects=[]
    while True:
        while cursor<len(content) and content[cursor].isspace():cursor+=1
        if cursor>=len(content):return objects,False
        if content[cursor]==']':return objects,True
        if objects:
            if content[cursor]!=',':return objects,False
            cursor+=1
            while cursor<len(content) and content[cursor].isspace():cursor+=1
        try:value,end=decoder.raw_decode(content,cursor)
        except ValueError:return objects,False
        if not isinstance(value,dict):return objects,False
        objects.append(value);cursor=end


def partial_annotation(record,packet):
    if isinstance(record.get('proposal'),dict):
        return record['proposal'],dict(original_state=record['state'],complete_json=True,original_protocol_accepted=record['state']=='protocol_valid')
    content=record.get('content','');decisions,decisions_complete=complete_array_objects(content,'decisions')
    valid=[];ids=set();errors=[]
    for i,d in enumerate(decisions):
        try:
            if d['id'] in ids or d['type'] not in ['indicator','obstacle','measure','standard'] or d['decision'] not in ['include','exclude','uncertain']:
                raise ValueError('invalid_completed_decision')
            materialize(dict(fragment=d['fragment']),packet);valid.append(d);ids.add(d['id'])
        except (ValueError,KeyError,TypeError) as exc:errors.append(dict(index=i,error=str(exc)))
    relations,relations_complete=complete_array_objects(content,'relations');kept=[]
    for i,r in enumerate(relations):
        try:
            if r['source_id'] not in ids or r['target_id'] not in ids:raise ValueError('unavailable_endpoint')
            materialize(r,packet);kept.append(r)
        except (ValueError,KeyError,TypeError) as exc:errors.append(dict(relation=i,error=str(exc)))
    normalization,norm_complete=complete_array_objects(content,'normalization')
    return dict(decisions=valid,relations=kept,normalization=normalization),dict(
        original_state=record['state'],complete_json=False,original_protocol_accepted=False,
        decisions_array_complete=decisions_complete,relations_array_complete=relations_complete,
        normalization_array_complete=norm_complete,complete_emitted_decisions=len(valid),complete_emitted_relations=len(kept),
        missing_items_not_assumed_negative=True,missing_json_not_fabricated=True,errors=errors)
