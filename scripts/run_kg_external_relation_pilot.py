"""Finite twelve-document native-task GraphRAG pilot, with per-call budgeting."""
import argparse
import asyncio
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from framework.knowledge_graph.external_benchmark_data import digest
from scripts.prepare_kg_external_benchmarks import write_json

OUT = REPO / "artifacts/knowledge_platform/external-benchmark-v1"
RUN = OUT / "runs/redocred-pilot-v1"
PYTHON = REPO / ".tools/graphrag-runtime/Scripts/python.exe"
CHILD = REPO / "scripts/graphrag_external_relations.py"


def prepare():
    roles = json.loads((OUT / "splits/redocred/effective-roles-v1.json").read_text(encoding="utf-8"))
    selected = set(roles["pilot_ids"])
    isolation = json.loads((OUT / "reports/isolation-screen-v1.json").read_text(encoding="utf-8"))["datasets"]["redocred"]
    unresolved = {row[side] for row in isolation["cross_partition_candidates"] for side in ("left", "right")}
    if selected & unresolved:
        raise ValueError("pilot_member_has_unresolved_isolation")
    with gzip.open(OUT / "sources/docred_upstream/huggingface/data/rel_info.json.gz", "rt", encoding="utf-8") as stream:
        relations = json.load(stream)
    jobs = []
    for line in (OUT / "normalized/redocred/train.inputs.jsonl").read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        if item["id"] in selected:
            jobs.append({"input": item, "relation_labels": relations})
    if len(jobs) != 12 or len(selected) != 12:
        raise ValueError("pilot_membership_changed")
    jobs.sort(key=lambda row: digest("external-v1-pilot-20261029:" + row["input"]["id"]))
    config = {"schema": "external-native-re-pilot-v1", "model": "deepseek-ai/DeepSeek-V4.1-Flash",
              "endpoint": "https://api.siliconflow.cn/v1", "runtime": "graphrag==3.3.0",
              "task": "given_entity_relation_native_ontology_custom_prompt_not_production_schema",
              "documents": 12, "source_partition": "native_train_effective_development", "temperature": 0,
              "gleanings": 0, "max_output_tokens": 8192, "concurrency": 2, "transient_retries": 1,
              "final_acceptance": False, "automatic_resume": False,
              "job_hashes": {row["input"]["id"]: digest(json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in jobs},
              "implementation_hashes": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                                         for path in [CHILD, Path(__file__).resolve(),
                                                      REPO / "framework/knowledge_graph/external_benchmark_budget.py",
                                                      REPO / "framework/knowledge_graph/acceptance_budget.py",
                                                      REPO / ".tools/graphrag-runtime/Lib/site-packages/graphrag/index/operations/extract_graph/graph_extractor.py"]}}
    path = RUN / "run-config.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != config:
        raise ValueError("frozen_run_changed_use_new_version")
    write_json(path, config)
    budget = open_external_budget(OUT)
    estimates = [len(json.dumps(row, ensure_ascii=False).encode("utf-8")) + 8192 + 16384 for row in jobs]
    preflight = {"requests_including_one_retry_each": 24, "conservative_reservation_all_attempts": 2 * sum(estimates),
                 "budget": budget.summary(), "input_contains_reference_relations": False,
                 "input_contains_given_entities_by_native_task_design": True,
                 "selected_members_clear_of_current_isolation_candidates": True}
    write_json(RUN / "preflight.json", preflight)
    return jobs, config, preflight


async def execute():
    jobs, config, preflight = prepare()
    budget = open_external_budget(OUT)
    snapshot = budget.summary()
    if snapshot["inflight"]:
        raise ValueError("other_external_requests_inflight")
    if snapshot["tokens_charged_or_reserved"] + preflight["conservative_reservation_all_attempts"] > snapshot["caps"]["total_tokens"]:
        raise ValueError("insufficient_budget_for_complete_pilot")
    if snapshot["requests"] + 24 > snapshot["caps"]["requests"]:
        raise ValueError("insufficient_request_budget_for_complete_pilot")
    sem = asyncio.Semaphore(2)
    stop = False
    async def one(job):
        nonlocal stop
        async with sem:
            identifier = job["input"]["id"]
            target = RUN / "responses" / (digest(identifier) + ".json")
            if target.exists() or stop:
                return
            start = time.monotonic()
            process = await asyncio.create_subprocess_exec(str(PYTHON), str(CHILD), cwd=REPO,
                       stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(job, ensure_ascii=False).encode("utf-8")), timeout=330)
                try:
                    result = json.loads(stdout.decode("utf-8"))
                except (ValueError, UnicodeError):
                    result = {"state": "failed", "error": "runtime_no_valid_result", "exit_code": process.returncode}
                for attempt in result.get("attempts", []):
                    if attempt.get("http_status") in (401, 402, 403):
                        stop = True
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                result = {"state": "failed", "error": "runtime_timeout"}
                # Only this confirmed-dead job's unknown usage is recovered.
                with budget.connect() as conn:
                    conn.execute("UPDATE attempts SET charged=reserved,state='interrupted',error='runtime_timeout_unknown_usage' WHERE job=? AND state='inflight'", (identifier,))
            result.update(id=identifier, title=job["input"]["title"], elapsed_seconds=time.monotonic()-start,
                          job_sha256=config["job_hashes"][identifier], saved_at=datetime.now(timezone.utc).isoformat())
            write_json(target, result)
            saved = list((RUN / "responses").glob("*.json"))
            write_json(RUN / "progress.json", {"target": 12, "saved": len(saved), "stopped": stop, "budget": budget.summary()})
            print(json.dumps({"saved": len(saved), "state": result["state"], "error": result.get("error")}), flush=True)
    await asyncio.gather(*(one(job) for job in jobs))
    write_json(RUN / "run-state.json", {"state": "stopped" if stop else "completed", "budget": budget.summary(), "final_acceptance": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute:
        asyncio.run(execute())
    else:
        _, _, preflight = prepare()
        print(json.dumps(preflight, ensure_ascii=False))
