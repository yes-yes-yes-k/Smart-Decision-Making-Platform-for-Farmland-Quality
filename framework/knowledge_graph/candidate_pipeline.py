"""Normalize extraction output into reviewable, evidence-bound candidates.

This module deliberately stops at candidate persistence.  It has no graph-store
dependency and therefore cannot publish extracted facts into the active graph.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping, Protocol, Sequence

from sqlalchemy import distinct

from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
)

from .contracts import (
    EntityCandidate,
    EvidenceReference,
    ExtractionRequest,
    ExtractionResult,
    SourceChunk,
    sha256_text,
    stable_digest,
)
from .jobs import document_is_graph_eligible
from .schema import GraphSchema, load_graph_schema


DEFAULT_GRAPH_PATH = (
    Path(__file__).resolve().parents[2]
    / "artifacts"
    / "minimal_kg"
    / "cultivated_land_minimal_graph_v0.4.json"
)


class CandidatePipelineError(ValueError):
    """A stable, machine-readable failure raised before candidate persistence."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PipelineIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class PipelineReport:
    entity_candidates: int
    relation_candidates: int
    claim_candidates: int
    evidence_records: int
    merged_relations: int
    issues: tuple[PipelineIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


class PublishedChunkReader(Protocol):
    def read_published_chunks(
        self, *, document_id: int, content_sha256: str, expected_count: int,
    ) -> Sequence[Mapping[str, Any]]: ...


class ChromaPublishedChunkReader:
    """Read source chunks through the existing ACL-aware Chroma API."""

    def __init__(self, vector_store):
        self.vector_store = vector_store

    def read_published_chunks(
        self, *, document_id: int, content_sha256: str, expected_count: int,
    ) -> Sequence[Mapping[str, Any]]:
        return self.vector_store.get_by_references(
            [{"document_id": int(document_id)}],
            filters={"$and": [
                {"visibility_scope": "public"},
                {"content_sha256": str(content_sha256)},
            ]},
            n_results=int(expected_count) + 1,
        )


class ExtractionInputBuilder:
    """Build one immutable extraction request from published page-aware chunks."""

    def __init__(self, session, chunk_reader: PublishedChunkReader):
        self.session = session
        self.chunk_reader = chunk_reader

    def build(self, job: KnowledgeGraphExtractionJob) -> ExtractionRequest:
        document = self.session.get(Document, int(job.document_id))
        if document is None:
            raise CandidatePipelineError("document_not_found", "source document does not exist")
        if not document_is_graph_eligible(document):
            raise CandidatePipelineError(
                "source_not_published", "document is not approved, public and completed",
            )
        if str(document.file_hash) != str(job.content_sha256):
            raise CandidatePipelineError(
                "stale_document_hash", "job content hash differs from the current document",
            )
        expected_count = int(document.chunk_count or 0)
        rows = tuple(self.chunk_reader.read_published_chunks(
            document_id=int(document.id),
            content_sha256=str(job.content_sha256),
            expected_count=expected_count,
        ))
        if len(rows) != expected_count:
            raise CandidatePipelineError(
                "chunk_count_mismatch",
                f"expected {expected_count} published chunks, received {len(rows)}",
            )

        chunks: list[SourceChunk] = []
        seen_indexes: set[int] = set()
        for offset, row in enumerate(rows):
            metadata = dict(row.get("metadata") or {})
            location = f"chunks.{offset}"
            try:
                row_document_id = int(metadata.get("document_id"))
                chunk_index = int(metadata.get("chunk_index"))
                page = int(metadata.get("page"))
            except (TypeError, ValueError):
                raise CandidatePipelineError(
                    "invalid_chunk_locator", f"{location} requires document, chunk and page",
                ) from None
            if row_document_id != int(document.id):
                raise CandidatePipelineError("foreign_chunk", f"{location} belongs to another document")
            if metadata.get("visibility_scope") != "public":
                raise CandidatePipelineError("source_not_published", f"{location} is not public")
            if str(metadata.get("content_sha256") or "") != str(job.content_sha256):
                raise CandidatePipelineError("stale_chunk_hash", f"{location} has a stale content hash")
            if chunk_index in seen_indexes:
                raise CandidatePipelineError("duplicate_chunk", f"chunk index {chunk_index} repeats")
            seen_indexes.add(chunk_index)
            content = str(row.get("content") or "")
            try:
                chunks.append(SourceChunk(
                    document_id=int(document.id),
                    content_sha256=str(job.content_sha256),
                    chunk_index=chunk_index,
                    content=content,
                    page=page,
                ))
            except ValueError as exc:
                raise CandidatePipelineError("invalid_chunk", f"{location}: {exc}") from exc

        chunks.sort(key=lambda item: item.chunk_index)
        if [item.chunk_index for item in chunks] != list(range(expected_count)):
            raise CandidatePipelineError(
                "non_contiguous_chunks", "published chunk indexes must be contiguous from zero",
            )
        return ExtractionRequest(
            job_id=str(job.id),
            document_id=int(document.id),
            content_sha256=str(job.content_sha256),
            schema_version=str(job.schema_version),
            chunks=tuple(chunks),
        )


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE)


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    entity_id: str
    entity_type: str
    name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EntityResolution:
    status: str
    canonical_id: str | None
    canonical_name: str | None
    risk_level: str
    suggestions: tuple[str, ...] = ()


