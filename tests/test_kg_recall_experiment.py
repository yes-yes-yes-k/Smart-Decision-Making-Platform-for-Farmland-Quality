import hashlib
from scripts.experiment_kg_recall import decompose


def test_missing_endpoint_is_distinct_from_missing_relation():
    text='liming addresses acidification'
    source=dict(text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),document_kind='academic_paper')
    entities=[dict(name='liming',type='measure'),dict(name='acidification',type='obstacle')]
    row=dict(sample_id='s',index=0,source=source,evaluation_eligible=True,disposition='relations',entities=entities,
        relationships=[dict(source='liming',target='acidification',relation_type='addresses',quote_sha256='x')])
    record=dict(sample_id='s',state='completed',source_text_sha256=source['text_sha256'],artifact=dict(entities=[],relationships=[]))
    report,_=decompose([row],[record])
    assert report['counts']['missing_endpoint']==1
    assert report['counts']['empty_prediction_on_positive']==1
    record['artifact']['entities']=[dict(title=e['name'],entity_type=e['type']) for e in entities]
    report,_=decompose([row],[record])
    assert report['counts']['endpoints_present_relation_missing']==1
    assert report['counts'].get('missing_endpoint',0)==0


def test_source_quality_exclusion_does_not_become_model_error():
    report,details=decompose([dict(evaluation_eligible=False)],[])
    assert report['counts']=={'excluded_source_quality':1}
    assert details==[]
