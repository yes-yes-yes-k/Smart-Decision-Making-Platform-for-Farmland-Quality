"""Audit and retire unverified Model-5 metrics and legacy acidification results.

Use the project interpreter documented in AGENTS.md. The default mode is a
read-only dry-run; ``--apply`` is required for any database change.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from datetime import datetime, timezone
from typing import Any, Iterable


REAL_MODEL5_SOURCES = {"shaoguan_rf", "global_etr", "rf_model"}
QUANTITATIVE_FIELDS = {
    "organic_fertilizer_dosage",
    "potential_increase",
    "om_improvement_target",
    "manure_dosage",
    "dose",
    "dose_prediction",
}
SQLITE_RETIRED_TABLE = "acidification_results"
SQLITE_REQUIRED_COLUMNS = {
    "parcel_id",
    "acidification_level",
    "target_pH",
    "lime_demand",
    "measures",
    "expected_effect",
}


class MigrationError(RuntimeError):
    def __init__(self, code: str, message: str, *, remediation: str):
        super().__init__(message)
        self.code = code
        self.remediation = remediation


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def archive_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, data: Any, *, read_only: bool = False) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    digest = sha256_file(path)
    if read_only:
        os.chmod(path, stat.S_IREAD)
    return digest


def normalize_postgres_dsn(dsn: str) -> str:
    return (
        dsn.replace("postgresql+psycopg2://", "postgresql://", 1)
        .replace("postgresql+psycopg://", "postgresql://", 1)
    )


def _output_source(output_result: Any) -> str:
    if not isinstance(output_result, dict):
        return "unknown"
    meta = output_result.get("meta")
    if isinstance(meta, dict) and meta.get("data_source"):
        return str(meta["data_source"])
    return str(output_result.get("data_source") or "unknown")


def _has_active_quantitative_value(record: dict[str, Any]) -> bool:
    if any(record.get(field) is not None for field in QUANTITATIVE_FIELDS):
        return True

    def visit(value: Any) -> bool:
        if isinstance(value, dict):
            return any(
                (key in QUANTITATIVE_FIELDS and item is not None) or visit(item)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(visit(item) for item in value)
        return False

    return visit(record.get("output_result"))


def classify_model5_record(record: dict[str, Any]) -> dict[str, Any]:
    source = _output_source(record.get("output_result"))
    status = str(record.get("execution_status") or "unknown").lower()
    model_version = record.get("model_version")
    reasons: list[str] = []
    unknown_source = False

    if record.get("execution_id") is None or record.get("log_id") is None:
        reasons.append("orphan_result")
        unknown_source = True
    if bool(record.get("result_simulated")) or bool(record.get("execution_simulated")):
        reasons.append("simulated")
    if status not in {"ok", "success", "complete", "completed"}:
        reasons.append("degraded_or_failed_status")
    if source not in REAL_MODEL5_SOURCES:
        reasons.append(f"untrusted_source:{source}")
        unknown_source = source in {"", "unknown", "unavailable", "none"}
    if not model_version or str(model_version).strip().lower() == "unknown":
        reasons.append("missing_model_version")
        unknown_source = True

    trusted = not reasons
    return {
        "trusted": trusted,
        "unknown_source": unknown_source,
        "source": source,
        "reasons": reasons,
        "has_active_values": _has_active_quantitative_value(record),
    }


def clear_quantitative_fields(value: Any) -> Any:
    cleaned = copy.deepcopy(value)
    if isinstance(cleaned, dict):
        for key, item in list(cleaned.items()):
            cleaned[key] = None if key in QUANTITATIVE_FIELDS else clear_quantitative_fields(item)
        if isinstance(cleaned.get("issues"), list):
            codes = {issue.get("code") for issue in cleaned["issues"] if isinstance(issue, dict)}
            if "MODEL5_QUANTITATIVE_UNAVAILABLE" not in codes:
                cleaned["issues"].append({
                    "code": "MODEL5_QUANTITATIVE_UNAVAILABLE",
                    "severity": "warning",
                    "message": "历史规则或来源不明的 Model-5 定量值已废弃。",
                })
    elif isinstance(cleaned, list):
        cleaned = [clear_quantitative_fields(item) for item in cleaned]
    return cleaned


def _reason_counts(classified: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classified:
        for reason in item["classification"]["reasons"]:
            counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def inspect_postgres(conn: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                om.id AS result_id,
                om.execution_id,
                om.organic_fertilizer_dosage,
                om.potential_increase,
                om.om_improvement_target,
                om.simulated AS result_simulated,
                log.id AS log_id,
                log.status AS execution_status,
                log.simulated AS execution_simulated,
                log.model_version,
                log.output_result
            FROM organic_matter_result AS om
            LEFT JOIN model_execution_log AS log ON log.id = om.execution_id
            ORDER BY om.id
            """
        )
        columns = [column.name if hasattr(column, "name") else column[0] for column in cur.description]
        records = [dict(zip(columns, row)) for row in cur.fetchall()]

    classified = []
    for record in records:
        item = {"record": record, "classification": classify_model5_record(record)}
        classified.append(item)
    candidates = [
        item for item in classified
        if not item["classification"]["trusted"] and item["classification"]["has_active_values"]
    ]
    summary = {
        "schema_version": "organic_matter_result+model_execution_log/v1",
        "total_records": len(records),
        "trusted_records": sum(1 for item in classified if item["classification"]["trusted"]),
        "retirement_candidates": len(candidates),
        "unknown_source_records": sum(1 for item in classified if item["classification"]["unknown_source"]),
        "reason_counts": _reason_counts(candidates),
    }
    return candidates, summary


