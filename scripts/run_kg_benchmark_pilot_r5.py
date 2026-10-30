"""Three-call reference workflow: blind A/B, then union support adjudication.

Compact selectors preserve every Unicode position. No candidate votes or old
answers enter the third request. All stages use provider JSON Schema constraints.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
import scripts.run_kg_benchmark_pilot_r4 as previous
from scripts.rebuild_kg_extraction_benchmark import OUT,dump,lines,readlines,verify_history
from scripts.review_kg_benchmark_reference import RULES
from scripts.replay_kg_benchmark_reference_review import validate as reference_validate
from framework.knowledge_graph.benchmark_compact_cells import indexed_block,to_linear,from_linear
from framework.knowledge_graph.benchmark_proposal_union import union_proposals
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_rebuild import sha256_file

BASE=OUT/'execution/pilot-r5';PROTO=OUT/'protocol-r5'


def compact_schema(value):
    if isinstance(value,dict):
        return {k:(r'^r(0|[1-9][0-9]*)c[0-9]$' if k=='pattern' and v==r'^c(0|[1-9][0-9]*)$' else compact_schema(v)) for k,v in value.items()}
    if isinstance(value,list):return [compact_schema(v) for v in value]
    return value


def primary_schema():
    def obj(p):return dict(type='object',properties=p,required=list(p),additionalProperties=False)
    def enum(v):return dict(type='string',enum=v)
    def arr(i):return dict(type='array',items=i)
    text=dict(type='string')
    cell=obj(dict(block_id=enum(['chunk','document_title']),start_cell=dict(type='string',pattern=r'^r(0|[1-9][0-9]*)c[0-9]$'),end_cell=dict(type='string',pattern=r'^r(0|[1-9][0-9]*)c[0-9]$')))
    proof=obj(dict(**cell['properties'],role=enum(['identity','assertion'])))
    decision=obj(dict(id=text,type=enum(['indicator','obstacle','measure','standard']),decision=enum(['include','exclude','uncertain']),reason=text,fragment=cell))
    norm=obj(dict(source_id=text,target_id=text,status=enum(['known','unknown']),evidence=arr(proof)))
    relation=obj(dict(type=enum([r['id'] for r in load_schema(ROOT)['relation_types']]),source_id=text,target_id=text,
        modality=enum(['asserted','normative','hypothetical','negated','unknown']),conditions=arr(text),evidence=arr(proof)))
    schema=obj(dict(decisions=arr(decision),normalization=arr(norm),relations=arr(relation),
        quality=obj(dict(readability=enum(['readable','partial','unreadable']),source_issues=arr(text))),notes=arr(text)))
    return dict(type='json_schema',json_schema=dict(name='source_annotation',strict=True,schema=schema))


def check_primary(packet,raw,schema):
    result=previous.check(packet,to_linear(raw),schema)
    ids={d['id'] for d in raw['decisions']}
    for i,n in enumerate(raw['normalization']):
        if n['source_id'] not in ids or n['target_id'] not in ids:
            result['errors'].append(dict(task='normalization',index=i,error='unknown_alias_endpoint'))
    result['protocol_complete']=not result['errors']
    return dict(result,compact_index=True,full_character_coverage=True)


def check_reference(packet,raw,schema):
    compiled=dict(packet,candidate=to_linear(packet['candidate']))
    return dict(reference_validate(compiled,to_linear(raw),schema),compact_index=True,
        full_character_coverage=True,reference_stage_count=3)


def packets():
    controls,pilots,handbook=previous.protocol()
    handbook=handbook.replace('统一标注协议 r4','统一标注协议 r5')
    handbook=handbook.replace('c0/c1等标识','r0c0/r0c1等行列标识')
    handbook+='''
索引传输r5：每行10列，r12的0:字表示r12c0；选择可见行列标识，不手算绝对坐标。所有原文字符均可选，空格换行也保留，程序切原文不重写内容。
实体规范化只记录source_id/target_id/status/evidence（可见实体之间的链接）；无明确等价证据时normalization=[]或unknown，不生成canonical_name，不发布专家canonical registry。
流程：A/B各独立只见原文和手册；第三请求见无票数、无理由的候选并集与原文，独立裁决所有取舍、证据、来源掩码及共同漏项。
'''
    # Two hard real sources supplement the 14 boundary controls. The previous
    # ten-source reference drafts remain available for deterministic replay.
    selected=[p for p in pilots if p['sample_id'].startswith(('rebuild-v2:128:','rebuild-v2:859:'))]
    result=controls+selected
    for p in result:p.update(handbook=handbook,output_protocol='extraction-benchmark-v2-r5')
    PROTO.mkdir(exist_ok=True)
    for path,rows in [(PROTO/'controls-inputs.jsonl',controls),(PROTO/'pilot-inputs.jsonl',selected),
        (PROTO/'private-control-keys.jsonl',readlines(OUT/'protocol-r4/private-control-keys.jsonl'))]:
        if path.exists() and readlines(path)!=rows:raise ValueError('r5_packets_frozen')
        if not path.exists():lines(path,rows)
    path=PROTO/'annotation-handbook.md'
    if path.exists() and path.read_text(encoding='utf-8')!=handbook:raise ValueError('r5_handbook_frozen')
    path.write_text(handbook,encoding='utf-8')
    return result


def prepare(mode):
    verify_history();items=packets();jobs=[]
    previous_records={}
    if mode=='review':
        for path in (BASE/'proposals').glob('*.json'):
            r=json.loads(path.read_text(encoding='utf-8'));previous_records[r['id']]=r
    for p in items:
        source=dict(sample_id=p['sample_id'],blocks=[indexed_block(b) for b in p['blocks']])
        if mode=='proposals':
            roles=['A','B'];fmt=primary_schema()
            system=p['handbook']+'\n只返回满足schema的JSON；normalization无明确可见等价证据时返回[]。\n本体：'+json.dumps(load_schema(ROOT)['relation_types'],ensure_ascii=False)
        else:
            pair=[previous_records.get(role+':'+p['sample_id']) for role in ['A','B']]
            if any(r is None or r['state']!='protocol_valid' for r in pair):raise ValueError('r5_source_proposal_pair_not_valid')
            candidate=union_proposals([r['proposal'] for r in pair])
            p=dict(p,candidate=candidate);source['candidate']=candidate
            fmt=compact_schema(build_reference_schema(candidate,load_schema(ROOT)))
            roles=['review']
            system=p['handbook']+'\n'+RULES+'\n索引使用r行c列格式，不用c绝对序号；所有来源字符均可选。候选并集不含投票或旧参考，不得按多数票裁决。'
        for role in roles:
            options=dict(messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
                max_tokens=4096 if mode=='proposals' else 6144,response_format=fmt)
            jobs.append(dict(id=role+':'+p['sample_id'],role=role,phase='stability',packet=p,options=options))
    run=BASE if mode=='proposals' else OUT/'execution/pilot-r5-reference-review'
    dump(run/'budget-approval.json',json.loads((OUT/'execution/pilot-r1/budget-approval.json').read_text(encoding='utf-8')))
    paths=[Path(__file__),ROOT/'scripts/run_kg_benchmark_pilot.py',ROOT/'scripts/replay_kg_benchmark_reference_review.py',
        ROOT/'scripts/review_kg_benchmark_reference.py',ROOT/'framework/knowledge_graph/benchmark_compact_cells.py',
        ROOT/'framework/knowledge_graph/benchmark_proposal_union.py',ROOT/'framework/knowledge_graph/benchmark_reference_schema.py',
        PROTO/'annotation-handbook.md',PROTO/'controls-inputs.jsonl',PROTO/'pilot-inputs.jsonl',PROTO/'private-control-keys.jsonl']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        mode=mode,reference_stage_count=3,full_character_coverage=True,same_model_error_correlation=True,expert_certified=False,
        budget_limits=engine.limits(),jobs={j['id']:engine.digest(j) for j in jobs},files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in paths])
    path=run/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('r5_config_frozen')
    if not path.exists():dump(path,config)
    return jobs,config


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['proposals','review']);args=parser.parse_args()
    engine.RUN=BASE if args.mode=='proposals' else OUT/'execution/pilot-r5-reference-review'
    jobs,config=prepare(args.mode)
    engine.validate_proposal=check_primary if args.mode=='proposals' else check_reference
    print(json.dumps(asyncio.run(engine.execute(jobs,config))))


if __name__=='__main__':main()
