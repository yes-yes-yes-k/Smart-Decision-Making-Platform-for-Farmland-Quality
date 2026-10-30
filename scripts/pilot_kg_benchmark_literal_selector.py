"""Matched source probe: exact quotes only, program-derived offsets, no repairs."""
import asyncio
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.run_kg_benchmark_pilot_r3 import check,CONTRACT
from scripts.build_kg_benchmark_references import freeze_config
from scripts.rebuild_kg_extraction_benchmark import OUT,OLD,readlines,lines,dump
from framework.knowledge_graph.benchmark_protocol import load_schema
from framework.knowledge_graph.benchmark_bounded_phase_budget import BoundedPhaseBudget
from framework.knowledge_graph.benchmark_rebuild import sha256_file
from scripts.prepare_kg_benchmark_metadata import current_qualification

RUN=OUT/'execution/literal-selector-pilot-v1';PHASE='semantic_literal_selector_pilot_v1';CAP=300000
AUTH=OUT/'execution/project-budget-authorization-v2.json';ALLOC=OUT/'execution/phase-allocation-v2.json'


def prepare():
    handbook=(ROOT/'docs/knowledge-graph-extraction-benchmark-v2-handbook-r3.md').read_text(encoding='utf-8')
    handbook+='\n选择协议：text必须从本请求原文逐字连续复制，包括内部空格、换行、连写和损坏字符。不能自己补空格、断词或修正拼写。occurrence为该逐字片段从0开始的非重叠出现序号。禁止start/end或字符c编号，程序计算真实坐标。实验室浸提不是农艺措施，图表单位不是指标。关系断言须包含谓词/否定/条件及必要上下文，不能仅重复两个端点词。'
    packets=[dict(p,handbook=handbook,output_protocol='strict_literal_selector_probe_v1') for p in readlines(OUT/'execution/dual-selector-pilot-v1/source-only-inputs.jsonl')]
    keys=readlines(OUT/'execution/dual-selector-pilot-v1/private-control-keys.jsonl')
    ontology=load_schema(ROOT);jobs=[]
    for p in packets:
        source={k:p[k] for k in ['sample_id','blocks','output_protocol']}
        for role in ['A','B']:
            system=handbook+'\n只输出JSON。字段契约如下（不是事实样例）：\n'+json.dumps(CONTRACT,ensure_ascii=False)
            system+='\n本体方向：'+json.dumps(dict(entity_types=ontology['entity_types'],relation_types=ontology['relation_types']),ensure_ascii=False)
            jobs.append(dict(id=role+':'+p['sample_id'],phase=PHASE,packet=p,answer_keys_in_request=False,
                options=dict(messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
                    max_tokens=4096,response_format=dict(type='json_object'))))
    lines(RUN/'source-only-inputs.jsonl',packets);lines(RUN/'private-control-keys.jsonl',keys)
    files=[Path(__file__),AUTH,ROOT/'framework/knowledge_graph/benchmark_bounded_phase_budget.py',
        ROOT/'framework/knowledge_graph/benchmark_protocol_r2.py',ROOT/'scripts/run_kg_benchmark_pilot_r3.py',
        RUN/'source-only-inputs.jsonl',RUN/'private-control-keys.jsonl']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        global_tokens=20000000,global_requests=5000,concurrency=2,phase_cap=CAP,semantic_retries=0,
        purpose='matched_exact_literal_selection_contract_probe_not_bulk_reference_construction',
        paired_input_blocks_identical_to='execution/dual-selector-pilot-v1/source-only-inputs.jsonl',
        expert_certified=False,same_model_error_correlation=True,jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files])
    freeze_config(RUN/'run-config.json',config);return jobs,config


async def run():
    factory=lambda p,**ignored:BoundedPhaseBudget(p,authorization=AUTH,allocation=ALLOC,bounded_phase=PHASE,phase_cap=CAP)
    if factory(OLD/'budget.sqlite3').summary()['inflight']:raise ValueError('another_request_is_inflight')
    jobs,config=prepare();ids={r['document_id'] for r in readlines(OUT/'dataset-v1/samples.jsonl') if any(j['packet']['sample_id']==r['sample_id'] for j in jobs)}
    docs=[r for r in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if r['id'] in ids]
    qualification=current_qualification(docs)
    if set(qualification)!=ids or not all(qualification.values()):raise ValueError('source_qualification_changed')
    dump(RUN/'source-qualification.json',dict(current_public_approved=qualification,read_only=True))
    engine.RUN=RUN;engine.validate_proposal=check;engine.Budget=factory
    engine.limits=lambda:dict(stability=2200000,total=20000000,requests=5000)
    print(json.dumps(await engine.execute(jobs,config)))


if __name__=='__main__':asyncio.run(run())
