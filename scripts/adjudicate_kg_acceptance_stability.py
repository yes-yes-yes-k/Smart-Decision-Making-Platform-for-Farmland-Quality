"""Compare and adjudicate blind relabels without modifying the original reference."""
import argparse
import asyncio
from collections import Counter,defaultdict
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,SILVER,verify_freeze,shared_budget_path
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_data import digest
from framework.knowledge_graph.acceptance_budget import Budget
from framework.knowledge_graph.acceptance_remote import run_jobs
from framework.knowledge_graph.silver_adjudication import build_decision,surface_facts,score_silver_sample
from framework.knowledge_graph.annotation_protocol_r4 import object_schema,response_schema,fragment_schema

def compact(a):
    if a is None:return None
    return dict(mentions=[dict(id=m['id'],type=m['type'],block=m['fragment']['block_id'],text=m['fragment']['text'],start=m['fragment']['span_start'],canonical_name=m['canonical_name']) for m in a['mentions']],
        relations=[dict(source=r['source'],target=r['target'],type=r['relation_type'],modality=r['modality'],evidence=[dict(block=e['block_id'],text=e['text']) for e in r['evidence']]) for r in a['relations']],
        quality=a['quality'],completeness=a['completeness'],eligibility_by_block=a.get('eligibility_by_block'))

def decision_schema():
    ent=object_schema(dict(type=dict(type='string',enum=['indicator','obstacle','measure','standard']),block=dict(type='string',enum=['chunk','document_title']),text=dict(type='string'),occurrence=dict(type='integer',minimum=0)))
    rel=object_schema(dict(source=dict(type='integer',minimum=0),target=dict(type='integer',minimum=0),type=dict(type='string',enum=['addresses','improves_indicator','characterized_by','includes_indicator','prescribes_measurement','assessment_basis']),
        modality=dict(type='string',enum=['asserted','normative','hypothetical','negated','unknown']),evidence=dict(type='array',items=fragment_schema())))
    review=object_schema(dict(origin=dict(type='string',enum=['old','new']),relation_index=dict(type='integer',minimum=0),verdict=dict(type='string',enum=['supported','unsupported','uncertain']),reason=dict(type='string')))
    return response_schema('source_adjudication',dict(entities=dict(type='array',items=ent),relations=dict(type='array',items=rel),entity_complete=dict(type='boolean'),relation_complete=dict(type='boolean'),
        title_eligible=dict(type='boolean'),reason=dict(type='string'),uncertainties=dict(type='array',items=dict(type='string')),relation_reviews=dict(type='array',items=review)))

def validate_decision(visible,answer,*,expected_reviews=None):
    d=copy.deepcopy(answer);reviews=d.pop('relation_reviews')
    for r in d['relations']:
        r['evidence']=[dict(block=e['block_id'],text=e['text'],occurrence=e['occurrence']) for e in r['evidence']]
    if expected_reviews is not None:
        keys=[(r['origin'],r['relation_index']) for r in reviews]
        if len(keys)!=len(set(keys)) or set(keys)!=set(expected_reviews):raise ValueError('every_proposed_relation_needs_evidence_review')
    annotation=build_decision(visible,d)
    annotation.update(reviewer='siliconflow-model',review_method='same_model_source_arbitration',legacy_exposure=True,independent_double_annotation=False)
    return dict(annotation=annotation,decision=d,relation_reviews=reviews)

