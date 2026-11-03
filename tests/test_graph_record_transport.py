import json
import pytest
from framework.knowledge_graph.schema import load_graph_schema
from framework.knowledge_graph.graph_record_transport import graph_response_schema, json_to_graph_records


def _payload():
    return dict(entities=[dict(name="施用石灰", type="measure"), dict(name="土壤酸化", type="obstacle")],
                relationships=[dict(source="施用石灰", target="土壤酸化", relation_type="addresses")])


def test_structured_output_uses_exact_domain_enums():
    schema = load_graph_schema()
    contract = graph_response_schema(schema)
    assert contract["json_schema"]["strict"] is True
    props = contract["json_schema"]["schema"]["properties"]
    assert set(props["entities"]["items"]["properties"]["type"]["enum"]) == schema.entity_type_ids
    assert set(props["relationships"]["items"]["properties"]["relation_type"]["enum"]) == schema.relation_type_ids


def test_json_transport_preserves_explicit_fact_and_supports_empty_results():
    schema = load_graph_schema()
    records = json_to_graph_records(json.dumps(_payload()), schema)
    assert '("relationship"<|>施用石灰<|>土壤酸化<|>addresses<|>1)' in records
    assert json_to_graph_records('{"entities":[],"relationships":[]}', schema) == "<|COMPLETE|>"


@pytest.mark.parametrize("case,code", [("direction", "invalid_relation_direction"),
    ("unknown", "unknown_relation_type"), ("missing", "missing_relation_endpoint"),
    ("injection", "invalid_model_output"), ("extra", "invalid_model_output")])
def test_structured_output_does_not_relax_validation(case, code):
    payload = _payload()
    if case == "direction":
        payload["relationships"][0].update(source="土壤酸化", target="施用石灰")
    elif case == "unknown":
        payload["relationships"][0]["relation_type"] = "is_related_to"
    elif case == "missing":
        payload["relationships"][0]["target"] = "不存在的端点"
    elif case == "injection":
        payload["entities"][0]["name"] = "injected##record"
    else:
        payload["entities"][0]["production_fact"] = True
    with pytest.raises(ValueError, match=code):
        json_to_graph_records(json.dumps(payload), load_graph_schema())


@pytest.mark.parametrize("corrects", [True, False])
def test_model_repairs_are_bounded_and_revalidated(corrects):
    import asyncio
    from types import SimpleNamespace
    from framework.knowledge_graph.graph_record_transport import complete_graph_records
    calls = []
    async def create(**kwargs):
        calls.append(kwargs)
        payload = _payload()
        if len(calls) == 1 or not corrects:
            payload["relationships"][0].update(source="土壤酸化", target="施用石灰")
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
            message=SimpleNamespace(content=json.dumps(payload)))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    trace = []
    run = complete_graph_records(create, messages=[{"role":"user","content":"public source"}],
        options={}, schema=load_graph_schema(), usage=usage, trace=trace)
    if corrects:
        assert "addresses" in asyncio.run(run)
        assert len(calls) == 2
        assert usage["total_tokens"] == 30
        assert [t['accepted'] for t in trace] == [False, True]
        assert trace[0]['error'] == 'invalid_relation_direction'
        assert 'addresses' in trace[1]['records']
    else:
        with pytest.raises(ValueError, match="invalid_relation_direction"):
            asyncio.run(run)
        assert len(calls) == 3
        assert usage["repair_requests"] == 2
        assert len(trace) == 3 and not any(t['accepted'] for t in trace)
