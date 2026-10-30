"""Source-cell selection pilot; no generated entity/evidence quote strings."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.run_kg_benchmark_pilot_r3 as r3
import scripts.adjudicate_kg_benchmark_pilot as arbitration
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,verify_history
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_protocol_r2 import ground
from framework.knowledge_graph.benchmark_cells import indexed_block,materialize
from framework.knowledge_graph.benchmark_rebuild import sha256_file

BASE=OUT/'execution/pilot-r4';PROTO=OUT/'protocol-r4'
EXAMPLE=dict(decisions=[dict(id='e1',type='measure',decision='include',reason='来源理由',
    fragment=dict(block_id='chunk',start_cell='c0',end_cell='c1')),
    dict(id='e2',type='obstacle',decision='include',reason='来源理由',fragment=dict(block_id='chunk',start_cell='c2',end_cell='c3'))],normalization=[],
    relations=[dict(type='addresses',source_id='e1',target_id='e2',modality='asserted',conditions=[],
        evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c1',role='assertion')])],
    quality=dict(readability='readable',source_issues=[]),notes=[])
ENUMS=dict(entity_type=['indicator','obstacle','measure','standard'],decision=['include','exclude','uncertain'],
    evidence_role=['identity','assertion'],modality=['asserted','normative','hypothetical','negated','unknown'],
    readability=['readable','partial','unreadable'])


def check(packet,raw,schema):
    resolved=materialize(raw,packet)
    return dict(r3.check(packet,resolved,schema),source_cell_selection=True,
                model_generated_entity_or_evidence_text=False)


def check_arbitration(packet,raw,schema):
    resolved=materialize(raw,packet)
    return dict(arbitration.check(packet,resolved,schema),source_cell_selection=True,
                model_generated_entity_or_evidence_text=False)


def protocol():
    original=(ROOT/'docs/knowledge-graph-extraction-benchmark-v2-handbook-r3.md').read_text(encoding='utf-8')
    start=original.index('fragment 为 block_id')
    end=original.index('\n\n不修 OCR',start)
    replacement='''fragment 仅含 block_id、start_cell、end_cell。输入的source_cells为每个原文字符提供c0/c1等标识，两个端点均包含在片段中。
直接选择可见端点，不手算、不输出text/occurrence/start/end；程序从原文切片并计算出现序号。所有原文字符都在表中，没有候选词过滤或覆盖限制。
块内c编号只用于当前block_id，不能跨块取端点。空格、换行和损坏字形均有自己的单元格，不能跳过或改写内部字符。
措施只保留干预动作和必要对象，“田间/旱地/温室”等情境或地点限定不入实体片段，必要时记入conditions。'''
    handbook=original[:start]+replacement+original[end:]
    handbook=handbook.replace('evidence 每项也提交逐字片段和出现序号','evidence 每项也提交block_id、start_cell和end_cell')
    handbook=handbook.replace('统一标注协议 r3','统一标注协议 r4')
    packets,keys=r3.controls(handbook)
    for p in packets:p['output_protocol']='extraction-benchmark-v2-r4'
    # New boundary questions alongside the existing development controls.
    for sid,text,measure,obstacle in [
        ('new_location','田间施用白云石缓解了土壤酸化。','施用白云石','土壤酸化'),
        ('new_context','旱地种植绿肥缓解了土壤板结。','种植绿肥','土壤板结')]:
        p=source_packet(dict(sample_id='control-r4:'+sid,text=text,document_title='田间试验结果'),handbook)
        p['output_protocol']='extraction-benchmark-v2-r4'
        raw=dict(decisions=[dict(id=i,type=t,decision='include',reason='原文明示',fragment=dict(block_id='chunk',text=q,occurrence=0))
            for i,t,q in [('m','measure',measure),('o','obstacle',obstacle)]],normalization=[],
            relations=[dict(type='addresses',source_id='m',target_id='o',modality='asserted',conditions=[],
                evidence=[dict(block_id='chunk',text=text,occurrence=0,role='assertion')])],
            quality=dict(readability='readable',source_issues=[]),notes=[])
        expected=r3.check(p,raw,load_schema(ROOT))['materialized_proposal']
        packets.append(p);keys.append(dict(sample_id=p['sample_id'],expected=expected,synthetic=True,
            formal_acceptance_eligible=False,reason='新地点边界控制题'))
    pilots=readlines(OUT/'protocol/pilot-inputs.jsonl')
    for p in pilots:p.update(handbook=handbook,output_protocol='extraction-benchmark-v2-r4')
    PROTO.mkdir(exist_ok=True)
    for path,rows in [(PROTO/'controls-inputs.jsonl',packets),(PROTO/'private-control-keys.jsonl',keys),(PROTO/'pilot-inputs.jsonl',pilots)]:
        if path.exists() and readlines(path)!=rows:raise ValueError('r4_inputs_frozen')
        if not path.exists():lines(path,rows)
    path=PROTO/'annotation-handbook.md'
    if path.exists() and path.read_text(encoding='utf-8')!=handbook:raise ValueError('r4_handbook_frozen')
    path.write_text(handbook,encoding='utf-8')
    return packets,pilots,handbook


def prepare(adjudicate=False):
    verify_history()
    controls,pilots,handbook=protocol()
    packets=controls+pilots;jobs=[]
    responses={}
    if adjudicate:
        for p in (BASE/'proposals').glob('*.json'):
            r=json.loads(p.read_text(encoding='utf-8'));responses[r['id']]=r
    for p in packets:
        source=dict(sample_id=p['sample_id'],blocks=[indexed_block(b) for b in p['blocks']],output_protocol=p['output_protocol'])
        instruction='只返回JSON。下面是字段形式示例，不是待抽取事实，不要照抄示例实体或关系。\n'+json.dumps(EXAMPLE,ensure_ascii=False)+'\n允许值枚举：'+json.dumps(ENUMS,ensure_ascii=False)
        ontology=load_schema(ROOT)
        instruction+='\n本体方向：'+json.dumps(dict(entity_types=ontology['entity_types'],relation_types=ontology['relation_types']),ensure_ascii=False)
        if adjudicate:
            pair={role:responses.get(role+':'+p['sample_id']) for role in ['A','B']}
            if any(r is None for r in pair.values()):raise ValueError('r4_proposal_pairs_incomplete')
            source['proposals']={role:dict(content=r.get('content'),state=r['state']) for role,r in pair.items()}
            instruction+='\n'+arbitration.INSTRUCTIONS+'''
本请求是获准的独立来源裁决，reference_masks可据原文设置unknown/excluded，不受标注者的quality字段限制。
没有关系不是排除理由；原文本身损坏无法判定时，固定unknown并给出source_cells证据即可。
已明确作unknown的规范化或已固定unknown掩码属于已处理的认识不确定性，不再列unresolved；只有未解决的规则冲突/相互矛盾的事实才列unresolved。
所有证据列表（包括rulings/reference_masks/relation_reviews/normalization_reviews）都选block_id/start_cell/end_cell，不生成text或occurrence。
evidence role只能identity/assertion；rulings等纯来源引文可不带role。'''
            roles=['arbitrate']
        else:roles=['A','B']
        for role in roles:
            options=dict(messages=[dict(role='system',content=handbook+'\n'+instruction),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
                max_tokens=6144 if adjudicate else 4096,response_format=dict(type='json_object'))
            jobs.append(dict(id=role+':'+p['sample_id'],role=role,phase='stability',packet=p,options=options))
    run=OUT/'execution'/('pilot-r4-adjudication' if adjudicate else 'pilot-r4')
    dump(run/'budget-approval.json',json.loads((OUT/'execution/pilot-r1/budget-approval.json').read_text(encoding='utf-8')))
    paths=[Path(__file__),ROOT/'scripts/run_kg_benchmark_pilot.py',ROOT/'scripts/run_kg_benchmark_pilot_r3.py',
        ROOT/'scripts/adjudicate_kg_benchmark_pilot.py',ROOT/'framework/knowledge_graph/benchmark_cells.py',
        ROOT/'framework/knowledge_graph/benchmark_protocol_r2.py',PROTO/'annotation-handbook.md',PROTO/'private-control-keys.jsonl',PROTO/'controls-inputs.jsonl',PROTO/'pilot-inputs.jsonl']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',same_model_error_correlation=True,
        expert_certified=False,full_character_coverage=True,adjudicate=adjudicate,budget_limits=engine.limits(),
        jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths])
    path=run/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('r4_run_config_frozen')
    if not path.exists():dump(path,config)
    return run,jobs,config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--adjudicate',action='store_true');parser.add_argument('--max-jobs',type=int,default=28);parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    engine.RUN=OUT/'execution'/('pilot-r4-adjudication' if args.adjudicate else 'pilot-r4')
    run,jobs,config=prepare(args.adjudicate)
    if args.prepare_only:print(json.dumps(dict(jobs=len(jobs),model_calls=0)));return
    if not 0<args.max_jobs<=len(jobs):raise ValueError('invalid_max_jobs')
    engine.validate_proposal=check_arbitration if args.adjudicate else check
    print(json.dumps(asyncio.run(engine.execute(jobs[:args.max_jobs],config))))


if __name__=='__main__':main()
