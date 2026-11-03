"""Backend-neutral JSON and Apache AGE graph-store adapters."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol

from sqlalchemy import create_engine, text

from .contracts import GraphQuery, GraphQueryResult


AGE_VERSION = "1.6.0"
POSTGRES_MAJOR = 16
DEFAULT_AGE_GRAPH = "cultivated_land_kg"
_GRAPH_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _evidence_reference(row: Mapping[str, Any], relation_id: str) -> dict[str, Any]:
    """Return locators only; graph stores must not bypass chunk ACLs with quote text."""
    allowed = (
        "evidence_id", "document_id", "document_key", "content_sha256",
        "chunk_index", "page", "span_start", "span_end", "quote_sha256",
    )
    result = {key: row.get(key) for key in allowed if row.get(key) is not None}
    result["relation_id"] = relation_id
    return result


def _bounded_result(result: GraphQueryResult, query: GraphQuery) -> GraphQueryResult:
    """Deterministically trim optional rows until the serialized result is bounded."""
    entities = list(result.entities)
    relations = list(result.relations)
    evidence = list(result.evidence_references)

    def size() -> int:
        return len(json.dumps({
            "active_release": result.active_release,
            "entities": entities,
            "relations": relations,
            "evidence_references": evidence,
        }, ensure_ascii=False, sort_keys=True).encode("utf-8"))

    truncated = result.truncated
    while size() > query.max_result_bytes and evidence:
        evidence.pop()
        truncated = True
    while size() > query.max_result_bytes and relations:
        relations.pop()
        truncated = True
    seed_ids = set(query.entity_ids)
    while size() > query.max_result_bytes and any(
        str(item.get("id")) not in seed_ids for item in entities
    ):
        index = next(
            index for index in range(len(entities) - 1, -1, -1)
            if str(entities[index].get("id")) not in seed_ids
        )
        entities.pop(index)
        truncated = True
    if size() > query.max_result_bytes:
        raise ValueError("graph query seed payload exceeds max_result_bytes")
    return GraphQueryResult(
        active_release=result.active_release,
        entities=tuple(entities), relations=tuple(relations),
        evidence_references=tuple(evidence), truncated=truncated,
    )


class JsonGraphStore:
    """Read-only GraphStore preserving the reviewed v0.4 artifact semantics."""

    def __init__(
        self,
        graph: str | Path | Mapping[str, Any],
        *,
        manifest: str | Path | Mapping[str, Any] | None = None,
    ):
        self.path = Path(graph) if isinstance(graph, (str, Path)) else None
        self.graph = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path is not None else json.loads(json.dumps(graph, ensure_ascii=False))
        )
        if isinstance(manifest, (str, Path)):
            self.manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
        elif manifest is not None:
            self.manifest = dict(manifest)
        elif self.path is not None and self.path.with_suffix(".manifest.json").is_file():
            self.manifest = json.loads(
                self.path.with_suffix(".manifest.json").read_text(encoding="utf-8")
            )
        else:
            self.manifest = {}

    def active_release(self) -> str | None:
        return (
            (self.graph.get("release") or {}).get("release_id")
            or self.manifest.get("release_id")
        )

    def activate_release(self, release_id: str) -> None:
        if release_id != self.active_release():
            raise ValueError("JsonGraphStore is read-only and contains one release")

    def export_snapshot(self, release_id: str) -> dict[str, Any]:
        if release_id != self.active_release():
            raise ValueError("JsonGraphStore contains only its active release")
        return json.loads(json.dumps(self.graph, ensure_ascii=False))

    def health(self) -> Mapping[str, Any]:
        entities = self.graph.get("entities") or []
        relations = self.graph.get("relations") or []
        entity_ids = [str(item.get("id") or "") for item in entities]
        errors = []
        if not self.graph.get("schema_version"):
            errors.append("schema_version_missing")
        if not self.active_release():
            errors.append("active_release_missing")
        if any(not item for item in entity_ids) or len(entity_ids) != len(set(entity_ids)):
            errors.append("invalid_entity_ids")
        known = set(entity_ids)
        if any(
            relation.get("source") not in known or relation.get("target") not in known
            for relation in relations
        ):
            errors.append("invalid_relation_endpoint")
        return {
            "ready": not errors,
            "backend": "json",
            "active_release": self.active_release(),
            "schema_version": self.graph.get("schema_version"),
            "entity_count": len(entities),
            "relation_count": len(relations),
            "evidence_count": sum(len(item.get("evidence") or []) for item in relations),
            "errors": errors,
        }

    def neighbors(self, query: GraphQuery) -> GraphQueryResult:
        release_id = self.active_release()
        if not release_id:
            raise RuntimeError("JSON graph has no active release")
        entities = {str(item["id"]): item for item in self.graph.get("entities") or []}
        allowed_types = set(query.relation_types)
        relations = [
            item for item in self.graph.get("relations") or []
            if not allowed_types or str(item.get("type")) in allowed_types
        ]
        adjacency: dict[str, list[int]] = {}
        for index, relation in enumerate(relations):
            adjacency.setdefault(str(relation["source"]), []).append(index)
            adjacency.setdefault(str(relation["target"]), []).append(index)

        distance = {entity_id: 0 for entity_id in query.entity_ids if entity_id in entities}
        queue = deque(distance)
        selected: set[int] = set()
        while queue:
            entity_id = queue.popleft()
            depth = distance[entity_id]
            if depth >= query.max_hops:
                continue
            for relation_index in adjacency.get(entity_id, ()):
                relation = relations[relation_index]
                is_source = str(relation["source"]) == entity_id
                if query.direction == "outbound" and not is_source:
                    continue
                if query.direction == "inbound" and is_source:
                    continue
                selected.add(relation_index)
                neighbor = (
                    str(relation["target"])
                    if str(relation["source"]) == entity_id
                    else str(relation["source"])
                )
                if neighbor not in distance:
                    distance[neighbor] = depth + 1
                    queue.append(neighbor)

        ordered = sorted(
            (relations[index] for index in selected),
            key=lambda item: (
                min(distance.get(str(item["source"]), 999), distance.get(str(item["target"]), 999)),
                str(item.get("type") or ""), str(item.get("id") or ""),
            ),
        )
        truncated = len(ordered) > query.top_k
        selected_relations = ordered[:query.top_k]
        result_entity_ids = set(query.entity_ids) & set(entities)
        for relation in selected_relations:
            result_entity_ids.update((str(relation["source"]), str(relation["target"])))
        relation_payloads = []
        evidence = []
        for relation in selected_relations:
            relation_payloads.append({
                key: value for key, value in relation.items() if key != "evidence"
            })
            evidence.extend(
                _evidence_reference(item, str(relation["id"]))
                for item in relation.get("evidence") or []
            )
        if len(evidence) > query.top_k:
            truncated = True
            evidence = evidence[:query.top_k]
        return _bounded_result(GraphQueryResult(
            active_release=release_id,
            entities=tuple(entities[item] for item in sorted(result_entity_ids)),
            relations=tuple(relation_payloads),
            evidence_references=tuple(evidence),
            truncated=truncated,
        ), query)


class AgeExecutor(Protocol):
    def execute(
        self, statement: str, parameters: Mapping[str, Any] | None = None,
    ) -> list[Mapping[str, Any]]: ...


def age_engine_for_config(config, default_engine):
    """Allow a dedicated PG16/AGE instance without moving the business database."""
    uri = config.get("KG_AGE_DATABASE_URI")
    return create_engine(uri, pool_pre_ping=True) if uri else default_engine


class SqlAlchemyAgeExecutor:
    """Small SQLAlchemy bridge that configures AGE on each transaction."""

    def __init__(self, engine):
        self.engine = engine

    def execute(self, statement, parameters=None):
        bound = dict(parameters or {})
        timeout_ms = bound.pop("_statement_timeout_ms", None)
        with self.engine.begin() as connection:
            if any(token in statement for token in (
                "cypher(", "create_graph(", "create_vlabel(", "create_elabel(",
            )):
                connection.exec_driver_sql("LOAD 'age'")
                connection.exec_driver_sql('SET LOCAL search_path = ag_catalog, "$user", public')
            if timeout_ms is not None:
                connection.exec_driver_sql(
                    f"SET LOCAL statement_timeout = {max(1, int(timeout_ms))}"
                )
            if "cypher_params" in bound and "cypher(" in statement:
                # AGE requires a server-side Param node, while psycopg2 binds
                # ordinary values as literals. PREPARE supplies the required $1.
                prepared = statement.replace("CAST(:cypher_params AS agtype)", "$1")
                connection.execute(
                    text("PREPARE kg_age_query(agtype) AS " + prepared),
                    {key: value for key, value in bound.items() if key != "cypher_params"},
                )
                try:
                    # A savepoint permits cleanup even if EXECUTE is rejected.
                    with connection.begin_nested():
                        result = connection.execute(
                            text("EXECUTE kg_age_query(CAST(:cypher_params AS agtype))"),
                            {"cypher_params": bound["cypher_params"]},
                        )
                        rows = [dict(row) for row in result.mappings()] if result.returns_rows else []
                    return rows
                finally:
                    connection.exec_driver_sql("DEALLOCATE kg_age_query")
            result = connection.execute(text(statement), bound)
            return [dict(row) for row in result.mappings()] if result.returns_rows else []


def _decode_agtype(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, int, float, bool)):
        return value
    if hasattr(value, "value"):
        return _decode_agtype(value.value)
    raw = str(value)
    raw = re.sub(r"::(?:vertex|edge|path)$", "", raw)
    try:
        return json.loads(raw)
    except ValueError:
        return raw.strip('"')


def _cypher(operation: str, body: str, columns: str) -> str:
    # SQLAlchemy TextClause treats ``:Label`` inside dollar-quoted Cypher as a
    # bind marker unless the colon is escaped.  The escape is removed while
    # compiling and never reaches PostgreSQL.
    body = re.sub(r"(?<!:):(?=[A-Za-z_])", r"\\:", body)
    return (
        f"/* {operation} */ SELECT * FROM cypher(:graph_name, $cypher$\n"
        f"{body}\n$cypher$, CAST(:cypher_params AS agtype)) AS ({columns})"
    )


class AgeGraphStore:
    """Apache AGE GraphStore with stable IDs and release validity intervals."""

    def __init__(
        self,
        executor: AgeExecutor,
        *,
        graph_name: str = DEFAULT_AGE_GRAPH,
        expected_postgres_major: int = POSTGRES_MAJOR,
        expected_age_version: str = AGE_VERSION,
    ):
        if not _GRAPH_NAME.fullmatch(graph_name):
            raise ValueError("AGE graph name must be a safe lowercase SQL identifier")
        self.executor = executor
        self.graph_name = graph_name
        self.expected_postgres_major = int(expected_postgres_major)
        self.expected_age_version = expected_age_version

    def _run(
        self, operation: str, body: str, columns: str, params=None, *, timeout_ms=None,
    ):
        params = dict(params or {})
        if "$properties" in body and "properties" in params:
            # AGE 1.6 requires a syntactic map for SET +=, not a map parameter.
            fields = []
            for key, value in params["properties"].items():
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    raise ValueError("unsafe AGE property name")
                parameter = "property_" + key
                params[parameter] = value
                fields.append(f"{key}: ${parameter}")
            body = body.replace("$properties", "{" + ", ".join(fields) + "}")
        parameters = {
            "graph_name": self.graph_name,
            "cypher_params": json.dumps(params or {}, ensure_ascii=False, sort_keys=True),
        }
        if timeout_ms is not None:
            parameters["_statement_timeout_ms"] = int(timeout_ms)
        return self.executor.execute(
            _cypher(operation, body, columns),
            parameters,
        )

    def ensure_graph(self) -> None:
        self.executor.execute(
            "/* age.ensure_graph */ SELECT create_graph(:graph_name) "
            "WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = :graph_name)",
            {"graph_name": self.graph_name},
        )

    def ensure_schema_indexes(self) -> tuple[str, ...]:
        """Create labels and property GIN indexes before bulk population.

        AGE translates map equality into containment on ``properties``.  The
        labels must exist before PostgreSQL can create the indexes, and the
        indexes must exist before the capacity load so the benchmark measures
        the production schema rather than an unindexed graph.
        """
        for function_name, label_name in (
            ("create_vlabel", "Entity"), ("create_vlabel", "GraphRelease"),
            ("create_vlabel", "GraphControl"), ("create_elabel", "RELATION"),
        ):
            self.executor.execute(
                f"/* age.ensure_labels */ SELECT {function_name}(:graph_name, :label_name) "
                "WHERE to_regclass(format('%I.%I', :graph_name, :label_name)) IS NULL",
                {"graph_name": self.graph_name, "label_name": label_name},
            )
        statements = (
            (
                "kg_entity_properties_gin",
                f'CREATE INDEX IF NOT EXISTS kg_entity_properties_gin '
                f'ON "{self.graph_name}"."Entity" USING gin (properties)',
            ),
            (
                "kg_relation_properties_gin",
                f'CREATE INDEX IF NOT EXISTS kg_relation_properties_gin '
                f'ON "{self.graph_name}"."RELATION" USING gin (properties)',
            ),
            (
                "kg_release_properties_gin",
                f'CREATE INDEX IF NOT EXISTS kg_release_properties_gin '
                f'ON "{self.graph_name}"."GraphRelease" USING gin (properties)',
            ),
            (
                "kg_control_properties_gin",
                f'CREATE INDEX IF NOT EXISTS kg_control_properties_gin '
                f'ON "{self.graph_name}"."GraphControl" USING gin (properties)',
            ),
        )
        for _, statement in statements:
            self.executor.execute(f"/* age.ensure_indexes */ {statement}")
        rows = self.executor.execute(
            "/* age.index_health */ SELECT indexname FROM pg_indexes "
            "WHERE schemaname=:graph_name "
            "ORDER BY indexname",
            {"graph_name": self.graph_name},
        )
        expected = {name for name, _ in statements}
        observed = tuple(
            str(row.get("indexname"))
            for row in rows
            if str(row.get("indexname")) in expected
        )
        if set(observed) != expected:
            raise RuntimeError("required AGE graph indexes are missing")
        return observed

    def entity_lookup_plan(self, entity_id: str) -> dict[str, Any]:
        """Return whether a representative single-entity lookup uses an index."""
        if not entity_id:
            raise ValueError("entity_id is required")
        statement = "EXPLAIN (FORMAT JSON, COSTS OFF) " + _cypher(
            "age.entity_lookup_plan",
            "MATCH (item:Entity {entity_id: $entity_id}) RETURN item.entity_id AS entity_id",
            "entity_id agtype",
        )
        rows = self.executor.execute(statement, {
            "graph_name": self.graph_name,
            "cypher_params": json.dumps({"entity_id": entity_id}, sort_keys=True),
        })
        raw_plan = rows[0].get("QUERY PLAN") if rows else None
        if raw_plan is None and rows:
            raw_plan = next(iter(rows[0].values()), None)
        serialized = json.dumps(raw_plan, ensure_ascii=False, default=str)
        index_scan = "Index Scan" in serialized or "Bitmap Index Scan" in serialized
        return {
            "entity_id": entity_id,
            "uses_index": index_scan,
            "full_graph_scan": not index_scan,
            "plan": raw_plan,
        }

    def health(self) -> Mapping[str, Any]:
        try:
            rows = self.executor.execute(
                "/* age.health */ SELECT CAST(current_setting('server_version_num') AS integer) AS server_version_num, "
                "(SELECT extversion FROM pg_extension WHERE extname='age') AS age_version, "
                "CASE WHEN to_regclass('ag_catalog.ag_graph') IS NULL THEN false "
                "ELSE EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name=:graph_name) END "
                "AS graph_exists",
                {"graph_name": self.graph_name},
            )
        except Exception as exc:
            return {
                "ready": False, "backend": "apache-age", "graph_name": self.graph_name,
                "active_release": None, "errors": ["age_health_query_failed"],
                "error_type": type(exc).__name__,
            }
        row = dict(rows[0]) if rows else {}
        server_number = int(row.get("server_version_num") or 0)
        postgres_major = server_number // 10000
        errors = []
        if postgres_major != self.expected_postgres_major:
            errors.append("postgres_major_mismatch")
        if str(row.get("age_version") or "") != self.expected_age_version:
            errors.append("age_version_mismatch")
        if not row.get("graph_exists"):
            errors.append("age_graph_missing")
        active = self.active_release() if not errors else None
        if not active and not errors:
            errors.append("active_release_missing")
        return {
            "ready": not errors,
            "backend": "apache-age",
            "postgres_major": postgres_major,
            "age_version": row.get("age_version"),
            "graph_name": self.graph_name,
            "active_release": active,
            "errors": errors,
        }

    def active_release(self) -> str | None:
        rows = self._run(
            "age.active_release",
            "MATCH (control:GraphControl {control_id: 'active'}) "
            "RETURN control.active_release AS active_release",
            "active_release agtype",
        )
        if not rows:
            return None
        value = _decode_agtype(rows[0].get("active_release"))
        return str(value) if value else None

    def activate_release(self, release_id: str) -> None:
        rows = self._run(
            "age.activate_release",
            "MATCH (release:GraphRelease {release_id: $release_id}) "
            "WHERE release.validated = true "
            "MERGE (control:GraphControl {control_id: 'active'}) "
            "SET control.active_release = release.release_id, "
            "control.active_sequence = release.sequence "
            "RETURN control.active_release AS active_release",
            "active_release agtype",
            {"release_id": release_id},
        )
        if not rows:
            raise ValueError("release does not exist or is not validated")

    def upsert_release(
        self,
        *,
        release_id: str,
        sequence: int,
        schema_version: str,
        checksum: str,
        entity_count: int,
        relation_count: int,
        evidence_count: int,
        validated: bool,
    ) -> None:
        properties = {
            "release_id": release_id, "sequence": int(sequence),
            "schema_version": schema_version, "checksum": checksum,
            "entity_count": int(entity_count), "relation_count": int(relation_count),
            "evidence_count": int(evidence_count), "validated": bool(validated),
        }
        self._run(
            "age.upsert_release",
            "MERGE (release:GraphRelease {release_id: $release_id}) "
            "SET release += $properties RETURN release.release_id AS release_id",
            "release_id agtype",
            {"release_id": release_id, "properties": properties},
        )

    def upsert_entity(
        self,
        entity: Mapping[str, Any],
        *,
        valid_from_release: str,
        valid_from_sequence: int,
        valid_to_release: str | None = None,
        valid_to_sequence: int | None = None,
    ) -> None:
        entity_id = str(entity.get("id") or "")
        if not entity_id:
            raise ValueError("entity id is required")
        properties = {
            "entity_version_key": f"{entity_id}|{int(valid_from_sequence)}",
            "entity_id": entity_id,
            "entity_type": str(entity.get("type") or ""),
            "name": str(entity.get("name") or ""),
            "payload_json": json.dumps(dict(entity), ensure_ascii=False, sort_keys=True),
            "valid_from_release": valid_from_release,
            "valid_from_sequence": int(valid_from_sequence),
            "valid_to_release": valid_to_release,
            "valid_to_sequence": valid_to_sequence,
        }
        self._run(
            "age.upsert_entity",
            "MERGE (entity:Entity {entity_version_key: $entity_version_key}) "
            "SET entity += $properties RETURN entity.entity_id AS entity_id",
            "entity_id agtype",
            {
                "entity_version_key": properties["entity_version_key"],
                "properties": properties,
            },
        )

    def upsert_relation(
        self,
        relation: Mapping[str, Any],
        *,
        evidence_references: list[Mapping[str, Any]],
        valid_from_release: str,
        valid_from_sequence: int,
        valid_to_release: str | None = None,
        valid_to_sequence: int | None = None,
    ) -> None:
        relation_type = str(relation.get("type") or "")
        source_id = str(relation.get("source") or "")
        target_id = str(relation.get("target") or "")
        if not all((relation_type, source_id, target_id)):
            raise ValueError("relation type and endpoints are required")
        relation_key = f"{relation_type}|{source_id}|{target_id}"
        relation_version_key = f"{relation_key}|{int(valid_from_sequence)}"
        payload = {key: value for key, value in relation.items() if key != "evidence"}
        properties = {
            "relation_key": relation_key,
            "relation_version_key": relation_version_key,
            "relation_id": str(relation.get("id") or relation_key),
            "relation_type": relation_type,
            "source_entity_id": source_id,
            "target_entity_id": target_id,
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            "evidence_refs_json": json.dumps(
                [dict(item) for item in evidence_references], ensure_ascii=False, sort_keys=True,
            ),
            "evidence_count": len(evidence_references),
            "valid_from_release": valid_from_release,
            "valid_from_sequence": int(valid_from_sequence),
            "valid_to_release": valid_to_release,
            "valid_to_sequence": valid_to_sequence,
        }
        rows = self._run(
            "age.upsert_relation",
            "MATCH (source:Entity {entity_id: $source_id}), "
            "(target:Entity {entity_id: $target_id}) "
            "WHERE source.valid_from_sequence <= $valid_from_sequence "
            "AND (source.valid_to_sequence IS NULL OR source.valid_to_sequence > $valid_from_sequence) "
            "AND target.valid_from_sequence <= $valid_from_sequence "
            "AND (target.valid_to_sequence IS NULL OR target.valid_to_sequence > $valid_from_sequence) "
            "MERGE (source)-[relation:RELATION {relation_version_key: $relation_version_key}]->(target) "
            "SET relation += $properties RETURN relation.relation_key AS relation_key",
            "relation_key agtype",
            {
                "source_id": source_id, "target_id": target_id,
                "valid_from_sequence": int(valid_from_sequence),
                "relation_version_key": relation_version_key, "properties": properties,
            },
        )
        if not rows:
            raise ValueError("relation endpoints do not exist")

    def close_relation(
        self, relation_key: str, *, valid_to_release: str,
        valid_to_sequence: int,
    ) -> None:
        rows = self._run(
            "age.close_relation",
            "MATCH ()-[relation:RELATION {relation_key: $relation_key}]->() "
            "WHERE relation.valid_to_sequence IS NULL "
            "SET relation.valid_to_release = $valid_to_release, "
            "relation.valid_to_sequence = $valid_to_sequence "
            "RETURN relation.relation_version_key AS relation_version_key",
            "relation_version_key agtype",
            {
                "relation_key": relation_key,
                "valid_to_release": valid_to_release,
                "valid_to_sequence": int(valid_to_sequence),
            },
        )
        if not rows:
            raise ValueError("active relation version does not exist")

    def _release_sequence(self, release_id: str) -> int:
        rows = self._run(
            "age.release_sequence",
            "MATCH (release:GraphRelease {release_id: $release_id}) "
            "RETURN release.sequence AS sequence",
            "sequence agtype",
            {"release_id": release_id},
        )
        if not rows:
            raise ValueError(f"unknown AGE release: {release_id}")
        return int(_decode_agtype(rows[0].get("sequence")))

    def release_counts(self, release_id: str) -> dict[str, int]:
        """Return server-side counts without exporting the complete graph."""
        sequence = self._release_sequence(release_id)
        params = {"release_sequence": sequence}
        validity = (
            "item.valid_from_sequence <= $release_sequence AND "
            "(item.valid_to_sequence IS NULL OR item.valid_to_sequence > $release_sequence)"
        )
        entity_rows = self._run(
            "age.count_entities",
            f"MATCH (item:Entity) WHERE {validity} RETURN count(item) AS item_count",
            "item_count agtype", params,
        )
        relation_rows = self._run(
            "age.count_relations",
            f"MATCH ()-[item:RELATION]->() WHERE {validity} "
            "RETURN count(item) AS item_count, "
            "coalesce(sum(item.evidence_count), 0) AS evidence_count",
            "item_count agtype, evidence_count agtype", params,
        )
        return {
            "entity_count": int(_decode_agtype(entity_rows[0]["item_count"])) if entity_rows else 0,
            "relation_count": int(_decode_agtype(relation_rows[0]["item_count"])) if relation_rows else 0,
            "evidence_count": int(_decode_agtype(relation_rows[0]["evidence_count"])) if relation_rows else 0,
        }

    def neighbors(self, query: GraphQuery) -> GraphQueryResult:
        release_id = self.active_release()
        if not release_id:
            raise RuntimeError("AGE graph has no active release")
        sequence = self._release_sequence(release_id)
        pattern = {
            "outbound": f"(seed:Entity)-[:RELATION*1..{query.max_hops}]->(neighbor:Entity)",
            "inbound": f"(seed:Entity)<-[:RELATION*1..{query.max_hops}]-(neighbor:Entity)",
            "both": f"(seed:Entity)-[:RELATION*1..{query.max_hops}]-(neighbor:Entity)",
        }[query.direction]
        body = (
            f"MATCH path={pattern} "
            "WHERE seed.entity_id IN $entity_ids "
            "UNWIND relationships(path) AS relation "
            "WITH DISTINCT relation "
            "WHERE (size($relation_types) = 0 OR relation.relation_type IN $relation_types) "
            "AND relation.valid_from_sequence <= $release_sequence "
            "AND (relation.valid_to_sequence IS NULL OR relation.valid_to_sequence > $release_sequence) "
            "RETURN properties(startNode(relation)) AS source, properties(relation) AS relation, "
            "properties(endNode(relation)) AS target "
            f"ORDER BY relation.relation_type, relation.relation_id LIMIT {query.top_k + 1}"
        )
        rows = self._run(
            "age.neighbors", body,
            "source agtype, relation agtype, target agtype",
            {
                "entity_ids": list(query.entity_ids),
                "relation_types": list(query.relation_types),
                "release_sequence": sequence,
            },
            timeout_ms=query.timeout_ms,
        )
        truncated = len(rows) > query.top_k
        entities: dict[str, dict[str, Any]] = {}
        relations = []
        evidence = []
        for row in rows[:query.top_k]:
            source = dict(_decode_agtype(row.get("source")) or {})
            target = dict(_decode_agtype(row.get("target")) or {})
            relation_props = dict(_decode_agtype(row.get("relation")) or {})
            for entity_props in (source, target):
                payload = json.loads(str(entity_props.get("payload_json") or "{}"))
                if payload.get("id"):
                    entities[str(payload["id"])] = payload
            payload = json.loads(str(relation_props.get("payload_json") or "{}"))
            relations.append(payload)
            refs = json.loads(str(relation_props.get("evidence_refs_json") or "[]"))
            evidence.extend(refs)
        if len(evidence) > query.top_k:
            evidence = evidence[:query.top_k]
            truncated = True
        return _bounded_result(GraphQueryResult(
            active_release=release_id,
            entities=tuple(entities[key] for key in sorted(entities)),
            relations=tuple(relations),
            evidence_references=tuple(evidence),
            truncated=truncated,
        ), query)

    def export_snapshot(self, release_id: str) -> dict[str, Any]:
        sequence = self._release_sequence(release_id)
        params = {"release_sequence": sequence}
        validity = (
            "item.valid_from_sequence <= $release_sequence AND "
            "(item.valid_to_sequence IS NULL OR item.valid_to_sequence > $release_sequence)"
        )
        entity_rows = self._run(
            "age.export_entities",
            f"MATCH (item:Entity) WHERE {validity} RETURN item.payload_json AS payload "
            "ORDER BY item.entity_id",
            "payload agtype", params,
        )
        relation_rows = self._run(
            "age.export_relations",
            f"MATCH ()-[item:RELATION]->() WHERE {validity} "
            "RETURN item.payload_json AS payload, item.evidence_refs_json AS evidence "
            "ORDER BY item.relation_type, item.relation_id",
            "payload agtype, evidence agtype", params,
        )
        release_rows = self._run(
            "age.export_release",
            "MATCH (release:GraphRelease {release_id: $release_id}) "
            "RETURN properties(release) AS release",
            "release agtype", {"release_id": release_id},
        )
        release = dict(_decode_agtype(release_rows[0]["release"])) if release_rows else {}
        entities = [
            json.loads(str(_decode_agtype(row["payload"]))) for row in entity_rows
        ]
        relations = []
        for row in relation_rows:
            relation = json.loads(str(_decode_agtype(row["payload"])))
            relation["evidence"] = json.loads(str(_decode_agtype(row["evidence"])))
            relations.append(relation)
        return {
            "schema_version": release.get("schema_version"),
            "release": {"release_id": release_id, "sequence": sequence},
            "entities": entities,
            "relations": relations,
        }
