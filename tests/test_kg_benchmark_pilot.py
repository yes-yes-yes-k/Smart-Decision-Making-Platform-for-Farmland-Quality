import asyncio
import json
import pytest
import scripts.run_kg_benchmark_pilot as runner


def test_resume_guard_precedes_client_and_reservation(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'RUN',tmp_path/'pilot')
    with pytest.raises(ValueError,match='resume_required'):
        asyncio.run(runner.execute([],{}))
    assert not list(tmp_path.rglob('*.sqlite3'))


def test_budget_extension_requires_recorded_user_and_fixed_project_caps(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'RUN',tmp_path)
    assert runner.limits()['stability']==1_000_000
    path=tmp_path/'budget-approval.json'
    path.write_text(json.dumps(dict(approved_by='agent',stability_tokens=2_000_000)),encoding='utf-8')
    with pytest.raises(ValueError,match='explicit_budget_approval'):
        runner.limits()
    value=dict(approved_by='user',explicit_instruction='同意阶段上限提高至200万，总上限不变',
               stability_tokens=2_000_000,total_tokens=10_000_000,requests=5000)
    path.write_text(json.dumps(value),encoding='utf-8')
    assert runner.limits()==dict(stability=2_000_000,total=10_000_000,requests=5000)
    value['total_tokens']=20_000_000
    path.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError):
        runner.limits()


def test_annotation_options_never_serialize_packet_extras():
    packet=dict(sample_id='x',blocks=[],handbook='manual',output_protocol='v2',
                old_answers='PRIVATE',sampling_layer='PRIVATE')
    options=runner.options(packet)
    assert 'PRIVATE' not in json.dumps(options)
    assert options['response_format']=={'type':'json_object'}
