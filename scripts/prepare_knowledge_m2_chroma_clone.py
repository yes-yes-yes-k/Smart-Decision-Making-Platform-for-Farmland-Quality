"""Copy the local vector store for real runtime measurements; source is read-only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_knowledge_m2_snapshot import OUT


def main():
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    from framework.config import Config
    source = Path(Config.CHROMA_PERSIST_DIR).resolve()
    target = (OUT/"runtime/chroma-clone").resolve()
    if target.exists() or OUT.resolve() not in target.parents or source in target.parents:
        raise ValueError("M2_clone_target_must_be_new_and_isolated")
    files = [path for path in source.rglob("*") if path.is_file() and path.name not in {"chroma.sqlite3", "chroma.sqlite3-wal", "chroma.sqlite3-shm"} and not path.name.startswith("lexical-index")]
    if any(source not in path.resolve().parents for path in files):
        raise ValueError("M2_source_directory_has_outside_file_link")
    before = {str(path.relative_to(source)): [path.stat().st_size, path.stat().st_mtime_ns] for path in files}
    total = sum(value[0] for value in before.values())+(source/"chroma.sqlite3").stat().st_size
    if shutil.disk_usage(OUT).free < total*2:
        raise ValueError("insufficient_isolated_clone_disk_headroom")
    target.mkdir(parents=True)
    origin = sqlite3.connect((source/"chroma.sqlite3").as_uri()+"?mode=ro", uri=True)
    destination = sqlite3.connect(target/"chroma.sqlite3")
    try:
        origin.backup(destination)
    finally:
        destination.close(); origin.close()
    for path in files:
        copy = target/path.relative_to(source)
        copy.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, copy)
    after = {str(path.relative_to(source)): [path.stat().st_size, path.stat().st_mtime_ns] for path in files}
    if before != after:
        raise ValueError("source_vector_files_changed_during_clone_do_not_measure")
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "source_not_written": True,
              "sqlite_transactional_backup": True, "vector_files_unchanged_during_copy": True,
              "copied_files": len(files)+1, "copied_bytes": total, "target": str(target.relative_to(REPO)),
              "not_a_production_backup_restore_or_capacity_certificate": True}
    (OUT/"chroma-clone-v1.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"copied_files": len(files)+1, "copied_bytes": total, "source_not_written": True}))


if __name__ == "__main__":
    main()
