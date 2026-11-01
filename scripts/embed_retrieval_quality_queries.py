"""Execute only the nine explicitly authorized R1 query embeddings, then stop."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework.knowledge_graph.retrieval_budget import RetrievalEmbeddingBudget

OUT = ROOT/"artifacts/knowledge_platform/retrieval-quality-r1/r1-r2-20261030-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amended", action="store_true", help="Use the separately authorized v2 manifest, preserving all prior attempts")
    args = parser.parse_args()
    manifest_path = OUT/("embedding-request-manifest-v2.json" if args.amended else "embedding-request-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    auth = json.loads((OUT/("budget-authorization-v2.json" if args.amended else "budget-authorization.json")).read_text(encoding="utf-8"))
    if auth.get("state") != "authorized" or auth.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest() or auth.get("caps") != manifest["proposed_caps"]:
        raise ValueError("matching_explicit_R1_authorization_required")
    from dotenv import load_dotenv
    load_dotenv(ROOT/".env")
    from framework.config import Config
    key = os.getenv("SILICONFLOW_KEY") or os.getenv("SILICONFLOW_API_KEY") or Config.SILICONFLOW_API_KEY
    base = (os.getenv("SILICONFLOW_API_BASE") or os.getenv("SILICONFLOW_BASE_URL") or Config.SILICONFLOW_BASE_URL).rstrip("/")
    url = urlsplit(base)
    if not key or url.scheme != "https" or url.hostname != "api.siliconflow.cn" or url.path != "/v1" or url.username or url.password or url.query or url.fragment:
        raise ValueError("authorized_SiliconFlow_endpoint_and_credentials_required")
    budget = RetrievalEmbeddingBudget(OUT/"execution/budget.sqlite3", manifest, amendment=auth.get("ledger_amendment"))
    if budget.summary()["inflight"]:
        raise ValueError("unresolved_inflight_attempts_require_explicit_recovery_not_automatic")
    directory = OUT/"embeddings"
    directory.mkdir(exist_ok=True)
    stop = threading.Event()

    def execute(item):
        if stop.is_set():
            return {"case_id": item["case_id"], "state": "not_attempted_infrastructure_failure"}
        output = directory/(item["case_id"]+".json")
        if output.exists():
            saved = json.loads(output.read_text(encoding="utf-8"))
            if saved["payload_sha256"] != item["payload_sha256"]:
                raise ValueError("cached_query_payload_changed")
            return {"case_id": item["case_id"], "state": "reused_exact_R1_query_vector"}
        permitted = budget.remaining_attempts(item["case_id"])
        for attempt in range(permitted):
            if stop.is_set():
                return {"case_id": item["case_id"], "state": "not_attempted_infrastructure_failure"}
            reservation = budget.reserve_query(item["case_id"], item["payload"])
            retry = False
            try:
                response = requests.post(base+"/embeddings", headers={"Authorization": "Bearer "+key}, json=item["payload"], timeout=(5, 30))
                if response.status_code == 429 or response.status_code >= 500:
                    retry = True
                response.raise_for_status()
                data = response.json()
                values = data.get("data")
                if not isinstance(values, list) or len(values) != 1 or values[0].get("index", 0) != 0:
                    raise ValueError("embedding_response_alignment_invalid")
                vector = values[0].get("embedding")
                if not isinstance(vector, list) or len(vector) != 1024 or any(type(v) not in (float, int) or not math.isfinite(v) for v in vector):
                    raise ValueError("embedding_response_dimension_or_values_invalid")
                usage = data.get("usage") or {}
                total = usage.get("total_tokens")
                budget.finish(reservation, SimpleNamespace(total_tokens=total))
                saved = {"case_id": item["case_id"], "payload_sha256": item["payload_sha256"],
                         "model": item["payload"]["model"], "origin": "fresh_authorized_R1_query_embedding",
                         "created_at_utc": datetime.now(timezone.utc).isoformat(), "usage": usage,
                         "attempt_id": reservation, "embedding": vector}
                output.write_text(json.dumps(saved, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
                return {"case_id": item["case_id"], "state": "completed", "attempt_id": reservation}
            except Exception as exc:
                if isinstance(exc, requests.exceptions.ProxyError):
                    stop.set()
                    retry = False
                elif isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                    retry = True
                status = getattr(getattr(exc, "response", None), "status_code", None)
                error = "HTTP_"+str(status) if status is not None else type(exc).__name__
                budget.finish(reservation, error=error)
                if not retry or attempt+1 == permitted:
                    return {"case_id": item["case_id"], "state": "failed", "error_type": error}
                time.sleep(1)
        return {"case_id": item["case_id"], "state": "not_attempted_case_attempt_limit"}

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute, item) for item in manifest["requests"]]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                result = {"state": "stopped", "error_type": type(exc).__name__}
            results.append(result)
            print(json.dumps(result), flush=True)
    report = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "results": results,
              "budget": budget.summary(), "automatic_continuation": False,
              "state": "completed" if len(list(directory.glob("*.json"))) == 9 else "incomplete"}
    report_path = OUT/("embedding-run-v2.json" if args.amended else "embedding-run.json")
    if report_path.exists():
        raise ValueError("embedding_report_exists_choose_new_execution_version")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if report["state"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
