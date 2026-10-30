import json
from scripts.build_kg_benchmark_references import initial_job,review_job
from framework.knowledge_graph.benchmark_protocol import source_packet


def test_initial_request_cannot_leak_partition_or_previous_answers():
    p=source_packet(dict(sample_id='s',text='土壤pH',document_title='题名'),'manual')
    p.update(old_answer='SECRET_GOLD',partition='SECRET_TEST',sampling_stratum='SECRET_LAYER')
    for role in ['A','B']:
        j=initial_job(p,role,'reference_calibration');message=json.dumps(j['options'],ensure_ascii=False)
        assert 'SECRET_' not in message
        visible=json.loads(j['options']['messages'][1]['content'])
        assert set(visible)=={'sample_id','blocks','output_protocol'}


def test_review_union_hides_votes_reasons_and_old_final_labels():
    p=source_packet(dict(sample_id='s',text='土壤pH',document_title='题名'),'manual')
    raw=dict(decisions=[dict(id='x',type='indicator',decision='include',reason='SECRET_REASON',
        fragment=dict(block_id='chunk',start_cell='c0',end_cell='c3'))],relations=[],normalization=[])
    job=review_job(p,[dict(proposal=raw),dict(proposal=raw)],'reference_calibration')
    message=job['options']['messages'][1]['content'];candidate=json.loads(message)['candidate']
    assert 'SECRET_REASON' not in message and len(candidate['decisions'])==1
    assert 'decision' not in candidate['decisions'][0] and 'reason' not in candidate['decisions'][0]
