"""Small sensitivity check for an ambiguity in the exploratory paired protocol."""
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import write,jsonl,sha
from scripts.verify_kg_annotation_load import cases,target_value
from scripts.verify_kg_annotator_controls import RULES,parse
from scripts.annotate_kg_v4_calibration import contract
from framework.knowledge_graph.evaluation_v4 import digest
from framework.knowledge_graph.evaluation_v4_r3 import validate_r3

OUT=ROOT/'artifacts/knowledge_platform/gold-v4/annotator-neutral-prompt-v1'

async def main():
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env')
    if OUT.exists():raise ValueError('neutral sensitivity run already frozen')
    OUT.mkdir();suite=[c for c in cases() if c['id'] in ('unknown_name','clear_empty')]
    system=RULES.replace('只根据给定短文本完成一个判断，返回JSON对象且只有answer字段，不加解释。','按给定输入完成任务，遵守用户指定的JSON输出协议，不加解释。')
    if '只有answer字段' in system or '完成一个判断' in system:raise ValueError('nonneutral_system')
    model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash')
    jsonl(OUT/'private-answer-key.jsonl',suite)
    write(OUT/'config.json',dict(cases=2,rounds=2,modes=['atomic','full_contract'],maximum_requests=8,retries=0,deadline_seconds=60,
        model=model,temperature=0,max_tokens=2048,enable_thinking=False,system_prompt=system,system_sha256=hashlib.sha256(system.encode()).hexdigest(),
        runner_sha256=sha(Path(__file__)),comparison='neutral system sensitivity only; previously used synthetic controls, not new qualification or corpus evaluation',
        original_results_retained=True,no_automatic_expansion=True))
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url='https://api.siliconflow.cn/v1',max_retries=0,timeout=65,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    sem=asyncio.Semaphore(2);records=[]
    async def one(c,mode,n):
        async with sem:
            visible=dict(sample_id='synthetic:'+c['id'],blocks=[dict(block_id='chunk',kind='chunk',text=c['text'],text_sha256=digest(c['text']))])
            prompt='任务：'+c['task']+'\n输入：'+json.dumps(visible,ensure_ascii=False)
            if mode=='atomic':prompt+='\n只输出 {"answer":...}，没有明示全称则answer为null。'
            else:prompt+='\n返回完整标注，不使用answer字段；无法规范化时unknown且canonical_name=null；A类entity_eligible和relation_eligible都为true，即使没有本体事实。质量、mentions、relations、completeness和notes都保留。输出此schema的实例：'+json.dumps(contract()['json_schema']['schema'],ensure_ascii=False)
            r=dict(id=c['id'],mode=mode,round=n,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),state='failed',correct=False)
            try:
                response=await asyncio.wait_for(client.chat.completions.create(model=model,messages=[dict(role='system',content=system),dict(role='user',content=prompt)],temperature=0,max_tokens=2048,response_format={'type':'json_object'},extra_body={'enable_thinking':False}),timeout=60)
                choice=response.choices[0];r.update(content=choice.message.content,finish_reason=choice.finish_reason,returned_model=response.model,request_id=response.id,usage=response.usage.model_dump() if response.usage else None)
                if choice.finish_reason!='stop':raise ValueError('incomplete_model_response')
                if mode=='atomic':value=parse(choice.message.content,None)
                else:
                    a=validate_r3(visible,json.loads(choice.message.content));r['annotation']=a;value=target_value(c,a)
                r.update(state='completed',answer=value,correct=value==c['expected'])
            except Exception as exc:r['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            records.append(r);write(OUT/(c['id']+'-'+mode+'-'+str(n)+'.json'),r)
            print(json.dumps(dict(id=c['id'],mode=mode,round=n,state=r['state'],correct=r['correct'])),flush=True)
    try:await asyncio.gather(*(one(c,m,n) for n in (1,2) for c in suite for m in ('atomic','full_contract')))
    finally:await client.close()
    jsonl(OUT/'responses.jsonl',records)
    report=dict(requests=len(records),by_mode={m:dict(correct=sum(r['correct'] for r in records if r['mode']==m),total=4,
        failures=dict(Counter(r.get('error') for r in records if r['mode']==m and r['state']!='completed'))) for m in ('atomic','full_contract')},
        reported_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records),v4_expansion_allowed=False,qualification_gate_unchanged=True,
        limitations='two previously used controls; not an independent qualification pass or a clean causal test of model internals')
    write(OUT/'report.json',report);print(json.dumps(report))

if __name__=='__main__':asyncio.run(main())
