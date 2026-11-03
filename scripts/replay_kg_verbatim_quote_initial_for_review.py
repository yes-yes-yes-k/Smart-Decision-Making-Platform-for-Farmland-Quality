"""Replay saved initial responses into a neutral, source-visible adjudication request."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.run_kg_verbatim_quote_pilot_v2 import (BASE,FAILURES,CASES,MODEL,review_job,validate_review,expected_score)
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,readlines,dump,lines,budget_snapshot
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=BASE/'source-review-replay-v1'
AUTH=BASE/'remote-authorization.json'
ENDPOINT='https://api.siliconflow.cn/v1'


def locate_options(blocks,span):
    if not isinstance(span,dict):return dict(block_id=None,quote=None,source_positions=[],verbatim_match=False)
    block=span.get('block_id');quote=span.get('quote');hits=[]
    if block in blocks and isinstance(quote,str) and quote:
        pos=0
        while True:
            pos=blocks[block].find(quote,pos)
            if pos<0:break
            hits.append(dict(start=pos,end=pos+len(quote),occurrence=len(hits)));pos+=len(quote)
    return dict(block_id=block,quote=quote,source_positions=hits,verbatim_match=bool(hits))


def source_neutral_union(packet,records):
    blocks={b['block_id']:b['text'] for b in packet['blocks']};entities={};relations={};maps=[]
    for rec in records:
        mapping={};raw=None
        if rec and rec.get('content'):
            try:raw=json.loads(rec['content'])
            except ValueError:pass
        if not isinstance(raw,dict):maps.append(mapping);continue
        for e in raw.get('entities',[]) if isinstance(raw.get('entities'),list) else []:
            obs=locate_options(blocks,e.get('surface'))
            key=(e.get('type'),obs['block_id'],obs['quote'])
            if key not in entities:
                entities[key]=dict(id=f'candE{len(entities):03d}',type=e.get('type'),
                    candidate_surface=dict(block_id=obs['block_id'],quote=obs['quote'],
                        source_positions=obs['source_positions'],verbatim_match=obs['verbatim_match']))
            mapping[e.get('id')]=entities[key]['id']
        for r in raw.get('relations',[]) if isinstance(raw.get('relations'),list) else []:
            ev=[]
            for item in r.get('evidence',[]) if isinstance(r.get('evidence'),list) else []:
                span=item.get('span',item)
                obs=locate_options(blocks,span)
                ev.append(dict(role=item.get('role'),candidate_window=obs))
            source=mapping.get(r.get('source_id'));target=mapping.get(r.get('target_id'))
            fact=dict(type=r.get('type'),source_id=source,target_id=target,modality=r.get('modality'),
                conditions=r.get('conditions'),candidate_evidence=ev)
            key=json.dumps(fact,ensure_ascii=False,sort_keys=True)
            if key not in relations:relations[key]=dict(id=f'candR{len(relations):03d}',**fact)
        maps.append(mapping)
    return dict(entities=list(entities.values()),relations=list(relations.values()))


async def run():
    packetdoc=json.loads((BASE/'source-packets.json').read_text(encoding='utf-8'));packets={p['sample_id']:p for p in packetdoc['cases']}
    cases={r['id']:r for r in CASES};schema=load_schema(ROOT)
    auth=BASE/'remote-authorization.json';authorization=json.loads(auth.read_text(encoding='utf-8'))
    if authorization.get('resumed_by')!='user' or authorization.get('suspended'):raise ValueError('scoped_user_authorization_inactive')
    proposals=BASE/'initial/proposals';reviews=[];inputerrors=[];requestfiles=[]
    for p in packetdoc['cases']:
        pair=[]
        for role in ['A','B']:
            path=proposals/(engine.digest(role+':'+p['sample_id'])+'.json')
            if not path.exists():raise ValueError('initial_response_missing:'+role+':'+p['sample_id'])
            rec=json.loads(path.read_text(encoding='utf-8'));pair.append(rec);requestfiles.append(path)
            if rec['state']!='protocol_valid':inputerrors.append(dict(id=rec['id'],state=rec['state'],error=rec.get('error')))
        union=source_neutral_union(p,pair);job=review_job(p,union,schema,p['handbook'])
        job['options']['messages'][0]['content']+='\n位置候选说明：candidate_surface和candidate_window中的source_positions列出程序对逐字引用找到的全部原文位置；引用无匹配时不要认可该候选，可独立补充正确的原文引用。引用有多个位置时，选择语义上下文支持该实体/断言的位置，并在最终span中给出occurrence。最终给出的quote必须逐字匹配source。'
        reviews.append(job)
    dump(RUN/'input-protocol-replay.json',dict(source_initial_attempts=len(requestfiles),
        prior_initial_states_replayed_from_raw=True,prior_model_outputs_unchanged=True,
        local_error='relation evidence quote spans are nested under evidence.span',
        source_quote_candidates_are_program_located=True,review_candidate_ids_have_no_role_or_votes=True,
        all_cases_have_full_source_review=True,initial_validator_errors=inputerrors))
    files=[Path(__file__),Path(__import__('scripts.run_kg_verbatim_quote_pilot_v2',fromlist=['__file__']).__file__),
        RUN/'input-protocol-replay.json',BASE/'source-packets.json',AUTH]
    config=dict(status='fresh_source_review_over_saved_initials',model=MODEL,endpoint=ENDPOINT,
        stage='independent_source_review',global_tokens=20000000,global_requests=5000,max_concurrency=2,semantic_retries=0,
        jobs={j['id']:engine.digest(j) for j in reviews},
        files=[dict(path=f.relative_to(ROOT).as_posix(),sha256=sha256_file(f)) for f in files+requestfiles])
    cfg=RUN/'run-config.json'
    if cfg.exists() and json.loads(cfg.read_text(encoding='utf-8'))!=config:raise ValueError('replay_review_requests_frozen')
    if not cfg.exists():dump(cfg,config)
    engine.RUN=RUN;engine.validate_proposal=lambda p,r,s:validate_review(p,r,schema)
    engine.Budget=lambda path,**kw:AuthorizedBudgetV2(path,authorization=OUT/'execution/project-budget-authorization-v2.json',allocation=OUT/'execution/phase-allocation-v2.json')
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    result=await engine.execute(reviews,config)
    rows=[];scores=[]
    for p in packetdoc['cases']:
        path=RUN/'proposals'/(engine.digest('review:'+p['sample_id'])+'.json')
        r=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        row=dict(sample_id=p['sample_id'],kind='synthetic_control' if p['sample_id'] in cases else 'known_failure_source',review_state=r['state'] if r else 'missing')
        if r and r.get('protocol'):
            proposal=r['protocol']['materialized_proposal'];row['reviewed_inventory']=dict(entities=len(proposal['entities']),relations=len(proposal['relations']))
            if p['sample_id'] in cases:
                row['control_counts']=expected_score(cases[p['sample_id']],proposal);scores.append(row['control_counts'])
            row['uncertain_items']=sum(x.get('decision')=='uncertain' for k in ['entity_reviews','relation_reviews'] for x in r['protocol']['source_reviews'][k])
        rows.append(row)
    report=dict(status='inconclusive',protocol='verbatim_quote_v2_source_review_checkpoint',
        cases=len(rows),controls=len(cases),known_failure_sources=len(FAILURES),input_initial_responses=len(requestfiles),
        initial_failures_replayed_offline=len(inputerrors),source_review_requests=len(reviews),rows=rows,
        source_adjudication_can_recover_initial_selector_errors=True,original_responses_unchanged=True,
        first_protocol_v1_pilot_not_retroactively_reclassified=True,semantic_support_still_AI_review=True,
        expert_certified=False,same_model_error_correlation=True,formal_acceptance=False,
        budget=budget_snapshot(),api_execute_summary=result)
    dump(RUN/'report.json',report);lines(RUN/'case-results.jsonl',rows)
    print(json.dumps(dict(status=report['status'],requests=len(reviews),rows=rows,budget=report['budget']),ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
