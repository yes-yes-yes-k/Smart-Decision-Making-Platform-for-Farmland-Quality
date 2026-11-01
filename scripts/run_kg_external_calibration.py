"""Freeze and execute the complete isolated 499-document calibration partition."""
import argparse
import asyncio
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from framework.knowledge_graph.external_benchmark_data import digest, dump_jsonl
from scripts.prepare_kg_external_benchmarks import write_json

OUT = REPO / "artifacts/knowledge_platform/external-benchmark-v1"
RUN = OUT / "runs/redocred-calibration-v1"
PYTHON = REPO / ".tools/graphrag-runtime/Scripts/python.exe"
CHILD = REPO / "scripts/graphrag_external_calibration.py"
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def hashes():
    paths = [CHILD, Path(__file__).resolve(), REPO / "framework/knowledge_graph/external_benchmark_budget.py",
             REPO / "framework/knowledge_graph/acceptance_budget.py", OUT / "budget-authorization.json",
             OUT / "splits/redocred/effective-roles-v2.json", OUT / "reports/isolation-screen-v2.json",
             OUT / "sources/docred_upstream/huggingface/data/rel_info.json.gz",
             OUT / "normalized/redocred/dev.inputs.jsonl",
             REPO / ".tools/graphrag-runtime/Lib/site-packages/graphrag/index/operations/extract_graph/graph_extractor.py"]
    return {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def prepare():
    config_path = RUN / "run-config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["implementation_and_input_hashes"] != hashes():
            raise ValueError("frozen_calibration_dependencies_changed")
        jobs = [json.loads(line) for line in (RUN / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
        if digest(json.dumps(jobs, sort_keys=True, ensure_ascii=False)) != config["jobs_sha256"]:
            raise ValueError("frozen_calibration_jobs_changed")
        return jobs, config
    roles = json.loads((OUT / "splits/redocred/effective-roles-v2.json").read_text(encoding="utf-8"))["roles"]
    selected = {row["id"] for row in roles if row["role"] == "calibration"}
    if len(selected) != 499:
        raise ValueError("calibration_partition_must_contain_all499_documents")
    isolation = json.loads((OUT / "reports/isolation-screen-v2.json").read_text(encoding="utf-8"))["datasets"]["redocred"]
    if isolation["cross_partition_candidates"]:
        raise ValueError("unresolved_effective_isolation")
    inputs = [json.loads(line) for line in (OUT / "normalized/redocred/dev.inputs.jsonl").read_text(encoding="utf-8").splitlines()]
    with gzip.open(OUT / "sources/docred_upstream/huggingface/data/rel_info.json.gz", "rt", encoding="utf-8") as stream:
        relations = json.load(stream)
    jobs = [{"stage": "calibration", "input": row, "relation_labels": relations} for row in inputs if row["id"] in selected]
    jobs.sort(key=lambda row: digest("external-calibration-v1:" + row["input"]["id"]))
    if len(jobs) != 499:
        raise ValueError("calibration_inputs_missing")
    process = subprocess.run([str(PYTHON), str(CHILD), "--preflight-batch"],
            input=json.dumps(jobs, ensure_ascii=False).encode("utf-8"), capture_output=True, cwd=REPO, env=ENV, timeout=600)
    if process.returncode:
        raise ValueError("calibration_request_preflight_failed")
    estimates = json.loads(process.stdout.decode("utf-8"))
    if len(estimates) != len(jobs) or any(row.get("model_calls") != 0 for row in estimates):
        raise ValueError("preflight_must_not_call_models")
    for job, estimate in zip(jobs, estimates):
        if job["input"]["id"] != estimate["id"]:
            raise ValueError("preflight_member_order_changed")
        job["expected_request_sha256"] = estimate["request_sha256"]
    original_pass = sum(row["request_reservation"] for row in estimates)
    ledger = open_external_budget(OUT)
    current = ledger.summary()
    remaining = current["caps"]["total_tokens"] - current["tokens_charged_or_reserved"]
    feasible = original_pass <= remaining and current["requests"] + 499 <= 5000 and not current["inflight"]
    budget_plan = {"documents": 499, "official_dev_documents": 500,
                  "inactive_source_overlap_documents": 1, "changed_reference_labels": 0,
                  "model": "deepseek-ai/DeepSeek-V4.1-Flash", "output_limit_unchanged_from_pilot": 8192,
                  "exact_first_pass_input_output_reservation": original_pass,
                  "worst_case_one_transient_retry_every_document": 2*original_pass,
                  "per_request_min": min(row["request_reservation"] for row in estimates),
                  "per_request_max": max(row["request_reservation"] for row in estimates),
                  "remaining_tokens_before_batch": remaining, "budget_before_batch": current,
                  "first_pass_fits": feasible, "all_possible_retries_fit": 2*original_pass <= remaining,
                  "retry_policy": "At most once for transient failure; each retry rechecks hard budget. Stop with incomplete report if contingency exceeds remaining allowance.",
                  "observed_pilot_linear_token_estimate": 47925/12*499,
                  "pilot_estimate_is_not_reservation": True, "requests_during_preflight": 0}
    write_json(OUT / "reports/calibration-budget-v1.json", budget_plan)
    write_json(RUN / "request-estimates.json", estimates)
    config = {"schema": "native-redocred-calibration-v1", "documents": 499, "source_split": "dev",
              "partition": "effective_calibration_v2_not_official_full_dev_score",
              "backend": "GraphRAG3.3.0_given_entity_native_ontology_custom_prompt",
              "model": "deepseek-ai/DeepSeek-V4.1-Flash", "temperature": 0, "max_output_tokens": 8192,
              "gleanings": 0, "concurrency": 2, "transient_retries": 1, "semantic_retries": 0,
              "stdin_stdout_encoding": "utf-8", "final_acceptance": False,
              "automatic_resume": False, "model_prompt_and_schema_tuning": False,
              "jobs_sha256": digest(json.dumps(jobs, sort_keys=True, ensure_ascii=False)),
              "implementation_and_input_hashes": hashes()}
    dump_jsonl(RUN / "jobs.jsonl", jobs)
    write_json(config_path, config)
    return jobs, config


async def execute():
    jobs, config = prepare()
    budget = open_external_budget(OUT)
    estimates = {row["id"]: row for row in json.loads((RUN / "request-estimates.json").read_text(encoding="utf-8"))}
    directory = RUN / "responses"
    directory.mkdir(parents=True, exist_ok=True)
    done = {json.loads(path.read_text(encoding="utf-8"))["id"] for path in directory.glob("*.json")}
    pending = [row for row in jobs if row["input"]["id"] not in done]
    remaining_first_pass = sum(estimates[row["input"]["id"]]["request_reservation"] for row in pending)
    summary = budget.summary()
    if summary["inflight"] or summary["tokens_charged_or_reserved"] + remaining_first_pass > 20_000_000 or summary["requests"] + len(pending) > 5000:
        raise ValueError("complete_remaining_first_pass_not_reservable")
    queue = asyncio.Queue()
    for job in pending:
        queue.put_nowait(job)
    stopped = False
    start_batch = time.monotonic()
    async def worker(number):
        nonlocal stopped
        process = await asyncio.create_subprocess_exec(str(PYTHON), str(CHILD), "--worker", cwd=REPO, env=ENV,
                     limit=2**21, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            while not stopped and not queue.empty():
                job = queue.get_nowait()
                identifier = job["input"]["id"]
                started = time.monotonic()
                try:
                    process.stdin.write((json.dumps(job, ensure_ascii=False)+"\n").encode("utf-8"))
                    await process.stdin.drain()
                    line = await asyncio.wait_for(process.stdout.readline(), timeout=330)
                    if not line:
                        raise RuntimeError("worker_exited")
                    result = json.loads(line.decode("utf-8"))
                except (asyncio.TimeoutError, RuntimeError, ValueError, BrokenPipeError, ConnectionResetError):
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                    with budget.connect() as conn:
                        conn.execute("UPDATE attempts SET charged=reserved,state='interrupted',error='confirmed_worker_stopped_unknown_usage' WHERE job=? AND state='inflight'", (identifier,))
                    result = {"state": "failed", "error": "worker_unavailable"}
                    stopped = True
                result.update(id=identifier, title=job["input"]["title"], elapsed_seconds=time.monotonic()-started,
                              source_split="dev", partition="effective_calibration_v2", worker=number,
                              input_request_sha256=job["expected_request_sha256"], saved_at=datetime.now(timezone.utc).isoformat())
                write_json(directory / (digest(identifier)+".json"), result)
                if any(row.get("http_status") in (401, 402, 403) for row in result.get("attempts", [])) or result.get("error") == "BudgetStop":
                    stopped = True
                saved = len(list(directory.glob("*.json")))
                write_json(RUN / "progress.json", {"target": 499, "saved": saved, "stopped": stopped,
                           "budget": budget.summary(), "elapsed_seconds": time.monotonic()-start_batch})
                print(json.dumps({"saved": saved, "target": 499, "state": result["state"], "error": result.get("error")}), flush=True)
                queue.task_done()
        finally:
            if process.returncode is None:
                process.stdin.close()
                await process.wait()
    write_json(RUN / "run-state.json", {"state": "running", "target": 499, "runner_pid": os.getpid(), "final_acceptance": False})
    await asyncio.gather(worker(0), worker(1))
    write_json(RUN / "run-state.json", {"state": "stopped" if stopped else "completed", "budget": budget.summary(),
               "saved": len(list(directory.glob("*.json"))), "target": 499, "final_acceptance": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    if parser.parse_args().execute:
        asyncio.run(execute())
    else:
        _, config = prepare()
        print(json.dumps({"documents": config["documents"], "budget_report": str(OUT / "reports/calibration-budget-v1.json")}))
