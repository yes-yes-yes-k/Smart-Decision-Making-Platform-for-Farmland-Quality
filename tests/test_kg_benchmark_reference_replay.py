from pathlib import Path
from framework.knowledge_graph.benchmark_protocol import source_packet,load_schema
from scripts.replay_kg_benchmark_reference_review import validate


def test_evidence_coordinate_replay_derives_positions_without_model_or_label_changes():
    packet=source_packet(dict(sample_id='x',text='施用石灰缓解土壤酸化',document_title='结果'),'manual')
    packet['candidate']=dict(decisions=[dict(id='m',type='measure',decision='include',fragment=dict(block_id='chunk',start_cell='c0',end_cell='c3')),
        dict(id='o',type='obstacle',decision='include',fragment=dict(block_id='chunk',start_cell='c6',end_cell='c9'))],normalization=[],
        relations=[dict(type='addresses',source_id='m',target_id='o',modality='asserted',conditions=[],
            evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c9',role='assertion')])])
    evidence=[dict(block_id='chunk',start_cell='c0',end_cell='c9')]
    raw=dict(decision_reviews=[dict(id=i,decision='include',entity_type=t,reason='来源支持',evidence=evidence) for i,t in [('m','measure'),('o','obstacle')]],
        additions=[],relation_reviews=[dict(index=0,status='supported',reason='来源明确缓解',evidence=evidence)],
        add_relations=[],normalization_reviews=[],mask_overrides=[],policy_conflicts=[])
    result=validate(packet,raw,load_schema(Path(__file__).resolve().parents[1]))
    assert result['reference_ready']
    quote=result['materialized_proposal']['relations'][0]['evidence'][0]
    assert (quote['start'],quote['end'],quote['text'])==(0,10,'施用石灰缓解土壤酸化')
    assert 'start' not in raw['relation_reviews'][0]['evidence'][0]
