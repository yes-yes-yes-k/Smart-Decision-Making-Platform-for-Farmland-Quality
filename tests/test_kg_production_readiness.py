import json
from concurrent.futures import ThreadPoolExecutor

from framework.knowledge_graph.release import prepare_graph_release, publish_graph_release
from framework.rag.kg_runtime import (
    KGMetrics, inspect_graph_release, rewrite_query_for_retrieval, rollout_decision,
)
from framework.rag.knowledge_graph_retriever import KnowledgeGraphRetriever


def _graph():
    return {
        "schema_version": "minimal-cultivated-land-kg-v0.4",
        "entities": [
            {"id": "standard:a", "type": "standard", "name": "标准A"},
            {"id": "indicator:a", "type": "indicator", "name": "指标A"},
        ],
        "relations": [{
            "id": "rel:a", "type": "includes_indicator",
            "source": "standard:a", "target": "indicator:a",
            "evidence": [{
                "document_id": 1, "document_title": "标准A", "page": 2,
                "chunk_index": 3, "quote": "标准A包含指标A。",
            }],
        }],
        "validation": {"passed": True},
        "lineage": {"base_schema_version": "minimal-cultivated-land-kg-v0.3"},
    }


def test_release_adds_stable_evidence_identity():
    first = prepare_graph_release(_graph(), release_id="r1", reviewed_by="reviewer")
    second = prepare_graph_release(_graph(), release_id="r2", reviewed_by="reviewer")
    a = first["relations"][0]["evidence"][0]
    b = second["relations"][0]["evidence"][0]
    assert a["evidence_id"] == b["evidence_id"]
    assert len(a["quote_sha256"]) == 64
    assert a["document_key"].startswith("document:")


def test_stable_document_key_survives_database_id_and_rechunking():
    from framework.rag.kg_runtime import stable_document_key
    reference = {
        "document_id": 1, "document_key": stable_document_key("标准A.pdf"),
        "page": 7, "chunk_index": 3,
    }
    metadata = {
        "document_id": 999, "document_key": stable_document_key("标准A.docx"),
        "page": 7, "chunk_index": 18,
    }
    assert KnowledgeGraphRetriever._reference_matches(metadata, reference) is True


def test_release_manifest_detects_tampering(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    manifest = tmp_path / "graph.manifest.json"
    publish_graph_release(
        graph, manifest_path=manifest, release_id="r1", reviewed_by="reviewer",
    )
    assert inspect_graph_release(graph, manifest_path=manifest)["ready"] is True
    graph.write_text(graph.read_text(encoding="utf-8") + " ", encoding="utf-8")
    health = inspect_graph_release(graph, manifest_path=manifest)
    assert health["ready"] is False
    assert "manifest_checksum_mismatch" in health["errors"]


def test_retriever_refuses_invalid_release_manifest(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps(_graph(), ensure_ascii=False), encoding="utf-8")
    manifest = tmp_path / "graph.manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "minimal-cultivated-land-kg-v0.4", "sha256": "bad",
    }), encoding="utf-8")
    retriever = KnowledgeGraphRetriever(str(graph), manifest_path=str(manifest))
    assert retriever._load_graph() is None
    assert retriever.health()["ready"] is False


def test_multiturn_rewrite_resolves_short_follow_up():
    rewritten = rewrite_query_for_retrieval(
        "那它属于哪类？", [{"role": "user", "content": "有机质在国标里怎么规定？"}],
    )
    assert "有机质" in rewritten
    assert "那它属于哪类" in rewritten
    assert rewrite_query_for_retrieval("请详细解释有机质检测流程和适用标准", []) == "请详细解释有机质检测流程和适用标准"


