import jsonschema
import scripts.validate_kg_reference_schema as runner
from framework.knowledge_graph.benchmark_reference_schema import build_reference_schema
from framework.knowledge_graph.benchmark_protocol import load_schema
from pathlib import Path


def test_strict_reference_schema_requires_fields_and_retains_negative_modalities(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'OUT',tmp_path)
    (tmp_path/'protocol-r4').mkdir()
    (tmp_path/'protocol-r4/annotation-handbook.md').write_text('Source-only manual',encoding='utf-8')
    jobs=runner.controls()
    assert len(jobs)==2
    for job in jobs:
        config=job['options']['response_format']
        assert config['type']=='json_schema' and config['json_schema']['strict']
        schema=config['json_schema']['schema']
        assert set(schema['required'])=={'decision_reviews','additions','relation_reviews','add_relations','normalization_reviews','mask_overrides','policy_conflicts'}
        assert schema['additionalProperties'] is False
        assert job['packet']['candidate']['relations'][0]['modality'] in {'hypothetical','negated'}
        assert build_reference_schema(job['packet']['candidate'],load_schema(Path(__file__).resolve().parents[1]))==config


def test_empty_candidate_schema_keeps_negative_source_evaluable():
    fmt=build_reference_schema(dict(decisions=[],relations=[],normalization=[]),load_schema(Path(__file__).resolve().parents[1]))
    schema=fmt['json_schema']['schema']
    jsonschema.Draft202012Validator.check_schema(schema)
    raw=dict(decision_reviews=[],additions=[],relation_reviews=[],add_relations=[],normalization_reviews=[],mask_overrides=[],policy_conflicts=[])
    jsonschema.validate(raw,schema)
    assert schema['properties']['decision_reviews']['maxItems']==0
