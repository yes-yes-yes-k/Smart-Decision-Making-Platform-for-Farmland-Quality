"""Small synthetic controls: domain recognition vs structured output vs index selection."""
import asyncio
import json
import os
from pathlib import Path
import sys
from datetime import datetime,UTC
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from framework.knowledge_graph.span_extraction import tokens,span

CASES=[
    dict(id='zh_positive',text='施用石灰提高土壤pH。',expected=['施用石灰','土壤pH'],
        candidates=['施用石灰','土壤pH','有机质','玉米产量']),
    dict(id='en_positive',text='Liming increases soil pH.',expected=['Liming','soil pH'],
        candidates=['Liming','soil pH','soil organic carbon','maize yield']),
    dict(id='negative',text='会议于星期三召开。',expected=[],
        candidates=['会议','星期三','土壤pH','施用石灰'])]

async def main():
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env')
    out=ROOT/'artifacts/knowledge_platform/gold-rebuild-v3/model-capability-controls'
    out.mkdir(exist_ok=True)
    if (out/'responses.jsonl').exists():raise ValueError('control run already exists')
    model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash')
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],
        base_url='https://api.siliconflow.cn/v1',max_retries=0,timeout=90,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    records=[];sem=asyncio.Semaphore(3)
    async def one(case,mode):
        async with sem:
            prompt='Extract all explicit soil-quality indicator and agricultural intervention entity names. No generic crops, meetings or invented names. '
            options={}
            if mode in ('plain','json_object','json_schema'):
                prompt+='Return JSON only: {"entities": ["exact source name"]}. Use [] when none. Source: '+case['text']
                contract=dict(type='object',properties=dict(entities=dict(type='array',items=dict(type='string'))),required=['entities'],additionalProperties=False)
            elif mode=='pointers':
                prompt+='Return JSON {"entities":[{"start":0,"end":1}]} selecting token intervals, start inclusive/end exclusive. Source: '+case['text']+' Tokens: '+json.dumps(tokens(case['text']),ensure_ascii=False)
                contract=dict(type='object',properties=dict(entities=dict(type='array',items=dict(type='object',properties=dict(start=dict(type='integer'),end=dict(type='integer')),required=['start','end'],additionalProperties=False))),required=['entities'],additionalProperties=False)
            else:
                prompt+='Select candidate IDs which occur in source and meet the definition. Return JSON {"entities":[0]}. Source: '+case['text']+' Candidates: '+json.dumps(dict(enumerate(case['candidates'])),ensure_ascii=False)
                contract=dict(type='object',properties=dict(entities=dict(type='array',items=dict(type='integer',enum=list(range(len(case['candidates'])))))),required=['entities'],additionalProperties=False)
            if mode=='json_object':options['response_format']=dict(type='json_object')
            if mode in ('json_schema','pointers','candidate_ids'):
                options['response_format']=dict(type='json_schema',json_schema=dict(name='entity_control',strict=True,schema=contract))
            record=dict(case=case['id'],mode=mode,source=case['text'],prompt=prompt,expected=case['expected'])
            try:
                r=await client.chat.completions.create(model=model,messages=[dict(role='user',content=prompt)],
                    temperature=0,max_tokens=512,extra_body={'enable_thinking':False},**options)
                record.update(content=r.choices[0].message.content,finish_reason=r.choices[0].finish_reason,
                    returned_model=r.model,request_id=r.id,usage=r.usage.model_dump() if r.usage else None)
                try:
                    p=json.loads(record['content']);values=p['entities']
                    if mode=='pointers':values=[span(case['text'],tokens(case['text']),x['start'],x['end'])[0] for x in values]
                    if mode=='candidate_ids':values=[case['candidates'][i] for i in values if type(i) is int and 0<=i<len(case['candidates'])]
                    record.update(resolved=values,exact_match=set(values)==set(case['expected']),state='completed')
                except Exception as exc:record.update(state='invalid_output',error=type(exc).__name__)
            except Exception as exc:record.update(state='request_failed',error=type(exc).__name__)
            records.append(record)
            print(json.dumps(dict(case=case['id'],mode=mode,state=record['state'],exact=record.get('exact_match'))),flush=True)
    try:await asyncio.gather(*(one(c,m) for c in CASES for m in ('plain','json_object','json_schema','pointers','candidate_ids')))
    finally:await client.close()
    (out/'responses.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    summary=dict(created_at=datetime.now(UTC).isoformat(),requested_model=model,synthetic_diagnostic_only=True,
        total=len(records),by_mode={m:dict(correct=sum(r.get('exact_match',False) for r in records if r['mode']==m),total=3) for m in ('plain','json_object','json_schema','pointers','candidate_ids')},
        reported_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__':asyncio.run(main())
