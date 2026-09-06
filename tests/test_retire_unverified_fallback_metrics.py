import sqlite3

import pytest

from scripts.retire_unverified_fallback_metrics import (
    MigrationError,
    apply_postgres_candidates,
    classify_model5_record,
    clear_quantitative_fields,
    inspect_sqlite,
    migrate_sqlite,
)


def _create_legacy_sqlite(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE evaluation_results (parcel_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE diagnosis_results (parcel_id TEXT PRIMARY KEY)")
        conn.execute(
            """
            CREATE TABLE acidification_results (
                parcel_id TEXT PRIMARY KEY,
                acidification_level TEXT,
                acidification_direction TEXT,
                target_pH REAL,
                lime_demand REAL,
                amendment_type TEXT,
                amendment_rate REAL,
                measures TEXT,
                expected_effect TEXT
            )
            """
        )
        conn.execute("INSERT INTO evaluation_results VALUES ('P-1')")
        conn.execute("INSERT INTO diagnosis_results VALUES ('P-1')")
        conn.execute(
            "INSERT INTO acidification_results VALUES ('P-1', '中', NULL, 6.0, 100, NULL, NULL, '[]', 'legacy')"
        )


def test_model5_classification_uses_provenance_not_numeric_pattern():
    trusted = classify_model5_record({
        "execution_id": 1,
        "log_id": 1,
        "result_simulated": False,
        "execution_simulated": False,
        "execution_status": "ok",
        "model_version": "rf-v1",
        "organic_fertilizer_dosage": 135.0,
        "output_result": {"meta": {"data_source": "rf_model"}},
    })
    fallback = classify_model5_record({
        "execution_id": 2,
        "log_id": 2,
        "result_simulated": True,
        "execution_simulated": True,
        "execution_status": "degraded",
        "model_version": "unknown",
        "organic_fertilizer_dosage": 9999.0,
        "output_result": {"meta": {"data_source": "rule_fallback"}},
    })
    assert trusted["trusted"] is True
    assert fallback["trusted"] is False
    assert fallback["has_active_values"] is True
    assert "simulated" in fallback["reasons"]


def test_clear_quantitative_fields_preserves_audit_and_adds_issue():
    original = {
        "status": "degraded",
        "result": {"dose_prediction": 135.0, "potential_increase": 1.5, "level": "低"},
        "issues": [],
        "meta": {"data_source": "rule_fallback"},
    }
    cleaned = clear_quantitative_fields(original)
    assert cleaned["result"]["dose_prediction"] is None
    assert cleaned["result"]["potential_increase"] is None
    assert cleaned["result"]["level"] == "低"
    assert cleaned["meta"] == original["meta"]
    assert cleaned["issues"][0]["code"] == "MODEL5_QUANTITATIVE_UNAVAILABLE"


def test_sqlite_dry_run_is_read_only(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_sqlite(db_path)
    before = db_path.read_bytes()
    result = migrate_sqlite(db_path, tmp_path / "archive", apply=False)
    assert result["summary"]["record_count"] == 1
    assert result["summary"]["expected_effect_non_null"] == 1
    assert db_path.read_bytes() == before


def test_sqlite_apply_backs_up_drops_only_retired_table_and_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy.db"
    archive = tmp_path / "archive"
    _create_legacy_sqlite(db_path)

    first = migrate_sqlite(db_path, archive, apply=True)
    assert first["status"] == "completed"
    assert first["backup"]["database_sha256"]
    assert first["backup"]["archive_sha256"]
    summary, _ = inspect_sqlite(db_path)
    assert summary["table_exists"] is False
    assert summary["protected_tables"]["evaluation_results"]["count"] == 1
    assert summary["protected_tables"]["diagnosis_results"]["count"] == 1

    second = migrate_sqlite(db_path, archive, apply=True)
    assert second["status"] == "completed"
    assert second["idempotent_noop"] is True


def test_sqlite_backup_failure_aborts_before_drop(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    _create_legacy_sqlite(db_path)
    monkeypatch.setattr(
        "scripts.retire_unverified_fallback_metrics.shutil.copy2",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(MigrationError) as exc_info:
        migrate_sqlite(db_path, tmp_path / "archive", apply=True)
    assert exc_info.value.code == "BACKUP_FAILED"
    summary, _ = inspect_sqlite(db_path)
    assert summary["table_exists"] is True


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params):
        self.calls.append((" ".join(statement.split()), params))


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def transaction(self):
        return _Context()

    def cursor(self):
        return self.cursor_instance


def test_postgres_apply_updates_only_preclassified_candidates():
    conn = _Connection()
    candidate = {
        "record": {
            "result_id": 2,
            "log_id": 20,
            "output_result": {"result": {"dose": 135.0, "level": "低"}, "issues": []},
        },
        "classification": {"trusted": False},
    }
    apply_postgres_candidates(conn, [candidate])
    calls = conn.cursor_instance.calls
    assert len(calls) == 2
    assert calls[0][1] == (2,)
    cleaned_output, log_id = calls[1][1]
    assert log_id == 20
    assert cleaned_output["result"]["dose"] is None
    assert cleaned_output["result"]["level"] == "低"
