"""Candidate-only adapter for Microsoft GraphRAG structured artifacts.

The adapter deliberately does not invoke an LLM or write a graph store.  It
converts the documented entities/relationships/text_units artifacts into the
project-owned extraction contract.  Exact source chunks, rather than LLM
descriptions, are used as evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from ..contracts import (
    EntityCandidate,
    EvidenceReference,
    ExtractionRequest,
    ExtractionResult,
    RelationCandidate,
    SourceChunk,
    stable_digest,
)
from ..schema import GraphSchema


class GraphRagAdapterError(ValueError):
    """Raised when GraphRAG output cannot be converted without guessing."""

    def __init__(self, message):
        super().__init__(message)
        self.code = "invalid_extraction_result"
        if "violates the project schema direction" in message:
            self.code = "invalid_relation_direction"
        elif message.startswith("entity titles map to multiple schema types"):
            self.code = "ambiguous_entity_types"
        elif message.startswith("unmapped GraphRAG entity type"):
            self.code = "unknown_entity_type"
        elif "references an unknown endpoint" in message:
            self.code = "missing_relation_endpoint"


@dataclass(frozen=True, slots=True)
class GraphRagEntityRecord:
    vendor_id: str
    title: str
    entity_type: str
    text_unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GraphRagRelationshipRecord:
    vendor_id: str
    source: str
    target: str
    text_unit_ids: tuple[str, ...]
    description: str = ""
    relation_type: str | None = None
    quote: str | None = None


@dataclass(frozen=True, slots=True)
class GraphRagTextUnitRecord:
    vendor_id: str
    text: str
    source_chunk_index: int | None = None


@dataclass(frozen=True, slots=True)
class GraphRagArtifactBundle:
    entities: tuple[GraphRagEntityRecord, ...]
    relationships: tuple[GraphRagRelationshipRecord, ...]
    text_units: tuple[GraphRagTextUnitRecord, ...]


class GraphRagArtifactProvider(Protocol):
    def load(self, request: ExtractionRequest) -> GraphRagArtifactBundle: ...


@dataclass(frozen=True, slots=True)
class StaticGraphRagArtifactProvider:
    """In-memory provider for offline evaluation and conformance fixtures."""

    bundle: GraphRagArtifactBundle

    def load(self, request: ExtractionRequest) -> GraphRagArtifactBundle:
        del request
        return self.bundle


def _as_records(frame: Any) -> list[Mapping[str, Any]]:
    try:
        rows = frame.to_dict(orient="records")
    except (AttributeError, TypeError) as exc:
        raise GraphRagAdapterError("parquet reader must return a tabular frame") from exc
    if not isinstance(rows, list):
        raise GraphRagAdapterError("parquet frame did not produce record rows")
    return rows


def _as_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    try:
        return tuple(str(item) for item in value if str(item))
    except TypeError as exc:
        raise GraphRagAdapterError("text_unit_ids must be a sequence") from exc


class ParquetGraphRagArtifactProvider:
    """Load the three documented GraphRAG artifact tables lazily.

    ``read_parquet`` is injectable so the conversion layer can be tested
    without installing GraphRAG or a parquet engine in the main application.
    """

    def __init__(
        self,
        output_dir: str | Path,
        *,
        read_parquet: Callable[[Path], Any] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self._reader = read_parquet

    def _read(self, name: str) -> list[Mapping[str, Any]]:
        path = self.output_dir / f"{name}.parquet"
        reader = self._reader
        if reader is None:
            try:
                import pandas as pd
            except ImportError as exc:  # pragma: no cover - project has pandas
                raise GraphRagAdapterError("pandas is required to read GraphRAG parquet") from exc
            reader = pd.read_parquet
        try:
            return _as_records(reader(path))
        except GraphRagAdapterError:
            raise
        except Exception as exc:
            raise GraphRagAdapterError(f"cannot read GraphRAG artifact: {path.name}") from exc

    def load(self, request: ExtractionRequest) -> GraphRagArtifactBundle:
        del request
        entity_rows = self._read("entities")
        relationship_rows = self._read("relationships")
        text_unit_rows = self._read("text_units")
        return GraphRagArtifactBundle(
            entities=tuple(
                GraphRagEntityRecord(
                    vendor_id=str(row.get("id") or ""),
                    title=str(row.get("title") or "").strip(),
                    entity_type=str(row.get("type") or "").strip(),
                    text_unit_ids=_as_string_tuple(row.get("text_unit_ids")),
                )
                for row in entity_rows
            ),
            relationships=tuple(
                GraphRagRelationshipRecord(
                    vendor_id=str(row.get("id") or ""),
                    source=str(row.get("source") or "").strip(),
                    target=str(row.get("target") or "").strip(),
                    description=str(row.get("description") or ""),
                    text_unit_ids=_as_string_tuple(row.get("text_unit_ids")),
                    relation_type=(
                        str(row["relation_type"]).strip()
                        if row.get("relation_type") else None
                    ),
                )
                for row in relationship_rows
            ),
            text_units=tuple(
                GraphRagTextUnitRecord(
                    vendor_id=str(row.get("id") or ""),
                    text=str(row.get("text") or ""),
                    source_chunk_index=(
                        int(row["source_chunk_index"])
                        if row.get("source_chunk_index") is not None else None
                    ),
                )
                for row in text_unit_rows
            ),
        )


def _normalized_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class MicrosoftGraphRagBackend:
    """Strict GraphRAG artifact converter that can only return candidates."""

    name = "microsoft-graphrag"
    candidate_only = True

    def __init__(
        self,
        *,
        provider: GraphRagArtifactProvider,
        schema: GraphSchema,
        version: str,
        entity_type_map: Mapping[str, str] | None = None,
    ) -> None:
        if not version or version.casefold() == "latest":
            raise ValueError("an exact GraphRAG version is required")
        self.provider = provider
        self.schema = schema
        self.version = version
        supplied = entity_type_map or {
            entity_type: entity_type for entity_type in schema.entity_type_ids
        }
        self._entity_type_map = {
            _normalized_name(source): target for source, target in supplied.items()
        }
        unknown = set(self._entity_type_map.values()) - schema.entity_type_ids
        if unknown:
            raise ValueError(f"entity type map targets unknown schema types: {sorted(unknown)}")
        self._config_digest = stable_digest({
            "adapter_contract": "graphrag-artifacts-v1",
            "entity_type_map": self._entity_type_map,
            "schema_digest": schema.digest,
            "version": version,
        })

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        if request.schema_version != self.schema.schema_version:
            raise GraphRagAdapterError("request schema does not match adapter schema")
        artifacts = self.provider.load(request)
        chunk_by_text_unit = self._bind_text_units(request, artifacts.text_units)
        entities, entity_by_title = self._convert_entities(artifacts.entities)
        relations = self._convert_relationships(
            artifacts.relationships, entity_by_title, chunk_by_text_unit,
        )
        fingerprint = stable_digest({
            "entities": [
                (row.vendor_id, row.title, row.entity_type, row.text_unit_ids)
                for row in sorted(artifacts.entities, key=lambda item: item.vendor_id)
            ],
            "relationships": [
                (
                    row.vendor_id, row.source, row.target, row.relation_type,
                    row.description, row.text_unit_ids,
                    *((row.quote,) if row.quote is not None else ()),
                )
                for row in sorted(artifacts.relationships, key=lambda item: item.vendor_id)
            ],
            "text_units": [
                (row.vendor_id, row.text, row.source_chunk_index)
                for row in sorted(artifacts.text_units, key=lambda item: item.vendor_id)
            ],
        })
        return ExtractionResult(
            backend_name=self.name,
            backend_version=self.version,
            backend_config_digest=self._config_digest,
            schema_version=request.schema_version,
            request_key=request.request_key,
            entities=entities,
            relations=relations,
            raw_output_fingerprint=fingerprint,
        )

    def _bind_text_units(
        self,
        request: ExtractionRequest,
        text_units: Sequence[GraphRagTextUnitRecord],
    ) -> dict[str, SourceChunk]:
        by_index = {chunk.chunk_index: chunk for chunk in request.chunks}
        by_text: dict[str, list[SourceChunk]] = {}
        for chunk in request.chunks:
            by_text.setdefault(chunk.content, []).append(chunk)
        result: dict[str, SourceChunk] = {}
        for unit in text_units:
            if not unit.vendor_id or not unit.text:
                raise GraphRagAdapterError("GraphRAG text units require id and text")
            if unit.vendor_id in result:
                raise GraphRagAdapterError(f"duplicate GraphRAG text unit id: {unit.vendor_id}")
            if unit.source_chunk_index is not None:
                chunk = by_index.get(unit.source_chunk_index)
                if chunk is None:
                    raise GraphRagAdapterError(
                        f"unknown source chunk index for text unit {unit.vendor_id}"
                    )
                if unit.text != chunk.content:
                    raise GraphRagAdapterError(
                        f"text unit {unit.vendor_id} does not exactly match its source chunk"
                    )
            else:
                matches = by_text.get(unit.text, [])
                if len(matches) != 1:
                    raise GraphRagAdapterError(
                        f"text unit {unit.vendor_id} needs an unambiguous source_chunk_index"
                    )
                chunk = matches[0]
            if chunk.page is None:
                raise GraphRagAdapterError("GraphRAG evidence requires page-aware chunks")
            result[unit.vendor_id] = chunk
        return result

    def _convert_entities(
        self, records: Iterable[GraphRagEntityRecord],
    ) -> tuple[tuple[EntityCandidate, ...], dict[str, EntityCandidate]]:
        by_key: dict[tuple[str, str], EntityCandidate] = {}
        title_index: dict[str, list[EntityCandidate]] = {}
        for record in records:
            if not record.vendor_id or not record.title or not record.entity_type:
                raise GraphRagAdapterError("GraphRAG entities require id, title and type")
            mapped_type = self._entity_type_map.get(_normalized_name(record.entity_type))
            if mapped_type is None:
                raise GraphRagAdapterError(
                    f"unmapped GraphRAG entity type: {record.entity_type}"
                )
            normalized_title = _normalized_name(record.title)
            key = (mapped_type, normalized_title)
            candidate = by_key.get(key)
            if candidate is None:
                candidate = EntityCandidate(
                    candidate_id=f"candidate:entity:{stable_digest(key)[:24]}",
                    entity_type=mapped_type,
                    mention=record.title,
                    canonical_id=None,
                    canonical_name=None,
                    confidence=0.0,
                )
                by_key[key] = candidate
                title_index.setdefault(normalized_title, []).append(candidate)
        ambiguous = {
            title for title, candidates in title_index.items() if len(candidates) != 1
        }
        if ambiguous:
            raise GraphRagAdapterError(
                f"entity titles map to multiple schema types: {sorted(ambiguous)}"
            )
        entities = tuple(sorted(by_key.values(), key=lambda item: item.candidate_id))
        return entities, {title: items[0] for title, items in title_index.items()}

    def _convert_relationships(
        self,
        records: Iterable[GraphRagRelationshipRecord],
        entities: Mapping[str, EntityCandidate],
        chunks: Mapping[str, SourceChunk],
    ) -> tuple[RelationCandidate, ...]:
        converted: list[RelationCandidate] = []
        seen_ids: set[str] = set()
        for record in records:
            if not record.vendor_id or not record.source or not record.target:
                raise GraphRagAdapterError("GraphRAG relationships require id and endpoints")
            source = entities.get(_normalized_name(record.source))
            target = entities.get(_normalized_name(record.target))
            if source is None or target is None:
                raise GraphRagAdapterError(
                    f"relationship {record.vendor_id} references an unknown endpoint"
                )
            relation_type = self._resolve_relation_type(record, source, target)
            evidence = self._evidence(record, chunks)
            identity = (
                relation_type, source.candidate_id, target.candidate_id,
                tuple(item.evidence_id for item in evidence),
            )
            candidate_id = f"candidate:relation:{stable_digest(identity)[:24]}"
            if candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            converted.append(RelationCandidate(
                candidate_id=candidate_id,
                relation_type=relation_type,
                source_candidate_id=source.candidate_id,
                target_candidate_id=target.candidate_id,
                evidence=evidence,
                confidence=0.0,
            ))
        return tuple(sorted(converted, key=lambda item: item.candidate_id))

    def _resolve_relation_type(
        self,
        record: GraphRagRelationshipRecord,
        source: EntityCandidate,
        target: EntityCandidate,
    ) -> str:
        if record.relation_type:
            if not self.schema.allows(
                record.relation_type, source.entity_type, target.entity_type,
            ):
                raise GraphRagAdapterError(
                    f"relation {record.relation_type} violates the project schema direction"
                )
            return record.relation_type
        allowed = sorted(
            relation.type_id
            for relation in self.schema.relation_types
            if source.entity_type in relation.source_types
            and target.entity_type in relation.target_types
        )
        if len(allowed) != 1:
            raise GraphRagAdapterError(
                "GraphRAG relationship needs an explicit structured relation_type; "
                f"direction permits {allowed or 'no relation'}"
            )
        return allowed[0]

    @staticmethod
    def _evidence(
        record: GraphRagRelationshipRecord,
        chunks: Mapping[str, SourceChunk],
    ) -> tuple[EvidenceReference, ...]:
        evidence_by_id: dict[str, EvidenceReference] = {}
        if not record.text_unit_ids:
            raise GraphRagAdapterError(
                f"relationship {record.vendor_id} has no text-unit provenance"
            )
        for text_unit_id in record.text_unit_ids:
            chunk = chunks.get(text_unit_id)
            if chunk is None:
                raise GraphRagAdapterError(
                    f"relationship {record.vendor_id} references unknown text unit {text_unit_id}"
                )
            start, end = 0, len(chunk.content)
            if record.quote is not None:
                if not record.quote.strip() or record.quote not in chunk.content:
                    raise GraphRagAdapterError('relationship quote is not literal source evidence')
                start = chunk.content.index(record.quote)
                end = start + len(record.quote)
            evidence = EvidenceReference.from_chunk(chunk, start, end)
            evidence_by_id[evidence.evidence_id] = evidence
        return tuple(sorted(evidence_by_id.values(), key=lambda item: item.evidence_id))
