"""Frozen new controls first, original ten documents only after qualification."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.evaluation_v4 import digest,input_digest
from framework.knowledge_graph.annotation_protocol_r4 import SYSTEM
from framework.knowledge_graph.annotation_tasks_r4 import annotate

BASE=ROOT/'artifacts/knowledge_platform/gold-v4'
OUT=BASE/'calibration/r4'

def controls():
    definitions=[
      dict(id='empty_agenda',text='会议安排在周二下午，地点为四楼会议室。',title='',kind='empty'),
      dict(id='unreadable_scan',text='��� ▒▒ ?◇ �',title='',kind='unreadable'),
      dict(id='soil_chloride',text='该土壤的氯离子含量为18mg/kg。',title='',kind='soil'),
      dict(id='calibrant_chloride',text='校准液的氯离子含量为18mg/kg，没有土壤样品。',title='',kind='empty'),
      dict(id='vortex_reagent',text='检测人员用涡旋振荡混匀试剂，此段没有田间操作。',title='',kind='empty'),
      dict(id='explicit_porosity_alias',text='本节所测土壤属性为土壤孔隙率（SP）。',title='',kind='alias'),
      dict(id='negative_mulch',text='秸秆覆盖未改善该土壤的结构稳定性。',title='',kind='negative'),
      dict(id='affirmed_mulch',text='秸秆覆盖显著改善该土壤的结构稳定性。',title='',kind='affirmed'),
      dict(id='title_identity_only',text='本页仅列会议日程与编制人员。',title='SYN-008 农田改良技术规范',kind='title'),
      dict(id='normative_testing',text='本规范规定必须测定土壤中的氯离子含量。',title='SYN-010 农田检测规范',kind='normative'),
      dict(id='english_property',text='Soil organic matter was measured. Laboratory water was not sampled.',title='',kind='english')]
    return definitions

def visible_control(c):
    blocks=[dict(block_id='chunk',kind='chunk',text=c['text'],text_sha256=digest(c['text']))]
    if c['title']:blocks.append(dict(block_id='document_title',kind='document_title',text=c['title'],text_sha256=digest(c['title'])))
    return dict(sample_id='r4-control:'+c['id'],blocks=blocks)

def control_check(c,result):
    if result['state']!='completed':return False,['task_failure']
    a=result['annotation'];ms=a['mentions'];rs=a['relations'];kind=c['kind'];issues=[]
    if kind=='unreadable':
        if a['quality']['grade']!='C' or a['quality']['entity_eligible'] or a['quality']['relation_eligible']:issues.append('unreadable_quality')
        if ms or rs:issues.append('unreadable_facts')
        return not issues,issues
    if a['quality']['grade']!='A' or not all(a['completeness'].values()):issues.append('readable_task_not_evaluable')
    if kind=='empty' and (ms or rs):issues.append('out_of_scope_facts')
    if kind=='soil':
        if not any(m['type']=='indicator' and m['fragment']['text'] in ('氯离子含量','土壤的氯离子含量') for m in ms):issues.append('soil_indicator_missing')
        if len(ms)!=1 or rs:issues.append('unexpected_soil_facts')
    if kind=='english':
        if not any(m['type']=='indicator' and m['fragment']['text'] in ('Soil organic matter','organic matter') for m in ms):issues.append('english_indicator_missing')
        if len(ms)!=1 or rs:issues.append('unexpected_english_facts')
    if kind=='alias':
        if not any(m['fragment']['text']=='SP' and m['type']=='indicator' and m['normalization_status']=='known' and m['canonical_name']=='土壤孔隙率' for m in ms):issues.append('explicit_alias_not_resolved')
        if rs or any(m['type']!='indicator' for m in ms):issues.append('unexpected_alias_facts')
    if kind in ('negative','affirmed'):
        lookup={m['id']:m for m in ms};target='negated' if kind=='negative' else 'asserted'
        if not any(r['relation_type']=='improves_indicator' and r['modality']==target and lookup[r['source']]['fragment']['text']=='秸秆覆盖' and lookup[r['target']]['fragment']['text'] in ('结构稳定性','土壤的结构稳定性') for r in rs):issues.append('effect_relation_missing_or_wrong')
        if len(ms)!=2 or len(rs)!=1:issues.append('unexpected_effect_facts')
    if kind=='title':
        if not any(m['type']=='standard' and m['context_entity'] for m in ms):issues.append('title_identity_missing')
        if rs or any(m['type']!='standard' for m in ms):issues.append('title_inferred_fact')
    if kind=='normative':
        if not any(r['relation_type']=='prescribes_measurement' and r['modality']=='normative' for r in rs):issues.append('normative_relation_missing')
        if any(m['type'] not in ('standard','indicator') for m in ms):issues.append('normative_wrong_type')
    if kind not in ('alias',) and any(m['normalization_status']!='unknown' or m['canonical_name'] is not None for m in ms):issues.append('unsupported_normalization')
    return not issues,issues

def identity(model):
    return dict(revision='v4-r4',model=model,endpoint='https://api.siliconflow.cn/v1',temperature=0,enable_thinking=False,
        system_sha256=digest(SYSTEM),protocol_sha256=sha(ROOT/'framework/knowledge_graph/annotation_protocol_r4.py'),
        tasks_sha256=sha(ROOT/'framework/knowledge_graph/annotation_tasks_r4.py'),validator_sha256=sha(ROOT/'framework/knowledge_graph/evaluation_v4_r3.py'),
        runner_sha256=sha(Path(__file__)),deadline_seconds=60,quality_max_tokens=512,entity_max_tokens=2048,normalization_max_tokens=1024,relation_max_tokens=1536,
        scope='AI calibration; no expert certification; no automatic 90-document expansion')

async def main(mode,arm):
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env');model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash');config=identity(model);config_sha=digest(json.dumps(config,sort_keys=True))
    OUT.mkdir(exist_ok=True)
    if mode=='pilot':
        gate=json.loads((OUT/'controls/gate.json').read_text(encoding='utf-8'))
        if not gate.get('passed') or gate['config_sha256']!=config_sha:raise ValueError('new_controls_gate_not_passed')
        directory=OUT/('pilot-'+arm);rows=read(BASE/'calibration'/('annotator-'+arm+'.jsonl'))[:10]
        jobs=[dict(id=r['sample_id'],round=1,visible=r) for r in rows];attempts=2
    else:
        directory=OUT/'controls';suite=controls();jobs=[dict(id=c['id'],round=n,visible=visible_control(c),expected=c) for n in (1,2) for c in suite];attempts=1
    directory.mkdir(exist_ok=True)
    path=directory/'config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('immutable_r4_config_changed')
    write(path,config)
    if mode=='controls' and not (directory/'protocol.json').exists():
        jsonl(directory/'private-cases.jsonl',controls())
        write(directory/'protocol.json',dict(cases=11,repetitions=2,expected_results_frozen_before_calls=True,
            gate='all 22 complete annotations pass all predeclared case checks; no retries or threshold relaxation',
            known_names_have_predeclared_valid_surface_variants=True,maximum_requests=88,max_attempts_per_stage=1,
            expected_answers_not_sent=True,pilot_requires_same_config=True))
    records=[];sem=asyncio.Semaphore(2)
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url=config['endpoint'],max_retries=0,timeout=65,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    async def one(job):
        async with sem:
            key=digest(job['id']+':'+str(job['round']));cache=directory/(key+'.json')
            if cache.exists():
                result=json.loads(cache.read_text(encoding='utf-8'))
                if result['config_sha256']!=config_sha:raise ValueError('stale_cached_annotation')
            else:
                async def create(**options):return await asyncio.wait_for(client.chat.completions.create(model=model,temperature=0,extra_body={'enable_thinking':False},**options),timeout=60)
                result=await annotate(job['visible'],create,attempts=attempts)
                result.update(id=job['id'],round=job['round'],config_sha256=config_sha)
                if mode=='controls':result['passed'],result['issues']=control_check(job['expected'],result)
                write(cache,result)
            records.append(result);write(directory/'progress.json',dict(target=len(jobs),completed=len(records),valid=sum(r['state']=='completed' for r in records),passed=sum(r.get('passed',False) for r in records)))
            print(json.dumps(dict(mode=mode,arm=arm,id=job['id'],round=job['round'],state=result['state'],passed=result.get('passed'),errors=result.get('errors'),issues=result.get('issues'))),flush=True)
    try:await asyncio.gather(*(one(j) for j in jobs))
    finally:await client.close()
    jsonl(directory/'responses.jsonl',records)
    if mode=='controls':
        gate=dict(passed=len(records)==22 and all(r['passed'] for r in records),config_sha256=config_sha,cases=11,annotations=22,
            correct=sum(r['passed'] for r in records),expert_certified=False,production_approved=False,real_corpus_quality_not_proven=True,
            tokens=sum(r['usage']['total_tokens'] for r in records))
        write(directory/'gate.json',gate);print(json.dumps(gate))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['controls','pilot']);p.add_argument('--arm',choices=['A','B'],default='A');args=p.parse_args();asyncio.run(main(args.mode,args.arm))
