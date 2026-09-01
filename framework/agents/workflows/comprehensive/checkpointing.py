from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver


CHECKPOINT_NAMESPACE = "single-parcel-v1"


def normalize_postgres_uri(uri: str) -> str:
    return (
        uri.replace("postgresql+psycopg2://", "postgresql://", 1)
        .replace("postgresql+psycopg://", "postgresql://", 1)
    )


def workflow_thread_config(
    conversation_id: int, run_id: str
) -> dict[str, dict[str, str]]:
    if conversation_id <= 0 or not run_id.strip():
        raise ValueError("conversation_id and run_id are required")
    return {
        "configurable": {
            "thread_id": f"chat:{conversation_id}:comprehensive:{run_id}",
            "checkpoint_ns": CHECKPOINT_NAMESPACE,
        }
    }


class PostgresCheckpointerRuntime:
    def __init__(self, uri: str, *, auto_setup: bool = False):
        self._uri = normalize_postgres_uri(uri)
        self._auto_setup = auto_setup
        self._context_manager: Any = None
        self._saver: BaseCheckpointSaver | None = None

    def start(self) -> BaseCheckpointSaver:
        if self._saver is not None:
            return self._saver
        self._context_manager = PostgresSaver.from_conn_string(self._uri)
        self._saver = self._context_manager.__enter__()
        if self._auto_setup:
            self._saver.setup()
        return self._saver

    def close(self) -> None:
        if self._context_manager is not None:
            self._context_manager.__exit__(None, None, None)
        self._context_manager = None
        self._saver = None