def test_rollout_supports_off_shadow_allowlist_and_percentage():
    assert rollout_decision(mode="off", user_id=1, conversation_id=1, query="q", canary_percent=100)["active"] is False
    assert rollout_decision(mode="shadow", user_id=1, conversation_id=1, query="q", canary_percent=100)["shadow"] is True
    allowed = rollout_decision(
        mode="canary", user_id=42, conversation_id=1, query="q",
        canary_percent=0, canary_user_ids=(42,),
    )
    assert allowed["active"] is True and allowed["reason"] == "allowlisted_user"
    assert rollout_decision(mode="canary", user_id=7, conversation_id=1, query="q", canary_percent=100)["active"] is True
    assert rollout_decision(mode="canary", user_id=7, conversation_id=1, query="q", canary_percent=0)["active"] is False


def test_shadow_compares_graph_without_changing_vector_answer(monkeypatch):
    from framework.config import Config
    from framework.rag.chain import RAGChain
    from framework.rag import chain as chain_module
    monkeypatch.setattr(Config, "KG_ROLLOUT_MODE", "shadow")
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    monkeypatch.setattr(chain_module, "route_category", lambda _: None)
    class Store:
        def hybrid_search(self, **kwargs):
            return {"results": [{"content": "vector", "metadata": {"document_id": 2}}], "count": 1}
    class KG:
        def retrieve(self, *args, **kwargs):
            return {"results": [{"content": "graph", "metadata": {"document_id": 1}}], "matched": True, "claim_assessment": None}
        def health(self):
            return {"schema_version": "minimal-cultivated-land-kg-v0.4"}
        @staticmethod
        def merge(graph, vector, *, top_k):
            return [*graph, *vector][:top_k]
    rag = RAGChain.__new__(RAGChain)
    rag.vector_store, rag.kg_retriever = Store(), KG()
    result = rag._retrieve_documents("问题", None, user_id=7)
    assert result["results"][0]["content"] == "vector"
    assert result["diagnostics"]["shadow"] is True
    assert result["diagnostics"]["graph_result_count"] == 1


def test_graph_exception_keeps_vector_retrieval_available(monkeypatch):
    from framework.config import Config
    from framework.rag.chain import RAGChain
    from framework.rag import chain as chain_module
    monkeypatch.setattr(Config, "KG_ROLLOUT_MODE", "enabled")
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    monkeypatch.setattr(chain_module, "route_category", lambda _: None)

    class Store:
        def hybrid_search(self, **kwargs):
            return {"results": [{"content": "vector survives", "metadata": {}}], "count": 1}

    class BrokenGraph:
        def retrieve(self, *args, **kwargs):
            raise RuntimeError("AGE internal path and provider secret")

        def health(self):
            return {"ready": False}

        @staticmethod
        def merge(graph, vector, *, top_k):
            return [*graph, *vector][:top_k]

    rag = RAGChain.__new__(RAGChain)
    rag.vector_store, rag.kg_retriever = Store(), BrokenGraph()
    result = rag._retrieve_documents("问题", None, user_id=7)
    assert result["results"][0]["content"] == "vector survives"
    assert result["diagnostics"]["graph_error"] == "graph_retrieval_unavailable"
    assert "secret" not in str(result["diagnostics"])


def test_allowlisted_canary_changes_only_eligible_user(monkeypatch):
    from framework.config import Config
    from framework.rag.chain import RAGChain
    from framework.rag import chain as chain_module
    monkeypatch.setattr(Config, "KG_ROLLOUT_MODE", "canary")
    monkeypatch.setattr(Config, "KG_CANARY_PERCENT", 0)
    monkeypatch.setattr(Config, "KG_CANARY_USER_IDS", (42,))
    monkeypatch.setattr(Config, "RERANK_ENABLED", False)
    monkeypatch.setattr(chain_module, "route_category", lambda _: None)
    class Store:
        def hybrid_search(self, **kwargs):
            return {"results": [{"content": "vector", "metadata": {"document_id": 2}}], "count": 1}
    class KG:
        def retrieve(self, *args, **kwargs):
            return {"results": [{"content": "graph", "metadata": {"document_id": 1}}], "matched": True, "claim_assessment": None}
        def health(self):
            return {"schema_version": "minimal-cultivated-land-kg-v0.4"}
        @staticmethod
        def merge(graph, vector, *, top_k):
            return [*graph, *vector][:top_k]
    rag = RAGChain.__new__(RAGChain)
    rag.vector_store, rag.kg_retriever = Store(), KG()
    canary = rag._retrieve_documents("问题", None, user_id=42)
    control = rag._retrieve_documents("问题", None, user_id=7)
    assert canary["results"][0]["content"] == "graph"
    assert control["results"][0]["content"] == "vector"


