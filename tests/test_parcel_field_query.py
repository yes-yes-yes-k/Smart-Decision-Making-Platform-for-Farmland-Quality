from framework.agents.parcel_field_query import (
    prepend_field_answer,
    query_requested_parcel_fields,
    requested_parcel_fields,
)
from framework.domain.data.parcel_data_accessor import ParcelDataSnapshot
from framework.domain.data.parcel_management_fields import (
    canonicalize_parcel_management_fields,
)
from types import SimpleNamespace


class _Accessor:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get_parcel_snapshot(self, parcel_id):
        assert parcel_id == "373"
        return self.snapshot


def _snapshot(
    indicators,
    *,
    land_type="upland",
    fertilizer_type="urea",
    target_ph=6.5,
):
    return ParcelDataSnapshot(
        parcel_id="373",
        area_code="440281",
        parcel_code="legacy-373",
        land_type=land_type,
        fertilizer_type=fertilizer_type,
        target_ph=target_ph,
        indicators=indicators,
        source_version="parcel:2026-10-24T00:00:00",
    )


def test_ph_query_reads_authoritative_value_and_classification():
    result = query_requested_parcel_fields(
        "这块地的pH值是多少，怎么治理",
        "373",
        accessor=_Accessor(_snapshot({"soil_ph": 4.31})),
    )

    assert result["status"] == "ok"
    field = result["fields"][0]
    assert field["key"] == "soil_ph"
    assert field["source_field"] == "soil_ph"
    assert field["label"] == "土壤酸碱度（pH）"
    assert field["value"] == 4.31
    assert field["classification"] == "极强酸性"
    assert field["classification_range"] == "<4.5"
    assert field["category"] == "measured_indicator"
    assert field["preconditions_met"] is True
    assert result["answer"] == "地块 373：土壤酸碱度（pH）为 4.31。"


def test_soil_depth_and_plow_depth_are_not_confused():
    snapshot = _snapshot({
        "effective_soil_depth": 82.5,
        "plow_layer_thickness": 16.0,
    })

    soil = query_requested_parcel_fields(
        "该地块的土层厚度多少？", "373", accessor=_Accessor(snapshot),
    )
    plow = query_requested_parcel_fields(
        "该地块的耕层厚度多少？", "373", accessor=_Accessor(snapshot),
    )

    assert soil["fields"][0]["source_field"] == "effective_soil_depth"
    assert soil["answer"] == "地块 373：有效土层厚度为 82.50cm。"
    assert plow["fields"][0]["source_field"] == "plow_layer_thickness"
    assert plow["answer"] == "地块 373：耕层厚度为 16.00cm。"


def test_supported_field_without_value_is_reported_as_missing():
    result = query_requested_parcel_fields(
        "这块地的有机质含量是多少？",
        "373",
        accessor=_Accessor(_snapshot({"organic_matter": None})),
    )

    assert result["status"] == "missing"
    assert result["answer"] == "地块 373：有机质含量暂无记录。"


def test_unrelated_question_does_not_trigger_field_lookup():
    assert requested_parcel_fields("这块地有什么主要障碍？") == ()
    assert query_requested_parcel_fields(
        "这块地有什么主要障碍？", "373", accessor=_Accessor(_snapshot({})),
    ) is None


def test_management_context_uses_only_canonical_columns_even_when_json_conflicts():
    snapshot = _snapshot(
        {
            "land_type": "paddy",
            "fertilizer_type": "compound",
            "target_ph": 6.5,
        },
        land_type="upland",
        fertilizer_type="urea",
        target_ph=6.8,
    )

    result = query_requested_parcel_fields(
        "这块地的土地利用类型、肥料类型和目标pH分别是什么？",
        "373",
        accessor=_Accessor(snapshot),
    )

    fields = {item["key"]: item for item in result["fields"]}
    assert fields["land_type"]["value"] == "upland"
    assert fields["land_type"]["value_source"] == "parcel_info.land_type"
    assert fields["fertilizer_type"]["value"] == "urea"
    assert fields["fertilizer_type"]["value_source"] == "parcel_info.fertilizer_type"
    assert fields["target_ph"]["value"] == 6.8
    assert fields["target_ph"]["value_source"] == "parcel_info.target_ph"
    assert result["answer"] == (
        "地块 373：土地利用类型为 旱地；肥料类型为 尿素；目标 pH为 6.80。"
    )


def test_management_context_does_not_fall_back_to_legacy_json_duplicate():
    result = query_requested_parcel_fields(
        "这块地的目标pH是多少？",
        "373",
        accessor=_Accessor(_snapshot({"target_ph": 6.5}, target_ph=None)),
    )

    assert result["status"] == "missing"
    assert result["fields"][0]["value"] is None
    assert result["answer"] == "地块 373：目标 pH暂无记录。"


def test_write_canonicalization_promotes_legacy_values_and_removes_duplicates():
    parcel = SimpleNamespace(
        land_type="upland",
        fertilizer_type=None,
        target_ph=None,
        soil_indicators={
            "soil_ph": 5.2,
            "fertilizer_type": "compound",
            "target_ph": "6.5",
        },
    )

    canonicalize_parcel_management_fields(parcel)

    assert parcel.fertilizer_type == "compound"
    assert parcel.target_ph == 6.5
    assert parcel.soil_indicators == {"soil_ph": 5.2}