def apply_postgres_candidates(conn: Any, candidates: list[dict[str, Any]], json_adapter=lambda value: value) -> None:
    """Clear active fields for classified candidates while retaining execution logs."""
    with conn.transaction(), conn.cursor() as cur:
        for item in candidates:
            record = item["record"]
            cleaned_output = clear_quantitative_fields(record.get("output_result"))
            cur.execute(
                """
                UPDATE organic_matter_result
                SET organic_fertilizer_dosage = NULL,
                    potential_increase = NULL,
                    om_improvement_target = NULL
                WHERE id = %s
                """,
                (record["result_id"],),
            )
            if record.get("log_id") is not None:
                cur.execute(
                    "UPDATE model_execution_log SET output_result = %s WHERE id = %s",
                    (json_adapter(cleaned_output), record["log_id"]),
                )


def migrate_postgres(dsn: str, archive_dir: Path, apply: bool) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as exc:
        raise MigrationError(
            "POSTGRES_DRIVER_UNAVAILABLE",
            "psycopg is required for PostgreSQL migration.",
            remediation="Run the CLI with the project Conda interpreter and installed requirements.",
        ) from exc

    target_id = hashlib.sha256(dsn.encode("utf-8")).hexdigest()[:12]
    with psycopg.connect(normalize_postgres_dsn(dsn)) as conn:
        candidates, summary = inspect_postgres(conn)
        result = {
            "target_type": "postgresql",
            "target_id": target_id,
            "mode": "apply" if apply else "dry-run",
            "summary": summary,
            "backup": None,
            "status": "planned" if not apply else "pending",
        }
        if not apply:
            result["planned_backup"] = str(archive_dir / f"postgres-model5-{target_id}-<timestamp>.json")
            return result
        if summary["retirement_candidates"] == 0:
            result["status"] = "completed"
            result["idempotent_noop"] = True
            return result

        backup_path = archive_dir / f"postgres-model5-{target_id}-{archive_stamp()}.json"
        backup_payload = {
            "created_at": utc_now(),
            "target_id": target_id,
            "records": [item["record"] for item in candidates],
        }
        checksum = write_json(backup_path, backup_payload, read_only=True)
        if sha256_file(backup_path) != checksum:
            raise MigrationError(
                "BACKUP_CHECKSUM_FAILED",
                f"PostgreSQL backup checksum verification failed: {backup_path}",
                remediation="Check archive storage and retry before applying changes.",
            )
        result["backup"] = {"path": str(backup_path), "sha256": checksum}

        try:
            apply_postgres_candidates(conn, candidates, Jsonb)
        except Exception:
            conn.rollback()
            raise

        _, post_summary = inspect_postgres(conn)
        result["post_summary"] = post_summary
        result["status"] = "completed"
        return result


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    return [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def inspect_sqlite(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.is_file():
        raise MigrationError(
            "SQLITE_TARGET_NOT_FOUND",
            f"SQLite target does not exist: {path}",
            remediation="Pass an explicit existing --sqlite path; the tool never searches recursively.",
        )
    with sqlite3.connect(path) as conn:
        tables = _sqlite_tables(conn)
        schema_version = conn.execute("PRAGMA user_version").fetchone()[0]
        protected = {}
        for table in ("evaluation_results", "diagnosis_results"):
            protected[table] = {
                "exists": table in tables,
                "count": conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in tables else 0,
            }
        if SQLITE_RETIRED_TABLE not in tables:
            return {
                "schema_version": schema_version,
                "table_exists": False,
                "columns": [],
                "record_count": 0,
                "expected_effect_non_null": 0,
                "protected_tables": protected,
            }, []

        columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{SQLITE_RETIRED_TABLE}")')]
        missing = sorted(SQLITE_REQUIRED_COLUMNS - set(columns))
        if missing:
            raise MigrationError(
                "SQLITE_SCHEMA_MISMATCH",
                f"acidification_results is missing expected columns: {missing}",
                remediation="Inspect this database manually and update the migration classification before apply.",
            )
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{SQLITE_RETIRED_TABLE}"')]
        non_null = sum(1 for row in rows if row.get("expected_effect") not in {None, ""})
        return {
            "schema_version": schema_version,
            "table_exists": True,
            "columns": columns,
            "record_count": len(rows),
            "expected_effect_non_null": non_null,
            "protected_tables": protected,
        }, rows


def migrate_sqlite(path: Path, archive_dir: Path, apply: bool) -> dict[str, Any]:
    path = path.resolve(strict=True)
    summary, rows = inspect_sqlite(path)
    target_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    result = {
        "target_type": "sqlite",
        "target_id": target_id,
        "path": str(path),
        "mode": "apply" if apply else "dry-run",
        "summary": summary,
        "backup": None,
        "status": "planned" if not apply else "pending",
    }
    if not apply:
        result["planned_backup"] = str(archive_dir / f"sqlite-{target_id}-{path.name}")
        return result
    if not summary["table_exists"]:
        result["status"] = "completed"
        result["idempotent_noop"] = True
        return result

    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = archive_stamp()
    backup_path = archive_dir / f"sqlite-{target_id}-{stamp}-{path.name}"
    export_path = archive_dir / f"sqlite-{target_id}-{stamp}-acidification_results.json"
    try:
        shutil.copy2(path, backup_path)
        backup_checksum = sha256_file(backup_path)
        if backup_checksum != sha256_file(path):
            raise OSError("checksum verification mismatch")
        os.chmod(backup_path, stat.S_IREAD)
        export_checksum = write_json(
            export_path,
            {"created_at": utc_now(), "source": str(path), "rows": rows},
            read_only=True,
        )
    except Exception as exc:
        raise MigrationError(
            "BACKUP_FAILED",
            f"SQLite backup failed before modification: {exc}",
            remediation="Fix archive permissions or free space, then retry; the active database was not modified.",
        ) from exc

    result["backup"] = {
        "database_path": str(backup_path),
        "database_sha256": backup_checksum,
        "archive_path": str(export_path),
        "archive_sha256": export_checksum,
    }
    before_protected = summary["protected_tables"]
    with sqlite3.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f'DROP TABLE "{SQLITE_RETIRED_TABLE}"')
        after_tables = _sqlite_tables(conn)
        after_protected = {}
        for table in ("evaluation_results", "diagnosis_results"):
            after_protected[table] = {
                "exists": table in after_tables,
                "count": conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in after_tables else 0,
            }
        if after_protected != before_protected:
            conn.rollback()
            raise MigrationError(
                "SQLITE_PROTECTED_TABLE_CHANGED",
                "Protected table existence or row counts changed during migration.",
                remediation="Restore the verified backup and inspect SQLite triggers or schema manually.",
            )
        conn.commit()

    post_summary, _ = inspect_sqlite(path)
    result["post_summary"] = post_summary
    result["status"] = "completed"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--postgres-dsn", help="Explicit PostgreSQL DSN; never inferred from application config.")
    parser.add_argument("--sqlite", action="append", default=[], help="Explicit SQLite path; repeat for multiple targets.")
    parser.add_argument("--archive-dir", default="backups/retired-fallback-metrics", help="Backup/archive directory.")
    parser.add_argument("--audit-output", help="JSON audit output path.")
    parser.add_argument("--apply", action="store_true", help="Apply changes after verified backups. Default is dry-run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.postgres_dsn and not args.sqlite:
        build_parser().error("at least one explicit --postgres-dsn or --sqlite target is required")

    started_at = utc_now()
    archive_dir = Path(args.archive_dir).resolve()
    audit_path = Path(args.audit_output).resolve() if args.audit_output else archive_dir / "migration-audit.json"
    audit: dict[str, Any] = {
        "migration": "retire-unverified-fallback-metrics",
        "mode": "apply" if args.apply else "dry-run",
        "started_at": started_at,
        "completed_at": None,
        "status": "running",
        "targets": [],
    }
    try:
        if args.postgres_dsn:
            audit["targets"].append(migrate_postgres(args.postgres_dsn, archive_dir, args.apply))
        for sqlite_target in args.sqlite:
            audit["targets"].append(migrate_sqlite(Path(sqlite_target), archive_dir, args.apply))
        audit["status"] = "completed"
        return_code = 0
    except MigrationError as exc:
        audit["status"] = "failed"
        audit["error"] = {"code": exc.code, "message": str(exc), "remediation": exc.remediation}
        return_code = 1
    except Exception as exc:
        audit["status"] = "failed"
        audit["error"] = {
            "code": "UNEXPECTED_MIGRATION_ERROR",
            "message": str(exc),
            "remediation": "Review the audit and database logs; restore only from the verified backup if apply began.",
        }
        return_code = 1
    finally:
        audit["completed_at"] = utc_now()
        try:
            write_json(audit_path, audit)
        except Exception as audit_exc:
            print(json.dumps({"status": "failed", "error": {"code": "AUDIT_WRITE_FAILED", "message": str(audit_exc)}}))
            return 1
        print(json.dumps(audit, ensure_ascii=False, indent=2, default=str))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