class CanonicalEntityCatalog:
    """Project-owned entity catalogue; vendor IDs are never accepted as truth."""

    BROAD_TERMS = frozenset({
        "土壤", "耕地", "土地", "指标", "措施", "标准", "规范", "问题", "质量",
    })

    def __init__(
        self,
        entities: Sequence[CanonicalEntity] = (),
        production_relations: Sequence[tuple[str, str, str]] = (),
        *,
        fuzzy_threshold: float = 0.86,
    ):
        self.entities = tuple(entities)
        self.production_relations = frozenset(production_relations)
        self.fuzzy_threshold = fuzzy_threshold
        self._by_id = {item.entity_id: item for item in self.entities}
        self._terms: dict[tuple[str, str], list[CanonicalEntity]] = {}
        for entity in self.entities:
            for term in (entity.name, *entity.aliases):
                normalized = _normalize(term)
                if normalized:
                    self._terms.setdefault((entity.entity_type, normalized), []).append(entity)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "CanonicalEntityCatalog":
        entities = tuple(CanonicalEntity(
            entity_id=str(row["id"]),
            entity_type=str(row["type"]),
            name=str(row["name"]),
            aliases=tuple(str(value) for value in row.get("aliases") or ()),
        ) for row in payload.get("entities") or ())
        relations = tuple(
            (str(row["type"]), str(row["source"]), str(row["target"]))
            for row in payload.get("relations") or ()
            if all(row.get(key) for key in ("type", "source", "target"))
        )
        return cls(entities, relations)

    @classmethod
    def from_json(cls, path: str | Path = DEFAULT_GRAPH_PATH) -> "CanonicalEntityCatalog":
        return cls.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))

    def resolve(self, candidate: EntityCandidate) -> EntityResolution:
        normalized = _normalize(candidate.mention)
        if normalized in {_normalize(value) for value in self.BROAD_TERMS}:
            return EntityResolution("rejected", None, None, "too_broad")

        if candidate.canonical_id:
            exact_id = self._by_id.get(candidate.canonical_id)
            if exact_id is not None and exact_id.entity_type == candidate.entity_type:
                return EntityResolution(
                    "resolved", exact_id.entity_id, exact_id.name, "existing_entity",
                )

        exact = self._terms.get((candidate.entity_type, normalized), [])
        unique = {item.entity_id: item for item in exact}
        if len(unique) == 1:
            entity = next(iter(unique.values()))
            return EntityResolution("resolved", entity.entity_id, entity.name, "existing_entity")
        if len(unique) > 1:
            return EntityResolution(
                "needs_entity_resolution", None, None, "ambiguous_exact_match",
                tuple(sorted(unique)),
            )

        scored: list[tuple[float, CanonicalEntity]] = []
        for entity in self.entities:
            if entity.entity_type != candidate.entity_type:
                continue
            score = max(
                (SequenceMatcher(None, normalized, _normalize(term)).ratio()
                 for term in (entity.name, *entity.aliases) if _normalize(term)),
                default=0.0,
            )
            if score >= self.fuzzy_threshold:
                scored.append((score, entity))
        if scored:
            scored.sort(key=lambda item: (-item[0], item[1].entity_id))
            return EntityResolution(
                "needs_entity_resolution", None, None, "fuzzy_match",
                tuple(item[1].entity_id for item in scored[:5]),
            )

        proposed_id = f"{candidate.entity_type}:candidate-{stable_digest({'name': normalized})[:16]}"
        return EntityResolution(
            "new_entity", proposed_id, candidate.mention.strip(), "new_entity",
        )


