"""Append source-specific Codex decisions and freeze an honest AI silver release."""
from collections import Counter
from datetime import datetime,UTC
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.silver_adjudication import build_decision,score_scope,surface_facts
from framework.knowledge_graph.evaluation_v4 import input_digest

BASE=ROOT/'artifacts/knowledge_platform/gold-v4';OUT=BASE/'silver-v1'

def sources():
    manifest=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    if sha(BASE/'calibration/inputs.jsonl')!=manifest['calibration_inputs_sha256']:raise ValueError('frozen_calibration_changed')
    return read(BASE/'calibration/inputs.jsonl')

def record(decisions):
    rows=sources();OUT.mkdir(exist_ok=True);path=OUT/'source-adjudications.jsonl'
    if (OUT/'reference.jsonl').exists():raise ValueError('silver release frozen')
    previous=read(path) if path.exists() else [];seen={r['index'] for r in previous};pending=[]
    for d in decisions:
        i=d['index']
        if type(i) is not int or not 0<=i<100 or i in seen:raise ValueError('duplicate_or_invalid_review_index')
        annotation=build_decision(rows[i],d)
        pending.append(dict(index=i,sample_id=rows[i]['sample_id'],input_sha256=input_digest(rows[i]),
            reviewed_at=datetime.now(UTC).isoformat(),decision=d,annotation=annotation));seen.add(i)
    with path.open('a',encoding='utf-8',newline='\n') as f:
        for item in pending:f.write(json.dumps(item,ensure_ascii=False)+'\n')
    write(OUT/'progress.json',dict(reviewed=len(seen),target=100,expert_certified=False,unresolved=100-len(seen)))
    print('source reviewed',len(seen),'/100')

def show(start,end):
    for i,row in enumerate(sources()[start:end],start):
        print(json.dumps(dict(index=i,sample_id=row['sample_id'],blocks=[{k:b[k] for k in ('block_id','text')} for b in row['blocks']]),ensure_ascii=False))

def freeze():
    rows=sources();ledger=read(OUT/'source-adjudications.jsonl')
    if len(ledger)!=100 or {r['index'] for r in ledger}!=set(range(100)):raise ValueError('all_100_source_decisions_required')
    if (OUT/'reference.jsonl').exists():raise ValueError('release already frozen')
    ordered=sorted(ledger,key=lambda r:r['index']);reference=[]
    migration={r['sample_id']:r for r in read(BASE/'migration-queue.jsonl')}
    for item in ordered:
        row=rows[item['index']]
        if item['input_sha256']!=input_digest(row):raise ValueError('stale_source_review')
        annotation=build_decision(row,item['decision'])
        if annotation!=item['annotation']:raise ValueError('validator_or_decision_changed')
        reference.append(dict(index=item['index'],visible_input=row,annotation=annotation,source=migration[row['sample_id']]['source'],
            release_status='AI_source_adjudicated_silver',expert_certified=False,production_approved=False))
    history=json.loads((BASE/'history-freeze.json').read_text(encoding='utf-8'))
    historical=[dict(path=f['path'],unchanged=sha(Path(f['path']))==f['sha256']) for f in history['files']]
    if not all(f['unchanged'] for f in historical):raise ValueError('historical_artifact_changed')
    counts=Counter();types=Counter();excluded=[]
    for r in reference:
        a=r['annotation'];scoped=score_scope(a);e,relations=surface_facts(scoped)
        masks=a['eligibility_by_block'];body=masks['chunk']['mentions'];rel=masks['chunk']['relations'];title=masks.get('document_title',{}).get('mentions',False)
        counts['mentions']+=len(a['mentions']);counts['relations']+=len(a['relations'])
        counts['fully_evaluable']+=a['body_annotation_complete'] and a['quality']['relation_eligible']
        counts['entity_body_excluded']+=not a['body_annotation_complete'];counts['relation_task_excluded']+=not a['quality']['relation_eligible']
        counts['normalization_known']+=sum(m['normalization_status']=='known' for m in a['mentions'])
        counts['scored_mentions']+=len(scoped['mentions']);counts['scored_surface_body_entities']+=sum(k[0]=='chunk' for k in e)
        counts['scored_surface_context_entities']+=sum(k[0]!='chunk' for k in e)
        counts['scored_positive_relations']+=len(relations);counts['relation_positive_samples']+=bool(relations)
        counts['body_entity_eligible_samples']+=body;counts['relation_eligible_samples']+=rel;counts['context_eligible_samples']+=title
        counts['fully_excluded_samples']+=not (body or rel or title)
        counts['context_only_samples']+=title and not body and not rel
        counts['body_clear_negative_samples']+=body and rel and not any(k[0]=='chunk' for k in e) and not relations
        types.update(t['relation_type'] for t in scoped['relations'] if t['modality'] in ('asserted','normative'))
        if not body or not rel or not title:
            excluded.append(dict(index=r['index'],sample_id=a['sample_id'],eligibility_by_block=masks,reason=a['quality']['reason'],uncertainties=a['uncertainties']))
    jsonl(OUT/'reference.jsonl',reference);jsonl(OUT/'exclusions.jsonl',excluded)
    write(OUT/'source-validation.json',dict(samples_rebuilt_and_validated=100,input_bindings_verified=True,historical_files=historical,
        source_review='single Codex source adjudication; semantic correctness not independently certified'))
    write(OUT/'manifest.json',dict(samples=100,status='AI_source_adjudicated_silver',counts=counts,relation_types=types,
        reference_sha256=sha(OUT/'reference.jsonl'),source_inputs_sha256=sha(BASE/'calibration/inputs.jsonl'),ledger_sha256=sha(OUT/'source-adjudications.jsonl'),
        validator_sha256=sha(ROOT/'framework/knowledge_graph/silver_adjudication.py'),
        scorer_policy='surface inventory primary, exact-span diagnostic; body/context separate; no exhaustive mention-occurrence claim',
        document_groups=len({r['source']['leakage_group'] for r in reference}),split='development',
        available_for='development regression with fixed per-task/block masks; not independent ranking or production acceptance',
        basis='user-authorized direct source adjudication; failed auto-label qualification is not marked passed',
        automated_annotation_qualification_passed=False,independent_double_annotation=False,legacy_exposure=True,
        expert_certified=False,production_approved=False))
    print(json.dumps(counts))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--show',nargs=2,type=int);p.add_argument('--freeze',action='store_true');args=p.parse_args()
    show(*args.show) if args.show else freeze() if args.freeze else p.error('choose --show or --freeze')
