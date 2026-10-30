import pytest
from scripts.review_kg_benchmark_metadata import schema_for,check


def packet():return dict(document_id=1,file_sha256='a',profile_scope='sampled',sections=[dict(id='b0',kind='stored_chunk_excerpt',text='土壤')])


def test_scanned_pdf_has_empty_title_identifier_arrays_not_empty_enum():
    import jsonschema
    schema=schema_for(packet())['json_schema']['schema']
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema['properties']['title_ids']['maxItems']==0


def test_filename_cannot_verify_identity_without_pdf_evidence():
    raw=dict(identity_status='verified',title_ids=[],identifier_ids=[],language_ids=['b0'],body_quality_ids=['b0'])
    with pytest.raises(ValueError,match='pdf_title_evidence'):check(packet(),raw,None)
