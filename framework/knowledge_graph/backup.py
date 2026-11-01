"""Whole-database PostgreSQL/AGE backup and restore verification primitives."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Sequence

from .age_migration import audit_checksum, snapshot_counts
from .stores import AgeGraphStore


class GraphBackupError(RuntimeError):
    pass


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run_checked(
    command: Sequence[str], runner: Callable[..., Any] = subprocess.run,
) -> None:
    result = runner(list(command), check=False, capture_output=True, text=True)
    if int(getattr(result, "returncode", 1)) != 0:
        message = str(getattr(result, "stderr", "") or "command failed")[-2000:]
        raise GraphBackupError(message)


def build_restore_manifest(
    store: AgeGraphStore,
    dump_path: str | Path,
    *,
    database_name: str,
) -> dict[str, Any]:
    health = dict(store.health())
    if not health.get("ready"):
        raise GraphBackupError(f"AGE store is not healthy: {health.get('errors')}")
    release_id = str(health["active_release"])
    snapshot = store.export_snapshot(release_id)
    return {
        "schema": "postgres-age-backup-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_name": database_name,
        "postgres_major": health.get("postgres_major"),
        "age_version": health.get("age_version"),
        "graph_name": health.get("graph_name"),
        "active_release": release_id,
        "counts": snapshot_counts(snapshot),
        "graph_checksum": audit_checksum(snapshot),
        "dump_sha256": sha256_file(dump_path),
        "dump_file": Path(dump_path).name,
    }


def create_postgres_age_backup(
    *,
    dsn: str,
    output_path: str | Path,
    database_name: str,
    store: AgeGraphStore,
    pg_dump: str = "pg_dump",
    pg_restore: str = "pg_restore",
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    """Back up the complete DB so AGE, governance rows and evidence stay consistent."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    _run_checked((
        pg_dump, "--dbname", dsn, "--format=custom", "--no-owner",
        "--no-privileges", "--file", str(temporary),
    ), runner)
    _run_checked((pg_restore, "--list", str(temporary)), runner)
    temporary.replace(destination)
    manifest = build_restore_manifest(store, destination, database_name=database_name)
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    return manifest


def repair_restored_age_catalog(engine) -> dict[str, Any]:
    """Explicit post-restore operation; never run implicitly during normal reads.

    Logical restores preserve bare source OIDs in AGE 1.6 catalogs. The
    regnamespace column already resolves to the restored schema's real OID.
    See https://github.com/apache/age/issues/2503.
    """
    from sqlalchemy import text
    with engine.begin() as connection:
        connection.exec_driver_sql("LOCK TABLE ag_catalog.ag_graph, ag_catalog.ag_label IN ACCESS EXCLUSIVE MODE")
        rows = list(connection.execute(text(
            "SELECT graphid, namespace::oid AS restored_oid FROM ag_catalog.ag_graph"
        )).mappings())
        changed = [row for row in rows if row["graphid"] != row["restored_oid"]]
        if not changed:
            return {"repaired_graphs": 0}
        old_ids = {row["graphid"] for row in rows}
        if any(row["restored_oid"] in old_ids for row in changed):
            raise GraphBackupError("restored AGE graph OIDs overlap; manual recovery required")
        connection.exec_driver_sql("ALTER TABLE ag_catalog.ag_label DROP CONSTRAINT fk_graph_oid")
        connection.exec_driver_sql(
            "UPDATE ag_catalog.ag_label AS label SET graph = graph.namespace::oid "
            "FROM ag_catalog.ag_graph AS graph "
            "WHERE label.graph = graph.graphid AND graph.graphid <> graph.namespace::oid"
        )
        connection.exec_driver_sql(
            "UPDATE ag_catalog.ag_graph SET graphid = namespace::oid "
            "WHERE graphid <> namespace::oid"
        )
        connection.exec_driver_sql(
            "ALTER TABLE ag_catalog.ag_label ADD CONSTRAINT fk_graph_oid "
            "FOREIGN KEY (graph) REFERENCES ag_catalog.ag_graph(graphid)"
        )
    engine.dispose()  # AGE caches graph metadata per connection.
    return {"repaired_graphs": len(changed)}


def verify_restored_store(
    store: AgeGraphStore, manifest: Mapping[str, Any], dump_path: str | Path,
) -> dict[str, Any]:
    issues = []
    if sha256_file(dump_path) != manifest.get("dump_sha256"):
        issues.append("dump_checksum_mismatch")
    health = dict(store.health())
    if not health.get("ready"):
        issues.append("age_health_failed")
    if health.get("active_release") != manifest.get("active_release"):
        issues.append("active_release_mismatch")
    snapshot = None
    if not issues:
        snapshot = store.export_snapshot(str(manifest["active_release"]))
        if snapshot_counts(snapshot) != dict(manifest.get("counts") or {}):
            issues.append("graph_count_mismatch")
        if audit_checksum(snapshot) != manifest.get("graph_checksum"):
            issues.append("graph_checksum_mismatch")
    return {
        "schema": "postgres-age-restore-verification-v1",
        "status": "completed",
        "passed": not issues,
        "issues": issues,
        "active_release": health.get("active_release"),
        "counts": snapshot_counts(snapshot) if snapshot is not None else None,
    }


def restore_postgres_age_backup(
    *,
    dsn: str,
    dump_path: str | Path,
    manifest: Mapping[str, Any],
    restored_store: AgeGraphStore,
    apply: bool,
    repair_catalog_oids: bool = False,
    pg_restore: str = "pg_restore",
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if not apply:
        raise GraphBackupError("restore requires explicit apply=True")
    if sha256_file(dump_path) != manifest.get("dump_sha256"):
        raise GraphBackupError("backup dump checksum does not match its manifest")
    _run_checked((
        pg_restore, "--dbname", dsn, "--clean", "--if-exists",
        "--exit-on-error", "--single-transaction", str(dump_path),
    ), runner)
    catalog_repair = None
    if repair_catalog_oids:
        catalog_repair = repair_restored_age_catalog(restored_store.executor.engine)
    report = verify_restored_store(restored_store, manifest, dump_path)
    if catalog_repair is not None:
        report["catalog_repair"] = catalog_repair
    if not report["passed"]:
        raise GraphBackupError(f"restored graph verification failed: {report['issues']}")
    return report
