"""Measure the frozen legacy path on all actual chunks, without app/model startup."""
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_knowledge_m2_snapshot import OUT
from framework.knowledge_graph.operational_measurements import process_memory


def main():
    path = OUT/"baseline-v1.json"
    if path.exists():
        raise ValueError("baseline_result_exists_use_new_version")
    started = time.perf_counter()
    result = {"state": "running", "scope": "all_actual_112168_chunks_legacy_lexical_path_only",
              "runner_pid": os.getpid(),
              "captured_at_utc": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
              "limits": {"wall_seconds": 600, "working_set_bytes": 4*1024**3}, "stages": []}
    lock = threading.Lock()
    def save():
        with lock:
            result["elapsed_seconds"] = time.perf_counter()-started
            result["memory"] = process_memory()
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            temporary.replace(path)
    def watchdog():
        while True:
            time.sleep(2)
            memory = process_memory()
            if time.perf_counter()-started > 600 or memory.get("working_set_bytes", 0) > 4*1024**3:
                result["state"] = "stopped_at_measurement_limit"
                result["incomplete_stages_are_not_zero_cost"] = True
                save(); os._exit(124)
    save()  # Fail immediately if native measurement is unavailable.
    threading.Thread(target=watchdog, daemon=True).start()
    spec = importlib.util.spec_from_file_location("M2_frozen_legacy_bm25", OUT/"baseline-code/bm25_store.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    connection = sqlite3.connect((OUT/"corpus/source.sqlite3").resolve().as_uri()+"?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    stores = {}
    stage_start = time.perf_counter()
    for (name,) in connection.execute("SELECT DISTINCT collection FROM chunks ORDER BY collection"):
        # Deliberately reproduce the real old accumulation/rebuild behavior.
        texts, metadatas = [], []
        for content, meta in connection.execute("SELECT content,metadata FROM chunks WHERE collection=? ORDER BY id", (name,)):
            texts.append(content); metadatas.append(json.loads(meta))
        store = module.BM25Store(); store.add_documents(texts, metadatas); stores[name] = store
        result["stages"].append({"stage": "legacy_collection_startup", "collection": name, "rows": len(texts),
                                  "cumulative_startup_seconds": time.perf_counter()-stage_start, "memory": process_memory()})
        print(json.dumps(result["stages"][-1]), flush=True); save()
    result["startup_seconds"] = time.perf_counter()-stage_start
    for query in ("石灰 土壤 酸化", "soil organic carbon", "交换性氢"):
        began = time.perf_counter()
        hits = []
        for store in stores.values():
            hits.extend(store.search(query, 20, {"visibility_scope": "public"}))
        hits.sort(key=lambda row: -row["score"])
        result["stages"].append({"stage": "legacy_query", "query": query, "seconds": time.perf_counter()-began,
            "top_document_ids": [row["metadata"].get("document_id") for row in hits[:20]], "memory": process_memory()})
        print(json.dumps(result["stages"][-1]), flush=True); save()
    # A real document replay exercises the old two full rebuilds on replacement.
    document_id = connection.execute("SELECT json_extract(metadata,'$.document_id') FROM chunks WHERE collection='enterprise_kb' LIMIT 1").fetchone()[0]
    rows = connection.execute("SELECT content,metadata FROM chunks WHERE collection='enterprise_kb' AND json_extract(metadata,'$.document_id')=? ORDER BY id", (document_id,)).fetchall()
    began = time.perf_counter()
    store = stores["enterprise_kb"]
    removed = store.delete_by_document_id(document_id)
    store.add_documents([row[0] for row in rows], [json.loads(row[1]) for row in rows])
    result["stages"].append({"stage": "legacy_single_document_replay", "document_id": document_id, "chunks": len(rows),
                              "removed": removed, "seconds": time.perf_counter()-began, "memory": process_memory()})
    result["state"] = "completed"; save(); connection.close()
    print(json.dumps({"state": result["state"], "elapsed_seconds": result["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); main()
