import hashlib
import json
from pathlib import Path

import pytest

from framework.knowledge_graph import (
    ClaimCandidate,
    EntityCandidate,
    EvidenceReference,
    ExtractionRequest,
    GraphQuery,
    RelationCandidate,
    SchemaValidationError,
    SourceChunk,
    load_graph_schema,
)
from framework.knowledge_graph.adapters import DeterministicStubBackend
from framework.knowledge_graph.conformance import evaluate_extraction_backend
from framework.knowledge_graph.schema import GraphSchema
from scripts.export_kg_extraction_gold import build_gold_rows


ROOT = Path(__file__).resolve().parents[1]


def _request_and_candidates(relation_type="addresses"):
    content = "针对土壤酸化，可以施用石灰进行治理。"
    chunk = SourceChunk(
        document_id=7,
        content_sha256="document-sha-7",
        chunk_index=3,
        page=9,
        content=content,
    )
    evidence = EvidenceReference.from_chunk(chunk, 0, len(content))
    entities = (
        EntityCandidate(
            "candidate:measure", "measure", "施用石灰",
            canonical_id="measure:liming", canonical_name="施用石灰",
            confidence=0.98,
        ),
        EntityCandidate(
            "candidate:obstacle", "obstacle", "土壤酸化",
            canonical_id="obstacle:acidification", canonical_name="土壤酸化",
            confidence=0.97,
        ),
    )
    relations = (
        RelationCandidate(
            "candidate:relation", relation_type,
            "candidate:measure", "candidate:obstacle",
            (evidence,), confidence=0.93,
        ),
    )
    request = ExtractionRequest(
        job_id="job:7",
        document_id=7,
        content_sha256="document-sha-7",
        schema_version="minimal-cultivated-land-kg-schema-v1",
        chunks=(chunk,),
    )
    return request, entities, relations


def test_v1_schema_preserves_reviewed_v04_types_and_directions():
    schema = load_graph_schema()

    assert schema.schema_version == "minimal-cultivated-land-kg-schema-v1"
    assert schema.entity_type_ids == {"indicator", "obstacle", "measure", "standard"}
    assert len(schema.relation_type_ids) == 10
    assert schema.allows("addresses", "measure", "obstacle")
    assert not schema.allows("addresses", "obstacle", "measure")
    assert schema.allows("assigns_by_laboratory_test", "standard", "indicator")


def test_schema_rejects_duplicate_and_unknown_types():
    with pytest.raises(SchemaValidationError, match="unique"):
        GraphSchema.from_mapping({
            "schema_version": "bad",
            "entity_types": [{"id": "indicator"}, {"id": "indicator"}],
            "relation_types": [{
                "id": "r", "source_types": ["indicator"],
                "target_types": ["indicator"],
            }],
            "evidence_contract": {"required_fields": ["quote"]},
        })

    with pytest.raises(SchemaValidationError, match="unknown entity"):
        GraphSchema.from_mapping({
            "schema_version": "bad",
            "entity_types": [{"id": "indicator"}],
            "relation_types": [{
                "id": "r", "source_types": ["missing"],
                "target_types": ["indicator"],
            }],
            "evidence_contract": {"required_fields": ["quote"]},
        })


def test_stub_backend_passes_shared_conformance_suite():
    request, entities, relations = _request_and_candidates()
    backend = DeterministicStubBackend(entities=entities, relations=relations)

    report = evaluate_extraction_backend(backend, request, load_graph_schema())

    assert report.passed, report.issues
    assert report.backend_name == "deterministic-stub"


def test_claim_candidate_uses_the_same_endpoint_and_evidence_conformance():
    request, entities, relations = _request_and_candidates()
    claim = ClaimCandidate(
        "candidate:claim", "causal_statement", "candidate:measure",
        "施用石灰治理土壤酸化", relations[0].evidence,
        object_candidate_id="candidate:obstacle", confidence=0.9,
    )
    valid = DeterministicStubBackend(entities=entities, claims=(claim,))
    assert evaluate_extraction_backend(valid, request, load_graph_schema()).passed

    invalid = DeterministicStubBackend(
        entities=entities,
        claims=(ClaimCandidate(
            "candidate:claim", "causal_statement", "missing",
            claim.statement, claim.evidence,
        ),),
    )
    report = evaluate_extraction_backend(invalid, request, load_graph_schema())
    assert "missing_endpoint" in {issue.code for issue in report.issues}


def test_conformance_rejects_vendor_relation_outside_domain_schema():
    request, entities, relations = _request_and_candidates("vendor_causes")
    backend = DeterministicStubBackend(entities=entities, relations=relations)

    report = evaluate_extraction_backend(backend, request, load_graph_schema())

    assert not report.passed
    assert {issue.code for issue in report.issues} == {"schema_direction"}


def test_conformance_rejects_vendor_id_as_canonical_entity_id():
    request, entities, relations = _request_and_candidates()
    vendor_entity = EntityCandidate(
        "candidate:measure", "measure", "施用石灰",
        canonical_id="neo4j:18427", canonical_name="施用石灰", confidence=0.98,
    )
    backend = DeterministicStubBackend(
        entities=(vendor_entity, entities[1]), relations=relations,
    )

    report = evaluate_extraction_backend(backend, request, load_graph_schema())

    assert not report.passed
    assert "canonical_id_policy" in {issue.code for issue in report.issues}


def test_graph_query_is_bounded_by_contract():
    assert GraphQuery(("indicator:soil_ph",), max_hops=2, top_k=100).max_hops == 2
    with pytest.raises(ValueError, match="one or two hops"):
        GraphQuery(("indicator:soil_ph",), max_hops=3)
    with pytest.raises(ValueError, match="top_k"):
        GraphQuery(("indicator:soil_ph",), top_k=101)


def test_capacity_manifest_matches_openspec_target():
    payload = json.loads((
        ROOT / "benchmarks" / "knowledge_platform" / "target-v1.json"
    ).read_text(encoding="utf-8"))

    assert payload["synthetic_only"] is True
    assert payload["capacity"] == {
        "source_documents": 100_000,
        "canonical_entities": 100_000,
        "relation_evidence": 1_000_000,
        "queued_jobs": 100_000,
        "increment_documents_max": 10_000,
    }
    assert payload["query_profile"]["max_hops"] == 2
    assert payload["query_profile"]["p95_ms_max"] == 1000


def test_reviewed_v04_can_form_a_94_item_extraction_gold_set():
    graph = json.loads((
        ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json"
    ).read_text(encoding="utf-8"))
    schema = load_graph_schema()

    rows = build_gold_rows(graph)

    assert len(rows) == 94
    assert {row["relation"]["type"] for row in rows} <= schema.relation_type_ids
    for row in rows:
        relation = row["relation"]
        assert schema.allows(
            relation["type"], relation["source"]["type"], relation["target"]["type"],
        )
        evidence = row["evidence"]
        assert evidence["page"] is not None
        assert evidence["quote_sha256"] == hashlib.sha256(
            evidence["quote"].encode("utf-8")
        ).hexdigest()
