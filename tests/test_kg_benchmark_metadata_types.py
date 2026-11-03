import jsonschema
from scripts.review_kg_benchmark_metadata_remaining import schema_for


def test_scan_cannot_claim_pdf_identity_from_vector_chunk():
    schema=schema_for(dict(sections=[dict(id='x',kind='stored_chunk_excerpt')]))['json_schema']['schema']
    jsonschema.Draft202012Validator.check_schema(schema)
    assert 'verified' not in schema['properties']['identity_status']['enum']
    assert schema['properties']['title_ids']['maxItems']==0
    assert schema['properties']['body_quality_ids']['items']['enum']==['s0']
