"""Analysis-context interaction counters and execution-log statistics."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from framework.models import ModelExecutionLog, db

from . import routing_log


EVENT_NEEDS_ANALYSIS_OBJECT = "analysis_context.needs_analysis_object"
EVENT_NEEDS_SCENARIO_INPUTS = "analysis_context.needs_scenario_inputs"
EVENT_ERROR_422 = "analysis_context.error.422"
EVENT_ERROR_409 = "analysis_context.error.409"
EVENT_ERROR_503 = "analysis_context.error.503"
EVENT_LEGACY_FIELD_USED = "analysis_context.legacy_field_used"

TRACKED_EVENTS = (
    EVENT_NEEDS_ANALYSIS_OBJECT,
    EVENT_NEEDS_SCENARIO_INPUTS,
    EVENT_ERROR_422,
    EVENT_ERROR_409,
    EVENT_ERROR_503,
    EVENT_LEGACY_FIELD_USED,
)


def record_analysis_context_event(event: str, **dimensions: Any) -> None:
    """Append a stable event to the existing daily JSONL observability stream."""
    if event not in TRACKED_EVENTS:
        raise ValueError(f"unknown analysis-context event: {event}")
    path = routing_log._resolve_log_path()
    if path is None:
        return
    entry = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **{key: value for key, value in dimensions.items() if value is not None},
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        # Observability must never alter the chat outcome.
        return


def summarize_analysis_context_events(entries: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {event: 0 for event in TRACKED_EVENTS}
    for entry in entries:
        event = entry.get("event")
        if event in counts:
            counts[event] += 1
    return {
        "needs_analysis_object": counts[EVENT_NEEDS_ANALYSIS_OBJECT],
        "needs_scenario_inputs": counts[EVENT_NEEDS_SCENARIO_INPUTS],
        "http_422": counts[EVENT_ERROR_422],
        "http_409": counts[EVENT_ERROR_409],
        "http_503": counts[EVENT_ERROR_503],
        "legacy_field_used": counts[EVENT_LEGACY_FIELD_USED],
    }


def apply_execution_log_filters(
    query,
    *,
    object_type: str | None = None,
    area_code: str | None = None,
    agent_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    if object_type:
        query = query.filter(ModelExecutionLog.analysis_object_type == object_type)
    if area_code:
        query = query.filter(ModelExecutionLog.area_code == area_code)
    if agent_id:
        query = query.filter(ModelExecutionLog.agent_id == agent_id)
    if date_from:
        query = query.filter(ModelExecutionLog.started_at >= datetime.combine(
            date_from, time.min, tzinfo=timezone.utc,
        ))
    if date_to:
        query = query.filter(ModelExecutionLog.started_at < datetime.combine(
            date_to + timedelta(days=1), time.min, tzinfo=timezone.utc,
        ))
    return query


def query_execution_statistics(
    *,
    object_type: str | None = None,
    area_code: str | None = None,
    agent_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Aggregate execution facts without reading conversation state."""
    query = db.session.query(
        ModelExecutionLog.area_code,
        ModelExecutionLog.agent_id,
        ModelExecutionLog.status,
        db.func.count(ModelExecutionLog.id).label("count"),
    )
    query = apply_execution_log_filters(
        query,
        object_type=object_type,
        area_code=area_code,
        agent_id=agent_id,
        date_from=date_from,
        date_to=date_to,
    )
    rows = query.group_by(
        ModelExecutionLog.area_code,
        ModelExecutionLog.agent_id,
        ModelExecutionLog.status,
    ).order_by(
        ModelExecutionLog.area_code,
        ModelExecutionLog.agent_id,
        ModelExecutionLog.status,
    ).all()
    return [dict(row._mapping) for row in rows]
