import copy
import pytest
from framework.knowledge_graph.acceptance_retrieval import FrozenRetrieval,build_prediction_graph,validate_answer
from framework.knowledge_graph.evaluation_v4 import digest
from framework.knowledge_graph.silver_adjudication import build_decision

def fixture():
    source=dict(sample_id='s',document_id=1,document_title='土壤管理',text='翻耕改善结构稳定性。',file_sha256='f'*64,chunk_index=0,page=1,partition='calibration',embedding=[1.,0.])
    visible=dict(sample_id='s',blocks=[dict(block_id=k,kind=k,text=t,text_sha256=digest(t)) for k,t in [('chunk',source['text']),('document_title',source['document_title'])]])
    a=build_decision(visible,dict(entities=[('measure','翻耕'),('indicator','结构稳定性')],relations=[dict(source=0,type='improves_indicator',target=1,evidence=[source['text']])],reason='原文明确给出翻耕改善结构稳定性，有完整依据。'))
    return source,dict(sample_id='s',origin='candidate_extractor',annotation=a)

def test_reference_cannot_build_candidate_graph():
    source,p=fixture();p['origin']='reference'
    with pytest.raises(ValueError,match='only_candidate'):build_prediction_graph([p],{'s':source},'r')

def test_wrong_source_and_duplicate_graph_predictions_blocked():
    source,p=fixture();bad=copy.deepcopy(p);bad['annotation']['input_sha256']='wrong'
    with pytest.raises(ValueError,match='source_mismatch'):build_prediction_graph([bad],{'s':source},'r')
    with pytest.raises(ValueError,match='duplicate_graph'):build_prediction_graph([p,p],{'s':source},'r')

def test_graph_partitions_cannot_mix():
    source,p=fixture();other=dict(source,sample_id='t',partition='test')
    with pytest.raises(ValueError,match='one_partition'):build_prediction_graph([p],{'s':source,'t':other},'r')

def test_real_json_backend_and_vector_arm_both_return_actual_source():
    source,p=fixture();graph=build_prediction_graph([p],{'s':source},'r')
    r=FrozenRetrieval([source],embedding_identity='e1',graph=graph)
    assert r.graph.health()['ready'] and r.graph.health()['relation_count']==1
    for arm in ('vector','graphrag'):
        found=r.retrieve('翻耕', [1.,0.],embedding_identity='e1',arm=arm,partition='calibration')
        assert found==[dict(sample_id='s',text=source['text'])]

def test_graph_unavailable_never_silently_becomes_vector():
    source,p=fixture();r=FrozenRetrieval([source],embedding_identity='e1')
    with pytest.raises(ValueError,match='unavailable_no_vector_fallback'):r.retrieve('q',[1.,0.],embedding_identity='e1',arm='graphrag',partition='calibration')

def test_vector_retrieval_never_reads_other_partition():
    s,p=fixture();t=dict(s,sample_id='t',document_id=2,partition='test')
    r=FrozenRetrieval([s,t],embedding_identity='e1')
    assert [c['sample_id'] for c in r.retrieve('q',[1.,0.],embedding_identity='e1',arm='vector',partition='calibration')]==['s']

def test_changed_embedding_identity_or_nonfinite_query_blocked():
    s,p=fixture();r=FrozenRetrieval([s],embedding_identity='e1')
    with pytest.raises(ValueError,match='identity_mismatch'):r.retrieve('q',[1.,0.],embedding_identity='other',arm='vector',partition='calibration')
    with pytest.raises(ValueError,match='nonfinite'):r.retrieve('q',[float('nan'),0.],embedding_identity='e1',arm='vector',partition='calibration')

def test_citation_must_be_inside_actual_retrieval_prompt():
    s,p=fixture();answer=dict(answer='yes',abstain=False,citations=[dict(sample_id='s',span_start=0,span_end=len(s['text']),text=s['text'])])
    with pytest.raises(ValueError,match='outside_retrieved'):validate_answer(answer,[dict(sample_id='s',text=s['text'][:2])],{'s':s})
    valid=validate_answer(answer,[dict(sample_id='s',text=s['text'])],{'s':s})
    assert valid['citation_bindings_validated']

def test_no_citations_cannot_be_valid_substantive_answer():
    s,p=fixture()
    with pytest.raises(ValueError,match='needs_citation'):validate_answer(dict(answer='yes',abstain=False,citations=[]),[],{'s':s})
