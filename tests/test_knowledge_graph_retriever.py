import json

from framework.rag.knowledge_graph_retriever import KnowledgeGraphRetriever


def _graph():
    return {
        "schema_version": "minimal-cultivated-land-kg-v0.3",
        "entities": [
            {"id": "obstacle:acidification", "type": "obstacle", "name": "土壤酸化", "aliases": ["酸化"]},
            {"id": "measure:liming", "type": "measure", "name": "施用石灰", "aliases": ["石灰"]},
            {"id": "measure:deep_tillage", "type": "measure", "name": "深松深耕", "aliases": ["深耕"]},
        ],
        "relations": [{
            "id": "rel:approved",
            "type": "addresses",
            "source": "measure:liming",
            "target": "obstacle:acidification",
            "supporting_document_count": 1,
            "evidence": [{
                "document_id": 30,
                "document_title": "材料A",
                "page": 7,
                "chunk_index": 2,
                "quote": "材料明确说明施用石灰用于改良土壤酸化。",
            }],
        }],
    }


class _Store:
    def __init__(self, rows):
        self.rows = rows
        self.call = None

    def get_by_references(self, references, **kwargs):
        self.call = {"references": references, **kwargs}
        return self.rows


def test_graph_result_is_resolved_through_acl_filtered_store(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    store = _Store([{
        "content": "向量库内的正式分块，不是图谱内嵌摘录。",
        "metadata": {
            "document_id": 30, "page": 7, "chunk_index": 2,
            "source": "authorized.pdf", "visibility_scope": "public",
        },
    }])
    filters = {"$and": [
        {"$or": [{"visibility_scope": "public"}, {"owner_id": 42}]},
        {"domain_cultivated_land_quality": True},
    ]}
    retriever = KnowledgeGraphRetriever(str(path))

    result = retriever.retrieve(
        "土壤酸化能不能施用石灰改良？", vector_store=store,
        filters=filters, category="cultivated_land_quality", top_k=5,
    )

    assert store.call["filters"] == filters
    assert result["results"][0]["content"] == "向量库内的正式分块，不是图谱内嵌摘录。"
    assert result["results"][0]["metadata"]["relation_id"] == "rel:approved"
    assert result["results"][0]["metadata"]["retrieval_source"] == "knowledge_graph_v0.3"
    assert result["claim_assessment"]["status"] == "supported"


def test_missing_authorized_chunk_does_not_inject_graph_quote(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    retriever = KnowledgeGraphRetriever(str(path))

    result = retriever.retrieve(
        "土壤酸化怎么改良？", vector_store=_Store([]),
        filters={"visibility_scope": "public"}, category=None, top_k=5,
    )

    assert result["matched"] is True
    assert result["results"] == []


def test_unsupported_measure_is_marked_as_constraint(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    store = _Store([{
        "content": "经授权的替代关系证据。",
        "metadata": {"document_id": 30, "page": 7, "chunk_index": 2},
    }])
    retriever = KnowledgeGraphRetriever(str(path))

    result = retriever.retrieve(
        "深耕能治理土壤酸化吗？", vector_store=store,
        filters={"visibility_scope": "public"}, category="acidification", top_k=5,
    )

    assert result["claim_assessment"]["status"] == "unsupported"
    assert result["results"][0]["metadata"]["graph_claim_status"] == "unsupported"


def test_unrelated_or_other_domain_query_keeps_graph_out(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    retriever = KnowledgeGraphRetriever(str(path))

    assert retriever.retrieve(
        "粮食产能趋势", vector_store=_Store([]), filters=None,
        category="food_security", top_k=5,
    )["matched"] is False
    assert retriever.retrieve(
        "天气怎么样", vector_store=_Store([]), filters=None,
        category=None, top_k=5,
    )["matched"] is False


def test_definition_and_spatial_intents_fall_back_to_vector(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    retriever = KnowledgeGraphRetriever(str(path))

    definition = retriever.retrieve(
        "什么是土壤酸化？", vector_store=_Store([]), filters=None,
        category=None, top_k=5,
    )
    spatial = retriever.retrieve(
        "土壤酸化的空间分布情况", vector_store=_Store([]), filters=None,
        category=None, top_k=5,
    )

    assert definition["matched"] is False
    assert spatial["matched"] is False


def test_merge_prefers_graph_and_deduplicates_same_chunk():
    graph = [{
        "content": "证据", "metadata": {
            "document_id": 1, "page": 2, "chunk_index": 3,
            "retrieval_source": "knowledge_graph_v0.3",
        },
    }]
    vector = [
        {"content": "证据", "metadata": {"document_id": 1, "page": 2, "chunk_index": 3}},
        {"content": "补充", "metadata": {"document_id": 2, "page": 1, "chunk_index": 0}},
    ]

    merged = KnowledgeGraphRetriever.merge(graph, vector, top_k=5)

    assert [row["content"] for row in merged] == ["证据", "补充"]
    assert merged[0]["metadata"]["retrieval_source"] == "knowledge_graph_v0.3"


def test_v04_graph_marks_results_with_v04_source(tmp_path):
    graph = _graph()
    graph["schema_version"] = "minimal-cultivated-land-kg-v0.4"
    graph["relations"][0]["display_label"] = "用于改良"
    graph["relations"][0]["semantics"] = {
        "dimension": "test_dimension", "value": "test_value",
    }
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    store = _Store([{
        "content": "经授权的图谱证据。",
        "metadata": {"document_id": 30, "page": 7, "chunk_index": 2},
    }])

    result = KnowledgeGraphRetriever(str(path)).retrieve(
        "土壤酸化能不能施用石灰改良？", vector_store=store,
        filters={"visibility_scope": "public"}, category=None, top_k=5,
    )

    assert result["results"][0]["metadata"]["retrieval_source"] == "knowledge_graph_v0.4"
    assert result["results"][0]["metadata"]["relation_label"] == "用于改良"
    assert result["results"][0]["metadata"]["relation_semantics"] == {
        "dimension": "test_dimension", "value": "test_value",
    }


def test_same_chunk_keeps_all_ranked_relation_ids(tmp_path):
    graph = _graph()
    graph["schema_version"] = "minimal-cultivated-land-kg-v0.4"
    graph["relations"].append({
        **graph["relations"][0],
        "id": "rel:second",
        "source": "measure:deep_tillage",
    })
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    store = _Store([{
        "content": "同一个经授权的证据分块。",
        "metadata": {"document_id": 30, "page": 7, "chunk_index": 2},
    }])

    result = KnowledgeGraphRetriever(str(path)).retrieve(
        "土壤酸化怎么改良？", vector_store=store,
        filters={"visibility_scope": "public"}, category=None, top_k=5,
    )

    metadata = result["results"][0]["metadata"]
    assert set(metadata["relation_ids"]) == {"rel:approved", "rel:second"}
    assert {item["relation_id"] for item in metadata["graph_relations"]} == {
        "rel:approved", "rel:second",
    }
