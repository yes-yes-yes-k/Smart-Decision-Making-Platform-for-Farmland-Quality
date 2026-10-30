"""Bounded, staged r3 AI calibration. Expansion requires a separately reviewed pilot gate."""
import argparse
import asyncio
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from scripts.annotate_kg_v4_calibration import contract
from framework.knowledge_graph.evaluation_v4 import input_digest
from framework.knowledge_graph.evaluation_v4_r3 import validate_r3
from framework.knowledge_graph.schema import load_graph_schema

BASE=ROOT/'artifacts/knowledge_platform/gold-v4'
R3=BASE/'calibration/r3'
RULES='''你是独立AI标注者。只使用可见chunk和document_title，不看旧标签、预测或另一标注者结果。
原文mention与规范名分开；复制原文片段并给从0起的出现序号。不要恢复OCR字形或扩写缩写。可保留未知规范化：normalization_status=unknown且canonical_name=null。
indicator是可测土壤/耕地属性；产品、水体、植物、葡萄糖校准液中的分析物不当成土壤指标。泛称“土壤肥沃”不标indicator。
obstacle是土壤退化、约束或污染，不是裸化学元素。measure是田间管理/治理措施，沸水提取、PCR、分光光度法、仪器、试剂、数学模型不是治理措施。
standard可为编号或具名标准/政策。标题可提供文档身份和显式mention；不能只凭标题主题建立治理/测定事实。
只标最小充分mention；同一正文标准编号与正文全称可各标一次，题名标准另标一次；其余相同指代同一类型通常只选首个明确occurrence。不同指代或不同关系证据确需不同occurrence时再增加。不为了数量重复所有词。
质量A=本任务可完整判断，因此entity_eligible和relation_eligible均true，即使没有实体或关系。B=有可读信息但部分任务不可判断，分别说明。C=信息不足，所有eligible=false。无事实不是不可评；不确定时completeness=false说明原因。
明确可读且无本体关系可返回空关系。前人明确陈述可标，假设、可能、研究目的、否定效果不可当肯定改善。联合措施效果不分给单项。
关系证据可多片段，必须有正文谓词支持，不能仅题名；不要引用整块，选择充分条款。原文空白差异可由程序审计定位，非空白字符必须完全一致。
所有判断理由不超过30个汉字，notes只写主要不确定性。不要发明不存在的内容以满足结构。'''

def config_for(arm):
    return dict(revision='v4-r3',arm=arm,model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash'),
        input_sha256=sha(BASE/'calibration'/('annotator-'+arm+'.jsonl')),
        rules_sha256=hashlib.sha256(RULES.encode()).hexdigest(),runner_sha256=sha(Path(__file__)),
        validator_sha256=sha(ROOT/'framework/knowledge_graph/evaluation_v4_r3.py'),
        base_validator_sha256=sha(ROOT/'framework/knowledge_graph/evaluation_v4.py'),schema_sha256=load_graph_schema().digest,
        handbook_sha256=sha(ROOT/'docs/knowledge-graph-v4-annotation-handbook.md'),errata_sha256=sha(ROOT/'docs/knowledge-graph-v4-calibration-errata.md'),
        max_tokens_per_call=3072,max_attempts_per_stage=2,request_deadline_seconds=60,
        annotation_identity='same-provider AI arms, separate requests; no expert certification',other_arm_visible=False,legacy_answers_visible=False)

def relation_pool(mentions):
    schema=load_graph_schema();pool=[]
    for s in mentions:
        for t in mentions:
            if s['id']==t['id']:continue
            if s['context_entity'] and t['context_entity']:continue
            for rule in schema.relation_types:
                if schema.allows(rule.type_id,s['type'],t['type']):
                    pool.append(dict(id=len(pool),source=s['id'],target=t['id'],relation_type=rule.type_id,
                        meaning=rule.label,source_mention=s['fragment']['text'],target_mention=t['fragment']['text']))
    return pool

