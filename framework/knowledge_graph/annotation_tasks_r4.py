"""One source contract, neutral system, four separately validated annotation tasks."""
import copy
import json
from .annotation_protocol_r4 import SYSTEM,object_schema,response_schema,fragment_schema,quality_schema,entity_schema,normalization_schema,resolve_quality,resolve_entities,resolve_normalization
from .evaluation_v4 import input_digest
from .evaluation_v4_r3 import validate_r3
from .schema import load_graph_schema

def relation_pool(mentions):
    result=[];schema=load_graph_schema()
    for s in mentions:
        for t in mentions:
            if s['id']==t['id'] or s['context_entity'] and t['context_entity']:continue
            for r in schema.relation_types:
                if schema.allows(r.type_id,s['type'],t['type']):
                    result.append(dict(id=len(result),source=s['id'],target=t['id'],relation_type=r.type_id,meaning=r.label))
    return result

async def annotate(visible,create,*,attempts=1,quality_advisory=False):
    trace=[];usage=dict(prompt_tokens=0,completion_tokens=0,total_tokens=0);status={};errors={}
    raw=None;annotation=None;normalization_proofs=[]
    source=json.dumps(visible,ensure_ascii=False)
    async def call(stage,prompt,fmt,validator,max_tokens):
        messages=[dict(role='system',content=SYSTEM),dict(role='user',content=prompt+'\n可见输入：'+source)]
        for attempt in range(attempts):
            try:
                response=await create(messages=messages,response_format=fmt,max_tokens=max_tokens)
                if response.usage:
                    for k in usage:usage[k]+=getattr(response.usage,k,0) or 0
                choice=response.choices[0];item=dict(stage=stage,attempt=attempt,content=choice.message.content,finish_reason=choice.finish_reason,
                    returned_model=getattr(response,'model',None),request_id=getattr(response,'id',None));trace.append(item)
                if choice.finish_reason!='stop':raise ValueError('incomplete_model_response')
                value=validator(json.loads(choice.message.content));item['accepted']=True;status[stage]='completed';return value
            except (ValueError,KeyError,TypeError) as exc:
                code=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                if trace and trace[-1]['stage']==stage:trace[-1].update(accepted=False,error=code)
                if attempt+1==attempts:raise ValueError(code) from None
                messages += [dict(role='assistant',content=trace[-1]['content'] or '{}'),dict(role='user',content='该阶段校验失败：'+code+'。只修正有原文依据的本阶段输出。')]
    try:
        try:
            quality=await call('quality','只判断来源可评程度，不输出grade、eligibility布尔值、实体或关系。evaluable=可以判断本体事实存在或不存在；可读但没有事实仍为evaluable。partial=来源部分可读但不能穷尽判断；unreadable=信息不足。只返回entities、relations两个状态和简短reason。',quality_schema(),resolve_quality,512)
        except Exception:
            if not quality_advisory:raise
            status['quality']='failed';errors['quality']='advisory_quality_failed'
            quality=resolve_quality(dict(entities='partial',relations='partial',reason='quality unavailable; source review required'))
        source_quality=copy.deepcopy(quality)
        if quality_advisory:
            # r5 opt-in: model quality never suppresses extraction. Completeness is
            # deliberately unconfirmed until source adjudication sets block masks.
            quality=dict(quality=dict(grade='B',entity_eligible=True,relation_eligible=True,numeric_eligible=False,
                reason='advisory only; all source blocks require adjudication'),completeness=dict(entities=False,relations=False))
        if quality['quality']['grade']=='C':
            raw,annotation=resolve_entities(visible,quality,dict(mentions=[]))
            status.update(entities='not_assessable',normalization='not_assessable',relations='not_assessable')
        else:
            raw,annotation=await call('entities','只找原文明确的实体mention，孤立实体也要保留。不要输出规范名、规范化状态、质量或关系。标完整名词短语，不包括“该/其”等指示词；措施包括原文施用动词。相同概念通常选首个明确出现位置；编号与全称、题名分别标，明确并列的缩写及其全称各标一次。SOC、SOM等明确土壤属性缩写不能因未展开而漏掉。不要把裸元素当障碍，不把已修复土壤自动当仍存在的障碍。返回mentions(type,fragment,reason)。',entity_schema(),lambda a:resolve_entities(visible,quality,a),2048)
            saved=annotation
            if annotation['mentions']:
                try:
                    raw,annotation=await call('normalization','只输出输入中明确的缩写/别名等价映射，不输出状态或null。没有明示等价关系则mappings=[]，本地会保持unknown和null。不要对所有实体复制自身名称，不凭常识扩写缩写。每个映射用证据同时覆盖mention和明示全称。\n已定位mentions：'+json.dumps(annotation['mentions'],ensure_ascii=False),normalization_schema([m['id'] for m in annotation['mentions']]),lambda a:resolve_normalization(visible,raw,a),1024)
                    normalization_proofs=annotation.get('normalization_evidence',[])
                except Exception as exc:status['normalization']='failed';errors['normalization']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__;annotation=saved
            else:status['normalization']='no_mentions'
            pool=relation_pool(annotation['mentions'])
            if pool and quality['quality']['relation_eligible']:
                props=dict(candidate_id=dict(type='integer',enum=[p['id'] for p in pool]),modality=dict(type='string',enum=['asserted','normative','hypothetical','negated','unknown']),evidence=dict(type='array',items=fragment_schema()),reason=dict(type='string',maxLength=80))
                fmt=response_schema('r4_relations',dict(relations=dict(type='array',items=object_schema(props))))
                def resolve(answer):
                    if set(answer)!={'relations'}:raise ValueError('invalid_relation_task_fields')
                    updated=copy.deepcopy(raw);updated['relations']=[]
                    for r in answer['relations']:
                        if set(r)!={'candidate_id','modality','evidence','reason'} or type(r['candidate_id']) is not int or not 0<=r['candidate_id']<len(pool):raise ValueError('invalid_candidate_id')
                        p=pool[r['candidate_id']];updated['relations'].append(dict(source=p['source'],target=p['target'],relation_type=p['relation_type'],modality=r['modality'],evidence=r['evidence'],reason=r['reason']))
                    return updated,validate_r3(visible,updated)
                try:
                    raw,annotation=await call('relations','只判断关系候选是否由正文支持，不更改实体或规范化。合法类型方向不等于事实成立。明确陈述用asserted，规范要求用normative，否定用negated，研究目的或可能性用hypothetical；明确的否定/假设也保留供单独评测，不计肯定正例。纯题名、共现或无支持不选。使用最小充分正文证据，可附题名身份片段。返回relations，未支持则[]。\nmentions：'+json.dumps(annotation['mentions'],ensure_ascii=False)+'\n候选：'+json.dumps(pool,ensure_ascii=False),fmt,resolve,1536)
                except Exception as exc:
                    status['relations']='failed';errors['relations']=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
                    annotation['completeness']['relations']=False
            else:status['relations']='no_candidates' if not pool else 'not_assessable'
        annotation['normalization_evidence']=normalization_proofs
    except Exception as exc:
        failed='quality' if 'quality' not in status else 'entities'
        status[failed]='failed';errors[failed]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    result=dict(sample_id=visible['sample_id'],input_sha256=input_digest(visible),state='completed' if annotation is not None and not errors else 'partial' if annotation is not None else 'failed',
        annotation=annotation,task_status=status,errors=errors,trace=trace,usage=usage,expert_certified=False,production_approved=False)
    if quality_advisory:
        result.update(source_quality_advisory=locals().get('source_quality'),requires_source_adjudication=True,
            state='needs_review' if annotation is not None else 'failed')
    return result
