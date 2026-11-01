from framework.knowledge_graph.gold_evaluation import prediction_rows, entity_scores, source_locator_score
from framework.knowledge_graph.candidate_pipeline import CanonicalEntityCatalog
from scripts.evaluate_kg_extraction_backend import evaluate_rows


def gold_row():
    return dict(relation=dict(type="addresses", source=dict(type="measure",name="施用石灰"),
        target=dict(type="obstacle",name="土壤酸化")), evidence=dict(document_id=1,page=2,chunk_index=None,quote_sha256="gold-span"))


def test_unknown_cost_is_not_reported_as_free():
    report=evaluate_rows([],[],backend_name="live",backend_version="1",elapsed_seconds=1,
        input_documents=1,cost_usd=None,cost_source="billing unavailable; tokens recorded",evaluation_mode="live_backend_predictions")
    assert report["cost"]["usd"] is None
    assert report["cost"]["status"] == "unavailable"


def test_standalone_entities_are_scored_even_without_predicted_relations():
    score=entity_scores([gold_row()],[dict(type="measure",name="施用石灰")])
    assert score["predicted"] == 1
    assert score["true_positive"] == 1
    assert score["recall"] == 0.5


def test_locator_supplement_does_not_replace_strict_quote_metric():
    gold=gold_row()
    predicted=dict(relation=gold["relation"],evidence=dict(document_id=1,page=2,chunk_index=9,quote_sha256="whole-chunk"))
    assert source_locator_score([gold],[predicted])["recall"] == 1
    strict=evaluate_rows([gold],[predicted],backend_name="live",backend_version="1",elapsed_seconds=1,
        input_documents=1,cost_usd=None,cost_source="unavailable",evaluation_mode="live_backend_predictions")
    assert strict["metrics"]["evidence_location"]["recall"] == 0


def test_alias_canonicalization_is_postprocessing_and_keeps_raw_result():
    result=dict(entities=[dict(candidate_id="e",entity_type="indicator",mention="有机质",canonical_id=None,
        canonical_name=None,confidence=0)],relations=[])
    catalog=CanonicalEntityCatalog.from_mapping(dict(entities=[dict(id="indicator:om",type="indicator",
        name="土壤有机质",aliases=["有机质"])],relations=[]))
    rows, entities=prediction_rows(result,catalog)
    assert rows == []
    assert entities[0]["name"] == "土壤有机质"
    assert result["entities"][0]["mention"] == "有机质"


def test_source_audit_only_accepts_literal_or_whitespace_equivalence():
    from scripts.audit_kg_gold_sources import locate_quote
    found=locate_quote("前言：土壤\n 有机质含量。", "土壤有机质含量")
    assert found["kind"] == "whitespace_only_equivalent"
    assert found["quote"] == "土壤\n 有机质含量"
    assert locate_quote("土壤 pH=5.0", "土壤pH=50") is None


def test_retry_policy_never_cherry_picks_semantic_failures():
    from framework.knowledge_graph.gold_evaluation import retry_transient_record
    original=dict(state="failed",code="extraction_backend_failed",usage=dict(total_tokens=0))
    assert retry_transient_record(original,True)
    assert not retry_transient_record(original,False)
    assert not retry_transient_record({**original,"prior_attempt":dict(code="extraction_backend_failed")},True)
    assert not retry_transient_record({**original,"usage":dict(total_tokens=100)},True)
    assert not retry_transient_record({**original,"code":"missing_relation_endpoint"},True)
