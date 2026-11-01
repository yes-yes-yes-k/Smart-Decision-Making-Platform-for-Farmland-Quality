"""Deterministic extraction backend used to lock the adapter contract."""
from __future__ import annotations

from typing import Sequence

from ..contracts import (
    ClaimCandidate,
    EntityCandidate,
    ExtractionRequest,
    ExtractionResult,
    RelationCandidate,
    stable_digest,
)


class DeterministicStubBackend:
    name = "deterministic-stub"
    version = "1.0"

    def __init__(
        self,
        *,
        entities: Sequence[EntityCandidate] = (),
        relations: Sequence[RelationCandidate] = (),
        claims: Sequence[ClaimCandidate] = (),
        config: dict[str, str] | None = None,
    ) -> None:
        self._entities = tuple(entities)
        self._relations = tuple(relations)
        self._claims = tuple(claims)
        self._config = dict(config or {})

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        payload = {
            "entities": [
                {
                    "candidate_id": item.candidate_id,
                    "entity_type": item.entity_type,
                    "mention": item.mention,
                    "canonical_id": item.canonical_id,
                    "canonical_name": item.canonical_name,
                    "confidence": item.confidence,
                }
                for item in self._entities
            ],
            "relations": [
                {
                    "candidate_id": item.candidate_id,
                    "relation_type": item.relation_type,
                    "source_candidate_id": item.source_candidate_id,
                    "target_candidate_id": item.target_candidate_id,
                    "evidence_ids": [e.evidence_id for e in item.evidence],
                    "confidence": item.confidence,
                }
                for item in self._relations
            ],
            "claims": [
                {
                    "candidate_id": item.candidate_id,
                    "claim_type": item.claim_type,
                    "subject_candidate_id": item.subject_candidate_id,
                    "object_candidate_id": item.object_candidate_id,
                    "statement": item.statement,
                    "evidence_ids": [e.evidence_id for e in item.evidence],
                    "confidence": item.confidence,
                }
                for item in self._claims
            ],
        }
        return ExtractionResult(
            backend_name=self.name,
            backend_version=self.version,
            backend_config_digest=stable_digest(self._config),
            schema_version=request.schema_version,
            request_key=request.request_key,
            entities=self._entities,
            relations=self._relations,
            raw_output_fingerprint=stable_digest(payload),
            claims=self._claims,
        )
