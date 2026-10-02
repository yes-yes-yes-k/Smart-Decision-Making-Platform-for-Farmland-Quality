from framework.rag.chain import RAGChain


def test_retrieval_applies_owner_filter(monkeypatch):
    captured = {}

    class _VectorStore:
        def hybrid_search(self, **kwargs):
            captured.update(kwargs)
            return {"results": [], "count": 0}

    rag = RAGChain.__new__(RAGChain)
    rag.vector_store = _VectorStore()
    monkeypatch.setattr("framework.rag.chain.route_category", lambda query: None)

    result = rag._retrieve_documents("酸化", None, user_id=42)

    assert result == {"results": [], "count": 0}
    assert captured["filters"] == {"owner_id": 42}


def test_owner_and_document_filters_are_combined():
    assert RAGChain._build_filters({"b.pdf", "a.pdf"}, 9) == {
        "$and": [
            {"owner_id": 9},
            {"source": {"$in": ["a.pdf", "b.pdf"]}},
        ]
    }
