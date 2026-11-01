"""Describe structure, semantics and boundary issues separately; never open a gate."""
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.evaluation_v4 import fact_keys,input_digest
from framework.knowledge_graph.evaluation_v4_scoring import metric
from scripts.calibrate_kg_v4_r4 import BASE,OUT,controls,visible_control

def main():
    control_records=read(OUT/'controls/responses.jsonl');cases={c['id']:c for c in controls()};boundary=[]
    for r in control_records:
        assert r['input_sha256']==input_digest(visible_control(cases[r['id']]))
        if r['id'] not in ('affirmed_mulch','negative_mulch') or r['issues']!=['effect_relation_missing_or_wrong'] or not r.get('annotation'):continue
        a=r['annotation'];ms={m['id']:m for m in a['mentions']};wanted='asserted' if r['id']=='affirmed_mulch' else 'negated'
        if len(a['mentions'])==2 and len(a['relations'])==1:
            rel=a['relations'][0];s,t=ms[rel['source']],ms[rel['target']]
            if rel['relation_type']=='improves_indicator' and rel['modality']==wanted and s['fragment']['text']=='秸秆覆盖' and t['fragment']['text']=='该土壤的结构稳定性':
                boundary.append(dict(id=r['id'],round=r['round'],review='predicate/modality correct; surface includes forbidden demonstrative; strict score unchanged'))
    write(OUT/'controls/boundary-audit.json',dict(strict_correct=sum(r['passed'] for r in control_records),strict_total=22,
        semantically_correct_effects_with_boundary_deviation=boundary,
        warning='These are compound full annotations, not directly comparable to previous single-judgment 33/34 controls; no revised qualification score'))
    source={r['sample_id']:r for r in read(BASE/'calibration/inputs.jsonl')[:10]}
    arms={a:{r['sample_id']:r for r in read(OUT/('diagnostic-'+a)/'responses.jsonl')} for a in ('A','B')}
    report={};sets_g=[set(),set()];sets_p=[set(),set()];pairs=0;details=[]
    for arm,rs in arms.items():
        assert set(rs)==set(source)
        config=json.loads((OUT/('diagnostic-'+arm)/'config.json').read_text(encoding='utf-8'))
        cs=__import__('hashlib').sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        assert all(r['input_sha256']==input_digest(source[sid]) and r['config_sha256']==cs for sid,r in rs.items())
        tasks=Counter();grades=Counter();contradictions=0
        for r in rs.values():
            tasks.update(k+':'+v for k,v in r['task_status'].items())
            a=r.get('annotation')
            if a:
                grades[a['quality']['grade']]+=1
                contradictions+=a['quality']['grade']=='A' and not(a['quality']['entity_eligible'] and a['quality']['relation_eligible'])
                contradictions+=sum(m['normalization_status']=='unknown' and m['canonical_name'] is not None for m in a['mentions'])
        report[arm]=dict(states=dict(Counter(r['state'] for r in rs.values())),tasks=tasks,quality_grades=grades,conflicting_derived_fields=contradictions,
            entity_mentions_retained=sum(len((r.get('annotation') or {}).get('mentions',[])) for r in rs.values()),
            relation_claims_retained=sum(len((r.get('annotation') or {}).get('relations',[])) for r in rs.values()),
            positive_relations=sum(len(fact_keys(r['annotation'])[1]) for r in rs.values() if r.get('annotation')),
            reported_tokens=sum(r['usage']['total_tokens'] for r in rs.values()))
    for sid in source:
        a,b=arms['A'][sid],arms['B'][sid]
        if a['state']=='completed' and b['state']=='completed':
            pairs+=1;aa,bb=fact_keys(a['annotation']),fact_keys(b['annotation'])
            for i in range(2):sets_g[i].update((sid,*k) for k in aa[i]);sets_p[i].update((sid,*k) for k in bb[i])
        details.append(dict(sample_id=sid,A_state=a['state'],B_state=b['state'],requires_source_review=True,
            A_quality=(a.get('annotation') or {}).get('quality'),B_quality=(b.get('annotation') or {}).get('quality')))
    report.update(paired_structurally_completed=pairs,mention_agreement=metric(sets_g[0],sets_p[0]),positive_relation_agreement=metric(sets_g[1],sets_p[1]),
        controls_passed=False,diagnostic_only=True,qualified_pilot_passed=False,remaining_90_submitted=False,expert_certified=False,production_approved=False,
        caveat='Completion and agreement do not establish semantic accuracy; quality C may wrongly skip entity tasks.')
    write(OUT/'diagnostic-report.json',report);jsonl(OUT/'source-review-queue.jsonl',details)
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
