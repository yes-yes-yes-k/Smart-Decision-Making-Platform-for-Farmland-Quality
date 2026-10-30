from scripts.audit_kg_reference_correlated_errors import primary_signature


def test_optional_repeated_mentions_do_not_become_primary_surface_disagreement():
    e=dict(id='a',type='indicator',block_id='chunk',text='土壤 pH',occurrence=0)
    a=dict(entities=[e,dict(e,id='b',occurrence=1)],relations=[])
    b=dict(entities=[dict(e,text='土壤pH')],relations=[])
    assert primary_signature(a)==primary_signature(b)
    b['entities'][0]['text']='土壤PH'
    assert primary_signature(a)!=primary_signature(b)
