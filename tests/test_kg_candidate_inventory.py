import pytest
from framework.knowledge_graph.candidate_inventory import build_vocabulary,inventory,apply_review

def row(group,split='development'):
    return dict(sample_id=group,source=dict(leakage_group=group,split=split,text='有效磷和速效钾'),evaluation_eligible=True,
        entities=[dict(name='有效磷',type='indicator'),dict(name='原文没有',type='indicator')])

def test_training_excludes_probe_groups_and_nonliteral_labels():
    with pytest.raises(ValueError,match='training_document_leakage'):build_vocabulary([row('probe')],{'probe'})
    with pytest.raises(ValueError,match='training_document_leakage'):build_vocabulary([row('test','test')],set())
    terms=build_vocabulary([row('train')],{'probe'})
    assert len(terms)==1 and terms[0]['name']=='有效磷'
    assert terms[0]['training_groups']==['train']

def test_candidates_preserve_positions_and_unreviewed_items():
    vocabulary=[dict(name='effective phosphorus',type='indicator',document_support=2)]
    text='effective  phosphorus; soil pH'
    rows=inventory(text,vocabulary)
    assert any(r['name']=='effective  phosphorus' for r in rows)
    assert all(text[r['span_start']:r['span_end']]==r['name'] for r in rows)
    reviewed=apply_review(rows,[dict(id=0,status='retained',reason='source verified')])
    assert len(reviewed)==len(rows) and reviewed[1]['review_status']=='needs_review'
    assert not any(r['confirmed_entity'] for r in reviewed)

def test_conflicts_are_preserved_for_review():
    rows=inventory('liming',[dict(name='liming',type='obstacle',document_support=1)])
    assert len(rows)==2 and all(r['review_status']=='needs_review' for r in rows)
