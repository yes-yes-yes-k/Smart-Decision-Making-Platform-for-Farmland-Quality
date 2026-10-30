import json
import pytest
from framework.knowledge_graph.benchmark_final_field_completion import plan_relation_completion,merge_relation_completion


def truncated():
    fields={k:[] for k in ['decision_reviews','additions','add_relations','normalization_reviews','mask_overrides','policy_conflicts']}
    fields['decision_reviews']=[dict(id='keep',decision='include')]
    return json.dumps(fields)[:-1]+',"relation_reviews":[{"index":0,"status":"supported"}, {"index":'


def test_only_unemitted_indices_and_completed_judgments_unchanged():
    completed,missing=plan_relation_completion(truncated(),3)
    before=json.dumps(completed,sort_keys=True)
    assert missing==[1,2]
    result=merge_relation_completion(completed,missing,dict(relation_reviews=[dict(index=2),dict(index=1)]))
    assert [r['index'] for r in result['relation_reviews']]==[0,2,1]
    assert json.dumps(completed,sort_keys=True)==before
    assert result['decision_reviews']==completed['decision_reviews']


def test_missing_variable_length_field_cannot_be_assumed_empty():
    with pytest.raises(ValueError,match='unavailable_nonrelation_field'):
        plan_relation_completion('{"decision_reviews":[],"relation_reviews":[',2)


@pytest.mark.parametrize('raw',[
    dict(relation_reviews=[dict(index=0),dict(index=2)]),
    dict(relation_reviews=[dict(index=1),dict(index=1)]),
    dict(relation_reviews=[dict(index=1),dict(index=2)],additions=[]),
])
def test_repeated_prior_indices_and_extra_fields_rejected(raw):
    completed,missing=plan_relation_completion(truncated(),3)
    with pytest.raises(ValueError):merge_relation_completion(completed,missing,raw)
