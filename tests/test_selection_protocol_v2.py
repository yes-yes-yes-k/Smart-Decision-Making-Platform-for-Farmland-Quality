"""R2.3 selection protocol: position first, then relation, exact matching only."""
import unittest

from framework.knowledge_graph.selection_protocol_v2 import (
    SelectionError, adjudicate_resolution, compile_selection, occurrences, resolve_enumeration,
    resolve_quote)

SHA = "a" * 64
CONTENT = "生物炭提高土壤有机碳。施石灰降低稻米镉。生物炭提高土壤有机碳。"


def packet(content=CONTENT, chunks=None, document_id=449):
    return {"document_id": document_id, "document_sha256": SHA,
            "parse_version": SHA, "chunk_set_version": SHA,
            "chunks": chunks or [{"chunk_index": 3, "page": 2, "content": content}]}


def selection(quote, chunk_index=3, start=None, end=None):
    value = {"chunk_index": chunk_index, "quote": quote}
    if start is not None:
        value.update(start=start, end=end)
    return value


def study(study_id="s1", kind="primary_experiment", context=None):
    return {"id": study_id, "kind": kind, "context": context or [selection("生物炭", start=0, end=3)],
            "attribution": None}


def entity(entity_id, entity_type, quote, start=None, end=None, study_id="s1"):
    mention = selection(quote, start=start, end=end)
    return {"id": entity_id, "study_id": study_id, "entity_type": entity_type, "mention": mention}


def relation(relation_id="r1", source="e_measure", target="e_indicator", result=None,
             direction="increase", study_id="s1"):
    first = CONTENT.index("生物炭提高土壤有机碳")
    value = {"id": relation_id, "study_id": study_id, "relation_type": "reports_effect",
             "source_id": source, "target_id": target,
             "result": result or selection("生物炭提高土壤有机碳", start=first, end=first + 10),
             "direction": direction,
             "qualifiers": {name: None for name in
                            ("soil_type", "conditions", "dose", "duration", "effect_size",
                             "unit", "negation", "uncertainty", "comparator")}}
    return value


def enumeration():
    return {"studies": [study()], "entities": [
        entity("e_measure", "measure", "生物炭", start=0, end=3),
        entity("e_indicator", "indicator", "土壤有机碳", start=5, end=10)]}


def decision(relations=None):
    return {"relations": relations or [relation()]}


