"""Read-only paired agreement; expansion always requires an explicit source-review record."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl
from framework.knowledge_graph.evaluation_v4 import fact_keys
from framework.knowledge_graph.evaluation_v4_scoring import metric
from scripts.calibrate_kg_v4_r3 import BASE,R3

def main():
    inputs=read(BASE/'calibration/inputs.jsonl')[:10];ids={r['sample_id'] for r in inputs}
    arms={arm:{r['sample_id']:r for r in read(R3/arm/'responses.jsonl')} for arm in ('A','B')}
    configs={arm:json.loads((R3/arm/'config.json').read_text(encoding='utf-8')) for arm in ('A','B')}
    hashes={arm:hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest() for arm,c in configs.items()}
    gold=[set(),set()];pred=[set(),set()];rows=[];alignment=Counter();quality=0;paired=0
    for sid in sorted(ids):
        a,b=arms['A'].get(sid),arms['B'].get(sid)
        for arm,r in (('A',a),('B',b)):
            if r and r['config_sha256']!=hashes[arm]:raise ValueError('stale_annotation_config')
        if not a or not b or a['state']!='completed' or b['state']!='completed':
            rows.append(dict(sample_id=sid,status='technical_failure',A=a.get('code') if a else 'missing',B=b.get('code') if b else 'missing'));continue
        aa,bb=a['annotation'],b['annotation'];paired+=1
        ae,ar=fact_keys(aa);be,br=fact_keys(bb)
        for i,(g,p) in enumerate(((ae,be),(ar,br))):gold[i].update((sid,*k) for k in g);pred[i].update((sid,*k) for k in p)
        for annot in (aa,bb):alignment.update(t['method'] for t in annot['binding_audit'])
        qsame=all(aa['quality'][k]==bb['quality'][k] for k in ('grade','entity_eligible','relation_eligible','numeric_eligible'));quality+=qsame
        rows.append(dict(sample_id=sid,status='source_review_required',mentions=metric(ae,be),relations=metric(ar,br),quality_equal=qsame))
    em,rm=metric(gold[0],pred[0]),metric(gold[1],pred[1])
    numeric=paired==10 and em['f1'] is not None and em['f1']>=.9 and rm['f1'] is not None and rm['f1']>=.85
    review_path=R3/'source-review.json';review=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    review_ok=(review.get('config_sha256')==hashes and review.get('samples_reviewed')==10 and review.get('unresolved_critical_violations')==0 and review.get('passed') is True)
    gate=dict(passed=numeric and review_ok,config_sha256=hashes,technical_pass=paired==10,agreement_pass=numeric,
        semantic_source_review_pass=review_ok,reason='all three gates required; pairwise agreement is not gold accuracy',expert_certified=False,production_approved=False)
    failures={arm:dict(Counter(r.get('code') for r in records.values() if r['state']!='completed')) for arm,records in arms.items()}
    report=dict(samples=10,paired_completed=paired,mention_agreement=em,positive_relation_agreement=rm,
        quality_equal_samples=quality,binding_methods=alignment,failures=failures,gate=gate,
        tokens=sum((r.get('usage') or {}).get('total_tokens',0) for records in arms.values() for r in records.values()),
        input_scope='same development pilot; not fresh blind performance data',same_provider_correlated=True)
    write(R3/'pilot-report.json',report);write(R3/'pilot-gate.json',gate);jsonl(R3/'review-queue.jsonl',rows)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
