from datetime import datetime, timezone

from framework.agents.capabilities import CAPABILITY_BY_AGENT_ID
from framework.analysis_context.contracts import AnalysisContext
from framework.analysis_context.provenance import ResultProvenanceBuilder
from framework.agents.nodes import aggregate_results
from framework.agents.manager import AgentManager


PARCEL_CONTEXT = AnalysisContext.from_dict({
    "mode": "spatial", "version": 3,
    "object": {
        "type": "parcel", "id": "P001", "display_name": "地块 P001",
        "area_code": "440281",
        "parent_path": [
            {"type": "province", "id": "44", "display_name": "广东省", "area_code": "44"},
            {"type": "city", "id": "4402", "display_name": "韶关市", "area_code": "4402"},
            {"type": "county", "id": "440281", "display_name": "乐昌市", "area_code": "440281"},
        ],
        "source": "parcel_info",
        "validated_at": "2026-08-31T00:00:00+00:00",
    },
})


def test_provenance_is_backend_owned_and_uses_actual_inputs():
    result = ResultProvenanceBuilder().build(
        trace_id="trace-1", analysis_context=PARCEL_CONTEXT,
        capability=CAPABILITY_BY_AGENT_ID["model-4"],
        agent_result={
            "model_version": "acid-v2", "data_as_of": "2024",
            "data_version": "soil-survey-3",
            "actual_inputs": {"SJD": 5.1, "JHX": 1.2, "JLA": 3.4, "db_path": "secret.db", "prompt": "hidden"},
        },
        calculated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert result["model_version"] == "acid-v2"
    assert result["key_inputs"] == {"SJD": 5.1, "JHX": 1.2, "JLA": 3.4}
    assert result["spatial_object"]["id"] == "P001"
    assert result["object_title"] == "分析对象：广东省韶关市乐昌市 地块 P001"
    assert "db_path" not in result["key_inputs"] and "prompt" not in result["key_inputs"]


def test_unknown_versions_and_scenario_title_are_deterministic():
    scenario = AnalysisContext.from_dict({"mode": "scenario", "version": None, "object": None})
    result = ResultProvenanceBuilder().build(
        trace_id="trace-2", analysis_context=scenario,
        capability=CAPABILITY_BY_AGENT_ID["model-4"], agent_result={},
        calculated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert result["model_version"] == "unknown"
    assert result["data_as_of"] is None and result["data_version"] is None
    assert result["scenario_result"] is True and result["spatial_object"] is None
    assert result["object_title"] == "情景试算，非具体空间对象结果"


def test_object_title_falls_back_without_administrative_parents():
    context = AnalysisContext.from_dict({
        "mode": "spatial", "version": 1,
        "object": {
            "type": "parcel", "id": "P001", "display_name": "地块 P001",
            "area_code": None, "parent_path": [], "source": "parcel_info",
            "validated_at": "2026-08-31T00:00:00+00:00",
        },
    })
    result = ResultProvenanceBuilder().build(
        trace_id="trace-3", analysis_context=context,
        capability=CAPABILITY_BY_AGENT_ID["model-4"], agent_result={},
        calculated_at=datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    assert result["object_title"] == "分析对象：地块 P001"


def test_aggregate_keeps_llm_limited_to_answer_body():
    state = {
        "request": {"question": "如何改良"}, "question_type": 4, "relevance": 0.9,
        "routing_status": "normal", "trace_id": "trace-1",
        "analysis_context": PARCEL_CONTEXT.to_dict(),
        "guard_decision": {"allowed": True, "interaction_state": "completed"},
        "model_results": {"status": "ok", "data": {
            "summary": "Agent 正文", "agents_invoked": ["model-4"],
            "details": {"model-4": {
                "model_version": "acid-v2", "data_as_of": "2024",
                "data_version": "soil-3", "actual_inputs": {"SJD": 5.1},
            }}, "recommendations": [],
        }},
        "llm_response": {
            "success": True,
            "content": "LLM 润色正文（即使声称对象是 P999，也只能作为正文）",
            "provenance": {"trace_id": "forged"},
            "analysis_context": {"object": {"id": "P999"}},
        },
        "rag_response": {}, "status": "model_completed", "error": None,
    }
    result = aggregate_results(state)["model_results"]
    assert result["answer"].startswith("分析对象：广东省韶关市乐昌市 地块 P001\n\nLLM 润色正文")
    assert result["provenance"]["trace_id"] == "trace-1"
    assert result["provenance"]["spatial_object"]["id"] == "P001"
    assert result["analysis_context"]["object"]["id"] == "P001"


def test_agent_manager_preserves_execution_context_without_reparsing():
    execution_context = {
        "trace_id": "trace-1", "analysis_context": PARCEL_CONTEXT.to_dict(),
        "user_id": 7, "conversation_id": 12,
    }
    payload = AgentManager._analysis_payload({
        "question_type": 4, "parcel_id": "P001", "execution_context": execution_context,
    })
    assert payload["execution_context"] is execution_context
