from pathlib import Path
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from framework.knowledge_graph.benchmark_reference_compile import compile_reference


def test_duplicate_supported_fact_keeps_both_evidence_spans_without_extra_fact():
    p=source_packet(dict(sample_id='x',text='施用石灰缓解土壤酸化。',document_title='结果'),'manual')
    a=dict(block_id='chunk',text='施用石灰',start=0,end=4,occurrence=0)
    b=dict(block_id='chunk',text='土壤酸化',start=6,end=10,occurrence=0)
    q=dict(block_id='chunk',text='施用石灰缓解土壤酸化',start=0,end=10,occurrence=0,role='assertion')
    r=dict(type='addresses',source_id='m',target_id='o',modality='asserted',conditions=[],evidence=[q])
    proposal=dict(entities=[dict(id='m',type='measure',**a),dict(id='o',type='obstacle',**b)],relations=[r,dict(r)],normalization=[],task_masks={t:'applicable' for t in ['entities','relations','normalization']})
    v=dict(materialized_proposal=proposal,errors=[dict(task='relation',error='duplicate_relation')],unresolved=[])
    result=compile_reference(p,v,load_schema(Path(__file__).resolve().parents[1]))
    assert result['reference_ready'] and len(result['materialized_proposal']['relations'])==1
    assert len(v['materialized_proposal']['relations'])==2
    assert result['canonical_fact_groups'][0]['validated_relation_indices']==[0,1]