def test_write_canonicalization_rejects_nonempty_conflicts():
    parcel = SimpleNamespace(
        land_type="upland",
        fertilizer_type="urea",
        target_ph=6.8,
        soil_indicators={"fertilizer_type": "compound", "target_ph": 6.5},
    )

    try:
        canonicalize_parcel_management_fields(parcel)
    except ValueError as exc:
        assert "来源冲突" in str(exc)
    else:
        raise AssertionError("非空来源冲突必须被拒绝")


def test_acidification_input_fields_are_returned_from_snapshot():
    result = query_requested_parcel_fields(
        "该地块的CEC、交换性酸总量和水解性总酸度是多少？",
        "373",
        accessor=_Accessor(_snapshot({
            "cation_exchange_capacity": 11.1782,
            "exchangeable_acid_total": 4.2611,
            "hydrolytic_total_acidity": 8.4076,
        })),
    )

    assert {item["key"]: item["value"] for item in result["fields"]} == {
        "cation_exchange_capacity": 11.1782,
        "exchangeable_acid_total": 4.2611,
        "hydrolytic_total_acidity": 8.4076,
    }
    assert result["answer"] == (
        "地块 373：阳离子交换量为 11.18cmol/kg；"
        "交换性酸总量为 4.26cmol/kg；水解性总酸度为 8.41cmol/kg。"
    )


def _verified_model2_result(*, simulated=False, include_version=True):
    meta = {
        "data_source": "db",
        "simulated": simulated,
        "calculation_result_id": 91,
        "coefficient_version": "grade-coeff-2026",
        "input_hash": "sha256:abc",
        "calculated_at": "2026-10-24T08:00:00+00:00",
    }
    if include_version:
        meta["model_version"] = "quality-grade-2.1.0"
    return {
        "models": {
            "model-2": {
                "status": "ok",
                "subject": {"type": "parcel", "id": "373"},
                "result": {"quality_grade": "2", "composite_index": 0.87654},
                "meta": meta,
            },
        },
    }


def test_derived_quality_fields_require_and_publish_verified_current_result():
    result = query_requested_parcel_fields(
        "该地块的耕地质量等级和综合指数是多少，模型版本是什么？",
        "373",
        accessor=_Accessor(_snapshot({"quality_grade": "1", "composite_index": 0.99})),
        professional_results=_verified_model2_result(),
    )

    fields = {item["key"]: item for item in result["fields"]}
    assert fields["quality_grade"]["value"] == "2"
    assert fields["composite_index"]["value"] == 0.87654
    assert fields["quality_grade"]["value_source"] == "model-2.result.quality_grade"
    assert fields["quality_grade"]["provenance"]["calculation_result_id"] == 91
    assert result["preconditions"]["derived_model_result"]["met"] is True
    assert result["answer"] == (
        "地块 373：耕地质量等级为 2级，模型版本为quality-grade-2.1.0；"
        "耕地质量综合指数为 0.88，模型版本为quality-grade-2.1.0。"
    )


def test_derived_quality_fields_are_withheld_without_complete_provenance():
    result = query_requested_parcel_fields(
        "该地块的耕地质量等级和综合指数是多少？",
        "373",
        accessor=_Accessor(_snapshot({"quality_grade": "1", "composite_index": 0.99})),
        professional_results=_verified_model2_result(include_version=False),
    )

    assert result["status"] == "missing"
    assert all(item["value"] is None for item in result["fields"])
    assert all(
        item["unavailable_reason"] == "model_provenance_incomplete"
        for item in result["fields"]
    )
    assert result["preconditions"]["derived_model_result"]["met"] is False
    assert result["answer"] == ""
    assert "暂无可发布的已验证模型结果" not in result["answer"]


def test_indicator_provenance_metadata_is_scoped_to_named_indicator():
    result = query_requested_parcel_fields(
        "该地块的pH是哪一年测的，数据来源、是否插补和质量标记是什么？",
        "373",
        accessor=_Accessor(_snapshot({
            "soil_ph": 5.290293,
            "indicator_provenance": {
                "soil_ph": {
                    "measurement_year": 2024,
                    "data_source": "model1_shapefile",
                    "is_imputed": False,
                    "quality_flag": "source_unverified",
                },
            },
        })),
    )

    assert result["preconditions"]["indicator_provenance"]["met"] is True
    assert result["answer"] == (
        "地块 373：土壤酸碱度（pH）为 5.29，测量年份为2024年，"
        "数据来源为模型1地块数据，是否插补为否，质量标记为来源未核验。"
    )


def test_metadata_query_without_named_indicator_requests_scope():
    result = query_requested_parcel_fields(
        "该地块的数据来源是什么？",
        "373",
        accessor=_Accessor(_snapshot({})),
    )

    assert result["status"] == "needs_indicator_for_metadata"
    assert result["preconditions"]["indicator_provenance"]["met"] is False
    assert result["answer"].startswith("请明确需要查询哪个指标")