def prepare():
    verify_freeze();references=read(SILVER/'reference.jsonl');directory=OUT/'stability/responses';jobs=[];comparison=[]
    for i,r in enumerate(references):
        p=directory/f'{i:03}.json';new=json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
        a=r['annotation'];b=new.get('annotation') if new else None
        ae,ar=surface_facts(a);be,br=surface_facts(b or dict(mentions=[],relations=[]))
        matched=a['input_sha256']==new.get('input_sha256') if new else False
        if new and not matched:raise ValueError('relabel_context_mismatch')
        advisory=new.get('source_quality_advisory') if new else None
        valid=bool(b is not None and not new.get('errors'))
        comparison.append(dict(index=i,sample_id=a['sample_id'],relabel_present=new is not None,relabel_structurally_complete=valid,
            entity_tp=len(ae&be),entity_fp=len(be-ae),entity_fn=len(ae-be),relation_tp=len(ar&br),relation_fp=len(br-ar),relation_fn=len(ar-br),
            entities_equal=ae==be if valid else None,relations_equal=ar==br if valid else None,
            source_quality_advisory=advisory,old_masks=a['eligibility_by_block'],errors=new.get('errors') if new else {'missing':'no_relabel'},
            new_proposals_are_untrusted=True))
        # Review every sample: apparent agreement does not certify its source quality.
        proposals=dict(old=compact(a),new=compact(b),new_protocol_errors=new.get('errors') if new else {'missing':True})
        expected=[('old',j) for j in range(len(a['relations']))]+[('new',j) for j in range(len(b['relations']))] if b else [('old',j) for j in range(len(a['relations']))]
        prompt='逐条来源仲裁。两个候选均可能出错，不能多数投票，也不能无审查沿用旧标签。完整阅读原文，重新给出代表性实体、关系与每块可评范围。所有关系候选逐项评证据支持。无法穷尽时明确排除对应任务；所有字段必须有来源依据。实体用列表零基下标作为关系端点。正文任务排除时不输出肯定关系。每个old/new关系必须在relation_reviews中出现一次，且保留原始relation_index。只对可见来源判定，不改字母或标点。规范名本轮保持unknown，不凭常识扩展。\n原文：'+json.dumps(r['visible_input'],ensure_ascii=False)+'\n待审候选：'+json.dumps(proposals,ensure_ascii=False)
        jobs.append(dict(id=f'stability-arbitration:{i}',index=i,phase='stability',prompt=prompt,format=decision_schema(),max_tokens=6144,
            source_ids=[a['sample_id']],expected_reviews=expected))
    jsonl(OUT/'stability/comparison.jsonl',comparison);jsonl(OUT/'stability/arbitration-jobs.jsonl',jobs)
    return jobs

async def run():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');verify_freeze()
    if not (OUT/'stability/run-state.json').exists():raise ValueError('wait_for_blind_relabel_runner_to_finish')
    jobs=prepare();refs=read(SILVER/'reference.jsonl')
    def validator(job,answer):return validate_decision(refs[job['index']]['visible_input'],answer,expected_reviews=[tuple(k) for k in job['expected_reviews']])
    result=await run_jobs(jobs,OUT/'stability/arbitrations',json.loads((OUT/'run-config.json').read_text(encoding='utf-8')),Budget(shared_budget_path()),validator)
    write(OUT/'stability/arbitration-run-state.json',result);summarize()

