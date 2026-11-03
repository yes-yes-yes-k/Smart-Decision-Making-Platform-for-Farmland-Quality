"""Reusable conformance checks for extraction backend adapters."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from .contracts import (
    ExtractionRequest,
    GraphExtractionBackend,
    sha256_text,
)
from .schema import GraphSchema


@dataclass(frozen=True, slots=True)
class ConformanceIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    backend_name: str
    backend_version: str
    issues: tuple[ConformanceIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def _issue(
    issues: list[ConformanceIssue], code: str, location: str, message: str,
) -> None:
    issues.append(ConformanceIssue(code, location, message))


def evaluate_extraction_backend(
    backend: GraphExtractionBackend,
    request: ExtractionRequest,
    schema: GraphSchema,
) -> ConformanceReport:
    issues: list[ConformanceIssue] = []
    try:
        first = backend.extract(request)
        second = backend.extract(request)
    except Exception as exc:  # pragma: no cover - exercised by real adapters
        _issue(issues, "backend_exception", "extract", type(exc).__name__)
        return ConformanceReport(
            getattr(backend, "name", "unknown"),
            getattr(backend, "version", "unknown"),
            tuple(issues),
        )

    first_json = json.dumps(first.to_dict(), ensure_ascii=False, sort_keys=True)
    second_json = json.dumps(second.to_dict(), ensure_ascii=False, sort_keys=True)
    if first_json != second_json:
        _issue(issues, "non_deterministic", "result", "same request changed output")
    if first.backend_name != backend.name or first.backend_version != backend.version:
        _issue(issues, "backend_identity", "result", "backend provenance mismatch")
    if first.schema_version != request.schema_version:
        _issue(issues, "schema_version", "result", "schema version mismatch")
    if first.request_key != request.request_key:
        _issue(issues, "request_key", "result", "request identity mismatch")

    entities = {item.candidate_id: item for item in first.entities}
    if len(entities) != len(first.entities):
        _issue(issues, "duplicate_entity_candidate", "entities", "candidate ids repeat")
    for entity in first.entities:
        location = f"entities.{entity.candidate_id}"
        if entity.entity_type not in schema.entity_type_ids:
            _issue(issues, "unknown_entity_type", location, "entity type is not in schema")
        if entity.canonical_id and not entity.canonical_id.startswith(
            f"{entity.entity_type}:"
        ):
            _issue(
                issues,
                "canonical_id_policy",
                location,
                "canonical id must use the project-owned entity type namespace",
            )
    chunks = {
        (item.document_id, item.content_sha256, item.chunk_index, item.page): item
        for item in request.chunks
    }
    seen_relations: set[str] = set()
    for relation in first.relations:
        location = f"relations.{relation.candidate_id}"
        if relation.candidate_id in seen_relations:
            _issue(issues, "duplicate_relation_candidate", location, "candidate id repeats")
        seen_relations.add(relation.candidate_id)
        source = entities.get(relation.source_candidate_id)
        target = entities.get(relation.target_candidate_id)
        if source is None or target is None:
            _issue(issues, "missing_endpoint", location, "candidate endpoint is missing")
            continue
        if not schema.allows(relation.relation_type, source.entity_type, target.entity_type):
            _issue(issues, "schema_direction", location, "relation is not allowed by schema")
        _validate_evidence(issues, location, relation.evidence, chunks)

    seen_claims: set[str] = set()
    for claim in first.claims:
        location = f"claims.{claim.candidate_id}"
        if claim.candidate_id in seen_claims:
            _issue(issues, "duplicate_claim_candidate", location, "candidate id repeats")
        seen_claims.add(claim.candidate_id)
        if claim.subject_candidate_id not in entities:
            _issue(issues, "missing_endpoint", location, "claim subject is missing")
        if claim.object_candidate_id and claim.object_candidate_id not in entities:
            _issue(issues, "missing_endpoint", location, "claim object is missing")
        _validate_evidence(issues, location, claim.evidence, chunks)

    return ConformanceReport(backend.name, backend.version, tuple(issues))


def _validate_evidence(
    issues: list[ConformanceIssue],
    relation_location: str,
    evidence_items: Iterable,
    chunks: dict,
) -> None:
    for index, evidence in enumerate(evidence_items):
        location = f"{relation_location}.evidence.{index}"
        chunk = chunks.get((
            evidence.document_id,
            evidence.content_sha256,
            evidence.chunk_index,
            evidence.page,
        ))
        if chunk is None:
            _issue(issues, "missing_chunk", location, "evidence chunk is not in request")
            continue
        if not (0 <= evidence.span_start < evidence.span_end <= len(chunk.content)):
            _issue(issues, "invalid_span", location, "evidence span is outside chunk")
            continue
        quote = chunk.content[evidence.span_start:evidence.span_end]
        if quote != evidence.quote:
            _issue(issues, "quote_mismatch", location, "quote does not match source span")
        if sha256_text(evidence.quote) != evidence.quote_sha256:
            _issue(issues, "quote_hash_mismatch", location, "quote hash is invalid")
        expected = type(evidence).from_chunk(
            chunk, evidence.span_start, evidence.span_end,
        )
        if evidence.evidence_id != expected.evidence_id:
            _issue(
                issues, "unstable_evidence_id", location,
                "evidence id is not derived from the immutable source locator",
            )
