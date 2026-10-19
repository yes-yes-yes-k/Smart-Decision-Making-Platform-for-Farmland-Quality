from framework.rag.chain import RAGChain


def test_retrieval_combines_public_and_owner_access(monkeypatch):
    captured = {}

    class _VectorStore:
        def hybrid_search(self, **kwargs):
            captured.update(kwargs)
            return {"results": [], "count": 0}

    rag = RAGChain.__new__(RAGChain)
    rag.vector_store = _VectorStore()
    monkeypatch.setattr("framework.rag.chain.route_category", lambda query: None)

    result = rag._retrieve_documents("酸化", None, user_id=42)

    assert result["results"] == []
    assert result["count"] == 0
    assert captured["filters"] == {
        "$or": [
            {"visibility_scope": "public"},
            {"owner_id": 42},
        ]
    }


def test_owner_and_document_filters_are_combined():
    assert RAGChain._build_filters({"b.pdf", "a.pdf"}, 9) == {
        "$and": [
            {"$or": [
                {"visibility_scope": "public"},
                {"owner_id": 9},
            ]},
            {"source": {"$in": ["a.pdf", "b.pdf"]}},
        ]
    }


def test_domain_filter_is_added_after_access_filter():
    assert RAGChain._build_filters(None, 9, "heavy_metal") == {
        "$and": [
            {"$or": [
                {"visibility_scope": "public"},
                {"owner_id": 9},
            ]},
            {"domain_heavy_metal": True},
        ]
    }


def test_anonymous_internal_retrieval_only_sees_public_documents():
    assert RAGChain._build_filters(None, None) == {
        "visibility_scope": "public",
    }
