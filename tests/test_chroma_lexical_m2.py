"""Real isolated Chroma integration, with offline test vectors and no app startup."""
import gc
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


class ChromaLexicalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="M2-isolated-chroma-")
        from framework.config import Config
        cls.config = Config
        cls.original_path = Config.CHROMA_PERSIST_DIR
        Config.CHROMA_PERSIST_DIR = str(Path(cls.temp.name)/"module-startup")
        # Test vectors only validate persistence and coordination, never quality.
        embedding = types.ModuleType("framework.embedding.service")
        embedding.embedding_service = types.SimpleNamespace(is_available=lambda: True,
            embed_documents=lambda texts: [[1.0, float(i+1)] for i, _ in enumerate(texts)], embed_query=lambda query: [1.0, 1.0])
        cls.patch_embedding = patch.dict(sys.modules, {"framework.embedding.service": embedding})
        cls.patch_embedding.start()
        from framework.vector_store.chroma_store import ChromaVectorStore
        cls.store_class = ChromaVectorStore

    @classmethod
    def tearDownClass(cls):
        import chromadb
        from framework.vector_store.chroma_store import vector_store
        vector_store.close()
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        cls.config.CHROMA_PERSIST_DIR = cls.original_path
        cls.patch_embedding.stop(); gc.collect(); cls.temp.cleanup()

    def setUp(self):
        self.path = Path(self.temp.name)/self._testMethodName
        self.config.CHROMA_PERSIST_DIR = str(self.path)
        self.store = self.store_class()
        self.addCleanup(self.store.close)

    def add(self, did=1, public=True, defer=False):
        return self.store.add_documents(["石灰降低土壤酸度"], [{"document_id": did, "owner_id": 1,
            "visibility_scope": "public" if public else "private", "source": str(did)+".pdf"}], ids=[str(did)+":0"], update_bm25=not defer)

    def test_warm_restart_reads_no_corpus_pages(self):
        self.assertEqual(self.add(), 1)
        with patch.object(self.store_class, "_lexical_batches", side_effect=AssertionError("warm_start_full_scan")):
            restarted = self.store_class()
            self.addCleanup(restarted.close)
        self.assertTrue(restarted._bm25_search("石灰", 5, {"visibility_scope": "public"}))
        self.assertEqual(restarted._bm25[self.config.CHROMA_COLLECTION_NAME].index.metrics["tokenized_rows"], 0)

    def test_hybrid_uses_one_query_embedding_for_multiple_collections_and_traces_ranks(self):
        import framework.vector_store.chroma_store as module
        self.add()
        self.store.add_documents(["水稻产量"], [{"document_id": 2, "source": "2.pdf", "visibility_scope": "public"}],
                                 ids=["2:0"], category="second_test")
        with patch.object(self.config, "HYBRID_SEARCH_ENABLED", True), patch.object(module.embedding_service, "embed_query", return_value=[1.0, 1.0]) as embed:
            result = self.store.hybrid_search("石灰", 2, {"visibility_scope": "public"})
        self.assertEqual(embed.call_count, 1)
        self.assertEqual(result["retrieval"]["mode"], "hybrid")
        self.assertIn("vector", result["results"][0]["retrieval_ranks"])
        self.assertGreater(result["results"][0]["rrf_score"], 0)

    def test_empty_embedding_preserves_lexical_results_but_reports_degraded(self):
        import framework.vector_store.chroma_store as module
        self.add()
        with patch.object(self.config, "HYBRID_SEARCH_ENABLED", True), patch.object(module.embedding_service, "embed_query", return_value=[]):
            result = self.store.hybrid_search("石灰", 2, {"visibility_scope": "public"})
        self.assertTrue(result["results"])
        self.assertEqual(result["retrieval"]["mode"], "degraded")
        self.assertEqual(result["retrieval"]["vector"]["state"], "failed")

    def test_domain_expansion_uses_original_vector_and_bounded_lexical_slots(self):
        import framework.vector_store.chroma_store as module
        self.store.add_documents(["Biochar increased organic carbon", "Biochar organic carbon private"],
            [{"document_id": 1, "content_sha256": "v1", "chunk_index": 0, "visibility_scope": "public"},
             {"document_id": 2, "content_sha256": "v2", "chunk_index": 0, "visibility_scope": "private"}],
            ids=["1:0", "2:0"])
        with patch.object(self.config, "HYBRID_SEARCH_ENABLED", True), patch.object(
                module.embedding_service, "embed_query", return_value=[1.0, 1.0]) as embed:
            result = self.store.hybrid_search("生物炭有机碳", 4, {"visibility_scope": "public"}, domain_expansion=True)
        embed.assert_called_once_with("生物炭有机碳")
        self.assertEqual({i["metadata"]["document_id"] for i in result["results"]}, {1})
        self.assertIn("lexical", result["results"][0]["retrieval_ranks"])
        expansion = result["retrieval"]["lexical"]["expansion"]
        self.assertEqual(expansion["original_limit"]+expansion["expanded_limit"], 4)
        self.assertTrue(expansion["query_vector_unchanged"])

    def test_expansion_failure_is_partial_and_preserves_original_leg(self):
        self.add()
        original = self.store._bm25_search
        def fail_expansion(*args, **kwargs):
            if kwargs.get("concept_groups"):
                kwargs["diagnostics"]["failures"] += 1
                return []
            return original(*args, **kwargs)
        with patch.object(self.config, "HYBRID_SEARCH_ENABLED", True), patch.object(
                self.store, "_bm25_search", side_effect=fail_expansion):
            result = self.store.hybrid_search("石灰", 4, {"visibility_scope": "public"}, domain_expansion=True)
        self.assertTrue(result["results"])
        self.assertEqual(result["retrieval"]["mode"], "degraded")
        self.assertEqual(result["retrieval"]["lexical"]["state"], "partial")

    def test_rrf_keeps_same_named_documents_and_versions_separate(self):
        one = {"content": "same", "metadata": {"source": "same.pdf", "document_id": 1, "content_sha256": "a", "chunk_index": 0}}
        two = {"content": "same", "metadata": {"source": "same.pdf", "document_id": 2, "content_sha256": "a", "chunk_index": 0}}
        newer = {"content": "same", "metadata": {"source": "same.pdf", "document_id": 1, "content_sha256": "b", "chunk_index": 0}}
        self.assertEqual(len(self.store._rrf_fuse([one, two, one], [newer, one])), 3)

    def test_deferred_update_is_recovered_by_new_instance(self):
        self.assertEqual(self.add(defer=True), 1)
        self.assertFalse(self.store._bm25_search("石灰", 5, None))
        restarted = self.store_class()
        self.addCleanup(restarted.close)
        self.assertEqual(restarted._bm25_search("石灰", 5, None)[0]["metadata"]["document_id"], 1)
        self.assertEqual(restarted._bm25[self.config.CHROMA_COLLECTION_NAME].index.health()["pending_operations"], 0)

    def test_metadata_update_retokenizes_zero_rows(self):
        self.add()
        index = self.store._bm25[self.config.CHROMA_COLLECTION_NAME].index
        before = index.metrics["tokenized_rows"]
        self.assertEqual(self.store.update_document_metadata(1, {"visibility_scope": "private"}), 1)
        self.assertEqual(index.metrics["tokenized_rows"], before)
        self.assertEqual(self.store._bm25_search("石灰", 5, {"visibility_scope": "public"}), [])

    def test_failed_derivative_update_retains_repair_and_vector_source(self):
        with patch.object(self.store_class, "_sync_lexical_pending", side_effect=RuntimeError("disk_error")):
            self.assertEqual(self.add(), 1)
        self.assertEqual(self.store.get_collection_stats()["count"], 1)
        self.assertEqual(self.store._bm25[self.config.CHROMA_COLLECTION_NAME].index.health()["pending_operations"], 1)
        self.store.rebuild_bm25_indexes()
        self.assertTrue(self.store._bm25_search("石灰", 5, None))

    def test_direct_outside_permission_change_is_revalidated(self):
        self.add()
        self.store._get_collection().update(ids=["1:0"], metadatas=[{"document_id": 1, "owner_id": 1, "visibility_scope": "private", "source": "1.pdf"}])
        self.assertEqual(self.store._bm25_search("石灰", 5, {"visibility_scope": "public"}), [])
        self.assertEqual(self.store._bm25[self.config.CHROMA_COLLECTION_NAME].index.health()["pending_operations"], 1)
        self.store.rebuild_bm25_indexes()
        self.assertTrue(self.store._bm25_search("石灰", 5, {"visibility_scope": "private"}))

    def test_incomplete_authoritative_page_cannot_clear_pending_repair(self):
        self.add(defer=True)
        collection = self.store._get_collection()
        with patch.object(type(collection), "get", return_value={"ids": ["1:0"], "documents": [], "metadatas": [{}]}):
            with self.assertRaisesRegex(ValueError, "alignment"):
                self.store._sync_lexical_pending(self.config.CHROMA_COLLECTION_NAME, collection)
        self.assertEqual(self.store._bm25[self.config.CHROMA_COLLECTION_NAME].index.health()["pending_operations"], 1)

    def test_delete_and_duplicate_ids_preserve_counts(self):
        self.assertEqual(self.add(), 1)
        self.assertEqual(self.add(), 0)
        self.assertEqual(self.add(did=2), 1)
        self.assertEqual(self.store.delete_by_document_id(1, owner_id=99), 0)
        self.assertEqual(self.store.delete_by_document_id(1, owner_id=1), 1)
        self.assertEqual(self.store.get_collection_stats()["count"], 1)
        self.assertEqual(self.store._bm25[self.config.CHROMA_COLLECTION_NAME].index.health()["rows"], 1)

    def test_candidate_reads_are_bounded(self):
        self.add(); collection = self.store._get_collection()
        original = collection.get
        sizes = []
        def bounded(*args, **kwargs):
            self.assertIn("ids", kwargs)
            sizes.append(len(kwargs["ids"]))
            return original(*args, **kwargs)
        with patch.object(collection, "get", side_effect=bounded):
            self.assertTrue(self.store._bm25_search("石灰", 5, None))
        self.assertEqual(sizes, [1])


if __name__ == "__main__":
    unittest.main()
