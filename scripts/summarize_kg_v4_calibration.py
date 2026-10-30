"""Agreement and release gates; agreement is not independent gold accuracy."""
from collections import Counter
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.evaluation_v4 import fact_keys,mention_key
from framework.knowledge_graph.evaluation_v4_scoring import metric,cluster_bootstrap,score_sample

BASE=ROOT/'artifacts/knowledge_platform/gold-v4'

def main(run_tag='r2',limit=None):
    cal=BASE/'calibration';inputs=read(cal/'inputs.jsonl');inputs=inputs[:limit] if limit else inputs;ids={r['sample_id'] for r in inputs}
    arms={a:{r['sample_id']:r for r in read(cal/('run-'+a+'-'+run_tag)/'responses.jsonl')} for a in ('A','B')}
    for arm,records in arms.items():
        assert set(records)==ids
        config=json.loads((cal/('run-'+arm+'-'+run_tag)/'config.json').read_text(encoding='utf-8'))
        assert config['input_sha256']==sha(cal/('annotator-'+arm+'.jsonl'))
    gs=[set(),set()];ps=[set(),set()];details=[];quality=0;normalization_disagreements=0
    migration={r['sample_id']:r for r in read(BASE/'migration-queue.jsonl')};pair_scores={}
    for sid in sorted(ids):
        a,b=arms['A'][sid],arms['B'][sid]
        if a['state']!='completed' or b['state']!='completed':
            details.append(dict(sample_id=sid,status='annotation_failure',a_state=a['state'],b_state=b['state']));continue
        a,b=a['annotation'],b['annotation']
        assert a['input_sha256']==b['input_sha256']
        aa,bb=fact_keys(a),fact_keys(b)
        for i in range(2):gs[i].update((sid,*k) for k in aa[i]);ps[i].update((sid,*k) for k in bb[i])
        qfields=('grade','entity_eligible','relation_eligible','numeric_eligible')
        qequal=all(a['quality'][k]==b['quality'][k] for k in qfields);quality+=qequal
        def links(x):return {(mention_key(m),m['normalization_status'],m['canonical_name']) for m in x['mentions']}
        nequal=links(a)==links(b);normalization_disagreements+=not nequal
        same=aa==bb and qequal and nequal and a['completeness']==b['completeness']
        # No automatic acceptance merely because entity/relation sets agree: evidence still needs adjudication.
        details.append(dict(sample_id=sid,status='agreement_needs_adjudication' if same else 'disagreement_needs_adjudication',
            mentions=metric(aa[0],bb[0]),relations=metric(aa[1],bb[1]),quality_equal=qequal,normalization_equal=nequal))
        pair_scores[sid]=score_sample(a,b)
    em,rm=metric(gs[0],ps[0]),metric(gs[1],ps[1])
    report=dict(samples=len(inputs),target_samples=100,run_tag=run_tag,paired_completed=len(pair_scores),states=dict(Counter(r['status'] for r in details)),
        mention_agreement=em,positive_relation_agreement=rm,quality_exact_agreement=quality/len(pair_scores) if pair_scores else None,
        normalization_disagreement_samples=normalization_disagreements,
        thresholds=dict(mention_f1=.90,relation_f1=.85,all_bindings_valid=True),
        numeric_agreement_gate=bool(len(pair_scores)==100 and em['f1'] is not None and em['f1']>=.9 and rm['f1'] is not None and rm['f1']>=.85),
        adjudication_complete=False,expert_certified=False,production_approved=False,model_experiments_allowed=False,
        identity='two separate AI annotation arms using same model/provider; correlated errors possible',
        tokens=sum((r.get('usage') or {}).get('total_tokens',0) for records in arms.values() for r in records.values()))
    groups={sid:migration[sid]['source']['leakage_group'] for sid in pair_scores}
    report['document_cluster_agreement_interval']=cluster_bootstrap(pair_scores,groups)
    suffix='-pilot' if limit else ''
    write(cal/('agreement-report'+suffix+'.json'),report);jsonl(cal/('adjudication-queue'+suffix+'.jsonl'),details)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-tag',default='r2');p.add_argument('--limit',type=int);args=p.parse_args();main(args.run_tag,args.limit)
