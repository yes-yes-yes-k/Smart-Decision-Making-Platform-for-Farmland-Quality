"""Real Chroma+lexical runtime on all existing data, with no paid embeddings."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import sys
import time
import types
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_knowledge_m2_snapshot import OUT
from framework.knowledge_graph.operational_measurements import process_memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("bootstrap", "warm"), required=True)
    args = parser.parse_args()
    target = OUT/("runtime-"+args.phase+"-v1.json")
    if target.exists():
        raise ValueError("frozen_runtime_measurement_exists_use_new_version")
    clone = (OUT/"runtime/chroma-clone").resolve()
    if not (clone/"chroma.sqlite3").is_file():
        raise ValueError("isolated_vector_clone_required")
    os.environ["CHROMA_PERSIST_DIR"] = str(clone)
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    embedding = types.ModuleType("framework.embedding.service")
    vector = []
    def embed_query(query):
        if not vector:
            raise RuntimeError("replayed_existing_vector_not_loaded")
        return vector
    def no_new_documents(texts):
        raise RuntimeError("M2_no_new_embedding_calls")
    embedding.embedding_service = types.SimpleNamespace(is_available=lambda: True, embed_query=embed_query, embed_documents=no_new_documents)
    sys.modules["framework.embedding.service"] = embedding
    began = time.perf_counter()
    from chromadb.api.models.Collection import Collection
    calls = {"text_get_calls": 0, "text_rows": 0, "max_text_page": 0}
    original_get = Collection.get
    def instrument(collection, *arguments, **kwargs):
        value = original_get(collection, *arguments, **kwargs)
        if "documents" in (kwargs.get("include") or []):
            calls["text_get_calls"] += 1
            calls["text_rows"] += len(value.get("ids") or [])
            calls["max_text_page"] = max(calls["max_text_page"], len(value.get("ids") or []))
        return value
    with patch.object(Collection, "get", instrument):
        from framework.vector_store.chroma_store import vector_store
        store = vector_store
        startup = {"seconds": time.perf_counter()-began, "memory": process_memory(), "source_reads": dict(calls),
                   "lexical": {name: item.index.health() for name,item in store._bm25.items()}}
        if sum(collection.count() for collection in store._collections.values()) != 112168:
            raise ValueError("full_actual_runtime_scope_changed")
        if args.phase == "warm" and (calls["text_get_calls"] or any(item.index.metrics["tokenized_rows"] for item in store._bm25.values())):
            raise ValueError("warm_start_rebuilt_or_read_corpus")
        print(json.dumps({"phase": args.phase, "startup_seconds": startup["seconds"], "source_reads": startup["source_reads"]}), flush=True)
        # Use an existing persisted vector solely to measure the actual backend.
        # This excludes query-embedding generation and says nothing about QA quality.
        first = next(iter(store._collections.values())).get(limit=1, include=["embeddings"])
        vector.extend(first["embeddings"][0].tolist())
        samples, lexical_samples, queries = [], [], []
        diagnostic = ["石灰 土壤 酸化", "soil organic carbon", "交换性氢", "有效钾", "生物炭", "cadmium soil", "秸秆", "有机质"]
        repetitions = 1 if args.phase == "bootstrap" else 5
        for repetition in range(repetitions):
            for query in diagnostic:
                started = time.perf_counter()
                lexical = store._bm25_search(query, 20, {"visibility_scope": "public"})
                lexical_elapsed = time.perf_counter()-started
                started = time.perf_counter()
                combined = store.hybrid_search(query, 20, {"visibility_scope": "public"})
                elapsed = time.perf_counter()-started
                samples.append(elapsed); lexical_samples.append(lexical_elapsed)
                queries.append({"query": query, "repetition": repetition, "lexical_seconds": lexical_elapsed,
                    "hybrid_seconds_excluding_embedding": elapsed, "count": combined["count"],
                    "lexical_top_document_ids": [row["metadata"].get("document_id") for row in lexical],
                    "hybrid_top_document_ids": [row["metadata"].get("document_id") for row in combined["results"]]})
        def summary(values):
            ordered = sorted(values)
            return {"samples": len(values), "median_seconds": statistics.median(values),
                    "p95_seconds": ordered[max(0, int(len(ordered)*.95+.999)-1)], "max_seconds": max(values)}
        report = {"state": "completed", "phase": args.phase, "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "actual_chunks": 112168, "backend": "real_cloned_Chroma_HNSW_plus_persistent_FTS5", "startup": startup,
            "queries": queries, "lexical_latency": summary(lexical_samples), "hybrid_latency": summary(samples),
            "final_memory": process_memory(), "public_api_source_reads": dict(calls),
            "model_calls": 0, "query_embedding": "replay_of_one_existing_persisted_vector_not_semantic_query_evaluation",
            "excluded": ["query_embedding_generation", "reranking", "LLM_generation", "full_application_startup"],
            "versions": {name: importlib.metadata.version(name) for name in ("chromadb", "jieba", "sqlalchemy")},
            "elapsed_seconds": time.perf_counter()-began}
        store.close()
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"state": "completed", "phase": args.phase, "lexical": report["lexical_latency"], "hybrid": report["hybrid_latency"]}), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8"); main()
