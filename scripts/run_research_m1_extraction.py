"""Execute only the authorized, frozen ten-paper M1 extraction batch."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT
from framework.knowledge_graph.acceptance_budget import Budget
from framework.knowledge_graph.research_extraction import identity


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temporary.replace(path)


def main():
    if (OUT/"completion-manifest-v1.json").exists():
        raise ValueError("M1_batch_frozen_no_automatic_model_resumption")
    from dotenv import load_dotenv
    load_dotenv(REPO/".env")
    auth = OUT/"budget-authorization.json"
    policy = json.loads(auth.read_text(encoding="utf-8"))
    if policy.get("scope") != "research-M1-ten-paper-v1" or policy.get("caps") != {"tokens": 500000, "attempts": 20, "concurrency": 2}:
        raise ValueError("M1_explicit_budget_authorization_required")
    preflight = json.loads((OUT/"extraction-preflight-v1.json").read_text(encoding="utf-8"))
    for path, expected in preflight["implementation_hashes"].items():
        if hashlib.sha256((REPO/path).read_bytes()).hexdigest() != expected:
            raise ValueError("frozen_M1_extraction_implementation_changed")
    budget = Budget(OUT/"execution/budget.sqlite3", total=500000, stability=500000, requests=20)
    fingerprint = hashlib.sha256(auth.read_bytes()).hexdigest()
    with budget.connect() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS M1_authorization (sha256 TEXT PRIMARY KEY)")
        bound = connection.execute("SELECT sha256 FROM M1_authorization").fetchall()
        if bound and bound != [(fingerprint,)]:
            raise ValueError("M1_budget_authorization_changed")
        if not bound:
            if budget.summary()["requests"]:
                raise ValueError("M1_refusing_to_reset_existing_unbound_ledger")
            connection.execute("INSERT INTO M1_authorization VALUES (?)", (fingerprint,))
    if budget.summary()["inflight"]:
        raise ValueError("M1_existing_attempts_need_confirmed_runner_recovery")
    from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError, APIStatusError
    import httpx
    stop = threading.Event()
    client = OpenAI(api_key=os.environ.get("KG_EXTRACTION_API_KEY") or os.environ["SILICONFLOW_API_KEY"],
        base_url="https://api.siliconflow.cn/v1", max_retries=0, timeout=120,
        http_client=httpx.Client(trust_env=False, follow_redirects=False))
    def one(item):
        document_id = item["document_id"]
        target = OUT/"responses"/(str(document_id)+".json")
        frozen = json.loads((OUT/"requests"/(str(document_id)+".json")).read_text(encoding="utf-8"))
        if identity(frozen["options"]) != item["request_sha256"]:
            raise ValueError("M1_request_hash_changed")
        if target.exists():
            old = json.loads(target.read_text(encoding="utf-8"))
            if old["request_sha256"] != item["request_sha256"]:
                raise ValueError("M1_cached_request_changed")
            return
        row = {"document_id": document_id, "request_sha256": item["request_sha256"], "state": "failed", "attempts": []}
        for retry in range(2):
            if stop.is_set():
                row["error"] = "batch_stopped_before_request"; break
            try:
                attempt = budget.reserve("research_M1", str(document_id), frozen["options"])
            except Exception:
                stop.set(); row["error"] = "budget_hard_stop"; break
            row["attempts"].append(attempt)
            try:
                response = client.chat.completions.create(**frozen["options"])
                budget.finish(attempt, response.usage)
                row.update(request_id=response.id, returned_model=response.model, usage=response.usage.model_dump() if response.usage else None,
                           finish_reason=response.choices[0].finish_reason, content=response.choices[0].message.content)
                if row["finish_reason"] != "stop":
                    raise ValueError("truncated_or_incomplete_response")
                value = json.loads(row["content"])
                if set(value) != {"records"} or not isinstance(value["records"], list) or len(value["records"]) > 8:
                    raise ValueError("invalid_research_output")
                row.update(state="completed", selection=value); break
            except Exception as exc:
                budget.finish(attempt, error=type(exc).__name__)
                row["error"] = type(exc).__name__
                if isinstance(exc, APIStatusError) and exc.status_code in (401, 402, 403):
                    stop.set()
                if retry == 0 and isinstance(exc, (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)) and not stop.is_set():
                    time.sleep(1); continue
                break
        save(target, row)
        print(json.dumps({"document_id": document_id, "state": row["state"], "attempts": len(row["attempts"])}), flush=True)
    save(OUT/"execution/run-state.json", {"state": "running", "runner_pid": os.getpid(), "scope": policy["scope"]})
    completed = False
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(one, preflight["jobs"]))
        completed = not stop.is_set()
    finally:
        client.close()
        save(OUT/"execution/run-state.json", {"state": "completed" if completed else "stopped", "budget": budget.summary(),
             "finished_at_utc": datetime.now(timezone.utc).isoformat(), "global_external_ledger_unchanged_by_this_runner": True})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