class CandidatePipeline:
    """Validate, normalize and persist candidates without publishing them."""

    def __init__(
        self,
        session,
        *,
        schema: GraphSchema | None = None,
        catalog: CanonicalEntityCatalog | None = None,
    ):
        self.session = session
        self.schema = schema or load_graph_schema()
        self.catalog = catalog or CanonicalEntityCatalog.from_json()

    def process(
        self,
        job: KnowledgeGraphExtractionJob,
        request: ExtractionRequest,
        result: ExtractionResult,
    ) -> PipelineReport:
        self._validate_provenance(job, request, result)
        issues: list[PipelineIssue] = []
        evidence_identities: dict[str, tuple[Any, ...]] = {}

        entities: dict[str, tuple[KnowledgeGraphEntityCandidate, EntityResolution]] = {}
        seen_entity_payloads: dict[str, tuple[Any, ...]] = {}
        for candidate in result.entities:
            identity = (candidate.entity_type, candidate.mention, candidate.canonical_id)
            previous = seen_entity_payloads.get(candidate.candidate_id)
            if previous is not None:
                issues.append(PipelineIssue(
                    "candidate_identity_conflict" if previous != identity else "duplicate_entity_candidate",
                    f"entities.{candidate.candidate_id}", "entity candidate id repeats",
                ))
                continue
            seen_entity_payloads[candidate.candidate_id] = identity
            if candidate.entity_type not in self.schema.entity_type_ids:
                issues.append(PipelineIssue(
                    "unknown_entity_type", f"entities.{candidate.candidate_id}",
                    "entity type is not in the active schema",
                ))
                continue
            resolution = self.catalog.resolve(candidate)
            row = self.session.query(KnowledgeGraphEntityCandidate).filter_by(
                job_id=job.id, candidate_key=candidate.candidate_id,
            ).one_or_none()
            if row is None:
                row = KnowledgeGraphEntityCandidate(job_id=job.id, candidate_key=candidate.candidate_id)
                self.session.add(row)
            row.entity_type = candidate.entity_type
            row.mention = candidate.mention
            row.canonical_entity_id = resolution.canonical_id
            row.canonical_name = resolution.canonical_name
            row.resolution_status = resolution.status
            row.risk_level = resolution.risk_level
            row.review_status = "not_reviewable" if resolution.status == "rejected" else "pending"
            row.confidence = candidate.confidence
            row.candidate_payload = {
                "backend_canonical_id": candidate.canonical_id,
                "backend_canonical_name": candidate.canonical_name,
                "suggestions": list(resolution.suggestions),
            }
            self.session.flush()
            entities[candidate.candidate_id] = (row, resolution)
            if resolution.status == "rejected":
                issues.append(PipelineIssue(
                    "concept_too_broad", f"entities.{candidate.candidate_id}",
                    "generic concepts cannot become canonical graph entities",
                ))

        relation_rows: set[int] = set()
        claim_rows: set[int] = set()
        evidence_rows_before = self._evidence_count()
        merged_relations = 0
        seen_relation_payloads: dict[str, tuple[str, str, str]] = {}
        for candidate in result.relations:
            location = f"relations.{candidate.candidate_id}"
            identity = (
                candidate.relation_type,
                candidate.source_candidate_id,
                candidate.target_candidate_id,
            )
            previous = seen_relation_payloads.get(candidate.candidate_id)
            if previous is not None:
                issues.append(PipelineIssue(
                    "candidate_identity_conflict" if previous != identity else "duplicate_relation_candidate",
                    location, "relation candidate id repeats",
                ))
                continue
            seen_relation_payloads[candidate.candidate_id] = identity
            source = entities.get(candidate.source_candidate_id)
            target = entities.get(candidate.target_candidate_id)
            if source is None or target is None:
                issues.append(PipelineIssue("missing_endpoint", location, "relation endpoint is missing"))
                continue
            source_row, source_resolution = source
            target_row, target_resolution = target
            semantic_error = None
            if candidate.relation_type not in self.schema.relation_type_ids:
                semantic_error = "unknown_relation_type"
            elif not self.schema.allows(
                candidate.relation_type, source_row.entity_type, target_row.entity_type,
            ):
                semantic_error = "schema_direction"
            evidence_issues = self._validate_evidence(
                candidate.evidence, request, location, evidence_identities,
            )
            issues.extend(evidence_issues)
            if semantic_error or evidence_issues:
                if semantic_error:
                    issues.append(PipelineIssue(
                        semantic_error, location,
                        "relation type or endpoint direction is not allowed by the schema",
                    ))
                row = self._upsert_local_relation(
                    job, candidate, source_row, target_row,
                    validation_status="rejected", review_status="not_reviewable",
                    risk_level="invalid_candidate",
                )
                relation_rows.add(row.id)
                continue

            resolved = (
                source_resolution.status == "resolved"
                and target_resolution.status == "resolved"
            )
            if not resolved:
                row = self._upsert_local_relation(
                    job, candidate, source_row, target_row,
                    validation_status="needs_entity_resolution", review_status="blocked",
                    risk_level="unresolved_endpoint",
                )
            else:
                triple = (
                    candidate.relation_type,
                    str(source_resolution.canonical_id),
                    str(target_resolution.canonical_id),
                )
                row = self._find_mergeable_relation(job.schema_version, triple)
                if row is None:
                    row = self._upsert_local_relation(
                        job, candidate, source_row, target_row,
                        validation_status="validated", review_status="pending",
                        risk_level=(
                            "evidence_append" if triple in self.catalog.production_relations
                            else "new_fact"
                        ),
                    )
                elif row.job_id != job.id:
                    merged_relations += 1
            relation_rows.add(row.id)
            for evidence in candidate.evidence:
                self._upsert_relation_evidence(row, evidence, job, result)
            self._refresh_support_count(row)

        seen_claim_payloads: dict[str, tuple[Any, ...]] = {}
        for candidate in result.claims:
            location = f"claims.{candidate.candidate_id}"
            identity = (
                candidate.claim_type, candidate.subject_candidate_id,
                candidate.object_candidate_id, candidate.statement,
            )
            previous = seen_claim_payloads.get(candidate.candidate_id)
            if previous is not None:
                issues.append(PipelineIssue(
                    "candidate_identity_conflict" if previous != identity else "duplicate_claim_candidate",
                    location, "claim candidate id repeats",
                ))
                continue
            seen_claim_payloads[candidate.candidate_id] = identity
            subject = entities.get(candidate.subject_candidate_id)
            object_pair = entities.get(candidate.object_candidate_id) if candidate.object_candidate_id else None
            if subject is None or (candidate.object_candidate_id and object_pair is None):
                issues.append(PipelineIssue("missing_endpoint", location, "claim endpoint is missing"))
                continue
            evidence_issues = self._validate_evidence(
                candidate.evidence, request, location, evidence_identities,
            )
            issues.extend(evidence_issues)
            subject_row, subject_resolution = subject
            object_row = object_pair[0] if object_pair else None
            object_resolution = object_pair[1] if object_pair else None
            resolved = subject_resolution.status == "resolved" and (
                object_resolution is None or object_resolution.status == "resolved"
            )
            status = "rejected" if evidence_issues else (
                "validated" if resolved else "needs_entity_resolution"
            )
            review_status = "not_reviewable" if evidence_issues else (
                "pending" if resolved else "blocked"
            )
            row = self._upsert_claim(
                job, candidate, subject_row, object_row,
                subject_resolution, object_resolution,
                validation_status=status, review_status=review_status,
            )
            claim_rows.add(row.id)
            if not evidence_issues:
                for evidence in candidate.evidence:
                    self._upsert_claim_evidence(row, evidence, job, result)

        job.raw_output_fingerprint = result.raw_output_fingerprint
        self.session.flush()
        return PipelineReport(
            entity_candidates=len(entities),
            relation_candidates=len(relation_rows),
            claim_candidates=len(claim_rows),
            evidence_records=self._evidence_count() - evidence_rows_before,
            merged_relations=merged_relations,
            issues=tuple(issues),
        )

    def _validate_provenance(self, job, request, result) -> None:
        document = self.session.get(Document, int(job.document_id))
        if document is None or not document_is_graph_eligible(document):
            raise CandidatePipelineError(
                "source_not_published",
                "source was withdrawn, made private or left the completed state",
            )
        if str(document.file_hash) != str(job.content_sha256):
            raise CandidatePipelineError(
                "stale_document_hash", "source content changed after the graph job was created",
            )
        checks = (
            (str(request.job_id) == str(job.id), "job_identity_mismatch"),
            (request.document_id == job.document_id, "document_identity_mismatch"),
            (request.content_sha256 == job.content_sha256, "content_hash_mismatch"),
            (request.schema_version == job.schema_version, "schema_version_mismatch"),
            (result.schema_version == job.schema_version, "schema_version_mismatch"),
            (result.request_key == request.request_key, "request_key_mismatch"),
            (result.backend_name == job.backend_name, "backend_identity_mismatch"),
            (result.backend_version == job.extractor_version, "backend_version_mismatch"),
            (result.backend_config_digest == job.backend_config_digest, "backend_config_mismatch"),
        )
        for passed, code in checks:
            if not passed:
                raise CandidatePipelineError(code, "extraction provenance does not match the job")

    def _validate_evidence(self, evidence_items, request, location, identities):
        issues: list[PipelineIssue] = []
        chunks = {
            (item.document_id, item.content_sha256, item.chunk_index, item.page): item
            for item in request.chunks
        }
        for index, evidence in enumerate(evidence_items):
            evidence_location = f"{location}.evidence.{index}"
            issue_count = len(issues)
            identity = (
                evidence.document_id, evidence.content_sha256, evidence.chunk_index,
                evidence.page, evidence.span_start, evidence.span_end,
                evidence.quote_sha256,
            )
            chunk = chunks.get((
                evidence.document_id, evidence.content_sha256,
                evidence.chunk_index, evidence.page,
            ))
            if chunk is None:
                issues.append(PipelineIssue(
                    "missing_source_chunk", evidence_location,
                    "evidence does not reference a chunk in the immutable request",
                ))
                continue
            if not 0 <= evidence.span_start < evidence.span_end <= len(chunk.content):
                issues.append(PipelineIssue("invalid_span", evidence_location, "span is outside source chunk"))
                continue
            if chunk.content[evidence.span_start:evidence.span_end] != evidence.quote:
                issues.append(PipelineIssue("quote_mismatch", evidence_location, "quote is not the source span"))
                continue
            previous = identities.get(evidence.evidence_id)
            if previous is not None and previous != identity:
                issues.append(PipelineIssue(
                    "evidence_identity_conflict", evidence_location,
                    "one evidence id maps to multiple source spans",
                ))
                continue
            expected = EvidenceReference.from_chunk(
                chunk, evidence.span_start, evidence.span_end,
            )
            if evidence.quote_sha256 != expected.quote_sha256:
                issues.append(PipelineIssue("quote_hash_mismatch", evidence_location, "quote hash is invalid"))
            if evidence.evidence_id != expected.evidence_id:
                issues.append(PipelineIssue(
                    "unstable_evidence_id", evidence_location,
                    "evidence id is not derived from the source locator and quote hash",
                ))
            if len(issues) != issue_count:
                continue
            identities[evidence.evidence_id] = identity
        return issues

    def _upsert_local_relation(
        self, job, candidate, source_row, target_row, *,
        validation_status, review_status, risk_level,
    ):
        row = self.session.query(KnowledgeGraphRelationCandidate).filter_by(
            job_id=job.id, candidate_key=candidate.candidate_id,
        ).one_or_none()
        if row is None:
            row = KnowledgeGraphRelationCandidate(job_id=job.id, candidate_key=candidate.candidate_id)
            self.session.add(row)
        row.relation_type = candidate.relation_type
        row.source_candidate_id = source_row.id
        row.target_candidate_id = target_row.id
        row.canonical_source_id = source_row.canonical_entity_id
        row.canonical_target_id = target_row.canonical_entity_id
        row.risk_level = risk_level
        row.validation_status = validation_status
        row.review_status = review_status
        row.confidence = candidate.confidence
        row.candidate_payload = {"backend_candidate_id": candidate.candidate_id}
        self.session.flush()
        return row

    def _find_mergeable_relation(self, schema_version, triple):
        relation_type, source_id, target_id = triple
        query = (
            self.session.query(KnowledgeGraphRelationCandidate)
            .join(
                KnowledgeGraphExtractionJob,
                KnowledgeGraphRelationCandidate.job_id == KnowledgeGraphExtractionJob.id,
            )
            .filter(
                KnowledgeGraphExtractionJob.schema_version == schema_version,
                KnowledgeGraphRelationCandidate.relation_type == relation_type,
                KnowledgeGraphRelationCandidate.canonical_source_id == source_id,
                KnowledgeGraphRelationCandidate.canonical_target_id == target_id,
                KnowledgeGraphRelationCandidate.validation_status == "validated",
                KnowledgeGraphRelationCandidate.review_status.in_(("pending", "approved")),
            )
            .order_by(KnowledgeGraphRelationCandidate.id)
        )
        if self.session.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        return query.first()

    def _upsert_relation_evidence(self, row, evidence, job, result):
        existing = self.session.query(KnowledgeGraphCandidateEvidence).filter_by(
            relation_candidate_id=row.id, evidence_key=evidence.evidence_id,
        ).one_or_none()
        if existing is not None:
            return existing
        record = KnowledgeGraphCandidateEvidence(
            relation_candidate_id=row.id,
            evidence_key=evidence.evidence_id,
            document_id=evidence.document_id,
            content_sha256=evidence.content_sha256,
            chunk_index=evidence.chunk_index,
            page=evidence.page,
            span_start=evidence.span_start,
            span_end=evidence.span_end,
            quote=evidence.quote,
            quote_sha256=evidence.quote_sha256,
            schema_version=job.schema_version,
            backend_name=result.backend_name,
            extractor_version=result.backend_version,
            validation_status="validated",
            review_status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return record

    def _refresh_support_count(self, row):
        document_ids = self.session.query(distinct(KnowledgeGraphCandidateEvidence.document_id)).filter(
            KnowledgeGraphCandidateEvidence.relation_candidate_id == row.id,
            KnowledgeGraphCandidateEvidence.is_active.is_(True),
            KnowledgeGraphCandidateEvidence.validation_status == "validated",
        ).all()
        row.support_document_count = len(document_ids)

    def _upsert_claim(
        self, job, candidate, subject_row, object_row,
        subject_resolution, object_resolution, *, validation_status, review_status,
    ):
        row = self.session.query(KnowledgeGraphClaimCandidate).filter_by(
            job_id=job.id, candidate_key=candidate.candidate_id,
        ).one_or_none()
        if row is None:
            row = KnowledgeGraphClaimCandidate(job_id=job.id, candidate_key=candidate.candidate_id)
            self.session.add(row)
        row.claim_type = candidate.claim_type
        row.subject_candidate_id = subject_row.id
        row.object_candidate_id = object_row.id if object_row else None
        row.canonical_subject_id = subject_resolution.canonical_id
        row.canonical_object_id = object_resolution.canonical_id if object_resolution else None
        row.statement = candidate.statement
        row.risk_level = "new_claim"
        row.validation_status = validation_status
        row.review_status = review_status
        row.confidence = candidate.confidence
        row.candidate_payload = {"backend_candidate_id": candidate.candidate_id}
        self.session.flush()
        return row

    def _upsert_claim_evidence(self, row, evidence, job, result):
        existing = self.session.query(KnowledgeGraphClaimEvidence).filter_by(
            claim_candidate_id=row.id, evidence_key=evidence.evidence_id,
        ).one_or_none()
        if existing is not None:
            return existing
        record = KnowledgeGraphClaimEvidence(
            claim_candidate_id=row.id,
            evidence_key=evidence.evidence_id,
            document_id=evidence.document_id,
            content_sha256=evidence.content_sha256,
            chunk_index=evidence.chunk_index,
            page=evidence.page,
            span_start=evidence.span_start,
            span_end=evidence.span_end,
            quote=evidence.quote,
            quote_sha256=evidence.quote_sha256,
            schema_version=job.schema_version,
            backend_name=result.backend_name,
            extractor_version=result.backend_version,
            validation_status="validated",
            review_status="pending",
        )
        self.session.add(record)
        self.session.flush()
        return record

    def _evidence_count(self):
        return (
            self.session.query(KnowledgeGraphCandidateEvidence).count()
            + self.session.query(KnowledgeGraphClaimEvidence).count()
        )