def summarize():
    refs=read(SILVER/'reference.jsonl');comparisons=read(OUT/'stability/comparison.jsonl');arms=[];missing=[];changed=0;statuses=Counter();maskdiff=0
    strata=json.loads((ROOT/'artifacts/knowledge_platform/gold-v4/calibration/private-sampling-manifest.json').read_text(encoding='utf-8'))['strata']
    strata_by_id={sid:k for k,ids in strata.items() for sid in ids};perstratum=defaultdict(Counter);reviews=Counter();type_support=defaultdict(Counter)
    fixed_scope=defaultdict(Counter)
    for c in comparisons:
        st=perstratum[strata_by_id[c['sample_id']]];st['samples']+=1;st['relabel_attempted']+=c['relabel_present'];st['protocol_complete']+=c['relabel_structurally_complete']
        if c['relabel_structurally_complete']:
            st['raw_entity_inventory_changed']+=not c['entities_equal'];st['raw_relation_inventory_changed']+=not c['relations_equal']
            old=refs[c['index']]['annotation'];new=json.loads((OUT/'stability/responses'/f"{c['index']:03}.json").read_text(encoding='utf-8'))['annotation']
            s=score_silver_sample(old,new)
            for task in ('surface_chunk_mentions','surface_relations'):
                if s[task] is not None:
                    fixed_scope[task]['paired_samples']+=1
                    for k in ('tp','fp','fn'):fixed_scope[task][k]+=s[task][k]
            _,gr=surface_facts(old);_,pr=surface_facts(new)
            for fact in gr:type_support[fact[1]]['reference_facts']+=1
            for fact in pr:type_support[fact[1]]['proposed_facts']+=1
            for fact in gr&pr:type_support[fact[1]]['matched_facts']+=1
    for i,r in enumerate(refs):
        path=OUT/'stability/arbitrations'/(digest(f'stability-arbitration:{i}')+'.json')
        row=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        valid=row is not None and row['state']=='completed'
        if not valid:missing.append(dict(index=i,sample_id=r['annotation']['sample_id'],reason=row.get('error') if row else 'not_completed'));continue
        a=row['validated']['annotation'];old=r['annotation'];different=surface_facts(a)!=surface_facts(old)
        md=a['eligibility_by_block']!=old['eligibility_by_block'];changed+=different;maskdiff+=md
        perstratum[strata_by_id[old['sample_id']]]['reviewed']+=1;perstratum[strata_by_id[old['sample_id']]]['label_changed']+=different;perstratum[strata_by_id[old['sample_id']]]['mask_changed']+=md
        reviews.update(x['verdict'] for x in row['validated']['relation_reviews'])
        arms.append(dict(index=i,visible_input=r['visible_input'],annotation=a,old_label_changed=different,mask_changed=md,source=r['source']))
    validcomparisons=[c for c in comparisons if c['relabel_structurally_complete']]
    def pairwise(prefix):
        tp=sum(c[prefix+'_tp'] for c in validcomparisons);fp=sum(c[prefix+'_fp'] for c in validcomparisons);fn=sum(c[prefix+'_fn'] for c in validcomparisons)
        return dict(tp=tp,fp=fp,fn=fn,f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,paired_support=len(validcomparisons),is_accuracy=False)
    report=dict(status='inconclusive' if missing else 'pass',meaning='review completion only; semantic stability requires reviewing rates, not automatic certification',
        samples=100,relabel_attempted=sum(c['relabel_present'] for c in comparisons),relabel_protocol_complete=len(validcomparisons),adjudicated=len(arms),unresolved=len(missing),
        changed_after_arbitration=changed if arms else None,change_rate_on_reviewed=changed/len(arms) if arms else None,mask_changed=maskdiff if arms else None,
        entity_agreement=pairwise('entity'),relation_agreement=pairwise('relation'),per_stratum=perstratum,relation_evidence_reviews=reviews,
        raw_agreement_scope='all retained proposals including unscored body candidates; diagnostic only, not accuracy',
        fixed_reference_scope_agreement={k:dict(v,f1=2*v['tp']/(2*v['tp']+v['fp']+v['fn']) if 2*v['tp']+v['fp']+v['fn'] else None) for k,v in fixed_scope.items()},
        per_relation_type_paired_support=type_support,all_100_failures_retained=True,
        budget=Budget(shared_budget_path()).summary(),same_model_error_correlation=True,expert_certified=False,production_approved=False,original_reference_unchanged=sha(SILVER/'reference.jsonl')==json.loads((SILVER/'manifest.json').read_text())['reference_sha256'])
    jsonl(OUT/'stability/adjudicated-revision-proposals.jsonl',arms);jsonl(OUT/'stability/unresolved.jsonl',missing);write(OUT/'stability/report.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','run','summarize']);a=p.parse_args()
    prepare() if a.command=='prepare' else summarize() if a.command=='summarize' else asyncio.run(run())
