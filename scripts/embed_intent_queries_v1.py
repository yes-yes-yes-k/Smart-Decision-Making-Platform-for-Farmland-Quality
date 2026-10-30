"""One-shot embedding of sub-question intents under a hard 17-attempt budget.

Each request is a single HTTP attempt: no internal retry, no silent fallback.
The ledger records every attempt so the budget cannot be exceeded by a retry
loop hiding inside the embedding service.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

R1 = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1"
CASES = R1 / "r0-20261030/query-cases.json"
MAX_ATTEMPTS = 17

# Five condition-shaped variants, derived only from the user questions.
CONDITION_VARIANTS = {
    "U1": "长期施用与单次施用生物炭在酸性土壤上对有机碳的影响持续多久",
    "U2": "酸性镉污染稻田施用石灰并设定目标pH后，稻米镉与水稻产量的变化",
    "U3": "长期施用粪肥在不同土壤类型和作物下的土壤物理性质变化",
    "U4": "紫云英、稻草和石灰联合施用对土壤有效镉与稻米镉的影响",
    "U5": "珠江三角洲不同地质区域土壤镉的空间分布与分区管控建议",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    requests = []
    for case in cases["cases"]:
        for subquestion in case.get("subquestions", []):
            requests.append({"id": "SQ." + subquestion["id"], "case_id": case["id"],
                             "kind": "subquestion", "text": subquestion["question"]})
        if case["id"] in CONDITION_VARIANTS:
            requests.append({"id": "CV." + case["id"], "case_id": case["id"],
                             "kind": "condition_variant", "text": CONDITION_VARIANTS[case["id"]]})
    return requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="r14-intent-embeddings-20261031-v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = R1 / args.run_id
    requests_plan = plan()
    if len(requests_plan) > MAX_ATTEMPTS:
        raise SystemExit(f"plan exceeds budget: {len(requests_plan)} > {MAX_ATTEMPTS}")
    if out.exists() and any((out / "embeddings").glob("*.json")):
        raise SystemExit("run id already has embeddings")

    load_dotenv(ROOT / ".env")
    from framework.config import Config
    api_key = os.environ.get("SILICONFLOW_API_KEY") or getattr(Config, "SILICONFLOW_API_KEY", "")
    base = os.environ.get("SILICONFLOW_BASE_URL") or getattr(Config, "SILICONFLOW_BASE_URL",
                                                            "https://api.siliconflow.cn/v1")
    model = getattr(Config, "SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")
    if not api_key:
        raise SystemExit("SILICONFLOW_API_KEY missing")

    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "model": model,
                "budget": {"max_attempts": MAX_ATTEMPTS, "attempts_used": 0, "retries_allowed": False},
                "purpose": "sub-question and condition-variant query vectors for R1.4 recall probe",
                "original_document_text_sent": False,
                "requests": [{**item, "payload": {"model": model, "input": [item["text"]]},
                              "payload_sha256": sha256_text(json.dumps({"model": model, "input": [item["text"]]},
                                                                       ensure_ascii=False, sort_keys=True)),
                              "estimated_tokens": max(1, round(len(item["text"]) / 1.6))}
                             for item in requests_plan]}
    (out / "embeddings").mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    if args.dry_run:
        print(json.dumps({"requests": len(requests_plan),
                          "estimated_tokens": sum(item["estimated_tokens"] for item in manifest["requests"])}))
        return 0

    attempts, saved = 0, 0
    for item in manifest["requests"]:
        if attempts >= MAX_ATTEMPTS:
            break
        attempts += 1
        started = time.perf_counter()
        record = {"id": item["id"], "attempt": attempts, "at_utc": datetime.now(timezone.utc).isoformat(),
                  "payload_sha256": item["payload_sha256"], "status": None, "http_status": None,
                  "seconds": None, "error": None}
        try:
            response = requests.post(f"{base}/embeddings",
                                     headers={"Authorization": f"Bearer {api_key}",
                                              "Content-Type": "application/json"},
                                     json=item["payload"], timeout=30)
            record["http_status"] = response.status_code
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
            record.update(status="succeeded", dimensions=len(vector))
            (out / "embeddings" / (item["id"] + ".json")).write_text(json.dumps(
                {"case_id": item["case_id"], "kind": item["kind"], "text": item["text"],
                 "origin": "fresh_authorized_R1.4_subquestion_embedding", "model": model,
                 "payload_sha256": item["payload_sha256"], "attempt": attempts,
                 "embedding": vector}, ensure_ascii=False) + "\n", encoding="utf-8")
            saved += 1
        except Exception as error:  # single attempt only: request failures are final
            record.update(status="failed", error=str(error)[:200])
        record["seconds"] = round(time.perf_counter() - started, 3)
        with (out / "ledger.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({"attempt": attempts, "id": item["id"], "status": record["status"],
                          "seconds": record["seconds"]}), flush=True)
        time.sleep(0.2)

    ledger = {"attempts_used": attempts, "saved": saved, "failed": attempts - saved,
              "max_attempts": MAX_ATTEMPTS}
    (out / "budget-ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    print(json.dumps(ledger, ensure_ascii=False))
    return 0 if saved == attempts else 1


if __name__ == "__main__":
    raise SystemExit(main())
