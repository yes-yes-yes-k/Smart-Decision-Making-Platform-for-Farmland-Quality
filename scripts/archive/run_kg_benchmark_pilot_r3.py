"""Unified prompt revision with program-declared enums and advisory quality."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,verify_history
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_protocol_r2 import ground
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/pilot-r3';PROTO=OUT/'protocol-r3'
CONTRACT=dict(decisions=[dict(id='unique string',type=['indicator','obstacle','measure','standard'],
    decision=['include','exclude','uncertain'],reason='source-based reason',
    fragment=dict(block_id=['chunk','document_title'],text='literal source',occurrence='integer >=0'))],
    normalization=[],relations=[dict(type='one schema relation id',source_id='included entity id',
    target_id='included entity id',modality=['asserted','normative','hypothetical','negated','unknown'],conditions=[],
    evidence=[dict(block_id=['chunk','document_title'],text='literal source',occurrence='integer >=0',role=['identity','assertion'])])],
    quality=dict(readability=['readable','partial','unreadable'],source_issues=[]),notes=[])


def check(packet,raw,schema):
    if 'task_masks' in raw:
        raise ValueError('annotation_has_no_scoring_exclusion_authority')
    quality=raw.get('quality')
    if not isinstance(quality,dict) or quality.get('readability') not in {'readable','partial','unreadable'} or not isinstance(quality.get('source_issues'),list):
        raise ValueError('advisory_source_quality_required')
    material=dict(raw,task_masks={k:'applicable' for k in ['entities','relations','normalization']})
    result=ground(packet,material,schema)
    return dict(result['protocol'],materialized_proposal=result['proposal'],
        inclusion_decisions=result['decisions'],coordinate_method=result['coordinates'],
        advisory_quality=quality,reference_mask_authority='separate_source_adjudication_only')


def controls(handbook):
    specs=[
        ('lab','用过氧化氢处理分析样品，再用移液器转移。', '实验步骤',[],[], '排除实验试剂和器具'),
        ('medium','小麦锰含量下降，土壤锰含量未变。','结果',
         [('i','indicator','chunk','土壤锰含量',0)],[],'介质边界'),
        ('algorithm','神经网络MAPE降低，分类精度提高。','模型',[],[],'算法属性不是土壤指标'),
        ('instrument','传感器灵敏度提高，检测器噪声降低。','仪器',[],[],'仪器属性排除'),
        ('standard','参考HJ 789—2023《土壤分析导则》实施。','规范引用',
         [('s1','standard','chunk','HJ 789—2023',0),('s2','standard','chunk','土壤分析导则',0)],[], '编号全称分别标'),
        ('title','本文件规定土壤全氮的测定要求。','HJ 789—2023',
         [('s','standard','document_title','HJ 789—2023',0),('i','indicator','chunk','土壤全氮',0)],
         [('prescribes_measurement','s','i','normative')],'身份与断言'),
        ('ocr','土壤样品报告的指标为“土壈pH”，数值为6.2。','检测记录',
         [('i','indicator','chunk','土壈pH',0)],[],'明确介质的可识别OCR表面形式不能改写或误删'),
        ('effect','田间施用腐熟堆肥缓解了土壤板结。','试验结果',
         [('m','measure','chunk','施用腐熟堆肥',0),('o','obstacle','chunk','土壤板结',0)],
         [('addresses','m','o','asserted')],'肯定治理'),
        ('negation','施用腐熟堆肥没有缓解土壤板结。','试验结果',
         [('m','measure','chunk','施用腐熟堆肥',0),('o','obstacle','chunk','土壤板结',0)],
         [('addresses','m','o','negated')],'否定不当肯定'),
        ('plan','拟施用腐熟堆肥来缓解土壤板结，尚无试验结果。','方案',
         [('m','measure','chunk','施用腐熟堆肥',0),('o','obstacle','chunk','土壤板结',0)],
         [('addresses','m','o','hypothetical')],'目的不当既成事实'),
        ('repeat','记录土壤全氮，复测土壤全氮。','测定记录',
         [('i1','indicator','chunk','土壤全氮',0),('i2','indicator','chunk','土壤全氮',1)],[],'保留两个不同位置'),
        ('solution_only','沸石仅用于烧杯中的水溶液吸附试验，未用于土壤治理。','材料试验',[],[],'材料名不推断田间干预')]
    packets=[];keys=[]
    for name,text,title,entities,relations,reason in specs:
        packet=source_packet(dict(sample_id='control-r3:'+name,text=text,document_title=title),handbook)
        packet['output_protocol']='extraction-benchmark-v2-r3'
        raw=dict(decisions=[dict(id=i,type=t,decision='include',reason=reason,
            fragment=dict(block_id=b,text=q,occurrence=o)) for i,t,b,q,o in entities],
            relations=[],normalization=[],quality=dict(readability='readable',source_issues=[]),notes=[])
        for t,s,d,m in relations:
            evidence=[dict(block_id='chunk',text=text,occurrence=0,role='assertion')]
            if name=='title':evidence.append(dict(block_id='document_title',text=title,occurrence=0,role='identity'))
            raw['relations'].append(dict(type=t,source_id=s,target_id=d,modality=m,conditions=[],evidence=evidence))
        checked=check(packet,raw,load_schema(ROOT))
        if not checked['protocol_complete']:raise ValueError('invalid_r3_control_key')
        packets.append(packet);keys.append(dict(sample_id=packet['sample_id'],expected=checked['materialized_proposal'],reason=reason,synthetic=True,formal_acceptance_eligible=False))
    return packets,keys


def prepare():
    verify_history()
    handbook=(ROOT/'docs/knowledge-graph-extraction-benchmark-v2-handbook-r3.md').read_text(encoding='utf-8')
    packets,keys=controls(handbook)
    pilots=readlines(OUT/'protocol/pilot-inputs.jsonl')
    for p in pilots:p.update(handbook=handbook,output_protocol='extraction-benchmark-v2-r3')
    PROTO.mkdir(exist_ok=True)
    for path,rows in [(PROTO/'controls-inputs.jsonl',packets),(PROTO/'private-control-keys.jsonl',keys),(PROTO/'pilot-inputs.jsonl',pilots)]:
        if path.exists() and readlines(path)!=rows:raise ValueError('r3_protocol_frozen')
        if not path.exists():lines(path,rows)
    if (PROTO/'annotation-handbook.md').exists() and (PROTO/'annotation-handbook.md').read_text(encoding='utf-8')!=handbook:raise ValueError('r3_handbook_frozen')
    (PROTO/'annotation-handbook.md').write_text(handbook,encoding='utf-8')
    jobs=[]
    for packet in packets+pilots:
        for role in ['A','B']:
            system=handbook+'\n返回一个JSON对象。type/decision/block_id/modality/role/readability 字段展示的是允许值枚举，只选一个字符串；decisions/relations/evidence 是对象列表，normalization/notes 可为空列表。\nOUTPUT CONTRACT\n'+json.dumps(CONTRACT,ensure_ascii=False)+'\nSCHEMA\n'+json.dumps(load_schema(ROOT),ensure_ascii=False)
            source={k:packet[k] for k in ['sample_id','blocks','output_protocol']}
            options=dict(messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(source,ensure_ascii=False))],max_tokens=4096,response_format=dict(type='json_object'))
            jobs.append(dict(id=role+':'+packet['sample_id'],role=role,phase='stability',packet=packet,options=options))
    dump(RUN/'budget-approval.json',json.loads((OUT/'execution/pilot-r1/budget-approval.json').read_text(encoding='utf-8')))
    paths=[Path(__file__),ROOT/'scripts/run_kg_benchmark_pilot.py',ROOT/'framework/knowledge_graph/benchmark_protocol_r2.py',ROOT/'framework/knowledge_graph/benchmark_protocol.py',PROTO/'annotation-handbook.md',PROTO/'controls-inputs.jsonl',PROTO/'private-control-keys.jsonl',PROTO/'pilot-inputs.jsonl']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',budget_limits=engine.limits(),
        previous_revisions=['r1','r2'],same_model_error_correlation=True,expert_certified=False,
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('r3_configuration_changed')
    if not path.exists():dump(path,config)
    return jobs,config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--max-jobs',type=int,default=24);parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    engine.RUN=RUN;jobs,config=prepare()
    if args.prepare_only:print(json.dumps(dict(jobs=len(jobs),model_calls=0)));return
    if not 0<args.max_jobs<=len(jobs):raise ValueError('invalid_max_jobs')
    engine.validate_proposal=check
    print(json.dumps(asyncio.run(engine.execute(jobs[:args.max_jobs],config))))


if __name__=='__main__':main()
