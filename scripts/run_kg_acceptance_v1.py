"""Frozen internal acceptance workflow. Final test execution requires approved thresholds."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime,UTC
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_budget import Budget,BudgetStop
from framework.knowledge_graph.annotation_tasks_r5 import annotate
from framework.knowledge_graph.evaluation_v4 import input_digest
from framework.knowledge_graph.acceptance_paths import active_output,shared_budget

OUT=active_output(ROOT)
SILVER=ROOT/'artifacts/knowledge_platform/gold-v4/silver-v1'

def shared_budget_path():return shared_budget(ROOT,OUT)
POLICY='''仅按可见原文标注，不修OCR。标代表性实体清单，同一表面形式同块通常选首个明确位置，不穷尽重复提及。土壤指标必须明确为土壤属性，食品、植物、水、产品、试剂和材料属性不能混入。土壤实验干预可算措施，分析准备和材料制造不算。题名主要提供标准身份；无编号或标准身份佐证时，不仅凭方法名猜标准；论文题名不补正文事实。目录和参考文献不当正文事实。丰度升降、显著性和模型精度不等于改善；不拆分联合处理效果。未知缩写不展开；只有明示等价才规范化。损坏正文保留可读候选，质量建议不得阻止实体及关系阶段。'''

def immutable(path,value):
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8'))!=value:raise ValueError('immutable_configuration_changed:'+path.name)
    else:write(path,value)

def freeze():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    OUT.mkdir(parents=True,exist_ok=True)
    files=[SILVER/'reference.jsonl',SILVER/'manifest.json',SILVER/'source-adjudications.jsonl',
        ROOT/'framework/knowledge_graph/silver_adjudication.py',ROOT/'framework/knowledge_graph/evaluation_v4_scoring.py',
        ROOT/'framework/knowledge_graph/annotation_tasks_r5.py',ROOT/'framework/knowledge_graph/annotation_tasks_r41.py',
        ROOT/'framework/knowledge_graph/annotation_tasks_r4.py',ROOT/'framework/knowledge_graph/annotation_protocol_r4.py',
        ROOT/'framework/knowledge_graph/acceptance_budget.py',ROOT/'docs/knowledge-graph-v4-silver-r5.md']
    immutable(OUT/'development-freeze.json',dict(files=[dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in files],
        reference_samples=100,reference_read_only=True,legacy_exposure=True,expert_certified=False))
    config=dict(version='internal-acceptance-v1',endpoint='https://api.siliconflow.cn/v1',
        model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4.1-Flash'),temperature=0,enable_thinking=False,
        seed='acceptance-v1-20261027',policy=POLICY,token_limits=dict(stability=1000000,total=10000000),request_limit=5000,
        concurrency=2,transient_retries=1,timeout_seconds=60,final_test_requires_user_confirmed_thresholds=True,
        same_provider_error_correlation=True,expert_certified=False,production_approved=False)
    immutable(OUT/'run-config.json',config)
    rows=read(SILVER/'reference.jsonl')
    path=OUT/'stability/inputs.jsonl'
    if path.exists():
        if read(path)!=[r['visible_input'] for r in rows]:raise ValueError('stability_inputs_changed')
    else:path.parent.mkdir(exist_ok=True);jsonl(path,[r['visible_input'] for r in rows])
    print('Frozen 100 development references and source-only stability inputs',flush=True)

def verify_freeze():
    f=json.loads((OUT/'development-freeze.json').read_text(encoding='utf-8'))
    for row in f['files']:
        if sha(ROOT/row['path'])!=row['sha256']:raise ValueError('frozen_dependency_changed:'+row['path'])

def ensure_remote_enabled():
    path=OUT/'remote-policy.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8')).get('suspended_by_user'):
        raise ValueError('cloud_calls_suspended_by_user')
    status=OUT/'provider-status.json'
    if status.exists() and json.loads(status.read_text(encoding='utf-8')).get('available') is False:
        raise ValueError('provider_unavailable_recheck_required_before_remote_work')

async def run_stability():
    from dotenv import load_dotenv
    from openai import AsyncOpenAI,APITimeoutError,APIConnectionError,RateLimitError,InternalServerError
    import httpx
    load_dotenv(ROOT/'.env');verify_freeze();ensure_remote_enabled()
    config=json.loads((OUT/'run-config.json').read_text(encoding='utf-8'))
    budget=Budget(shared_budget_path());sem=asyncio.Semaphore(2);directory=OUT/'stability/responses';directory.mkdir(exist_ok=True)
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url=config['endpoint'],max_retries=0,timeout=60,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    stopped=False
    async def one(i,visible):
        nonlocal stopped
        async with sem:
            path=directory/f'{i:03}.json'
            if path.exists():return
            if stopped:return
            async def create(**options):
                nonlocal stopped
                if stopped:raise BudgetStop('budget_stopped')
                options['messages'][0]['content']+='\n'+config['policy']
                for retry in range(2):
                    try:attempt=budget.reserve('stability',f'relabel:{i}',options)
                    except BudgetStop:stopped=True;raise
                    try:
                        response=await client.chat.completions.create(model=config['model'],temperature=0,extra_body={'enable_thinking':False},**options)
                        budget.finish(attempt,response.usage);return response
                    except BaseException as exc:
                        budget.finish(attempt,error=type(exc).__name__)
                        if retry==0 and isinstance(exc,(APITimeoutError,APIConnectionError,RateLimitError,InternalServerError)):
                            await asyncio.sleep(1);continue
                        raise
            result=await annotate(visible,create,attempts=1)
            result.update(index=i,source_only_relabel=True,old_answers_in_prompt=False,run_config_sha256=sha(OUT/'run-config.json'))
            write(path,result)
            completed=len(list(directory.glob('*.json')))
            write(OUT/'stability/progress.json',dict(target=100,attempted_samples=completed,budget=budget.summary(),budget_stopped=stopped,updated_at=datetime.now(UTC).isoformat()))
            print(json.dumps(dict(index=i,state=result['state'],completed=completed,budget=budget.summary()),ensure_ascii=False),flush=True)
    try:await asyncio.gather(*(one(i,v) for i,v in enumerate(read(OUT/'stability/inputs.jsonl'))))
    finally:await client.close()
    records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(directory.glob('*.json'))]
    jsonl(OUT/'stability/responses.jsonl',records)
    write(OUT/'stability/run-state.json',dict(state='budget_exhausted' if stopped else 'finished',attempted=len(records),target=100,budget=budget.summary(),background_running=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','stability']);a=p.parse_args()
    freeze() if a.command=='freeze' else asyncio.run(run_stability())
