import json
import pytest
from scripts.verify_kg_annotator_controls import cases,parse

def test_controls_are_unique_and_answer_key_is_not_in_visible_input():
    suite=cases();assert len(suite)==17 and len({r['id'] for r in suite})==17
    assert all(set(r['visible'])=={'task','source'} for r in suite)
    assert all('expected' not in r['visible'] for r in suite)
    assert {r['category'] for r in suite}=={'type','relation','eligibility','normalization','copy','transport'}

def test_null_is_distinct_from_string_and_copy_preserves_whitespace():
    assert parse('{"answer":null}',None) is None
    assert parse('{"answer":"null"}',None)=='null'
    assert parse(json.dumps({'answer':'soil\nnitrate'}),None)=='soil\nnitrate'
    for content in ('[]','{"answer":"indicator","extra":1}','{"answer":[]}'):
        with pytest.raises(ValueError):parse(content,None)

def test_out_of_scope_and_unsupported_not_silently_coerced():
    assert parse('{"answer":"out_of_scope"}',['indicator','out_of_scope'])=='out_of_scope'
    with pytest.raises(ValueError):parse('{"answer":"standard"}',['indicator','out_of_scope'])
