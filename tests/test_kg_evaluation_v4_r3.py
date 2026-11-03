import copy
import pytest
from framework.knowledge_graph.evaluation_v4 import digest
from framework.knowledge_graph.evaluation_v4_r3 import align_fragment,validate_r3

def fixture():
    text='施用石灰提高土壤pH。'
    v=dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])
    a=dict(quality=dict(grade='A',entity_eligible=True,relation_eligible=True,numeric_eligible=False,reason='readable'),
        mentions=[dict(id='a',type='measure',fragment=dict(block_id='chunk',text='施用石灰',occurrence=0),canonical_name=None,normalization_status='unknown',reason='explicit'),
        dict(id='b',type='indicator',fragment=dict(block_id='chunk',text='土壤pH',occurrence=0),canonical_name=None,normalization_status='unknown',reason='explicit')],
        relations=[dict(source='a',target='b',relation_type='improves_indicator',modality='asserted',evidence=[dict(block_id='chunk',text=text,occurrence=0)],reason='explicit')],
        completeness=dict(entities=True,relations=True),notes='')
    return v,a

def test_whitespace_alignment_restores_actual_characters_and_audits():
    text='chemicalremediation\nreduces metals. chemical remediation'
    blocks={'chunk':dict(text=text)}
    r,a=align_fragment(dict(block_id='chunk',text='chemical remediation reduces metals.',occurrence=0),blocks)
    assert r['text']=='chemicalremediation\nreduces metals.' and a['method']=='whitespace_only_alignment'
    with pytest.raises(ValueError,match='fragment_not_in_visible_input'):
        align_fragment(dict(block_id='chunk',text='Chemical remediation reduces metals.',occurrence=0),blocks)
    with pytest.raises(ValueError,match='fragment_not_in_visible_input'):
        align_fragment(dict(block_id='chunk',text='chemical remediation reduces cadmium.',occurrence=0),blocks)

def test_repeated_occurrence_maps_to_correct_original_location():
    r,a=align_fragment(dict(block_id='chunk',text='a b',occurrence=1),{'chunk':dict(text='ab a b')})
    assert r==dict(block_id='chunk',text='a b',occurrence=0) and a['span_start']==3

def test_empty_readable_relation_task_is_eligible():
    v,a=fixture();a['relations']=[];a['quality']['relation_eligible']=False
    with pytest.raises(ValueError,match='grade_A'):validate_r3(v,a)
    a['quality']['relation_eligible']=True
    assert validate_r3(v,a)['relations']==[]

def test_duplicate_facts_and_title_only_evidence_rejected():
    v,a=fixture();a['relations'].append(copy.deepcopy(a['relations'][0]))
    with pytest.raises(ValueError,match='duplicate_fact'):validate_r3(v,a)
    v,a=fixture();title='施用石灰提高土壤pH';v['blocks'].append(dict(block_id='document_title',kind='document_title',text=title,text_sha256=digest(title)))
    a['relations'][0]['evidence']=[dict(block_id='document_title',text=title,occurrence=0)]
    with pytest.raises(ValueError,match='title_alone'):validate_r3(v,a)

def test_laboratory_method_not_measure_and_generic_indicator_rejected():
    v,a=fixture();v['blocks'][0].update(text='沸水提取 土壤pH',text_sha256=digest('沸水提取 土壤pH'));a['mentions'][0]['fragment']['text']='沸水提取';a['relations']=[]
    with pytest.raises(ValueError,match='laboratory_method'):validate_r3(v,a)
    v,a=fixture();v['blocks'][0].update(text='施用石灰 土壤肥沃',text_sha256=digest('施用石灰 土壤肥沃'));a['mentions'][1]['fragment']['text']='土壤肥沃';a['relations']=[]
    with pytest.raises(ValueError,match='generic_description'):validate_r3(v,a)
