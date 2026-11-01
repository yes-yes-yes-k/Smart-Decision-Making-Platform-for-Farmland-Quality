"""Queue limits and count conservation against the real isolated SQL store."""
from concurrent.futures import ThreadPoolExecutor
import unittest
from tests import test_research_evidence as fixtures
from framework.knowledge_graph.research_service import ResearchError


class AdmissionTests(unittest.TestCase):
    setUp = fixtures.ResearchEvidenceTests.setUp
    initialize = fixtures.ResearchEvidenceTests.initialize

    def test_owner_capacity_duplicate_reuse_and_cancellation_release(self):
        self.initialize()
        self.service.max_pending_per_owner = 2
        one, _ = self.service.submit(1, {"query": "石灰1"})
        self.service.submit(1, {"query": "石灰2"})
        reused, hit = self.service.submit(1, {"query": "石灰1"})
        self.assertTrue(hit)
        self.assertEqual(reused["id"], one["id"])
        with self.assertRaises(ResearchError) as error:
            self.service.submit(1, {"query": "石灰3"})
        self.assertEqual(error.exception.status, 429)
        self.service.cancel(1, one["id"])
        self.assertEqual(self.service.submit(1, {"query": "石灰3"})[0]["state"], "queued")

    def test_concurrent_global_admission_never_exceeds_cap(self):
        self.initialize()
        self.service.max_pending_total = 3
        def submit(index):
            try:
                return self.service.submit(index+1, {"query": "石灰"})[0]["state"]
            except ResearchError as exc:
                self.assertEqual(exc.status, 429)
                return "rejected_full"
        with ThreadPoolExecutor(max_workers=6) as pool:
            states = list(pool.map(submit, range(8)))
        self.assertEqual(states.count("queued"), 3)
        self.assertEqual(states.count("rejected_full"), 5)


if __name__ == "__main__":
    unittest.main()
