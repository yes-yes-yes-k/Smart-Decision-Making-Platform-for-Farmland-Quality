"""Offline availability check: would exact model quotes be locatable without model offsets?"""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.prepare_kg_quoted_selection_pilot import BASE
from scripts.rebuild_kg_extraction_benchmark import dump


def inspect(value,blocks,path='$'):
    rows=[]
    if isinstance(value,list):
        for i,item in enumerate(value):rows.extend(inspect(item,blocks,f'{path}[{i}]'))
    elif isinstance(value,dict):
        if {'block_id','quote'}.issubset(value):
            block=value.get('block_id');quote=value.get('quote')
            positions=[]
            if block in blocks and isinstance(quote,str) and quote:
                cursor=0
                while True:
                    pos=blocks[block].find(quote,cursor)
                    if pos<0:break
                    positions.append(pos);cursor=pos+len(quote)
            rows.append(dict(path=path,block_id=block,quote=quote,exact_occurrences=len(positions),
                can_bind_without_model_offsets=len(positions)==1,positions=positions if len(positions)<4 else []))
        else:
            for k,v in value.items():rows.extend(inspect(v,blocks,f'{path}.{k}'))
    return rows


def main():
    base=BASE;source=json.loads((base/'source-packets.json').read_text(encoding='utf-8'));packets={p['sample_id']:p for p in source['cases']}
    details=[];counts=Counter()
    for stage in ['initial','review']:
        for file in (base/stage/'proposals').glob('*.json'):
            record=json.loads(file.read_text(encoding='utf-8'));sid=record['id'].split(':',1)[-1]
            packet=packets[sid];blocks={b['block_id']:b['text'] for b in packet['blocks']}
            try:raw=json.loads(record.get('content') or '')
            except (ValueError,TypeError):raw=None
            rows=inspect(raw,blocks) if raw is not None else []
            states=Counter('unique' if x['exact_occurrences']==1 else 'repeated' if x['exact_occurrences']>1 else 'not_found' for x in rows)
            counts.update({stage+':'+k:v for k,v in states.items()})
            details.append(dict(stage=stage,job_id=record['id'],original_state=record['state'],
                original_errors=record.get('error'),span_count=len(rows),span_statuses=dict(states),spans=rows,
                counterfactual_only=True,original_result_unchanged=True))
    report=dict(status='inconclusive',pilot='quoted_selection_v1',responses_audited=len(details),
        raw_span_locations=dict(counts),
        quote_only_structural_availability='diagnostic only; unique exact quotes can be program-located without asking the model for offsets',
        repeated_quotes_require_occurrence_or_review=True,not_semantic_validation=True,
        not_permission_to_reclassify_old_responses_as_success=True,old_responses_unchanged=True,
        next_protocol_candidate='verbatim_quote_v2; model returns exact source substring and only an occurrence ordinal when exact substring repeats')
    dump(base/'quote-only-counterfactual.json',dict(report=report,items=details));print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
