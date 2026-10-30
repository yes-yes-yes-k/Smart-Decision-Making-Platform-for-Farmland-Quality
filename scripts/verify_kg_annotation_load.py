"""Pre-registered paired synthetic controls: atomic judgment vs full annotation protocol."""
import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import write,jsonl,sha
from scripts.verify_kg_annotator_controls import RULES,parse
from scripts.annotate_kg_v4_calibration import contract
from framework.knowledge_graph.evaluation_v4 import digest
from framework.knowledge_graph.evaluation_v4_r3 import validate_r3

OUT=ROOT/'artifacts/knowledge_platform/gold-v4/annotator-protocol-load-v1'

def cases():
    return [
      dict(id='unknown_name',text='土壤指标RZ9的数值为12。原文没有解释RZ9的全称。',title='',
        task='将指标RZ9规范化为输入明示的全称，不能确定返回null。',expected=None,target='RZ9'),
      dict(id='known_name',text='本节测定土壤可利用水容量（AWC）。',title='',
        task='将缩写AWC规范化为输入明示的中文全称。',expected='土壤可利用水容量',target='AWC'),
      dict(id='clear_empty',text='会议安排在星期五上午，地点是二楼会议室。',title='',
        task='判断输入是可评且无本体事实evaluable_empty，还是信息不足unreadable。',expected='evaluable_empty',target=''),
      dict(id='laboratory_only',text='实验室将消解液进行离心分离，不涉及任何田间管理或治理措施。',title='',
        task='判断候选离心分离是田间措施measure，还是out_of_scope。',expected='out_of_scope',target='离心分离'),
      dict(id='negative_relation',text='试验表明，施用堆肥未改善土壤团聚体稳定性。',title='',
        task='判断施用堆肥改善土壤团聚体稳定性的语气。此控制必须保留否定关系为negated，不当作肯定正例。',expected='negated',target=''),
      dict(id='title_not_fact',text='会议议程将在下午公布。',title='施用堆肥改良土壤技术',
        task='判断题名中的施用堆肥改良土壤这一关系是否有正文支持，支持则asserted，否则unsupported。',expected='unsupported',target='')]

def target_value(case,annotation):
    if case['id'] in ('unknown_name','known_name'):
        mentions=[m for m in annotation['mentions'] if m['fragment']['text']==case['target']]
        if not mentions:raise ValueError('target_mention_omitted')
        values={m['canonical_name'] for m in mentions}
        if len(values)!=1:raise ValueError('conflicting_target_normalization')
        return next(iter(values))
    if case['id']=='clear_empty':
        q=annotation['quality'];comp=annotation['completeness']
        return 'evaluable_empty' if q['entity_eligible'] and q['relation_eligible'] and comp['entities'] and comp['relations'] and not annotation['mentions'] and not annotation['relations'] else 'not_evaluable_empty'
    if case['id']=='laboratory_only':
        return 'measure' if any(m['type']=='measure' and m['fragment']['text']==case['target'] for m in annotation['mentions']) else 'out_of_scope'
    if case['id']=='negative_relation':
        ms={m['id']:m for m in annotation['mentions']}
        rs=[r for r in annotation['relations'] if r['relation_type']=='improves_indicator' and ms[r['source']]['fragment']['text']=='施用堆肥' and ms[r['target']]['fragment']['text']=='土壤团聚体稳定性']
        if not rs:raise ValueError('explicit_negative_relation_omitted')
        return rs[0]['modality']
    return 'asserted' if any(r['modality'] in ('asserted','normative') for r in annotation['relations']) else 'unsupported'

