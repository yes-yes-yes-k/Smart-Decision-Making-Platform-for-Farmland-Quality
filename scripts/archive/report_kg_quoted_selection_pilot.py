"""Report the frozen quoted-selection pilot, including every rejected quote/offset pair."""
from collections import Counter
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.prepare_kg_quoted_selection_pilot import BASE,CASES,FAILURES
from scripts.rebuild_kg_extraction_benchmark import OUT,readlines,dump
from scripts.run_kg_benchmark_pilot import digest
from framework.knowledge_graph.benchmark_quoted_selection_v1 import verify_selected_span


def span_diagnostics(value,blocks,path='$'):
    found=[]
    if isinstance(value,list):
        for i,item in enumerate(value):found.extend(span_diagnostics(item,blocks,f'{path}[{i}]'))
    elif isinstance(value,dict):
        if {'block_id','quote','start','end'}.issubset(value):
            try:verified=verify_selected_span(value,blocks);found.append(dict(path=path,state='valid',span=verified))
            except ValueError as exc:
                block=value.get('block_id');start=value.get('start');end=value.get('end')
                sliced=blocks[block][start:end] if block in blocks and type(start) is int and type(end) is int and 0<=start<end<=len(blocks[block]) else None
                found.append(dict(path=path,state='invalid',error=str(exc),quote=value.get('quote'),coordinate_slice=sliced))
        else:
            for k,v in value.items():found.extend(span_diagnostics(v,blocks,f'{path}.{k}'))
    return found


def main():
    packet_doc=json.loads((BASE/'source-packets.json').read_text(encoding='utf-8'))
    packets={p['sample_id']:p for p in packet_doc['cases']};items=[];allstates=Counter();percase={}
    for p in packet_doc['cases']:
        blocks={b['block_id']:b['text'] for b in p['blocks']};row=dict(sample_id=p['sample_id'],kind='synthetic_control' if p['sample_id'].startswith('control-') else 'known_failure_source')
        for role in ['A','B']:
            path=BASE/'initial/proposals'/(digest(role+':'+p['sample_id'])+'.json')
            record=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            row[role+'_state']=record['state'] if record else 'missing';allstates[row[role+'_state']]+=1
            raw=None
            if record and record.get('content'):
                try:raw=json.loads(record['content'])
                except ValueError:pass
            diag=span_diagnostics(raw,blocks) if raw is not None else []
            row[role+'_span_checks']=dict(total=len(diag),valid=sum(d['state']=='valid' for d in diag),
                invalid=sum(d['state']=='invalid' for d in diag),failures=[d for d in diag if d['state']=='invalid'])
            if record and record.get('selection_check_error'):row[role+'_protocol_error']=record['selection_check_error']
        reviewpath=BASE/'review/proposals'/(digest('review:'+p['sample_id'])+'.json')
        review=json.loads(reviewpath.read_text(encoding='utf-8')) if reviewpath.exists() else None
        row['source_review_state']=review['state'] if review else 'missing'
        if review and review.get('content'):
            try:
                result=json.loads(review['content']);diag=span_diagnostics(result,blocks)
                row['review_span_checks']=dict(total=len(diag),valid=sum(d['state']=='valid' for d in diag),
                    invalid=sum(d['state']=='invalid' for d in diag),failures=[d for d in diag if d['state']=='invalid'])
            except ValueError:row['review_json_parse_failure']=True
        if p['sample_id'].startswith('control-'):
            row['control_definition_issue']=('source is not title-only; full body states the standard measurement' if p['sample_id']=='control-title-only'
                else 'soil sample is not a measurable indicator; expected key will exclude this item' if p['sample_id']=='control-cn-lab-negative'
                else None)
        items.append(row);percase[p['sample_id']]=row
    rows=readlines(OUT/'dataset-v1/samples.jsonl');member={r['sample_id']:r for r in rows}
    valid_config=json.loads((BASE/'run-config.json').read_text(encoding='utf-8'))
    report=dict(status='inconclusive',protocol='quoted_selection_v1',model=valid_config['model'],
        expected_cases=10,synthetic_controls=6,known_failure_sources=4,expected_initial_requests=20,
        expected_source_review_requests=10,saved_initial_responses=len(list((BASE/'initial/proposals').glob('*.json'))),
        saved_review_responses=len(list((BASE/'review/proposals').glob('*.json'))),initial_states=dict(allstates),
        cases=percase,initial_control_definition_corrections=['control-title-only is body-explicit, not title-only',
            'control-cn-lab-negative expected entity soil sample is out-of-scope and excluded from the control key'],
        candidate_display_note='Initial spans were validated then materialized with text/start/end; the review-union adapter expects quote/start/end. Review inputs therefore show null quote beside a verified source slice. Adjudication outputs are diagnostic only and cannot validate the review-stage span contract.',
        original_model_outputs_immutable=True,old_reference_labels_modified=False,formal_acceptance=False,
        same_model_error_correlation=True,expert_certified=False,bulk_annotation_resumed=False,
        inherited_shared_budget=json.loads((BASE/'run-state.json').read_text(encoding='utf-8'))['budget'])
    dump(BASE/'report.json',report);print(json.dumps(dict(status=report['status'],initial_states=report['initial_states'],
        saved_initial=report['saved_initial_responses'],saved_review=report['saved_review_responses']),ensure_ascii=False))


if __name__=='__main__':main()
