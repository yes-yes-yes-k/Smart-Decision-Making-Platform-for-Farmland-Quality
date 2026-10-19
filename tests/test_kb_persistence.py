from framework.config import Config
from framework.vector_store import chroma_store as chroma_module
from framework.vector_store.chroma_store import ChromaVectorStore


def _patch_embeddings(monkeypatch):
    monkeypatch.setattr(chroma_module.embedding_service, "is_available", lambda: True)
    monkeypatch.setattr(
        chroma_module.embedding_service,
        "embed_documents",
        lambda texts: [[float(index + 1), 0.5] for index, _ in enumerate(texts)],
    )
    monkeypatch.setattr(
        chroma_module.embedding_service, "embed_query", lambda text: [1.0, 0.5],
    )


def test_domain_collection_and_bm25_survive_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    _patch_embeddings(monkeypatch)

    first = ChromaVectorStore()
    assert first.add_documents(
        ["酸化治理采用石灰调理"],
        [{
            "source": "acid.pdf", "doc_name": "酸化资料.pdf",
            "document_id": 10, "owner_id": 7, "treatment_type": None,
        }],
        ids=["doc-10-chunk-0"],
        category="acidification",
    ) == 1

    restarted = ChromaVectorStore()
    assert "kb_acidification" in restarted._collections
    assert restarted.get_collection_stats()["count"] == 1
    results = restarted._bm25_search(
        "酸化治理", 5, {"owner_id": 7}, "acidification",
    )
    assert results[0]["metadata"]["document_id"] == 10


def test_generated_ids_do_not_collide_between_batches(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    _patch_embeddings(monkeypatch)
    store = ChromaVectorStore()

    assert store.add_documents(
        ["第一份资料"], [{"source": "a.pdf", "owner_id": 1}],
        category="acidification",
    ) == 1
    assert store.add_documents(
        ["第二份资料"], [{"source": "b.pdf", "owner_id": 1}],
        category="acidification",
    ) == 1
    assert store._get_collection("acidification").count() == 2


def test_delete_by_document_id_respects_owner(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    _patch_embeddings(monkeypatch)
    store = ChromaVectorStore()
    store.add_documents(
        ["用户一", "用户二"],
        [
            {"source": "same.pdf", "document_id": 1, "owner_id": 1},
            {"source": "same.pdf", "document_id": 2, "owner_id": 2},
        ],
        ids=["doc-1-chunk-0", "doc-2-chunk-0"],
    )

    assert store.delete_by_document_id(1, owner_id=1) == 1
    remaining = store._get_collection().get(include=["metadatas"])
    assert remaining["metadatas"] == [
        {"source": "same.pdf", "document_id": 2, "owner_id": 2}
    ]


def test_update_document_metadata_updates_chroma_and_bm25(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    _patch_embeddings(monkeypatch)
    store = ChromaVectorStore()
    store.add_documents(
        ["镉污染风险评价"],
        [{"source": "risk.pdf", "document_id": 7, "owner_id": 1}],
        ids=["doc-7-chunk-0"],
        category="cultivated_land_quality",
    )

    assert store.update_document_metadata(7, {
        "visibility_scope": "public",
        "domain_heavy_metal": True,
    }, owner_id=1) == 1

    metadata = store._get_collection("cultivated_land_quality").get(
        ids=["doc-7-chunk-0"], include=["metadatas"],
    )["metadatas"][0]
    assert metadata["visibility_scope"] == "public"
    assert metadata["domain_heavy_metal"] is True
    results = store._bm25_search(
        "镉污染", 5,
        {"$and": [
            {"visibility_scope": "public"},
            {"domain_heavy_metal": True},
        ]},
        "heavy_metal",
    )
    assert results[0]["metadata"]["document_id"] == 7
