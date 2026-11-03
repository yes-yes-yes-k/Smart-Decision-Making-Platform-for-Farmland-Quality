"""Replay one actual document on the isolated full-corpus clone, no models."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import types
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_knowledge_m2_snapshot import OUT
from framework.knowledge_graph.operational_measurements import process_memory


def main():
    target = OUT/"incremental-v1.json"
    if target.exists():
        raise ValueError("measurement_exists_use_new_version")
    clone = (OUT/"runtime/chroma-clone").resolve()
    if OUT.resolve() not in clone.parents or not (clone/"lexical-index.sqlite3").exists():
        raise ValueError("isolated_ready_clone_required")
    os.environ["CHROMA_PERSIST_DIR"] = str(clone)
    embeddings = []
    fake = types.ModuleType("framework.embedding.service")
    def replay(texts):
        if texts != documents:
            raise ValueError("only_identical_actual_document_replay_allowed")
        return embeddings
    fake.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_documents=replay,
        embed_query=lambda query: (_ for _ in ()).throw(RuntimeError("no_embedding_calls")))
    sys.modules["framework.embedding.service"] = fake
    from framework.vector_store.chroma_store import vector_store, ChromaVectorStore
    store = vector_store
    collection = store._get_collection()
    data = collection.get(where={"document_id": 100}, include=["documents", "metadatas", "embeddings"])
    documents, metas, identifiers = data["documents"], data["metadatas"], data["ids"]
    embeddings.extend(data["embeddings"].tolist())
    if len(identifiers) != 102:
        raise ValueError("actual_replay_document_changed")
    owner = metas[0]["owner_id"]
    phases = []
    def health():
        return {"vectors": store.get_collection_stats()["count"],
            "lexical": {name: bm.index.health() for name, bm in store._bm25.items()}}
    def measure(name, operation):
        before = health(); started = time.perf_counter(); cpu = time.process_time()
        result = operation()
        phases.append({"phase": name, "seconds": time.perf_counter()-started, "cpu_seconds": time.process_time()-cpu,
            "result": result, "before": before, "after": health(), "memory": process_memory()})
        print(json.dumps({"phase": name, "seconds": phases[-1]["seconds"], "result": result}), flush=True)
        return result
    initial = health()
    if initial["vectors"] != 112168:
        raise ValueError("full_actual_scope_changed")
    assert measure("duplicate_idempotent_replay", lambda: store.add_documents(documents, metas, ids=identifiers)) == 0
    assert measure("delete_one_actual_document", lambda: store.delete_by_document_id(100, owner)) == 102
    assert measure("replay_one_actual_document", lambda: store.add_documents(documents, metas, ids=identifiers)) == 102
    before_tokens = sum(bm.index.metrics["tokenized_rows"] for bm in store._bm25.values())
    assert measure("permission_revoke", lambda: store.update_document_metadata(100, {"visibility_scope": "private"}, owner)) == 102
    assert not store._bm25_search("soil", 10, {"$and": [{"document_id": 100}, {"visibility_scope": "public"}]})
    assert measure("permission_restore", lambda: store.update_document_metadata(100, {"visibility_scope": "public"}, owner)) == 102
    after_tokens = sum(bm.index.metrics["tokenized_rows"] for bm in store._bm25.values())
    assert after_tokens == before_tokens
    assert measure("deferred_metadata_update", lambda: store.update_document_metadata(100, {"visibility_scope": "private"}, owner, rebuild_indexes=False)) == 102
    dirty = health()
    assert sum(v["pending_operations"] for v in dirty["lexical"].values()) == 1
    store.close()
    started = time.perf_counter(); store = ChromaVectorStore()
    phases.append({"phase": "restart_recovers_deferred_scope", "seconds": time.perf_counter()-started, "after": health(), "memory": process_memory()})
    assert sum(bm.index.metrics["tokenized_rows"] for bm in store._bm25.values()) == 0
    with patch.object(ChromaVectorStore, "_sync_lexical_pending", side_effect=RuntimeError("injected_derivative_failure")):
        assert measure("derived_failure_keeps_primary_and_journal", lambda: store.update_document_metadata(100, {"visibility_scope": "public"}, owner)) == 102
    assert sum(v["pending_operations"] for v in health()["lexical"].values()) == 1
    store.close()
    started = time.perf_counter(); store = ChromaVectorStore()
    phases.append({"phase": "restart_recovers_failed_scope", "seconds": time.perf_counter()-started, "after": health(), "memory": process_memory()})
    final = health()
    assert final["vectors"] == 112168
    assert sum(v["rows"] for v in final["lexical"].values()) == 112168
    assert sum(v["pending_operations"] for v in final["lexical"].values()) == 0
    final_data = store._get_collection().get(ids=identifiers, include=["documents", "metadatas"])
    assert dict(zip(final_data["ids"], zip(final_data["documents"], final_data["metadatas"]))) == dict(zip(identifiers, zip(documents, metas)))
    report = {"state": "completed", "captured_at_utc": datetime.now(timezone.utc).isoformat(), "document_id": 100,
        "actual_document_chunks": 102, "model_calls": 0, "scope": "isolated_full_corpus_clone_only",
        "embedding_cost": "excluded_identical_existing_vectors_replayed", "phases": phases, "initial": initial, "final": final,
        "metadata_update_retokenized_rows": after_tokens-before_tokens, "document_restored_exactly": True,
        "published_claims_added": 0}
    store.close()
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"state": report["state"], "vectors": final["vectors"], "pending": 0}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); main()
