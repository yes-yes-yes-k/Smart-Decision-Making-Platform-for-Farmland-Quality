from pathlib import Path

import pytest

from framework.knowledge_graph import ExtractionRequest, SourceChunk, load_graph_schema
from framework.knowledge_graph.adapters import (
    GraphRagAdapterError,
    GraphRagArtifactBundle,
    GraphRagEntityRecord,
    GraphRagRelationshipRecord,
    GraphRagTextUnitRecord,
    MicrosoftGraphRagBackend,
    ParquetGraphRagArtifactProvider,
    StaticGraphRagArtifactProvider,
)
from framework.knowledge_graph.conformance import evaluate_extraction_backend


def _request():
    chunk = SourceChunk(
        document_id=17,
        content_sha256="sha-17",
        chunk_index=2,
        page=8,
        content="土壤酸化可通过施用石灰进行治理。",
    )
    return ExtractionRequest(
        job_id="job:17",
        document_id=17,
        content_sha256="sha-17",
        schema_version="minimal-cultivated-land-kg-schema-v1",
        chunks=(chunk,),
    )


def _bundle(*, relation_type=None, text=None):
    return GraphRagArtifactBundle(
        entities=(
            GraphRagEntityRecord("graphrag:e1", "施用石灰", "MEASURE", ("tu-1",)),
            GraphRagEntityRecord("graphrag:e2", "土壤酸化", "OBSTACLE", ("tu-1",)),
        ),
        relationships=(
            GraphRagRelationshipRecord(
                "graphrag:r1",
                "施用石灰",
                "土壤酸化",
                ("tu-1",),
                description="模型生成的总结，不得作为证据原文",
                relation_type=relation_type,
            ),
        ),
        text_units=(
            GraphRagTextUnitRecord(
                "tu-1", text or "土壤酸化可通过施用石灰进行治理。", 2,
            ),
        ),
    )


def _backend(bundle=None):
    return MicrosoftGraphRagBackend(
        provider=StaticGraphRagArtifactProvider(bundle or _bundle()),
        schema=load_graph_schema(),
        version="3.3.0",
    )


def test_graphrag_adapter_is_candidate_only_and_passes_conformance():
    request = _request()
    backend = _backend()

    result = backend.extract(request)
    report = evaluate_extraction_backend(backend, request, load_graph_schema())

    assert backend.candidate_only is True
    assert report.passed, report.issues
    assert result.backend_name == "microsoft-graphrag"
    assert result.backend_version == "3.3.0"
    assert len(result.entities) == 2
    assert all(entity.canonical_id is None for entity in result.entities)
    assert len(result.relations) == 1
    assert result.relations[0].relation_type == "addresses"
    evidence = result.relations[0].evidence[0]
    assert evidence.quote == request.chunks[0].content
    assert evidence.quote != _bundle().relationships[0].description


def test_graphrag_adapter_requires_explicit_type_for_ambiguous_direction():
    chunk = SourceChunk(17, "sha-17", 2, "标准规定土壤pH测定方法。", 8)
    request = ExtractionRequest(
        "job:17", 17, "sha-17", "minimal-cultivated-land-kg-schema-v1", (chunk,),
    )
    bundle = GraphRagArtifactBundle(
        entities=(
            GraphRagEntityRecord("e1", "标准A", "standard"),
            GraphRagEntityRecord("e2", "土壤pH", "indicator"),
        ),
        relationships=(
            GraphRagRelationshipRecord("r1", "标准A", "土壤pH", ("tu-1",)),
        ),
        text_units=(GraphRagTextUnitRecord("tu-1", chunk.content, 2),),
    )

    with pytest.raises(GraphRagAdapterError, match="explicit structured relation_type"):
        _backend(bundle).extract(request)

    explicit = GraphRagArtifactBundle(
        entities=bundle.entities,
        relationships=(
            GraphRagRelationshipRecord(
                "r1", "标准A", "土壤pH", ("tu-1",),
                relation_type="prescribes_measurement",
            ),
        ),
        text_units=bundle.text_units,
    )
    assert _backend(explicit).extract(request).relations[0].relation_type == (
        "prescribes_measurement"
    )


def test_graphrag_adapter_rejects_non_exact_or_unlocated_evidence():
    with pytest.raises(GraphRagAdapterError, match="does not exactly match"):
        _backend(_bundle(text="被改写的模型文本")).extract(_request())

    missing = GraphRagArtifactBundle(
        entities=_bundle().entities,
        relationships=(
            GraphRagRelationshipRecord("r1", "施用石灰", "土壤酸化", ("missing",)),
        ),
        text_units=_bundle().text_units,
    )
    with pytest.raises(GraphRagAdapterError, match="unknown text unit"):
        _backend(missing).extract(_request())


class _Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


def test_parquet_provider_reads_documented_tables_without_importing_graphrag():
    tables = {
        "entities.parquet": [
            {"id": "e1", "title": "施用石灰", "type": "measure", "text_unit_ids": ["t1"]},
            {"id": "e2", "title": "土壤酸化", "type": "obstacle", "text_unit_ids": ["t1"]},
        ],
        "relationships.parquet": [{
            "id": "r1", "source": "施用石灰", "target": "土壤酸化",
            "description": "治理", "text_unit_ids": ["t1"],
        }],
        "text_units.parquet": [{
            "id": "t1", "text": _request().chunks[0].content, "source_chunk_index": 2,
        }],
    }
    observed = []

    def reader(path: Path):
        observed.append(path.name)
        return _Frame(tables[path.name])

    provider = ParquetGraphRagArtifactProvider("ignored", read_parquet=reader)
    backend = MicrosoftGraphRagBackend(
        provider=provider, schema=load_graph_schema(), version="3.3.0",
    )

    result = backend.extract(_request())

    assert observed == ["entities.parquet", "relationships.parquet", "text_units.parquet"]
    assert result.relations[0].relation_type == "addresses"


def test_graphrag_adapter_rejects_unpinned_version_and_vendor_ids_never_escape():
    with pytest.raises(ValueError, match="exact GraphRAG version"):
        MicrosoftGraphRagBackend(
            provider=StaticGraphRagArtifactProvider(_bundle()),
            schema=load_graph_schema(),
            version="latest",
        )

    result = _backend().extract(_request())
    serialized = str(result.to_dict())
    assert "graphrag:e1" not in serialized
    assert "graphrag:r1" not in serialized
