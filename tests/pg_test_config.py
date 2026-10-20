"""PostgreSQL integration-test environment loading."""

from __future__ import annotations

import os
from pathlib import Path


_DB_KEYS = {"DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"}


def load_pg_test_environment(env_file: str | os.PathLike[str]) -> str:
    """Load DB settings and force pytest onto an isolated ``*_test`` database."""
    path = Path(env_file)
    if not path.exists():
        return os.environ.get("DB_NAME", "")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in _DB_KEYS:
            values[key] = value.strip().strip("\"'")

    source_db = values.get("DB_NAME", os.environ.get("DB_NAME", ""))
    if not source_db:
        raise RuntimeError("DB_NAME is required for PostgreSQL integration tests")
    test_db = source_db if source_db.endswith("_test") else f"{source_db}_test"

    for key, value in values.items():
        os.environ[key] = value
    os.environ["DB_NAME"] = test_db
    return test_db
