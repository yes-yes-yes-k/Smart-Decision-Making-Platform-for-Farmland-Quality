"""±N neighbour window: expand verified chunks without crossing versions."""
import unittest

from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch

SHA = "a" * 64


def chunk(document_id, index, text):
    return {"content": text, "retrieval_ranks": {"vector": index + 1},
            "metadata": {"document_id": document_id, "document_kind": "academic_paper",
                         "content_sha256": SHA, "chunk_index": index, "page": 1}}


class Store:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def hybrid_search(self, query, n_results=20, filters=None, **kwargs):
        return {"results": self.items[:n_results], "retrieval": {"mode": "hybrid"}}

    def get_by_references(self, references, *, filters=None, n_results=20):
        self.calls.append(list(references))
        wanted = {(ref["document_id"], ref["chunk_index"]) for ref in references}
        found = []
        for document_id, index in wanted:
            text = self.lookup.get((document_id, index))
            if text is not None:
                found.append({"content": text,
                              "metadata": {"document_id": document_id, "chunk_index": index,
                                           "content_sha256": SHA, "page": 1}})
        return found


class Sources:
    def lookup_many(self, ids, owner_id, require_academic=False):
        return {document_id: {"title": f"doc {document_id}", "document_kind": "academic_paper",
                              "content_sha256": SHA, "version": "v1", "visibility_scope": "public",
                              "review_status": "approved", "completed": True, "source_bytes_valid": True}
                for document_id in ids}


class WindowTests(unittest.TestCase):
    def build(self, window, lookup):
        store = Store([chunk(1, 5, "anchor text")])
        store.lookup = lookup
        return PublishedCorpusSearch(store, Sources(), window=window), store

    def test_window_off_keeps_original_list(self):
        search, store = self.build(0, {})
        response = search.search(1, {"query": "生物炭"})
        self.assertEqual(len(response["sources"]), 1)
        self.assertNotIn("window", response)
        self.assertEqual(store.calls, [])

    def test_window_one_appends_neighbours_after_anchor(self):
        search, store = self.build(1, {(1, 4): "before", (1, 6): "after"})
        response = search.search(1, {"query": "生物炭"})
        self.assertEqual([item["chunk_index"] for item in response["sources"]], [5, 6, 4])
        self.assertEqual(response["window"]["neighbours"], 2)
        self.assertEqual(response["sources"][1]["retrieval"]["window_delta"], 1)
        self.assertEqual(response["sources"][2]["retrieval"]["window_delta"], -1)

    def test_window_two_fetches_four_offsets(self):
        lookup = {(1, 3): "a", (1, 4): "b", (1, 6): "c", (1, 7): "d"}
        search, _ = self.build(2, lookup)
        response = search.search(1, {"query": "生物炭"})
        self.assertEqual([item["chunk_index"] for item in response["sources"]], [5, 6, 4, 7, 3])

    def test_negative_index_is_not_requested(self):
        search, store = self.build(1, {(1, 1): "before", (1, 3): "after"})
        store.items = [chunk(1, 2, "anchor")]
        response = search.search(1, {"query": "生物炭"})
        requested = {(ref["document_id"], ref["chunk_index"]) for call in store.calls for ref in call}
        self.assertIn((1, 1), requested)
        self.assertNotIn((1, -1), requested)
        self.assertEqual(len(response["sources"]), 3)

    def test_neighbour_from_other_document_is_dropped(self):
        search, store = self.build(1, {(1, 6): "after"})
        store.get_by_references = lambda refs, **kwargs: [
            {"content": "foreign", "metadata": {"document_id": 2, "chunk_index": 6,
                                                "content_sha256": SHA, "page": 1}}]
        response = search.search(1, {"query": "生物炭"})
        self.assertEqual([item["document_id"] for item in response["sources"]], [1])

    def test_invalid_window_is_rejected(self):
        for value in (-1, 3, "2"):
            with self.assertRaises(ValueError):
                PublishedCorpusSearch(Store([]), Sources(), window=value)


if __name__ == "__main__":
    unittest.main()
