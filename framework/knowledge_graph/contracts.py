"""Backend-neutral contracts for the scalable knowledge platform.

The domain schema, evidence identity and review workflow belong to this
project.  Extraction and graph-storage products implement these contracts
instead of leaking vendor identifiers into published knowledge.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return sha256_text(payload)


@dataclass(frozen=True, slots=True)
class SourceChunk:
    """A persisted, page-aware chunk that an extractor may inspect."""

    document_id: int
    content_sha256: str
    chunk_index: int
    content: str
    page: int | None = None

    def __post_init__(self) -> None:
        if self.document_id <= 0:
            raise ValueError("document_id must be positive")
        if not self.content_sha256:
            raise ValueError("content_sha256 is required")
        if self.chunk_index < 0:
            raise ValueError("chunk_index must be non-negative")
        if not self.content:
            raise ValueError("content is required")
        if self.page is not None and self.page <= 0:
            raise ValueError("page must be positive when present")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Exact evidence span; production candidates cannot use free-form quotes."""

    evidence_id: str
    document_id: int
    content_sha256: str
    chunk_index: int
    page: int | None
    span_start: int
    span_end: int
    quote: str
    quote_sha256: str

    def __post_init__(self) -> None:
        if self.document_id <= 0 or self.chunk_index < 0:
            raise ValueError("evidence document and chunk identities are invalid")
        if not self.content_sha256 or not self.evidence_id:
            raise ValueError("evidence identity and document hash are required")
        if self.page is None or self.page <= 0:
            raise ValueError("page-located evidence is required")
        if self.span_start < 0 or self.span_end <= self.span_start:
            raise ValueError("evidence span is invalid")
        if not self.quote or sha256_text(self.quote) != self.quote_sha256:
            raise ValueError("evidence quote and quote hash must match")

    @classmethod
    def from_chunk(
        cls, chunk: SourceChunk, span_start: int, span_end: int,
    ) -> "EvidenceReference":
        if span_start < 0 or span_end <= span_start or span_end > len(chunk.content):
            raise ValueError("evidence span is outside the source chunk")
        quote = chunk.content[span_start:span_end]
        quote_hash = sha256_text(quote)
        identity = stable_digest({
            "document_id": chunk.document_id,
            "content_sha256": chunk.content_sha256,
            "chunk_index": chunk.chunk_index,
            "page": chunk.page,
            "span_start": span_start,
            "span_end": span_end,
            "quote_sha256": quote_hash,
        })
        return cls(
            evidence_id=f"evidence:{identity[:24]}",
            document_id=chunk.document_id,
            content_sha256=chunk.content_sha256,
            chunk_index=chunk.chunk_index,
            page=chunk.page,
            span_start=span_start,
            span_end=span_end,
            quote=quote,
            quote_sha256=quote_hash,
        )


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    candidate_id: str
    entity_type: str
    mention: str
    canonical_id: str | None = None
    canonical_name: str | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.entity_type or not self.mention:
            raise ValueError("candidate_id, entity_type and mention are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class RelationCandidate:
    candidate_id: str
    relation_type: str
    source_candidate_id: str
    target_candidate_id: str
    evidence: tuple[EvidenceReference, ...]
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not all((
            self.candidate_id, self.relation_type,
            self.source_candidate_id, self.target_candidate_id,
        )):
            raise ValueError("relation candidate identity and endpoints are required")
        if not self.evidence:
            raise ValueError("relation candidates require evidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ClaimCandidate:
    candidate_id: str
    claim_type: str
    subject_candidate_id: str
    statement: str
    evidence: tuple[EvidenceReference, ...]
    object_candidate_id: str | None = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not all((
            self.candidate_id, self.claim_type,
            self.subject_candidate_id, self.statement,
        )):
            raise ValueError("claim candidate identity, subject and statement are required")
        if not self.evidence:
            raise ValueError("claim candidates require evidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    job_id: str
    document_id: int
    content_sha256: str
    schema_version: str
    chunks: tuple[SourceChunk, ...]

    def __post_init__(self) -> None:
        if not all((self.job_id, self.content_sha256, self.schema_version)):
            raise ValueError("job_id, content_sha256 and schema_version are required")
        if self.document_id <= 0 or not self.chunks:
            raise ValueError("a positive document_id and at least one chunk are required")
        for chunk in self.chunks:
            if chunk.document_id != self.document_id:
                raise ValueError("all chunks must belong to the request document")
            if chunk.content_sha256 != self.content_sha256:
                raise ValueError("all chunks must use the request content hash")

    @property
    def request_key(self) -> str:
        return stable_digest({
            "document_id": self.document_id,
            "content_sha256": self.content_sha256,
            "schema_version": self.schema_version,
        })


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    backend_name: str
    backend_version: str
    backend_config_digest: str
    schema_version: str
    request_key: str
    entities: tuple[EntityCandidate, ...]
    relations: tuple[RelationCandidate, ...]
    raw_output_fingerprint: str
    claims: tuple[ClaimCandidate, ...] = ()

    def __post_init__(self) -> None:
        if not all((
            self.backend_name, self.backend_version, self.backend_config_digest,
            self.schema_version, self.request_key, self.raw_output_fingerprint,
        )):
            raise ValueError("complete extraction provenance is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GraphQuery:
    entity_ids: tuple[str, ...]
    relation_types: tuple[str, ...] = ()
    direction: str = "both"
    max_hops: int = 1
    top_k: int = 20
    timeout_ms: int = 1_000
    max_result_bytes: int = 262_144

    def __post_init__(self) -> None:
        if not self.entity_ids:
            raise ValueError("at least one entity_id is required")
        if self.direction not in {"outbound", "inbound", "both"}:
            raise ValueError("direction must be outbound, inbound, or both")
        if self.max_hops not in {1, 2}:
            raise ValueError("online graph queries are limited to one or two hops")
        if not 1 <= self.top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if not 1_024 <= self.max_result_bytes <= 1_048_576:
            raise ValueError("max_result_bytes must be between 1024 and 1048576")


@dataclass(frozen=True, slots=True)
class GraphQueryResult:
    active_release: str
    entities: tuple[Mapping[str, Any], ...]
    relations: tuple[Mapping[str, Any], ...]
    evidence_references: tuple[Mapping[str, Any], ...]
    truncated: bool = False


@runtime_checkable
class GraphExtractionBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def extract(self, request: ExtractionRequest) -> ExtractionResult: ...


@runtime_checkable
class GraphStore(Protocol):
    def health(self) -> Mapping[str, Any]: ...

    def active_release(self) -> str | None: ...

    def neighbors(self, query: GraphQuery) -> GraphQueryResult: ...

    def activate_release(self, release_id: str) -> None: ...


@runtime_checkable
class GraphJobExecutor(Protocol):
    def claim(self, *, worker_id: str, limit: int, lease_seconds: int) -> Sequence[Any]: ...

    def renew(self, *, worker_id: str, job_id: str, lease_seconds: int) -> bool: ...

    def complete(self, *, worker_id: str, job_id: str, result_digest: str) -> bool: ...

    def fail(
        self, *, worker_id: str, job_id: str, error_code: str, retryable: bool,
    ) -> bool: ...
