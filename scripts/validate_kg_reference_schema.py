"""Fresh synthetic interface controls for required JSON Schema reference fields."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import scripts.run_kg_benchmark_pilot as engine
from scripts.rebuild_kg_extraction_benchmark import OUT,dump
from scripts.review_kg_benchmark_reference import RULES
from scripts.replay_kg_benchmark_reference_review import validate
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_cells import indexed_block
from framework.knowledge_graph.benchmark_rebuild import sha256_file

RUN=OUT/'execution/reference-schema-validation-r1'


def obj(properties):
    return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)


def array(items):return dict(type='array',items=items)


def enum(values):return dict(type='string',enum=list(values))


def response_schema(candidate):
    string=dict(type='string')
    cell=obj(dict(block_id=enum(['chunk','document_title']),start_cell=dict(type='string',pattern=r'^c(0|[1-9][0-9]*)$'),end_cell=dict(type='string',pattern=r'^c(0|[1-9][0-9]*)$')))
    decision=obj(dict(id=enum([d['id'] for d in candidate['decisions']]),decision=enum(['include','exclude','uncertain']),
        entity_type=dict(anyOf=[enum(['indicator','obstacle','measure','standard']),dict(type='null')]),reason=string,evidence=array(cell)))
    additional=obj(dict(id=string,type=enum(['indicator','obstacle','measure','standard']),decision=enum(['include']),reason=string,fragment=cell))
    def reviews(count):
        record=obj(dict(index=dict(type='integer',minimum=0,maximum=max(0,count-1)),status=enum(['supported','unsupported','uncertain']),reason=string,evidence=array(cell)))
        return dict(type='array',items=record,minItems=count,maxItems=count)
    ontology=load_schema(ROOT)
    rel_evidence=obj(dict(**cell['properties'],role=enum(['identity','assertion'])))
    relation=obj(dict(type=enum([r['id'] for r in ontology['relation_types']]),source_id=string,target_id=string,
        modality=enum(['asserted','normative','hypothetical','negated','unknown']),conditions=array(string),
        evidence=array(rel_evidence),review_reason=string))
    masks=obj(dict(task=enum(['entities','relations','normalization']),block_id=enum(['chunk','document_title']),
        status=enum(['unknown','excluded']),reason=string,evidence=array(cell)))
    result=obj(dict(decision_reviews=dict(type='array',items=decision,minItems=len(candidate['decisions']),maxItems=len(candidate['decisions'])),
        additions=array(additional),relation_reviews=reviews(len(candidate['relations'])),add_relations=array(relation),
        normalization_reviews=reviews(len(candidate['normalization'])),mask_overrides=array(masks),
        policy_conflicts=array(obj(dict(issue=string,reason=string)))))
    return dict(type='json_schema',json_schema=dict(name='reference_support_review',strict=True,schema=result))


def controls():
    handbook=(OUT/'protocol-r4/annotation-handbook.md').read_text(encoding='utf-8')
    rows=[]
    for name,text,measure,obstacle,modality in [
        ('new_hypothesis','计划施用稻壳灰以缓解土壤酸化，尚未进行试验。','施用稻壳灰','土壤酸化','hypothetical'),
        ('new_denial','施用秸秆堆肥并没有缓解土壤板结。','施用秸秆堆肥','土壤板结','negated')]:
        p=source_packet(dict(sample_id='schema-control:'+name,text=text,document_title='开发协议控制'),handbook)
        def span(quote):
            start=text.index(quote)
            return dict(block_id='chunk',start_cell='c'+str(start),end_cell='c'+str(start+len(quote)-1))
        candidate=dict(decisions=[dict(id=i,type=t,decision='include',reason='待独立复核',fragment=span(q))
            for i,t,q in [('m','measure',measure),('o','obstacle',obstacle)]],normalization=[],
            relations=[dict(type='addresses',source_id='m',target_id='o',modality=modality,conditions=[],
                            evidence=[dict(**span(text),role='assertion')])])
        p['candidate']=candidate
        source=dict(sample_id=p['sample_id'],blocks=[indexed_block(b) for b in p['blocks']],candidate=candidate)
        options=dict(messages=[dict(role='system',content=handbook+'\n'+RULES),dict(role='user',content=json.dumps(source,ensure_ascii=False))],
            max_tokens=4096,response_format=response_schema(candidate))
        rows.append(dict(id='strict-review:'+p['sample_id'],phase='stability',packet=p,options=options))
    return rows


def main():
    engine.RUN=RUN
    dump(RUN/'budget-approval.json',json.loads((OUT/'execution/pilot-r1/budget-approval.json').read_text(encoding='utf-8')))
    jobs=controls()
    files=[Path(__file__),ROOT/'scripts/review_kg_benchmark_reference.py',ROOT/'scripts/replay_kg_benchmark_reference_review.py',OUT/'protocol-r4/annotation-handbook.md']
    config=dict(model='deepseek-ai/DeepSeek-V4.1-Flash',endpoint='https://api.siliconflow.cn/v1',
        budget_limits=engine.limits(),scope='fresh_synthetic_reference_interface_only_not_formal_acceptance',
        prior_failed_calls_not_retried=True,jobs={j['id']:engine.digest(j) for j in jobs},
        files=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha256_file(p)) for p in files])
    path=RUN/'run-config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('schema_validation_config_frozen')
    if not path.exists():dump(path,config)
    engine.validate_proposal=validate
    print(json.dumps(asyncio.run(engine.execute(jobs,config))))


if __name__=='__main__':main()
