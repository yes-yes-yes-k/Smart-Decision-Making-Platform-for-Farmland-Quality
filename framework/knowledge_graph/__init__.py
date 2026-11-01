"""Cultivated-land knowledge graph and scalable platform contracts.

ORM-backed candidate/job services are loaded lazily so offline graph tooling
does not import the application's complete spatial model dependency graph.
"""

from importlib import import_module

from .minimal_graph import (
    MinimalGraphBuilder,
    PilotDocument,
    assess_graph_claim,
    build_pilot_graph,
    entity_match_scores,
    query_graph,
    rank_graph_evidence,
)
from .release import prepare_graph_release, publish_graph_release
from .contracts import (
    ClaimCandidate,
    EntityCandidate,
    EvidenceReference,
    ExtractionRequest,
    ExtractionResult,
    GraphExtractionBackend,
    GraphJobExecutor,
    GraphQuery,
    GraphQueryResult,
    GraphStore,
    RelationCandidate,
    SourceChunk,
)
from .schema import GraphSchema, SchemaValidationError, load_graph_schema

_LAZY_EXPORTS = {
    name: (".candidate_pipeline", name) for name in (
        "CandidatePipeline", "CandidatePipelineError", "CanonicalEntity",
        "CanonicalEntityCatalog", "ChromaPublishedChunkReader",
        "ExtractionInputBuilder", "PipelineIssue", "PipelineReport",
    )
}
_LAZY_EXPORTS.update({
    name: (".stores", name) for name in (
        "AGE_VERSION", "POSTGRES_MAJOR", "AgeGraphStore", "JsonGraphStore", "SqlAlchemyAgeExecutor",
    )
})
_LAZY_EXPORTS.update({
    name: (".age_migration", name) for name in (
        "GraphMigrationError", "GraphMigrationReport", "audit_checksum", "migrate_reviewed_graph",
    )
})
_LAZY_EXPORTS["compare_graph_stores"] = (".dual_read", "compare_graph_stores")
_LAZY_EXPORTS.update({
    name: (".jobs", name) for name in (
        "KnowledgeGraphOutboxDispatcher", "SqlAlchemyGraphJobExecutor",
        "document_is_graph_eligible", "enqueue_document_indexed",
        "materialize_outbox_event",
    )
})
_LAZY_EXPORTS.update({
    name: (".release_platform", name) for name in (
        "KnowledgeGraphReleaseService", "ReleaseAuditExporter",
        "ReleaseError", "ReleasePreview",
    )
})
_LAZY_EXPORTS["SafeGraphQueryService"] = (".query", "SafeGraphQueryService")
_LAZY_EXPORTS["invalidate_document_evidence"] = (
    ".evidence_lifecycle", "invalidate_document_evidence",
)
_LAZY_EXPORTS["HistoricalGraphBackfill"] = (".backfill", "HistoricalGraphBackfill")


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value

__all__ = [
    "MinimalGraphBuilder",
    "PilotDocument",
    "assess_graph_claim",
    "build_pilot_graph",
    "entity_match_scores",
    "query_graph",
    "rank_graph_evidence",
    "prepare_graph_release",
    "publish_graph_release",
    "EntityCandidate",
    "ClaimCandidate",
    "EvidenceReference",
    "ExtractionRequest",
    "ExtractionResult",
    "GraphExtractionBackend",
    "GraphJobExecutor",
    "GraphQuery",
    "GraphQueryResult",
    "GraphStore",
    "RelationCandidate",
    "SourceChunk",
    "GraphSchema",
    "SchemaValidationError",
    "load_graph_schema",
    "CandidatePipeline",
    "CandidatePipelineError",
    "CanonicalEntity",
    "CanonicalEntityCatalog",
    "ChromaPublishedChunkReader",
    "ExtractionInputBuilder",
    "PipelineIssue",
    "PipelineReport",
    "AGE_VERSION",
    "POSTGRES_MAJOR",
    "AgeGraphStore",
    "JsonGraphStore",
    "SqlAlchemyAgeExecutor",
    "GraphMigrationError",
    "GraphMigrationReport",
    "audit_checksum",
    "migrate_reviewed_graph",
    "compare_graph_stores",
    "KnowledgeGraphOutboxDispatcher",
    "SqlAlchemyGraphJobExecutor",
    "document_is_graph_eligible",
    "enqueue_document_indexed",
    "materialize_outbox_event",
    "KnowledgeGraphReleaseService",
    "ReleaseAuditExporter",
    "ReleaseError",
    "ReleasePreview",
    "SafeGraphQueryService",
    "invalidate_document_evidence",
    "HistoricalGraphBackfill",
]
