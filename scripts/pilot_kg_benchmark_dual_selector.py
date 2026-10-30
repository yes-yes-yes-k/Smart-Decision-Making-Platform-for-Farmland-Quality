"""Finite source-only contract probe; never edits references or lifts release hold."""
import asyncio
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.run_kg_benchmark_pilot_r3 import check as literal_check
from scripts.build_kg_benchmark_references import initial_job,freeze_config
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,readlines,lines,dump
from framework.knowledge_graph.benchmark_dual_selector import materialize_dual
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_budget_policy_v2 import AuthorizedBudgetV2
from framework.knowledge_graph.acceptance_budget import BudgetStop
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/dual-selector-pilot-v1';PHASE='semantic_selector_pilot_v1';PHASE_CAP=600000
AUTH=OUT/'execution/project-budget-authorization-v2.json';ALLOC=OUT/'execution/phase-allocation-v2.json'

CONTROLS=[
 ('cn_effect','施用石灰缓解土壤酸化。',[('measure','施用石灰'),('obstacle','土壤酸化')],[('addresses','施用石灰','土壤酸化','asserted')]),
 ('en_effect','Liming alleviated soil acidification.',[('measure','Liming'),('obstacle','soil acidification')],[('addresses','Liming','soil acidification','asserted')]),
 ('joined_english','Limingalleviatedsoilacidification.',[('measure','Liming'),('obstacle','soilacidification')],[('addresses','Liming','soilacidification','asserted')]),
 ('laboratory','将土壤样品用盐酸浸提后测定土壤有效磷。',[('indicator','土壤有效磷')],[]),
 ('chart_unit','图表纵轴单位为cmol/kg，测定指标为土壤阳离子交换量。',[('indicator','土壤阳离子交换量')],[]),
 ('generic','本文讨论soil properties这一泛称，不列具体土壤指标。',[],[]),
 ('negation','施用生物炭未提高土壤有机碳含量。',[('measure','施用生物炭'),('indicator','土壤有机碳含量')],[('improves_indicator','施用生物炭','土壤有机碳含量','negated')]),
 ('separate_records','记录：施用生物炭。\n另一篇文献题名：土壤有机碳含量测定。\n两项记录无作用关系说明。',[('measure','施用生物炭'),('indicator','土壤有机碳含量')],[]),
 ('planned','拟施用硅钙肥缓解土壤酸化，尚无试验。',[('measure','施用硅钙肥'),('obstacle','土壤酸化')],[('addresses','施用硅钙肥','土壤酸化','hypothetical')]),
 ('medium','食品样品中的镉含量下降，土壤镉含量未变。',[('indicator','土壤镉含量')],[]),
]


class PilotBudget(AuthorizedBudgetV2):
    def reserve(self,phase,job,options):
        # All pilot calls use this single finite process. BEGIN IMMEDIATE keeps
        # its phase cap, shared global cap and concurrent reservations atomic.
        if phase!=PHASE:raise ValueError('unexpected_pilot_phase')
        reserved=len(json.dumps(options,ensure_ascii=False).encode('utf-8'))+options['max_tokens']+1024
        import time
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=conn.execute('SELECT phase,reserved,charged,state FROM attempts').fetchall()
            used=lambda records:sum(ch if ch is not None else r for p,r,ch,s in records)
            if used([r for r in rows if r[0]==PHASE])+reserved>PHASE_CAP:raise BudgetStop('bounded_semantic_pilot_cap_reached')
            if len(rows)>=self.requests or used(rows)+reserved>self.total:raise BudgetStop('request_or_token_budget_reached')
            if sum(r[3]=='inflight' for r in rows)>=2:raise BudgetStop('global_concurrency_limit')
            return conn.execute('INSERT INTO attempts(phase,job,reserved,state,created) VALUES(?,?,?,?,?)',
                (phase,job,reserved,'inflight',time.time())).lastrowid


