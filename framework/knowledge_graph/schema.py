"""Versioned cultivated-land graph schema loader and validator."""
from __future__ import annotations

from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .contracts import stable_digest


class SchemaValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EntityTypeDefinition:
    type_id: str
    label: str


@dataclass(frozen=True, slots=True)
class RelationTypeDefinition:
    type_id: str
    source_types: tuple[str, ...]
    target_types: tuple[str, ...]
    label: str


@dataclass(frozen=True, slots=True)
class GraphSchema:
    schema_version: str
    compatible_graph_versions: tuple[str, ...]
    entity_types: tuple[EntityTypeDefinition, ...]
    relation_types: tuple[RelationTypeDefinition, ...]
    required_evidence_fields: tuple[str, ...]
    digest: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GraphSchema":
        schema_version = str(payload.get("schema_version") or "").strip()
        if not schema_version:
            raise SchemaValidationError("schema_version is required")

        raw_entities = list(payload.get("entity_types") or [])
        raw_relations = list(payload.get("relation_types") or [])
        entity_ids = [str(item.get("id") or "").strip() for item in raw_entities]
        relation_ids = [str(item.get("id") or "").strip() for item in raw_relations]
        if not entity_ids or any(not item for item in entity_ids):
            raise SchemaValidationError("entity type ids are required")
        if not relation_ids or any(not item for item in relation_ids):
            raise SchemaValidationError("relation type ids are required")
        if len(entity_ids) != len(set(entity_ids)):
            raise SchemaValidationError("entity type ids must be unique")
        if len(relation_ids) != len(set(relation_ids)):
            raise SchemaValidationError("relation type ids must be unique")

        entities = tuple(
            EntityTypeDefinition(
                type_id=entity_id,
                label=str(item.get("label") or entity_id),
            )
            for entity_id, item in zip(entity_ids, raw_entities)
        )
        known_entities = set(entity_ids)
        relations = []
        for relation_id, item in zip(relation_ids, raw_relations):
            sources = tuple(str(value) for value in item.get("source_types") or [])
            targets = tuple(str(value) for value in item.get("target_types") or [])
            if not sources or not targets:
                raise SchemaValidationError(
                    f"relation {relation_id} requires source_types and target_types"
                )
            unknown = (set(sources) | set(targets)) - known_entities
            if unknown:
                raise SchemaValidationError(
                    f"relation {relation_id} uses unknown entity types: {sorted(unknown)}"
                )
            relations.append(RelationTypeDefinition(
                type_id=relation_id,
                source_types=sources,
                target_types=targets,
                label=str(item.get("label") or relation_id),
            ))

        required = tuple(str(value) for value in (
            (payload.get("evidence_contract") or {}).get("required_fields") or []
        ))
        if not required:
            raise SchemaValidationError("evidence_contract.required_fields is required")

        normalized = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return cls(
            schema_version=schema_version,
            compatible_graph_versions=tuple(
                str(value) for value in payload.get("compatible_graph_versions") or []
            ),
            entity_types=entities,
            relation_types=tuple(relations),
            required_evidence_fields=required,
            digest=stable_digest(normalized),
        )

    @property
    def entity_type_ids(self) -> frozenset[str]:
        return frozenset(item.type_id for item in self.entity_types)

    @property
    def relation_type_ids(self) -> frozenset[str]:
        return frozenset(item.type_id for item in self.relation_types)

    def allows(self, relation_type: str, source_type: str, target_type: str) -> bool:
        return any(
            item.type_id == relation_type
            and source_type in item.source_types
            and target_type in item.target_types
            for item in self.relation_types
        )


DEFAULT_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "minimal-cultivated-land-kg-schema-v1.json"
)


@lru_cache(maxsize=8)
def load_graph_schema(path: str | Path = DEFAULT_SCHEMA_PATH) -> GraphSchema:
    schema_path = Path(path)
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    return GraphSchema.from_mapping(payload)
