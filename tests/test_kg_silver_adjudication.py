import asyncio
import copy
import json
from types import SimpleNamespace
import pytest
from framework.knowledge_graph.evaluation_v4 import digest
from framework.knowledge_graph.silver_adjudication import build_decision,literal_fragment,review_routes,score_silver_sample

def visible(text='翻耕改善结构稳定性。',title='土壤治理规范'):
    return dict(sample_id='s',blocks=[dict(block_id=k,kind=k,text=t,text_sha256=digest(t)) for k,t in [('chunk',text),('document_title',title)]])

def decision(**kw):
    d=dict(entities=[('measure','翻耕'),('indicator','结构稳定性')],relations=[dict(source=0,type='improves_indicator',target=1,evidence=['翻耕改善结构稳定性。'])],reason='原文明确给出翻耕改善结构稳定性，逐条确认。')
    return dict(d,**kw)

def test_routes_ignore_model_grade_and_relevance():
    r=review_routes(visible(),dict(grade='C',relevant=False))
    assert r['entity_blocks']==['chunk','document_title'] and r['relation_blocks']==['chunk']
    assert r['blocks_skipped_by_model_quality']==[]

def test_literal_occurrence_is_per_fragment_not_list_index():
    v=visible('甲乙甲')
    assert literal_fragment(v,'chunk','乙')[1]['span_start']==1
    assert literal_fragment(v,'chunk','甲',1)[1]['span_start']==2

def test_anchor_disambiguates_soil_from_plant():
    v=visible('植物Cd，土壤Cd。')
    assert literal_fragment(v,'chunk','Cd',anchor='土壤Cd')[1]['span_start']==7

def test_whitespace_only_no_ocr_repair():
    v=visible('土壤 pH Cnu')
    assert literal_fragment(v,'chunk','土壤pH')[0]['text']=='土壤 pH'
    with pytest.raises(ValueError):literal_fragment(v,'chunk','Cu')

def test_known_normalization_needs_source_proof():
    v=visible('soil carbon (SOC)')
    d=decision(entities=[dict(type='indicator',text='SOC',canonical_name='soil carbon')],relations=[])
    with pytest.raises(ValueError,match='requires_source_proof'):build_decision(v,d)
    d['entities'][0]['normalization_evidence']='soil carbon (SOC)'
    assert build_decision(v,d)['normalization_evidence'][0]['canonical_name']=='soil carbon'

def test_fully_masked_row_never_negative():
    a=build_decision(visible(),decision(relations=[],entity_complete=False,relation_complete=False,title_eligible=False))
    s=score_silver_sample(a,a)
    assert s['mentions'] is None and s['relations'] is None and not s['correct_negative'] and not s['body_correct_negative']

def test_context_does_not_enable_excluded_body():
    a=build_decision(visible(),decision(relations=[],entity_complete=False,relation_complete=False))
    s=score_silver_sample(a,a)
    assert s['chunk_mentions'] is None and s['surface_chunk_mentions'] is None
    assert s['context_mentions'] is not None and s['relations'] is None

def test_reference_masks_also_remove_prediction_false_positives():
    v=visible();gold=build_decision(v,decision(entities=[],relations=[],entity_complete=False,relation_complete=False))
    pred=build_decision(v,decision())
    s=score_silver_sample(gold,pred)
    assert s['mentions']['fp']==0 and s['chunk_mentions'] is None and s['relations'] is None
    assert len(pred['mentions'])==2  # inputs remain immutable

def test_model_quality_cannot_suppress_false_negatives():
    a=build_decision(visible(),decision());p=copy.deepcopy(a);p['mentions']=[];p['relations']=[]
    p['quality'].update(entity_eligible=False,relation_eligible=False)
    s=score_silver_sample(a,p)
    assert s['surface_chunk_mentions']['fn']==2 and s['surface_relations']['fn']==1

def test_missing_prediction_counts_fn_not_success():
    a=build_decision(visible(),decision());s=score_silver_sample(a)
    assert not s['completed'] and s['surface_chunk_mentions']['fn']==2 and s['surface_relations']['fn']==1

def test_clear_empty_body_is_true_negative_only_when_completed():
    a=build_decision(visible('作者机构信息。'),decision(entities=[],relations=[]))
    assert score_silver_sample(a,a)['body_correct_negative']
    assert not score_silver_sample(a)['body_correct_negative']