async def run(arm,expand):
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env');config=config_for(arm);config_hash=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    directory=R3/arm;directory.mkdir(parents=True,exist_ok=True)
    if expand:
        gate=json.loads((R3/'pilot-gate.json').read_text(encoding='utf-8'))
        if not gate.get('passed') or gate.get('config_sha256',{}).get(arm)!=config_hash:raise ValueError('pilot_gate_not_passed_for_this_config')
    path=directory/'config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('run_config_changed')
    write(path,config)
    rows=read(BASE/'calibration'/('annotator-'+arm+'.jsonl'));rows=rows if expand else rows[:10]
    records=[];sem=asyncio.Semaphore(2)
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url='https://api.siliconflow.cn/v1',max_retries=0,timeout=65,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))

    async def one(row):
        async with sem:
            path=directory/(input_digest(row)+'.json')
            if path.exists():
                result=json.loads(path.read_text(encoding='utf-8'))
                if result['config_sha256']!=config_hash:raise ValueError('stale_annotation_cache')
            else:
                result=dict(sample_id=row['sample_id'],input_sha256=input_digest(row),config_sha256=config_hash,state='failed',attempts=[],usage=Counter())
                async def call(stage,prompt,fmt,validate):
                    messages=[dict(role='system',content=RULES+'\n标注者 '+arm),dict(role='user',content=prompt)]
                    for attempt in range(2):
                        try:
                            response=await asyncio.wait_for(client.chat.completions.create(model=config['model'],messages=messages,temperature=0,max_tokens=3072,response_format=fmt,extra_body={'enable_thinking':False}),timeout=60)
                            if response.usage:
                                for key in ('prompt_tokens','completion_tokens','total_tokens'):result['usage'][key]+=getattr(response.usage,key,0) or 0
                            choice=response.choices[0];entry=dict(stage=stage,attempt=attempt,content=choice.message.content,finish_reason=choice.finish_reason);result['attempts'].append(entry)
                            if choice.finish_reason!='stop':raise ValueError('incomplete_model_response')
                            answer=json.loads(choice.message.content);value=validate(answer);entry['accepted']=True
                            return answer,value
                        except (ValueError,KeyError,TypeError) as exc:
                            code=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                            if result['attempts']:result['attempts'][-1].update(accepted=False,error=code)
                            if attempt==1:raise ValueError(code) from None
                            messages += [dict(role='assistant',content=result['attempts'][-1]['content'] or '{}'),dict(role='user',content='校验错误：'+code+'。重新检查原文、类型及质量规则，只修正有来源依据的标注。')]
                try:
                    fmt=copy.deepcopy(contract());fmt['json_schema']['schema']['properties']['relations']['maxItems']=0
                    def validate_inventory(a):
                        if a.get('relations'):raise ValueError('entity_stage_must_not_judge_relations')
                        return validate_r3(row,a)
                    answer,annotation=await call('entities_quality','第一阶段：只标实体、规范化未知项和任务质量。relations必须为空，不判断关系。\n可见输入：'+json.dumps(row,ensure_ascii=False),fmt,validate_inventory)
                    result['entity_stage']=annotation
                    pool=relation_pool(annotation['mentions'])
                    result['relation_candidates']=pool
                    if pool and annotation['quality']['relation_eligible']:
                        fragment=contract()['json_schema']['schema']['properties']['mentions']['items']['properties']['fragment']
                        item=dict(type='object',properties=dict(candidate_id=dict(type='integer',enum=[r['id'] for r in pool]),
                            modality=dict(type='string',enum=['asserted','normative','hypothetical','negated','unknown']),evidence=dict(type='array',items=fragment),reason=dict(type='string',maxLength=80)),
                            required=['candidate_id','modality','evidence','reason'],additionalProperties=False)
                        fmt=dict(type='json_schema',json_schema=dict(name='v4r3_relations',strict=True,schema=dict(type='object',properties=dict(relations=dict(type='array',items=item)),required=['relations'],additionalProperties=False)))
                        def resolve(p):
                            if set(p)!={'relations'}:raise ValueError('invalid_relation_output')
                            merged=copy.deepcopy(answer);merged['relations']=[]
                            for r in p['relations']:
                                if set(r)!={'candidate_id','modality','evidence','reason'} or type(r['candidate_id']) is not int or not 0<=r['candidate_id']<len(pool):raise ValueError('invalid_candidate_id')
                                candidate=pool[r['candidate_id']]
                                merged['relations'].append(dict(source=candidate['source'],target=candidate['target'],relation_type=candidate['relation_type'],modality=r['modality'],evidence=r['evidence'],reason=r['reason']))
                            return validate_r3(row,merged)
                        _,annotation=await call('relations','第二阶段：仅选有正文证据的关系候选；规范要求用normative，事实用asserted；不支持则不选，空数组是合法结果。不能仅凭标题、共现或实验试剂建关系。\n可见输入：'+json.dumps(row,ensure_ascii=False)+'\n已标实体：'+json.dumps(annotation['mentions'],ensure_ascii=False)+'\n候选（合法方向不代表事实成立）：'+json.dumps(pool,ensure_ascii=False),fmt,resolve)
                    result.update(state='completed',annotation=annotation)
                except Exception as exc:result['code']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                write(path,result)
            records.append(result)
            write(directory/'progress.json',dict(target=len(rows),completed=len(records),succeeded=sum(r['state']=='completed' for r in records),failed=sum(r['state']=='failed' for r in records)))
            print(json.dumps(dict(arm=arm,completed=len(records),state=result['state'])),flush=True)
    try:await asyncio.gather(*(one(r) for r in rows))
    finally:await client.close()
    jsonl(directory/'responses.jsonl',sorted(records,key=lambda r:r['sample_id']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['A','B'],required=True);p.add_argument('--expand',action='store_true');args=p.parse_args();asyncio.run(run(args.arm,args.expand))
