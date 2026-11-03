"""Compare protocol pilot proposals without equating agreement with accuracy."""
from collections import Counter
from pathlib import Path
import argparse
import html
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,budget_snapshot


def signature(proposal):
    entities=proposal.get('entities',[])
    byid={e['id']:(e.get('type'),e.get('block_id'),e.get('text'),e.get('occurrence')) for e in entities}
    es=set(byid.values())
    rs=set()
    for r in proposal.get('relations',[]):
        rs.add((r.get('type'),byid.get(r.get('source_id')),byid.get(r.get('target_id')),r.get('modality')))
    return es,rs


def results(revision):
    run=OUT/f'execution/pilot-{revision}'
    protocol=OUT/('protocol' if revision=='r1' else 'protocol-'+revision)
    keys={k['sample_id']:k for k in readlines(protocol/'private-control-keys.jsonl')}
    packets={p['sample_id']:p for name in ['controls-inputs.jsonl','pilot-inputs.jsonl'] for p in readlines(protocol/name)}
    records={}
    for path in (run/'proposals').glob('*.json'):
        row=json.loads(path.read_text(encoding='utf-8'))
        records[row['id']]=row
    details=[]
    for sid,p in packets.items():
        pair={}
        for role in ('A','B'):
            record=records.get(role+':'+sid)
            if not record:
                continue
            proposal=record.get('protocol',{}).get('materialized_proposal',record.get('proposal',{}))
            es,rs=signature(proposal)
            entry=dict(state=record['state'],protocol_valid=record['state']=='protocol_valid',
                protocol_errors=record.get('protocol',{}).get('errors',[]),proposal=proposal,
                inclusion_decisions=record.get('protocol',{}).get('inclusion_decisions'),
                request_attempt_ids=record['attempt_ids'],raw_content=record.get('content'))
            if sid in keys:
                ee,rr=signature(keys[sid]['expected'])
                entry.update(entity_inventory_exact=es==ee,relation_inventory_exact=rs==rr,
                    control_pass=entry['protocol_valid'] and es==ee and rs==rr,
                    entity_false_positives=[list(v) for v in sorted(es-ee,key=repr)],
                    entity_false_negatives=[list(v) for v in sorted(ee-es,key=repr)])
            pair[role]=entry
        agreement=None
        if set(pair)=={'A','B'}:
            agreement=signature(pair['A']['proposal'])==signature(pair['B']['proposal'])
        details.append(dict(sample_id=sid,synthetic_control=sid in keys,source_packet=p,
            pair=pair,exact_inventory_agreement=agreement,
            both_wrong_on_control=(not pair['A']['control_pass'] and not pair['B']['control_pass'])
                if sid in keys and set(pair)=={'A','B'} else None))
    controls=[r for r in details if r['synthetic_control']]
    paired=[r for r in controls if set(r['pair'])=={'A','B'}]
    observed=sum(len(r['pair']) for r in controls)
    passed=sum(e['control_pass'] for r in controls for e in r['pair'].values())
    completed_pairs=[r for r in details if set(r['pair'])=={'A','B'}]
    source_pairs=[r for r in completed_pairs if not r['synthetic_control']]
    summary=dict(revision=revision,status='inconclusive',model='deepseek-ai/DeepSeek-V4.1-Flash',
        controls=len(controls),observed_control_responses=observed,expected_control_responses=2*len(controls),
        protocol_states=dict(Counter(r['state'] for r in records.values())),
        control_responses_passed=passed,control_response_pass_fraction=passed/(2*len(controls)),
        paired_control_cases=len(paired),both_wrong_control_cases=sum(r['both_wrong_on_control'] for r in paired),
        both_wrong_control_fraction=sum(r['both_wrong_on_control'] for r in paired)/len(paired) if paired else None,
        paired_inventory_agreement=sum(r['exact_inventory_agreement'] for r in completed_pairs)/len(completed_pairs) if completed_pairs else None,
        critical_control_gate_passed=observed==2*len(controls) and passed==observed,
        real_source_pairs=len(source_pairs),expected_real_source_pairs=sum(sid not in keys for sid in packets),
        source_inventory_disagreements=[r['sample_id'] for r in source_pairs if not r['exact_inventory_agreement']],
        real_source_arbitrations=0,handbook_validated=False,
        formal_acceptance_ready=False,expert_certified=False,same_model_error_correlation=True,
        agreement_is_not_accuracy=True,shared_budget=budget_snapshot())
    arbitration=run/'adjudication-summary.json'
    if arbitration.exists():
        summary['adjudication']=json.loads(arbitration.read_text(encoding='utf-8'))
        summary['real_source_arbitrations']=summary['adjudication'].get('real_source_arbitrations_valid',0)
    return summary,details


def main():
    parser=argparse.ArgumentParser();parser.add_argument('revision',choices=['r1','r2','r3','r4','r5'])
    args=parser.parse_args()
    summary,details=results(args.revision)
    run=OUT/f'execution/pilot-{args.revision}'
    dump(run/'report.json',summary)
    lines(run/'item-comparisons.jsonl',details)
    e=lambda value:html.escape(str(value),quote=True)
    cards=[]
    for row in details:
        if not row['pair']:continue
        source=row['source_packet']
        text='\n'.join(b['block_id']+': '+b['text'] for b in source['blocks'])
        panels=''.join('<details><summary>'+role+' '+e(value['state'])+'</summary><pre>'+e(json.dumps(value,ensure_ascii=False,indent=2))+'</pre></details>' for role,value in row['pair'].items())
        cards.append('<section><h2>'+e(row['sample_id'])+'</h2><pre>'+e(text)+'</pre><p>实体/关系清单一致：'+e(row['exact_inventory_agreement'])+'</p>'+panels+'</section>')
    (run/'review.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>标注流程试标诊断</title><style>body{font:15px system-ui;margin:30px;max-width:1300px}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #bbb;margin-top:25px}details{background:#f4f6fa;padding:12px;margin:8px 0}</style><h1>标注流程试标诊断</h1><p>控制题是开发协议检查，不是正式质量验收；同模型双标的一致不证明正确。原始响应保持原样。</p><pre>'+e(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'+''.join(cards)+'</html>',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
