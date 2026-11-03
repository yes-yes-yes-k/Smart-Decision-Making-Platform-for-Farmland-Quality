import copy
import hashlib
import pytest
from scripts.repair_legacy_graph_evidence import repair_graph_evidence


def fixture(quote='ab c',content='a b\nc'):
    old={'document_id':1,'page':1,'quote':quote,'evidence_id':'legacy:1'}
    graph={'relations':[{'id':'r1','evidence':[old]}]}
    chunks=[{'content':content,'metadata':{'document_id':1,'page':1,'chunk_index':0,'visibility_scope':'public','content_sha256':'a'*64}}]
    docs={1:{'file_hash':'a'*64,'source_hash_verified':True}}
    return graph,chunks,docs


def test_exact_span_uses_real_whitespace_and_keeps_original_unchanged():
    graph,chunks,docs=fixture();original=copy.deepcopy(graph)
    repaired,audit=repair_graph_evidence(graph,chunks,docs,{})
    row=repaired['relations'][0]['evidence'][0]
    assert row['quote']=='a b\nc'
    assert chunks[0]['content'][row['span_start']:row['span_end']]==row['quote']
    assert row['quote_sha256']==hashlib.sha256(row['quote'].encode()).hexdigest()
    assert row['content_sha256']==docs[1]['file_hash']
    assert graph==original and audit[0]['mode']=='exact_whitespace_normalized'


def test_paraphrase_is_never_fuzzy_approved_without_review_plan():
    graph,chunks,docs=fixture(quote='different summary')
    with pytest.raises(ValueError,match='manual_source_review_required'):
        repair_graph_evidence(graph,chunks,docs,{})


def test_reviewed_cross_page_context_has_real_spans_on_both_pages():
    graph,chunks,docs=fixture(quote='reviewed paraphrase')
    second=copy.deepcopy(chunks[0]);second['metadata'].update(page=2,chunk_index=1);second['content']='continuation'
    chunks.append(second)
    plan={'legacy:1':{'review_reason':'Reviewed both source pages','locators':[{'page':1,'chunk_index':0},{'page':2,'chunk_index':1}]}}
    repaired,_=repair_graph_evidence(graph,chunks,docs,plan)
    rows=repaired['relations'][0]['evidence']
    assert [row['page'] for row in rows]==[1,2]
    assert rows[1]['quote']=='continuation'
    assert len({row['evidence_id'] for row in rows})==2


@pytest.mark.parametrize('failure',['unverified','private','conflicting_hash'])
def test_unsafe_sources_are_rejected(failure):
    graph,chunks,docs=fixture()
    if failure=='unverified':docs[1]['source_hash_verified']=False
    if failure=='private':chunks[0]['metadata']['visibility_scope']='private'
    if failure=='conflicting_hash':chunks[0]['metadata']['content_sha256']='b'*64
    with pytest.raises(ValueError):repair_graph_evidence(graph,chunks,docs,{})
