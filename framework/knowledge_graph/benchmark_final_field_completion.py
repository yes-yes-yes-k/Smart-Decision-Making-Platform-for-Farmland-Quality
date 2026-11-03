"""Complete only absent relation reviews; never invent unfinished JSON fields."""
import copy
from .benchmark_partial_annotation import complete_array_objects

FIELDS=['decision_reviews','additions','relation_reviews','add_relations',
    'normalization_reviews','mask_overrides','policy_conflicts']


def plan_relation_completion(content,relation_count):
    completed={};relation_done=True
    for key in FIELDS:
        values,done=complete_array_objects(content,key);completed[key]=values
        if key=='relation_reviews':relation_done=done
        elif not done:raise ValueError('unavailable_nonrelation_field:'+key)
    if relation_done:raise ValueError('relation_array_already_complete')
    emitted=[r.get('index') for r in completed['relation_reviews']]
    expected=set(range(relation_count))
    if len(set(emitted))!=len(emitted) or not set(emitted).issubset(expected):
        raise ValueError('invalid_completed_relation_indices')
    missing=sorted(expected-set(emitted))
    if not missing:raise ValueError('no_unemitted_relation_judgments')
    return completed,missing


def merge_relation_completion(completed,missing,raw):
    if set(raw)!= {'relation_reviews'}:raise ValueError('only_missing_relation_reviews_allowed')
    values=raw['relation_reviews']
    if not isinstance(values,list) or len(values)!=len(missing) or {r.get('index') for r in values}!=set(missing):
        raise ValueError('only_all_missing_indices_allowed')
    result=copy.deepcopy(completed);result['relation_reviews']+=copy.deepcopy(values)
    return result