def test_metrics_are_thread_safe():
    metrics = KGMetrics(max_events=20)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: metrics.record({"mode": "canary", "active": True, "latency_ms": 1}), range(200)))
    snapshot = metrics.snapshot()
    assert snapshot["counts"]["requests"] == 200
    assert snapshot["counts"]["active"] == 200
    assert len(snapshot["recent_events"]) == 20


def test_prompt_separates_role_and_acquisition_dimensions():
    from framework.rag.chain import RAGChain
    prompt = RAGChain.__new__(RAGChain)._build_prompt("问题", "证据")
    assert "两个维度相互独立" in prompt
    assert "不得用一个维度证明另一个维度" in prompt
    assert "证据不足" in prompt


def test_authoritative_queries_fail_closed():
    from framework.rag.chain import RAGChain
    assert RAGChain._is_authoritative_query("国标把有机质列为什么指标？") is True
    assert RAGChain._is_authoritative_query("写一首稻田的诗") is False


def test_source_contract_exposes_graph_provenance():
    from framework.rag.chain import RAGChain
    rows = [{"content": "证据", "metadata": {
        "source": "a.pdf", "page": 2, "chunk_index": 3,
        "retrieval_source": "knowledge_graph_v0.4",
        "graph_schema_version": "minimal-cultivated-land-kg-v0.4",
        "relation_id": "rel:a", "relation_type": "includes_indicator",
        "relation_label": "包含指标", "source_entity": "标准A",
        "target_entity": "指标A", "evidence_id": "evidence:a",
    }}]
    source = RAGChain._build_sources(rows, {})[0]
    assert source["relation_id"] == "rel:a"
    assert source["evidence_id"] == "evidence:a"
    assert source["graph_schema_version"] == "minimal-cultivated-land-kg-v0.4"


def test_professional_evidence_node_uses_shared_acl_path(monkeypatch):
    from framework.agents.nodes import retrieve_professional_evidence
    from framework.rag.chain import rag_chain
    seen = {}
    def fake_bundle(query, **kwargs):
        seen.update({"query": query, **kwargs})
        return {"context": "证据", "sources": [{"doc_name": "标准A"}], "retrieved_count": 1, "diagnostics": {}}
    monkeypatch.setattr(rag_chain, "retrieve_evidence_bundle", fake_bundle)
    state = {
        "request": {"question": "解释障碍诊断结果"}, "user_id": 7,
        "conversation_id": 9, "conversation_history": [], "rag_response": {},
    }
    result = retrieve_professional_evidence(state)
    assert seen["user_id"] == 7 and seen["conversation_id"] == 9
    assert result["rag_response"]["context"] == "证据"


def test_production_acceptance_builder_has_120_unique_questions():
    from scripts.build_kg_production_acceptance import build
    graph = {
        "schema_version": "minimal-cultivated-land-kg-v0.4",
        "entities": [], "relations": [],
    }
    # The real artifact is required because the production set covers all 66
    # reviewed relations rather than a toy fixture.
    from pathlib import Path
    path = Path(__file__).parents[1] / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    payload = build(graph)
    assert payload["question_count"] == 120
    assert len({
        (json.dumps(row.get("history") or [], ensure_ascii=False, sort_keys=True), row["question"])
        for row in payload["questions"]
    }) == 120
    assert payload["strata"]["permission_adversarial"] == 5