async def main():
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env')
    if OUT.exists():raise ValueError('protocol-load comparison already exists')
    OUT.mkdir();suite=cases();jsonl(OUT/'private-answer-key.jsonl',suite)
    model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash')
    config=dict(model=model,rounds=2,modes=['atomic','full_contract'],cases=6,max_requests=24,max_tokens=2048,
        temperature=0,enable_thinking=False,deadline_seconds=60,retries=0,runner_sha256=sha(Path(__file__)),
        answer_key_sha256=sha(OUT/'private-answer-key.jsonl'),system_rules_sha256=hashlib.sha256(RULES.encode()).hexdigest(),
        comparison='same visible source/task and system rules; output protocol and associated instruction length differ',
        caveat='not a pure prompt-length experiment; targeted common-field correctness and full-form validity are separately measured',
        no_v4_source_or_old_predictions=True,qualification_gate_unchanged=True,no_automatic_expansion=True)
    write(OUT/'config.json',config)
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url='https://api.siliconflow.cn/v1',max_retries=0,timeout=65,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    records=[];sem=asyncio.Semaphore(3)
    async def one(c,mode,n):
        async with sem:
            blocks=[dict(block_id='chunk',kind='chunk',text=c['text'],text_sha256=digest(c['text']))]
            if c['title']:blocks.append(dict(block_id='document_title',kind='document_title',text=c['title'],text_sha256=digest(c['title'])))
            visible=dict(sample_id='synthetic:'+c['id'],blocks=blocks)
            prompt='任务：'+c['task']+'\n可见输入：'+json.dumps(visible,ensure_ascii=False)
            if mode=='atomic':prompt+='\n仅回答目标判断，返回 {"answer":...}，无法确定规范全称时answer为null。'
            else:
                prompt+='\n同时完成完整标注表单，不使用answer字段。mentions逐字片段按出现序号绑定。unknown规范名必须null。A质量两个任务均可评，即使无事实；B/C按不确定性填写。正文与题名分开，不把实验室方法当田间措施。方向：improves_indicator为measure->indicator；prescribes_measurement为standard->indicator。否定关系按本控制要求保留negated。输出如下JSON schema的实例：'+json.dumps(contract()['json_schema']['schema'],ensure_ascii=False)
            r=dict(id=c['id'],mode=mode,round=n,prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),state='failed',target_correct=False,usable_correct=False)
            try:
                response=await asyncio.wait_for(client.chat.completions.create(model=model,messages=[dict(role='system',content=RULES.replace('返回JSON对象且只有answer字段，不加解释。','遵守任务指定的JSON输出协议，不加解释。')),dict(role='user',content=prompt)],
                    temperature=0,max_tokens=2048,response_format={'type':'json_object'},extra_body={'enable_thinking':False}),timeout=60)
                choice=response.choices[0];r.update(content=choice.message.content,finish_reason=choice.finish_reason,returned_model=response.model,request_id=response.id,usage=response.usage.model_dump() if response.usage else None)
                if choice.finish_reason!='stop':raise ValueError('incomplete_model_response')
                if mode=='atomic':value=parse(choice.message.content,None)
                else:
                    annotation=validate_r3(visible,json.loads(choice.message.content));r['annotation']=annotation;value=target_value(c,annotation)
                r.update(state='completed',answer=value,target_correct=value==c['expected'],usable_correct=value==c['expected'])
            except Exception as exc:r['error']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            records.append(r);write(OUT/(c['id']+'-'+mode+'-'+str(n)+'.json'),r)
            print(json.dumps(dict(id=c['id'],mode=mode,round=n,state=r['state'],correct=r['target_correct'])),flush=True)
    try:await asyncio.gather(*(one(c,mode,n) for n in (1,2) for c in suite for mode in ('atomic','full_contract')))
    finally:await client.close()
    jsonl(OUT/'responses.jsonl',sorted(records,key=lambda r:(r['id'],r['mode'],r['round'])))
    report=dict(requests=len(records),by_mode={mode:dict(correct=sum(r['usable_correct'] for r in records if r['mode']==mode),total=12,
        invalid_or_failed=sum(r['state']!='completed' for r in records if r['mode']==mode),errors=dict(Counter(r.get('error') for r in records if r['mode']==mode and r['state']!='completed'))) for mode in ('atomic','full_contract')},
        reported_tokens=sum((r.get('usage') or {}).get('total_tokens',0) for r in records),v4_expansion_allowed=False,expert_certified=False,
        inference_scope='small paired protocol comparison; no claim of statistical significance or independent semantic accuracy')
    write(OUT/'report.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