def prepare():
    handbook=(OUT/'protocol-r4/annotation-handbook.md').read_text(encoding='utf-8')
    handbook=handbook.replace('fragment 仅含 block_id、start_cell、end_cell。','fragment 必须同时含 block_id、start_cell、end_cell、text。')
    handbook=handbook.replace('不输出text/occurrence/start/end','不输出occurrence/start/end；text必须逐字抄出所选连续片段')
    handbook+='\n本次新契约：所有实体fragment和关系evidence同时提交逐字text与source_cells端点。程序严格交叉核验，二者不一致则整份无效，不自动修正名称或位置。不要删掉词头/词尾、包含列表标点，不能把字符索引合法当语义正确。实验室浸提不是农艺措施；图表单位不是指标；泛称soil properties不是具名指标。关系assertion要含足以判断谓词/否定/条件的完整原文窗口，不能只有端点词。'
    packets=[];keys=[]
    for name,text,entities,relations in CONTROLS:
        p=source_packet(dict(sample_id='dual-control-v1:'+name,text=text,document_title='标注练习'),handbook)
        packets.append(p);keys.append(dict(sample_id=p['sample_id'],entities=entities,relations=relations))
    failed_ids={r['sample_id'] for r in readlines(OUT/'semantic-quality-audit-v1/items.jsonl') if r['judgment']=='fail'}
    for p in readlines(OUT/'dataset-v1/annotation-inputs.jsonl'):
        if p['sample_id'] in failed_ids:packets.append(dict(p,handbook=handbook))
    jobs=[]
    for p in packets:
        for role in ['A','B']:
            job=initial_job(p,role,PHASE)
            example=json.loads(job['options']['messages'][0]['content'].split('下面是字段形式示例，不是待抽取事实，不要照抄示例实体或关系。\n')[1].split('\n允许值枚举：')[0])
            for d in example['decisions']:d['fragment']['text']='逐字片段示例'
            for r in example['relations']:
                for e in r['evidence']:e['text']='逐字断言示例'
            old=job['options']['messages'][0]['content']
            start=old.index('下面是字段形式示例，不是待抽取事实，不要照抄示例实体或关系。\n')+len('下面是字段形式示例，不是待抽取事实，不要照抄示例实体或关系。\n')
            end=old.index('\n允许值枚举：',start)
            job['options']['messages'][0]['content']=old[:start]+json.dumps(example,ensure_ascii=False)+old[end:]
            jobs.append(job)
    lines(RUN/'source-only-inputs.jsonl',packets);lines(RUN/'private-control-keys.jsonl',keys)
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        global_tokens=20000000,global_requests=5000,concurrency=2,phase_cap=PHASE_CAP,
        purpose='bounded_protocol_probe_only_not_resume_batch_or_relabel_reference',semantic_retries=0,
        same_model_error_correlation=True,expert_certified=False,jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in [Path(__file__),AUTH,
            ROOT/'framework/knowledge_graph/benchmark_dual_selector.py',RUN/'source-only-inputs.jsonl',RUN/'private-control-keys.jsonl']])
    freeze_config(RUN/'run-config.json',config)
    return jobs,config


def check(packet,raw,schema):
    resolved=materialize_dual(raw,packet)
    return dict(literal_check(packet,resolved,schema),verbatim_and_cell_agreement=True,semantic_accuracy_not_certified=True)


async def run():
    budget=PilotBudget(OLD/'budget.sqlite3',authorization=AUTH,allocation=ALLOC)
    if budget.summary()['inflight']:raise ValueError('another_request_is_inflight')
    jobs,config=prepare()
    auth=json.loads((OUT/'execution/remote-authorization.json').read_text(encoding='utf-8'))
    if auth.get('suspended'):raise ValueError('public_source_authorization_suspended')
    # The general execution authorization remains active; the failed final
    # construction's separate authorization and release hold stay suspended.
    engine.RUN=RUN;engine.validate_proposal=check
    engine.Budget=lambda p,**ignored:PilotBudget(p,authorization=AUTH,allocation=ALLOC)
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
