from framework.knowledge_graph.acceptance_inspection import source_flags,inspect_entity_fragments
from framework.knowledge_graph.evaluation_v4 import digest

def visible(text):return dict(sample_id='s',blocks=[dict(block_id='chunk',kind='chunk',text=text,text_sha256=digest(text))])

def test_pdf_glyph_diagnostic_does_not_invent_unreadability():
    assert 'unmapped_pdf_glyph' in source_flags('soil carbon (cid:17)')
    assert 'unmapped_pdf_glyph' not in source_flags('soil carbon')

def test_wrong_occurrence_is_identified_without_rebinding_or_scoring():
    raw=dict(mentions=[dict(type='indicator',fragment=dict(block_id='chunk',text='土壤pH',occurrence=2))])
    r=inspect_entity_fragments(visible('土壤pH'),raw)[0]
    assert not r['bound'] and r['first_occurrence_is_bindable']
    assert raw['mentions'][0]['fragment']['occurrence']==2

def test_literal_binding_does_not_repair_ocr_and_duplicates_stay_visible():
    raw=dict(mentions=[dict(type='indicator',fragment=dict(block_id='chunk',text=t,occurrence=0)) for t in ('Cnu','Cu','Cnu')])
    r=inspect_entity_fragments(visible('Cnu'),raw)
    assert r[0]['bound'] and not r[1]['bound'] and r[2]['duplicate']
