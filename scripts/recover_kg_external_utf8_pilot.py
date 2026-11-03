"""Versioned recovery of only jobs proven not sent due to local GBK decoding."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_kg_external_relation_pilot import prepare, OUT, RUN as PREVIOUS, PYTHON, CHILD
from framework.knowledge_graph.external_benchmark_budget import open_external_budget
from framework.knowledge_graph.external_benchmark_data import digest
from scripts.prepare_kg_external_benchmarks import write_json

RUN = OUT / "runs/redocred-pilot-v2-utf8"


async def main():
    state = json.loads((PREVIOUS / "run-state.json").read_text(encoding="utf-8"))
    if state["state"] != "completed":
        raise ValueError("prior_run_not_terminal")
    jobs, config, _ = prepare()
    pending, reused = [], []
    budget = open_external_budget(OUT)
    with budget.connect() as conn:
        sent_jobs = {row[0] for row in conn.execute("SELECT job FROM attempts")}
    for job in jobs:
        identifier = job["input"]["id"]
        source = PREVIOUS / "responses" / (digest(identifier) + ".json")
        row = json.loads(source.read_text(encoding="utf-8"))
        if row["state"] == "completed":
            # A successful first-run job is reusable only if its actual GBK
            # decoding left the complete intended JSON input unchanged.
            encoded = json.dumps(job, ensure_ascii=False).encode("utf-8")
            decoded = json.loads(encoded.decode("gbk", errors="surrogateescape"))
            if decoded != job:
                raise ValueError("successful_prior_input_corrupted_do_not_reuse")
            reused.append({"id": identifier, "path": str(source.relative_to(OUT)),
                           "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                           "input_roundtrip": "unchanged"})
        elif row.get("error") == "UnicodeEncodeError" and not row.get("attempts") and identifier not in sent_jobs:
            pending.append(job)
        else:
            raise ValueError("not_an_unsent_local_encoding_failure")
    if len(reused) != 8 or len(pending) != 4:
        raise ValueError("unexpected_recovery_membership")
    config = {**config, "recovery": "only_4_pre_request_encoding_failures",
              "stdin_stdout_encoding": "utf-8", "prior_run": str(PREVIOUS.relative_to(OUT)),
              "reused_responses": reused, "recovery_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    config_path = RUN / "run-config.json"
    if config_path.exists() and json.loads(config_path.read_text(encoding="utf-8")) != config:
        raise ValueError("recovery_configuration_changed")
    write_json(config_path, config)
    write_json(RUN / "reused-responses.json", reused)
    estimate = 2 * sum(len(json.dumps(job, ensure_ascii=False).encode("utf-8")) + 8192 + 16384 for job in pending)
    summary = budget.summary()
    if summary["inflight"] or summary["tokens_charged_or_reserved"] + estimate > 20_000_000 or summary["requests"] + 8 > 5000:
        raise ValueError("recovery_budget_or_inflight_gate")
    write_json(RUN / "preflight.json", {"pending_unsent_documents": 4, "reused_unchanged_responses": 8,
               "conservative_reservation": estimate, "budget": summary})
    sem = asyncio.Semaphore(2)
    stopped = False
    async def one(job):
        nonlocal stopped
        async with sem:
            identifier = job["input"]["id"]
            target = RUN / "responses" / (digest(identifier) + ".json")
            if target.exists() or stopped:
                return
            start = time.monotonic()
            process = await asyncio.create_subprocess_exec(str(PYTHON), str(CHILD), cwd=OUT.parents[2],
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                       stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(json.dumps(job, ensure_ascii=False).encode("utf-8")), timeout=330)
                result = json.loads(stdout.decode("utf-8"))
            except asyncio.TimeoutError:
                process.kill(); await process.wait()
                with budget.connect() as conn:
                    conn.execute("UPDATE attempts SET charged=reserved,state='interrupted',error='runtime_timeout_unknown_usage' WHERE job=? AND state='inflight'", (identifier,))
                result = {"state": "failed", "error": "runtime_timeout"}
            except (ValueError, UnicodeError):
                result = {"state": "failed", "error": "runtime_no_valid_result"}
            result.update(id=identifier, title=job["input"]["title"], elapsed_seconds=time.monotonic()-start,
                          job_sha256=config["job_hashes"][identifier], local_encoding="utf-8")
            if any(row.get("http_status") in (401, 402, 403) for row in result.get("attempts", [])):
                stopped = True
            write_json(target, result)
            saved = len(list((RUN / "responses").glob("*.json")))
            write_json(RUN / "progress.json", {"target": 12, "saved": saved+8, "reused": 8, "budget": budget.summary()})
            print(json.dumps({"saved_including_reused": saved+8, "state": result["state"], "error": result.get("error")}), flush=True)
    await asyncio.gather(*(one(job) for job in pending))
    write_json(RUN / "run-state.json", {"state": "stopped" if stopped else "completed", "budget": budget.summary()})


if __name__ == "__main__":
    asyncio.run(main())
