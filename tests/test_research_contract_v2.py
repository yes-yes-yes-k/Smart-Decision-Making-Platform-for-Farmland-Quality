import copy
import unittest

from framework.knowledge_graph.research_contract_v2 import QUALIFIERS, compile_bundle, schemas


class ContractV2Tests(unittest.TestCase):
    def setUp(self):
        self.text = "Trial A: lime did not significantly change rice yield. Trial B: manure increased SOC. lime lime"
        self.source = {"document_id": 1, "document_sha256": "a"*64, "parse_version": "b"*64,
                       "chunk_set_version": "c"*64, "chunks": [{"chunk_index": 0, "page": 1, "content": self.text}]}
        self.provenance = {"origin": "offline_fixture", "configuration_sha256": "d"*64}
        self.enumeration = {"studies": [{"id": "S1", "kind": "primary_experiment", "context": [self.select("Trial A")], "attribution": None}],
                            "entities": [{"id": "E1", "study_id": "S1", "entity_type": "measure", "mention": self.select("lime")},
                                         {"id": "E2", "study_id": "S1", "entity_type": "indicator", "mention": self.select("rice yield")}]}
        self.decision = {"relations": [{"id": "R1", "study_id": "S1", "relation_type": "reports_effect", "source_id": "E1", "target_id": "E2",
                                       "result": self.select("did not significantly change rice yield"), "direction": "no_significant_change",
                                       "qualifiers": {k: None for k in QUALIFIERS}}]}
        self.decision["relations"][0]["qualifiers"]["negation"] = self.select("not significantly")

    def select(self, quote, start=None):
        start = self.text.index(quote) if start is None else start
        return {"chunk_index": 0, "start": start, "end": start+len(quote), "quote": quote}

    def compile(self):
        return compile_bundle(self.source, self.enumeration, self.decision, provenance=self.provenance)

    def test_unknown_negation_pending_and_separate_normalization(self):
        result = self.compile()
        relation = result["relations"][0]
        self.assertEqual(relation["direction"], "no_significant_change")
        self.assertEqual(relation["qualifiers"]["soil_type"], {"status": "unknown", "evidence": None})
        self.assertEqual(relation["qualifiers"]["negation"]["evidence"]["quote"], "not significantly")
        self.assertEqual(result["entities"][0]["normalization"]["status"], "unresolved")
        self.assertEqual(result["semantic_support"], "unreviewed")
        self.assertEqual(result["published_claims_added"], 0)

    def test_explicit_offsets_disambiguate_repeated_mention(self):
        self.enumeration["entities"][0]["mention"] = self.select("lime", len(self.text)-4)
        result = self.compile()
        self.assertEqual(result["entities"][0]["mention"]["start"], len(self.text)-4)

    def test_source_version_changes_span_and_bundle_identity(self):
        original = self.compile()
        self.source["parse_version"] = "e"*64
        changed = self.compile()
        self.assertNotEqual(original["identity"], changed["identity"])
        self.assertNotEqual(original["entities"][0]["mention"]["id"], changed["entities"][0]["mention"]["id"])

    def test_wrong_span_chunk_bool_and_generated_name_rejected(self):
        original = copy.deepcopy(self.enumeration)
        for patch in ({"start": 0}, {"chunk_index": 9}, {"start": True}, {"quote": "liming"}):
            with self.subTest(patch=patch):
                self.enumeration = copy.deepcopy(original)
                self.enumeration["entities"][0]["mention"].update(patch)
                with self.assertRaises(ValueError):
                    self.compile()
        self.enumeration = original
        self.enumeration["entities"][0]["canonical_name"] = "lime treatment"
        with self.assertRaisesRegex(ValueError, "field_set"):
            self.compile()

    def test_cross_study_or_reversed_endpoint_rejected(self):
        relation = self.decision["relations"][0]
        relation["source_id"], relation["target_id"] = "E2", "E1"
        with self.assertRaisesRegex(ValueError, "endpoint_type"):
            self.compile()
        relation["source_id"], relation["target_id"] = "E1", "E2"
        self.enumeration["studies"].append({"id": "S2", "kind": "primary_experiment", "context": [self.select("Trial B")], "attribution": None})
        self.enumeration["entities"][1]["study_id"] = "S2"
        with self.assertRaisesRegex(ValueError, "cross_study"):
            self.compile()

    def test_cited_study_requires_attribution_and_duplicates_cannot_inflate(self):
        self.enumeration["studies"][0]["kind"] = "review_cited_study"
        with self.assertRaisesRegex(ValueError, "attribution_required"):
            self.compile()
        self.enumeration["studies"][0]["attribution"] = self.select("Trial A")
        duplicate = dict(self.enumeration["entities"][0], id="E3")
        self.enumeration["entities"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate_entity_mention"):
            self.compile()

    def test_schema_is_closed_and_legacy_model_not_modified(self):
        import jsonschema
        contract = schemas()
        jsonschema.validate(self.enumeration, contract["enumeration"])
        jsonschema.validate(self.decision, contract["decision"])
        invalid = copy.deepcopy(self.decision)
        invalid["relations"][0]["review_status"] = "approved"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, contract["decision"])


if __name__ == "__main__":
    unittest.main()
