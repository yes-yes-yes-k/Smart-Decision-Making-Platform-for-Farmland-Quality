from collections import Counter
import random
import pytest
from framework.knowledge_graph.benchmark_sampling_v2 import sample
from framework.knowledge_graph.acceptance_data import assert_isolation


def fixtures(n=240):
    docs=[];chunks=[]
    for i in range(n):
        docs.append(dict(document_id=i,isolation_group=i,profile=dict(source_kind='academic_paper',language='en',
            body_profile='unreadable' if i==0 else 'readable'),topic_source_folders=['soil']))
        for q in range(4):chunks.append(dict(document_id=i,isolation_group=i,sample_id=f'{i}:{q}',position_quartile=q,text='No effect. Soil increased.'))
    return docs,chunks


def test_full_scale_isolation_quartiles_and_hard_quality_stratum():
    docs,chunks=fixtures();rows,report=sample(docs,chunks,'frozen')
    assert len(rows)==500 and report['counts']==report['targets']
    assert_isolation(rows)
    representative=[r for r in rows if r['track']=='representative']
    assert 0 in {r['document_id'] for r in representative}
    for part,count in [('calibration',15),('test',60)]:
        assert Counter(r['position_quartile'] for r in representative if r['partition']==part)==dict.fromkeys(range(4),count)
    assert all(r['group_inclusion_probability']>0 for r in representative)


def test_input_order_does_not_change_membership():
    docs,chunks=fixtures();before,_=sample(docs,chunks,'fixed')
    random.Random(9).shuffle(docs);random.Random(2).shuffle(chunks)
    after,_=sample(docs,chunks,'fixed')
    assert before==after


def test_short_documents_remain_and_shortfall_is_visible():
    docs,chunks=fixtures(2);chunks=[r for r in chunks if r['position_quartile']==0]
    rows,report=sample(docs,chunks,'short')
    assert len(rows)==2 and report['counts']!=report['targets']
    assert all(0<r['group_partition_inclusion_probability']<=1 for r in rows)
