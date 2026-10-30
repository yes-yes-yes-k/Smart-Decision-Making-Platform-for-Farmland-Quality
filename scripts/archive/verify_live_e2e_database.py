"""Verify live E2E conversations and provenance directly in PostgreSQL."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RAW_PATH = ROOT / "docs" / "generated" / "live-chat-e2e-raw.json"
OUTPUT_PATH = ROOT / "docs" / "generated" / "live-chat-e2e-db-verification.json"
REQUIRED_PROVENANCE_COLUMNS = {
    "user_id", "conversation_id", "parcel_id", "analysis_object_type",
    "analysis_object_id", "area_code", "context_version",
    "analysis_context_snapshot", "model_version", "data_as_of", "data_version",
}
FAKE_PARCEL_IDS = ("P-VERIFY-001", "P-VERIFY-002", "P-VERIFY-003")


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def rows_as_dict(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


def main() -> int:
    env_path = find_dotenv(usecwd=True)
    if env_path:
        load_dotenv(env_path)
    from framework.config import Config

    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    conversation_ids = raw["conversation_ids"]
    final_exchange = next(
        item for item in raw["exchanges"]
        if item["label"] == "综合诊断：用户确认发布最终报告"
    )
    final_data = final_exchange["response"]["json"]["data"]
    trace_id = final_data["trace_id"]
    comprehensive_id = int(conversation_ids["comprehensive"])
    all_ids = [int(value) for value in conversation_ids.values()]

    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    with engine.connect() as connection:
        columns = {
            column["name"]
            for column in inspect(connection).get_columns("model_execution_log")
        }
        conversations = rows_as_dict(connection.execute(text("""
            SELECT id, title, user_id, analysis_object, context_version
            FROM kb_conversation
            WHERE id = ANY(:conversation_ids)
            ORDER BY id
        """), {"conversation_ids": all_ids}))
        message_counts = rows_as_dict(connection.execute(text("""
            SELECT conversation_id, COUNT(*) AS message_count,
                   ARRAY_AGG(role ORDER BY id) AS roles
            FROM kb_message
            WHERE conversation_id = ANY(:conversation_ids)
            GROUP BY conversation_id
            ORDER BY conversation_id
        """), {"conversation_ids": all_ids}))
        executions = rows_as_dict(connection.execute(text("""
            SELECT id, trace_id, agent_id, status, user_id, conversation_id,
                   parcel_id, analysis_object_type, analysis_object_id,
                   area_code, context_version, model_version, data_as_of,
                   data_version, simulated
            FROM model_execution_log
            WHERE trace_id = :trace_id AND conversation_id = :conversation_id
            ORDER BY id
        """), {
            "trace_id": trace_id,
            "conversation_id": comprehensive_id,
        }))
        fake_count = connection.execute(text("""
            SELECT COUNT(*)
            FROM parcel_info
            WHERE parcel_id = ANY(:parcel_ids)
        """), {"parcel_ids": list(FAKE_PARCEL_IDS)}).scalar_one()

    expected_counts = {
        int(conversation_ids["unselected"]): 2,
        int(conversation_ids["selected"]): 2,
        int(conversation_ids["scenario"]): 4,
        comprehensive_id: 4,
    }
    actual_counts = {
        int(item["conversation_id"]): int(item["message_count"])
        for item in message_counts
    }
    if len(conversations) != 4:
        raise AssertionError(f"expected 4 conversations, got {len(conversations)}")
    if actual_counts != expected_counts:
        raise AssertionError(f"message counts differ: {actual_counts}")
    missing_columns = sorted(REQUIRED_PROVENANCE_COLUMNS - columns)
    if missing_columns:
        raise AssertionError(f"missing provenance columns: {missing_columns}")
    if fake_count != 0:
        raise AssertionError(f"fake parcel rows remain: {fake_count}")
    executed_agents = {item["agent_id"] for item in executions}
    if executed_agents != {"model-1", "model-2", "model-3", "model-4", "model-5"}:
        raise AssertionError(f"unexpected executed agents: {sorted(executed_agents)}")
    if any(
        item["parcel_id"] != "4190"
        or item["analysis_object_id"] != "4190"
        or item["analysis_object_type"] != "parcel"
        or item["conversation_id"] != comprehensive_id
        for item in executions
    ):
        raise AssertionError("execution provenance does not match the selected parcel")

    record = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "database": {
            "dialect": engine.dialect.name,
            "credentials_included": False,
        },
        "conversation_ids": conversation_ids,
        "conversations": conversations,
        "message_counts": message_counts,
        "comprehensive_trace_id": trace_id,
        "model_executions": executions,
        "provenance_columns": sorted(REQUIRED_PROVENANCE_COLUMNS),
        "fake_parcel_ids_checked": list(FAKE_PARCEL_IDS),
        "fake_parcel_row_count": int(fake_count),
        "checks": {
            "all_conversations_persisted": True,
            "complete_message_histories_persisted": True,
            "five_professional_executions_share_trace": True,
            "execution_logs_match_selected_parcel": True,
            "provenance_columns_present": True,
            "fake_parcels_absent": True,
        },
    }
    OUTPUT_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    print(json.dumps({
        "status":"ok",
        "output":str(OUTPUT_PATH),
        "trace_id":trace_id,
        "agents":sorted(executed_agents),
        "fake_parcel_row_count":int(fake_count),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
