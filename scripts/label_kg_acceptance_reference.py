"""Independent proposal arms and source adjudication for the isolated calibration."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_kg_acceptance_v1 import OUT,verify_freeze,ensure_remote_enabled,shared_budget_path
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_budget import Budget,BudgetStop
from framework.knowledge_graph.annotation_tasks_r5 import annotate
from framework.knowledge_graph.acceptance_remote import run_jobs
from scripts.adjudicate_kg_acceptance_stability import decision_schema,validate_decision,compact

async def proposals(partition):
    from dotenv import load_dotenv
    from openai import AsyncOpenAI,APITimeoutError,APIConnectionError,RateLimitError,InternalServerError
    import httpx
    load_dotenv(ROOT/'.env');verify_freeze();ensure_remote_enabled()
    config=json.loads((OUT/'run-config.json').read_text(encoding='utf-8'));budget=Budget(shared_budget_path())
    directory=OUT/partition/'proposals';directory.mkdir(exist_ok=True);rows=read(OUT/partition/'inputs.jsonl');sem=asyncio.Semaphore(2);stopped=False
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url=config['endpoint'],max_retries=0,timeout=60,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    async def one(i,arm,visible):
        nonlocal stopped
        async with sem:
            path=directory/f'{i:03}-{arm}.json'
            if path.exists():return
            if stopped:return
            async def create(**options):
                nonlocal stopped
                if stopped:raise BudgetStop('budget_stopped')
                options['messages'][0]['content']+='\n'+config['policy']
                for retry in range(2):
                    try:attempt=budget.reserve('reference',f'{partition}:{i}:{arm}',options)
                    except BudgetStop:stopped=True;raise
                    try:
                        r=await client.chat.completions.create(model=config['model'],temperature=0,extra_body={'enable_thinking':False},**options)
                        budget.finish(attempt,r.usage);return r
                    except BaseException as exc:
                        budget.finish(attempt,error=type(exc).__name__)
                        if retry==0 and isinstance(exc,(APITimeoutError,APIConnectionError,RateLimitError,InternalServerError)):
                            await asyncio.sleep(1);continue
                        raise
            result=await annotate(visible,create,attempts=1)
            result.update(index=i,arm=arm,other_arm_visible=False,reference_visible=False,run_config_sha256=sha(OUT/'run-config.json'))
            write(path,result);write(OUT/partition/'proposal-progress.json',dict(target=2*len(rows),saved=len(list(directory.glob('*.json'))),budget=budget.summary(),stopped=stopped))
            print(json.dumps(dict(partition=partition,index=i,arm=arm,state=result['state'],saved=len(list(directory.glob('*.json'))))),flush=True)
    try:await asyncio.gather(*(one(i,arm,v) for i,v in enumerate(rows) for arm in ('A','B')))
    finally:await client.close()
    write(OUT/partition/'proposal-run-state.json',dict(target=2*len(rows),saved=len(list(directory.glob('*.json'))),stopped=stopped,budget=budget.summary()))

async def adjudicate(partition):
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env');verify_freeze();rows=read(OUT/partition/'inputs.jsonl');sources=read(OUT/partition/'samples.jsonl');jobs=[]
    for i,v in enumerate(rows):
        arms=[]
        for arm in ('A','B'):
            p=OUT/partition/'proposals'/f'{i:03}-{arm}.json';arms.append(json.loads(p.read_text(encoding='utf-8')) if p.exists() else {})
        a,b=[r.get('annotation') for r in arms]
        expected=[('old',j) for j in range(len(a['relations']))] if a else []
        expected += [('new',j) for j in range(len(b['relations']))] if b else []
        prompt='根据原文仲裁两份独立请求产生的候选，不能多数投票。old/new仅代表A/B两臂，不是权威或旧参考。重新输出完整代表性实体清单与关系，不能按候选遗漏推断不存在。正文不完整时明确entity_complete/relation_complete=false；排除关系任务时不输出肯定关系。关系端点为输出实体列表零基下标，每个候选关系在relation_reviews逐项判supported/unsupported/uncertain。所有片段必须复制原文，规范化保持unknown。\n原文：'+json.dumps(v,ensure_ascii=False)+'\n候选：'+json.dumps(dict(old=compact(a),new=compact(b),arm_errors=[r.get('errors') for r in arms]),ensure_ascii=False)
        jobs.append(dict(id=f'{partition}-reference:{i}',index=i,phase='reference',prompt=prompt,format=decision_schema(),max_tokens=6144,expected_reviews=expected,source_ids=[v['sample_id']]))
    jsonl(OUT/partition/'reference-arbitration-jobs.jsonl',jobs)
    def validate(job,answer):return validate_decision(rows[job['index']],answer,expected_reviews=[tuple(x) for x in job['expected_reviews']])
    state=await run_jobs(jobs,OUT/partition/'reference-arbitrations',json.loads((OUT/'run-config.json').read_text(encoding='utf-8')),Budget(shared_budget_path()),validate)
    from framework.knowledge_graph.acceptance_data import digest
    reference=[];unresolved=[]
    for i,v in enumerate(rows):
        p=OUT/partition/'reference-arbitrations'/(digest(f'{partition}-reference:{i}')+'.json');r=json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
        if r and r['state']=='completed':reference.append(dict(visible_input=v,annotation=r['validated']['annotation'],source=sources[i],status='AI_arbitrated_reference_proposal'))
        else:unresolved.append(dict(index=i,sample_id=v['sample_id'],reason=r.get('error') if r else 'not_attempted'))
    jsonl(OUT/partition/'reference-proposals.jsonl',reference);jsonl(OUT/partition/'unresolved.jsonl',unresolved)
    write(OUT/partition/'reference-status.json',dict(status='inconclusive' if unresolved else 'pass',samples=len(rows),adjudicated=len(reference),unresolved=len(unresolved),
        frozen_reference=False,same_model_error_correlation=True,expert_certified=False,run=state))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['proposals','adjudicate']);p.add_argument('--partition',choices=['calibration','test'],default='calibration');a=p.parse_args()
    asyncio.run(proposals(a.partition) if a.command=='proposals' else adjudicate(a.partition))
