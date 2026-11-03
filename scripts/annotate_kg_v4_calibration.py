"""Independent AI calibration annotations, no legacy labels or cross-arm proposals."""
import argparse
import asyncio
from collections import Counter
import json
import logging
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.evaluation_v4 import validate_annotation,input_digest

BASE=ROOT/'artifacts/knowledge_platform/gold-v4'

def contract():
    from framework.knowledge_graph.schema import load_graph_schema
    schema=load_graph_schema()
    def obj(p):return dict(type='object',properties=p,required=list(p),additionalProperties=False)
    string=dict(type='string');reason=dict(type='string',maxLength=120)
    fragment=obj(dict(block_id=dict(type='string',enum=['chunk','document_title']),text=string,occurrence=dict(type='integer',minimum=0)))
    mention=obj(dict(id=string,type=dict(type='string',enum=sorted(schema.entity_type_ids)),fragment=fragment,
        canonical_name=dict(type=['string','null']),normalization_status=dict(type='string',enum=['known','unknown']),reason=reason))
    relation=obj(dict(source=string,target=string,relation_type=dict(type='string',enum=sorted(schema.relation_type_ids)),
        modality=dict(type='string',enum=['asserted','normative','hypothetical','negated','unknown']),evidence=dict(type='array',items=fragment),reason=reason))
    root=obj(dict(quality=obj(dict(grade=dict(type='string',enum=['A','B','C']),entity_eligible=dict(type='boolean'),relation_eligible=dict(type='boolean'),numeric_eligible=dict(type='boolean'),reason=reason)),
        mentions=dict(type='array',items=mention),relations=dict(type='array',items=relation),completeness=obj(dict(entities=dict(type='boolean'),relations=dict(type='boolean'))),notes=dict(type='string',maxLength=300)))
    return dict(type='json_schema',json_schema=dict(name='kg_annotation_v4',strict=True,schema=root))

async def run(arm,run_tag,limit):
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env');directory=BASE/'calibration'/('run-'+arm+'-'+run_tag);directory.mkdir(exist_ok=True)
    rows=read(BASE/'calibration'/('annotator-'+arm+'.jsonl'))
    handbook=(ROOT/'docs/knowledge-graph-v4-annotation-handbook.md').read_text(encoding='utf-8')
    from framework.knowledge_graph.schema import load_graph_schema
    directions='; '.join(f'{r.type_id}: {",".join(r.source_types)} -> {",".join(r.target_types)}' for r in load_graph_schema().relation_types)
    instructions=('你是独立标注者 '+arm+'。只按以下手册从可见输入重新标注，不使用外部资料，不猜测旧标签。'
        '保留所有原文明示的本体实体，孤立实体也标；原文文本必须逐字复制，位置由程序根据 occurrence 定位。'
        '返回单个 JSON 对象，不返回示例占位符。mentions 和 relations 可为空。每个关系端点必须指向已有 mention ID。'
        'normalization_status=unknown 时 canonical_name 必须为 null。reason 尽量简短。'
        '严格方向表：'+directions+'。手册：\n'+handbook)
    config=dict(arm=arm,input_sha256=sha(BASE/'calibration'/('annotator-'+arm+'.jsonl')),handbook_sha256=sha(ROOT/'docs/knowledge-graph-v4-annotation-handbook.md'),
        model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash'),prompt_sha256=__import__('hashlib').sha256(instructions.encode()).hexdigest(),
        module_sha256=sha(ROOT/'framework/knowledge_graph/evaluation_v4.py'),contract=contract(),max_tokens=4096,request_deadline_seconds=60,
        run_tag=run_tag,same_provider_correlated=True,legacy_answers_visible=False,other_arm_visible=False)
    if (directory/'config.json').exists() and json.loads((directory/'config.json').read_text(encoding='utf-8'))!=config:raise ValueError('calibration config changed')
    write(directory/'config.json',config);records=[];sem=asyncio.Semaphore(4)
    if limit:rows=rows[:limit]
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url='https://api.siliconflow.cn/v1',max_retries=0,timeout=150,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    async def one(row):
        async with sem:
            path=directory/(input_digest(row)+'.json')
            if path.exists():result=json.loads(path.read_text(encoding='utf-8'))
            else:
                result=dict(sample_id=row['sample_id'],input_sha256=input_digest(row),state='failed',attempts=[],usage=Counter())
                messages=[dict(role='system',content=instructions),dict(role='user',content=json.dumps(row,ensure_ascii=False))]
                for attempt in range(3):
                    try:
                        response=await asyncio.wait_for(client.chat.completions.create(model=config['model'],messages=messages,temperature=0,max_tokens=4096,response_format=contract(),extra_body={'enable_thinking':False}),timeout=60)
                        if response.usage:
                            for k in ('prompt_tokens','completion_tokens','total_tokens'):result['usage'][k]+=getattr(response.usage,k,0) or 0
                        choice=response.choices[0];entry=dict(attempt=attempt,content=choice.message.content,finish_reason=choice.finish_reason);result['attempts'].append(entry)
                        if choice.finish_reason!='stop':raise ValueError('incomplete_model_response')
                        answer=json.loads(choice.message.content);annotation=validate_annotation(row,answer)
                        result.update(state='completed',annotation=annotation);result.pop('code',None);break
                    except (ValueError,KeyError,TypeError) as exc:
                        code=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                        result['code']=code
                        if result['attempts']:result['attempts'][-1]['error']=code
                        if attempt==2:break
                        messages += [dict(role='assistant',content=result['attempts'][-1]['content'] or '{}'),dict(role='user',content='校验失败：'+code+'。只修正格式、ID或逐字引用；不要发明实体。原文不支持则记 unknown/不完整，返回同一结构 JSON。')]
                    except Exception as exc:result['code']=type(exc).__name__;break
                write(path,result)
            records.append(result)
            write(directory/'progress.json',dict(total=len(rows),completed=len(records),succeeded=sum(r['state']=='completed' for r in records),failed=sum(r['state']=='failed' for r in records)))
            if len(records)%20==0:print(json.dumps(dict(arm=arm,completed=len(records),failed=sum(r['state']=='failed' for r in records))),flush=True)
    try:await asyncio.gather(*(one(row) for row in rows))
    finally:await client.close()
    jsonl(directory/'responses.jsonl',sorted(records,key=lambda r:r['sample_id']))

if __name__=='__main__':
    logging.disable(logging.CRITICAL)
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['A','B'],required=True);p.add_argument('--run-tag',default='r2');p.add_argument('--limit',type=int);args=p.parse_args();asyncio.run(run(args.arm,args.run_tag,args.limit))