def test_repeated_location_surface_inventory_but_exact_diagnostic():
    v=visible('翻耕 翻耕');a=build_decision(v,decision(entities=[('measure','翻耕')],relations=[]))
    p=build_decision(v,decision(entities=[dict(type='measure',text='翻耕',occurrence=1)],relations=[]))
    s=score_silver_sample(a,p)
    assert s['surface_chunk_mentions']['tp']==1 and s['chunk_mentions']['fp']==1

def test_wrong_input_hash_rejected():
    a=build_decision(visible(),decision());p=copy.deepcopy(a);p['input_sha256']='wrong'
    with pytest.raises(ValueError,match='input_context'):score_silver_sample(a,p)

def test_batch_is_all_validated_before_append(tmp_path,monkeypatch):
    import scripts.adjudicate_kg_silver100 as script
    monkeypatch.setattr(script,'OUT',tmp_path);monkeypatch.setattr(script,'sources',lambda:[visible()]*100)
    with pytest.raises(ValueError):script.record([dict(decision(),index=0),dict(decision(entities=[('indicator','absent')]),index=1)])
    assert not (tmp_path/'source-adjudications.jsonl').exists()
    script.record([dict(decision(),index=0)])
    before=(tmp_path/'source-adjudications.jsonl').read_bytes()
    with pytest.raises(ValueError,match='duplicate'):script.record([dict(decision(),index=0)])
    assert (tmp_path/'source-adjudications.jsonl').read_bytes()==before

@pytest.fixture
def release(tmp_path):
    from scripts.experiment_kg_recall import jsonl,write,sha
    rows=[]
    for i in range(100):
        v=visible();v['sample_id']=str(i);a=build_decision(v,decision())
        rows.append(dict(visible_input=v,annotation=a,source=dict(leakage_group=str(i//2))))
    jsonl(tmp_path/'reference.jsonl',rows)
    write(tmp_path/'manifest.json',dict(reference_sha256=sha(tmp_path/'reference.jsonl'),counts={}))
    return tmp_path,rows

def test_prediction_input_mismatch_stops_release_scoring(release):
    from scripts.score_kg_silver100 import score_release
    path,rows=release
    with pytest.raises(ValueError,match='input_hash_mismatch'):
        score_release(path,[dict(sample_id='0',input_sha256='wrong',answer={})])

def test_duplicate_predictions_cannot_inflate_availability(release):
    from scripts.score_kg_silver100 import score_release
    path,rows=release;p=dict(sample_id='0',input_sha256=rows[0]['annotation']['input_sha256'],answer={})
    with pytest.raises(ValueError,match='duplicate_prediction'):
        score_release(path,[p,p])

def test_invalid_prediction_preserves_full_denominator_and_false_negatives(release):
    from scripts.score_kg_silver100 import score_release
    path,rows=release;p=dict(sample_id='0',input_sha256=rows[0]['annotation']['input_sha256'],answer={})
    s=score_release(path,[p])
    assert s['samples']==100 and s['valid_completed']==0 and len(s['missing_samples'])==99
    assert len(s['invalid_predictions'])==1 and s['tasks']['surface_chunk_mentions']['fn']==200
    assert s['tasks']['surface_relations']['fn']==100 and s['body_correct_negatives']==0

@pytest.mark.parametrize('quality_fails',[False,True])
def test_r5_quality_cannot_skip_entity_or_relation_calls(quality_fails):
    from framework.knowledge_graph.annotation_tasks_r5 import annotate
    calls=[];responses=[dict(entities='unreadable',relations='unreadable',reason='wrong model opinion'),
        dict(mentions=[dict(type='measure',fragment=dict(block_id='chunk',text='翻耕',occurrence=0),reason='literal'),dict(type='indicator',fragment=dict(block_id='chunk',text='结构稳定性',occurrence=0),reason='literal')]),
        dict(mappings=[]),dict(relations=[dict(candidate_id=0,modality='asserted',evidence=[dict(block_id='chunk',text='翻耕改善结构稳定性。',occurrence=0)],reason='explicit')])]
    async def create(**kw):
        calls.append(kw);data=responses.pop(0)
        if len(calls)==1 and quality_fails:data={'broken':True}
        return SimpleNamespace(usage=None,choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(data)))])
    r=asyncio.run(annotate(visible(),create))
    assert len(calls)==4 and len(r['annotation']['mentions'])==2 and len(r['annotation']['relations'])==1
    assert r['state']=='needs_review' and r['requires_source_adjudication']
    assert not r['annotation']['completeness']['entities'] and not r['annotation']['completeness']['relations']
    assert all('不是mention列表编号' in c['messages'][0]['content'] for c in calls)
