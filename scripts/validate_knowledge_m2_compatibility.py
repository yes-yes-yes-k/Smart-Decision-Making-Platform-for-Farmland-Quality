"""Run relevant existing tests without root app/conftest or paid embeddings."""
import json
from pathlib import Path
import sys
import tempfile
import types

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main():
    from framework.config import Config
    temp = tempfile.TemporaryDirectory(prefix="M2-compatibility-")
    Config.CHROMA_PERSIST_DIR = str(Path(temp.name)/"module-startup")
    fake = types.ModuleType("framework.embedding.service")
    def forbidden(*args, **kwargs):
        raise RuntimeError("M2_compatibility_no_model_calls")
    fake.embedding_service = types.SimpleNamespace(is_available=lambda: False, embed_documents=forbidden, embed_query=forbidden)
    sys.modules["framework.embedding.service"] = fake
    import pytest
    from framework.vector_store.chroma_store import ChromaVectorStore
    instances = []
    original = ChromaVectorStore.__init__
    def track(self):
        original(self); instances.append(self)
    ChromaVectorStore.__init__ = track
    result = pytest.main(["--noconftest", "-q", "tests/test_bm25_store.py", "tests/test_kb_persistence.py",
        "tests/test_collection_routing.py", "tests/test_hybrid_search.py"])
    from framework.vector_store.chroma_store import vector_store
    for instance in instances:
        instance.close()
    vector_store.close()
    import chromadb
    chromadb.api.client.SharedSystemClient.clear_system_cache()
    temp.cleanup()
    print(json.dumps({"exit_code": result, "app_started": False, "model_calls": 0}))
    return result


if __name__ == "__main__":
    sys.exit(main())