def test_selected_parcel_field_lookup_bypasses_generic_rag_route():
    from framework.agents.nodes import route_after_requirement

    state = {
        "question_type": 0,
        "routing_status": "normal",
        "request": {"question": "这块地的耕层厚度是多少？"},
        "analysis_context": {
            "mode": "spatial",
            "version": 1,
            "object": {"type": "parcel", "id": "373"},
        },
        "guard_decision": {"allowed": True},
    }

    assert route_after_requirement(state) == "execute_models"


def test_aggregate_keeps_field_lookup_when_classifier_returns_rag_type():
    from framework.agents.nodes import aggregate_results

    field_query = query_requested_parcel_fields(
        "这块地的耕层厚度是多少？",
        "373",
        accessor=_Accessor(_snapshot({"plow_layer_thickness": 20})),
    )
    state = {
        "request": {"question": "这块地的耕层厚度是多少？"},
        "question_type": 0,
        "relevance": 0.8,
        "routing_status": "normal",
        "analysis_context": {
            "mode": "spatial",
            "version": 1,
            "object": {"type": "parcel", "id": "373"},
        },
        "guard_decision": {"allowed": True, "interaction_state": "completed"},
        "model_results": {
            "models": {},
            "field_query": field_query,
            "answer": field_query["answer"],
        },
        "llm_response": {},
        "rag_response": {},
        "trace_id": "trace-field-only",
    }

    result = aggregate_results(state)["model_results"]

    assert result["field_query"] == field_query
    assert result["answer"] == "地块 373：耕层厚度为 20cm。"


def test_field_answer_is_prepended_once():
    field_query = {"answer": "地块 373：有效土层厚度为 82.5cm。"}
    body = "建议结合坡度采取客土和水土保持措施。"

    combined = prepend_field_answer(field_query, body)

    assert combined == field_query["answer"] + "\n\n" + body
    assert prepend_field_answer(field_query, combined) == combined


def test_execute_models_enriches_professional_result_with_raw_field(monkeypatch):
    from framework.agents import nodes
    from framework.agents.manager import agent_manager
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor,
        "get_parcel_snapshot",
        lambda self, parcel_id: _snapshot({"soil_ph": 4.31}),
    )
    monkeypatch.setattr(nodes, "_execute_via_function_calling", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        agent_manager,
        "process",
        lambda question, context: {
            "status": "ok",
            "question_type": 4,
            "models": {},
            "answer": "建议依据酸化改良模型结果治理。",
            "routing_method": "keyword_fallback",
        },
    )
    state = {
        "request": {"question": "这块地的pH值是多少，怎么治理"},
        "question_type": 4,
        "analysis_context": {
            "mode": "spatial",
            "version": 1,
            "object": {"type": "parcel", "id": "373"},
        },
        "validated_identifiers": {},
        "scenario_inputs": {},
        "trace_id": "trace-field-query",
        "user_id": 1,
        "conversation_id": 2,
    }

    result = nodes.execute_models(state)["model_results"]

    assert result["field_query"]["fields"][0]["value"] == 4.31
    assert result["answer"].startswith(
        "地块 373：土壤酸碱度（pH）为 4.31。\n\n"
    )
    assert result["answer"].endswith("建议依据酸化改良模型结果治理。")


def test_execute_models_refreshes_derived_fields_from_current_model2_result(monkeypatch):
    from framework.agents import nodes
    from framework.agents.manager import agent_manager
    from framework.domain.data.parcel_data_accessor import ParcelDataAccessor

    monkeypatch.setattr(
        ParcelDataAccessor,
        "get_parcel_snapshot",
        lambda self, parcel_id: _snapshot({
            "quality_grade": "1",
            "composite_index": 0.99,
        }),
    )
    monkeypatch.setattr(nodes, "_execute_via_function_calling", lambda *args, **kwargs: None)
    professional_result = {
        **_verified_model2_result(),
        "status": "ok",
        "question_type": 2,
        "answer": "本次质量评价已完成。",
        "routing_method": "keyword_fallback",
    }
    monkeypatch.setattr(
        agent_manager,
        "process",
        lambda question, context: professional_result,
    )
    state = {
        "request": {"question": "该地块的耕地质量等级和综合指数是多少？"},
        "question_type": 2,
        "analysis_context": {
            "mode": "spatial",
            "version": 1,
            "object": {"type": "parcel", "id": "373"},
        },
        "validated_identifiers": {},
        "scenario_inputs": {},
        "trace_id": "trace-derived-field-query",
        "user_id": 1,
        "conversation_id": 2,
    }

    result = nodes.execute_models(state)["model_results"]

    fields = {item["key"]: item for item in result["field_query"]["fields"]}
    assert fields["quality_grade"]["value"] == "2"
    assert fields["composite_index"]["value"] == 0.87654
    assert result["answer"].startswith(
        "地块 373：耕地质量等级为 2级；耕地质量综合指数为 0.88。\n\n"
    )