class ExactMatchingTests(unittest.TestCase):
    def test_unique_quote_resolves_without_offsets(self):
        span = resolve_quote(packet(), chunk_index=3, quote="施石灰降低稻米镉",
                             kind="entity_mention")
        self.assertEqual((span["start"], span["end"]), (11, 19))
        self.assertEqual(CONTENT[span["start"]:span["end"]], span["quote"])

    def test_duplicate_quote_requires_explicit_position(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_quote(packet(), chunk_index=3, quote="生物炭提高土壤有机碳",
                          kind="entity_mention")
        self.assertEqual(caught.exception.code, "ambiguous_quote_requires_position")

    def test_duplicate_quote_with_offsets_selects_that_occurrence(self):
        second = CONTENT.rindex("生物炭提高土壤有机碳")
        span = resolve_quote(packet(), chunk_index=3, quote="生物炭提高土壤有机碳",
                             start=second, end=second + 10, kind="entity_mention")
        self.assertEqual(span["start"], second)

    def test_no_case_or_whitespace_normalization(self):
        text = "Long term biochar increased SOC."
        with self.assertRaises(SelectionError) as caught:
            resolve_quote(packet(text), chunk_index=3, quote="long term", kind="entity_mention")
        self.assertEqual(caught.exception.code, "quote_not_found")
        with self.assertRaises(SelectionError):
            resolve_quote(packet("在 红壤 上施用"), chunk_index=3, quote="在红壤上施用",
                          kind="entity_mention")

    def test_occurrences_are_exact_and_ordered(self):
        self.assertEqual(occurrences(CONTENT, "生物炭提高土壤有机碳"),
                         [(0, 10), (CONTENT.rindex("生物炭提高土壤有机碳"),
                                    CONTENT.rindex("生物炭提高土壤有机碳") + 10)])


class RejectionTests(unittest.TestCase):
    def test_unknown_chunk_is_rejected(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_quote(packet(), chunk_index=99, quote="生物炭", kind="entity_mention")
        self.assertEqual(caught.exception.code, "unknown_source_chunk")

    def test_out_of_bounds_and_mismatched_offsets_are_rejected(self):
        for start, end, code in ((0, 999, "invalid_offsets"), (5, 3, "invalid_offsets"),
                                 (0, 2, "span_quote_mismatch")):
            with self.assertRaises(SelectionError) as caught:
                resolve_quote(packet(), chunk_index=3, quote="生物炭", start=start, end=end,
                              kind="entity_mention")
            self.assertEqual(caught.exception.code, code)

    def test_relation_evidence_always_needs_explicit_position(self):
        with self.assertRaises(SelectionError) as caught:
            resolve_quote(packet(), chunk_index=3, quote="施石灰降低稻米镉",
                          kind="relation_result")
        self.assertEqual(caught.exception.code, "ambiguous_quote_requires_position")

    def test_duplicate_entity_mention_is_rejected(self):
        payload = {"studies": [study()], "entities": [
            entity("e1", "measure", "生物炭", start=0, end=3),
            entity("e2", "measure", "生物炭", start=0, end=3)]}
        with self.assertRaises(SelectionError) as caught:
            resolve_enumeration(packet(), payload)
        self.assertEqual(caught.exception.code, "duplicate_entity_mention")


class RelationOrderTests(unittest.TestCase):
    def test_unknown_endpoint_is_rejected(self):
        resolved, ledger = resolve_enumeration(packet(), enumeration())
        unknown = relation(source="e_missing")
        from framework.knowledge_graph.selection_protocol_v2 import resolve_decision
        with self.assertRaises(SelectionError) as caught:
            resolve_decision(packet(), {"relations": [unknown]}, ledger)
        self.assertEqual(caught.exception.code, "unknown_relation_endpoint")

    def test_cross_study_relation_is_rejected(self):
        payload = enumeration()
        payload["studies"].append(study("s2", context=[selection("施石灰")]))
        payload["entities"].append(entity("e_other", "indicator", "稻米镉", start=16, end=19,
                                          study_id="s2"))
        _, ledger = resolve_enumeration(packet(), payload)
        cross = relation(target="e_other")
        from framework.knowledge_graph.selection_protocol_v2 import resolve_decision
        with self.assertRaises(SelectionError) as caught:
            resolve_decision(packet(), {"relations": [cross]}, ledger)
        self.assertEqual(caught.exception.code, "cross_study_relation_forbidden")

    def test_adjudication_reports_pending_and_rejected_items(self):
        payload = enumeration()
        relations = [relation("r1"), relation("r2", direction="uncertain"),
                     relation("r3", target="e_missing")]
        report = adjudicate_resolution(packet(), payload, {"relations": relations})
        self.assertEqual(report["status"], "partially_rejected")
        self.assertEqual(len(report["accepted"]), 1)
        self.assertEqual(len(report["pending"]), 1)
        self.assertEqual(report["rejected"][0]["code"], "unknown_relation_endpoint")


class ContractIntegrationTests(unittest.TestCase):
    def provenance(self):
        return {"origin": "unit-test", "configuration_sha256": SHA}

    def test_resolved_bundle_passes_v2_contract(self):
        result = compile_selection(packet(), enumeration(), decision(), provenance=self.provenance())
        self.assertEqual(result["rule_validation"], "passed")
        self.assertEqual(result["review_status"], "pending")
        self.assertEqual(result["published_claims_added"], 0)
        self.assertEqual(result["semantic_support"], "unreviewed")
        self.assertEqual(len(result["entities"]), 2)
        self.assertEqual(len(result["relations"]), 1)
        self.assertEqual(result["relations"][0]["result"]["start"], 0)

    def test_ambiguous_entity_blocks_relation_stage(self):
        payload = {"studies": [study()], "entities": [
            entity("e_measure", "measure", "生物炭提高土壤有机碳"),
            entity("e_indicator", "indicator", "土壤有机碳", start=5, end=10)]}
        with self.assertRaises(SelectionError) as caught:
            compile_selection(packet(), payload, decision(), provenance=self.provenance())
        self.assertEqual(caught.exception.code, "ambiguous_quote_requires_position")

    def test_incomplete_version_binding_is_rejected_by_contract(self):
        bad = packet()
        bad["document_sha256"] = "not-a-hash"
        with self.assertRaises(ValueError) as caught:
            compile_selection(bad, enumeration(), decision(), provenance=self.provenance())
        self.assertEqual(str(caught.exception), "complete_version_binding_required")


if __name__ == "__main__":
    unittest.main()


class QuoteOnlyTests(unittest.TestCase):
    def payloads(self):
        enumeration_payload = {"studies": [study(context=[{"chunk_index": 3, "quote": "施石灰"}])],
                               "entities": [
                                   {"id": "e_measure", "study_id": "s1", "entity_type": "measure",
                                    "mention": {"chunk_index": 3, "quote": "施石灰"}},
                                   {"id": "e_indicator", "study_id": "s1", "entity_type": "indicator",
                                    "mention": {"chunk_index": 3, "quote": "稻米镉"}}]}
        relation_payload = relation(result={"chunk_index": 3, "quote": "施石灰降低稻米镉"})
        return enumeration_payload, {"relations": [relation_payload]}

    def provenance(self):
        return {"origin": "unit-test", "configuration_sha256": SHA}

    def test_unique_quotes_are_resolved_without_offsets(self):
        from framework.knowledge_graph.selection_protocol_v2 import compile_selection_quote_only
        enumeration_payload, decision_payload = self.payloads()
        result = compile_selection_quote_only(packet(), enumeration_payload, decision_payload,
                                              provenance=self.provenance())
        self.assertEqual(result["rule_validation"], "passed")
        self.assertEqual(result["relations"][0]["result"]["start"], 11)
        self.assertEqual(result["entities"][1]["mention"]["start"], 16)

    def test_duplicate_quote_is_rejected(self):
        from framework.knowledge_graph.selection_protocol_v2 import compile_selection_quote_only
        enumeration_payload, decision_payload = self.payloads()
        enumeration_payload["entities"][1]["mention"]["quote"] = "生物炭提高土壤有机碳"
        with self.assertRaises(SelectionError) as caught:
            compile_selection_quote_only(packet(), enumeration_payload, decision_payload,
                                         provenance=self.provenance())
        self.assertEqual(caught.exception.code, "ambiguous_quote_requires_position")

    def test_missing_quote_is_rejected(self):
        from framework.knowledge_graph.selection_protocol_v2 import compile_selection_quote_only
        enumeration_payload, decision_payload = self.payloads()
        enumeration_payload["entities"][0]["mention"]["quote"] = "不存在的短语"
        with self.assertRaises(SelectionError) as caught:
            compile_selection_quote_only(packet(), enumeration_payload, decision_payload,
                                         provenance=self.provenance())
        self.assertEqual(caught.exception.code, "quote_not_found")


class PartialCompileTests(unittest.TestCase):
    def payloads(self):
        enumeration_payload = {"studies": [study(context=[{"chunk_index": 3, "quote": "施石灰"}])],
                               "entities": [
                                   {"id": "e_ok", "study_id": "s1", "entity_type": "measure",
                                    "mention": {"chunk_index": 3, "quote": "施石灰"}},
                                   {"id": "e_bad", "study_id": "s1", "entity_type": "indicator",
                                    "mention": {"chunk_index": 3, "quote": "不存在的短语"}},
                                   {"id": "e_target", "study_id": "s1", "entity_type": "indicator",
                                    "mention": {"chunk_index": 3, "quote": "稻米镉"}}]}
        relations = [relation("r_ok", source="e_ok", target="e_target",
                              result={"chunk_index": 3, "quote": "施石灰降低稻米镉"}),
                     relation("r_bad", source="e_bad", target="e_target",
                              result={"chunk_index": 3, "quote": "施石灰降低稻米镉"})]
        return enumeration_payload, {"relations": relations}

    def test_unverifiable_items_are_rejected_individually(self):
        from framework.knowledge_graph.selection_protocol_v2 import compile_partial_quote_only
        enumeration_payload, decision_payload = self.payloads()
        result = compile_partial_quote_only(packet(), enumeration_payload, decision_payload,
                                            provenance={"origin": "unit-test", "configuration_sha256": SHA})
        self.assertEqual(result["accepted_counts"], {"studies": 1, "entities": 2, "relations": 1})
        self.assertEqual(result["reason_counts"]["quote_not_found"], 1)
        self.assertEqual(result["reason_counts"]["unknown_relation_endpoint"], 1)
        self.assertEqual(result["candidates"]["relations"][0]["local_id"], "r_ok")

    def test_unresolvable_study_context_drops_the_study(self):
        from framework.knowledge_graph.selection_protocol_v2 import compile_partial_quote_only
        enumeration_payload, decision_payload = self.payloads()
        enumeration_payload["studies"][0]["context"] = [{"chunk_index": 3, "quote": "不存在的短语"}]
        result = compile_partial_quote_only(packet(), enumeration_payload, decision_payload,
                                            provenance={"origin": "unit-test", "configuration_sha256": SHA})
        self.assertEqual(result["accepted_counts"]["studies"], 0)
        self.assertIn("study_context_unresolved", result["reason_counts"])
        self.assertEqual(result["accepted_counts"]["relations"], 0)
