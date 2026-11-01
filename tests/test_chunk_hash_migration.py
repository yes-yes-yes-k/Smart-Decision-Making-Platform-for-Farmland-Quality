import hashlib
from pathlib import Path

import pytest

from framework.knowledge_graph.chunk_hash_migration import (
    ChunkHashMigration, HashMigrationJournal, HashMigrationError,
)


@pytest.fixture
def migration(tmp_path, monkeypatch):
    import chromadb
    from chromadb.config import Settings
    from framework.upload import document_parser
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"),
        settings=Settings(anonymized_telemetry=False, allow_reset=False))
    collection = client.create_collection("published", embedding_function=None)
    original = tmp_path / "source.pdf"
    original.write_bytes(b"verified original")
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    source = dict(id=1, file_hash=digest, file_path=str(original), file_type="pdf", chunk_count=2,
                  status=1, processing_stage="completed", review_status="approved",
                  visibility_scope="public", document_kind="standard")
    collection.add(ids=["a", "b"], embeddings=[[0.1, 0.2], [0.2, 0.3]], documents=["first", "second"],
        metadatas=[dict(document_id=1, visibility_scope="public", chunk_index=i, page=i+1, owner_id=7) for i in range(2)])
    monkeypatch.setattr(document_parser, "parse_document", lambda *_a, **_k: [(1, "first"), (2, "second")])
    journal = HashMigrationJournal(tmp_path / "audit.sqlite", scope="fixture")
    service = ChunkHashMigration(client, journal, tmp_path)
    yield service, source, collection, journal
    journal.close()


def test_plan_apply_rollback_preserve_vectors_and_all_other_metadata(migration):
    service, source, collection, journal = migration
    original = collection.get(include=["documents", "metadatas", "embeddings"])
    assert service.plan(source)["missing_chunks"] == 2
    assert collection.get()["metadatas"] == original["metadatas"]
    assert service.execute(source)["updated_chunks"] == 2
    assert service.execute(source)["updated_chunks"] == 0
    after = collection.get(include=["documents", "metadatas", "embeddings"])
    assert all(m["content_sha256"] == source["file_hash"] for m in after["metadatas"])
    assert after["documents"] == original["documents"]
    assert (after["embeddings"] == original["embeddings"]).all()
    assert service.execute(source, rollback=True)["updated_chunks"] == 2
    assert collection.get()["metadatas"] == original["metadatas"]
    assert journal.get(1)[1] == "rolled_back"


def test_interrupted_partial_update_resumes_from_immutable_plan(migration):
    service, source, collection, journal = migration
    service.plan(source)
    journal.state(1, "prepared")
    collection.update(ids=["a"], metadatas=[{"content_sha256": source["file_hash"]}])
    assert service.execute(source)["updated_chunks"] == 1
    assert journal.get(1)[1] == "applied"


def test_changed_text_is_blocked_without_writing_hash(migration):
    service, source, collection, _ = migration
    service.plan(source)
    collection.update(ids=["a"], documents=["changed"], embeddings=[[0.1, 0.2]])
    with pytest.raises(HashMigrationError, match="chunks_changed_since_plan"):
        service.execute(source)
    assert all("content_sha256" not in m for m in collection.get()["metadatas"])


def test_changed_original_is_blocked_without_writing_hash(migration):
    service, source, collection, _ = migration
    service.plan(source)
    Path(source["file_path"]).write_bytes(b"changed source")
    with pytest.raises(HashMigrationError, match="source_file_hash_mismatch"):
        service.execute(source)
    assert all("content_sha256" not in m for m in collection.get()["metadatas"])


def test_hash_conflict_and_wrong_scope_are_rejected(migration, tmp_path):
    service, source, collection, _ = migration
    collection.update(ids=["a"], metadatas=[{"content_sha256": "wrong"}])
    with pytest.raises(HashMigrationError, match="existing_hash_conflict"):
        service.plan(source)
    with pytest.raises(HashMigrationError, match="journal_scope_mismatch"):
        HashMigrationJournal(tmp_path / "audit.sqlite", scope="different store")


def test_foreign_metadata_update_is_preserved_and_blocks_stale_plan(migration):
    service, source, collection, _ = migration
    service.plan(source)
    collection.update(ids=["a"], metadatas=[{"owner_id": 8}])
    with pytest.raises(HashMigrationError, match="chunks_changed_since_plan"):
        service.execute(source)
    assert collection.get(ids=["a"])["metadatas"][0]["owner_id"] == 8


def test_withdrawn_source_cannot_be_migrated(migration):
    service, source, collection, _ = migration
    service.plan(source)
    source["visibility_scope"] = "private"
    with pytest.raises(HashMigrationError, match="source_not_eligible"):
        service.execute(source)
    assert all("content_sha256" not in m for m in collection.get()["metadatas"])


def test_already_bound_source_does_not_need_a_new_write_plan(migration):
    service, source, collection, journal = migration
    collection.update(ids=["a", "b"], metadatas=[{"content_sha256": source["file_hash"]}]*2)
    assert service.plan(source)["state"] == "already_bound"
    assert service.execute(source)["updated_chunks"] == 0
    assert journal.get(1) is None
