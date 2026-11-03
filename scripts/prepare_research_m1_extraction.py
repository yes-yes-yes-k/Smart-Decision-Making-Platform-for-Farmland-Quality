"""Prepare exactly ten requests and independent budget, without API calls."""
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT, write
from framework.knowledge_graph.research_extraction import options, identity, select_chunks


def main():
    selection = json.loads((OUT/"selection.json").read_text(encoding="utf-8"))
    jobs, reserve = [], 0
    for item in selection["documents"]:
        document = json.loads((OUT/"corpus"/(str(item["id"])+".json")).read_text(encoding="utf-8"))
        request = options(document)
        amount = len(json.dumps(request, ensure_ascii=False).encode())+request["max_tokens"]+1024
        reserve += amount
        job = {"document_id": item["id"], "request_sha256": identity(request), "options": request,
               "reservation": amount, "source_selection": [{"chunk_index": row["chunk_index"], "page": row["page"],
                   "text_sha256": hashlib.sha256(row["content"].encode()).hexdigest()} for row in select_chunks(document)]}
        write(OUT/"requests"/(str(item["id"])+".json"), job)
        jobs.append({key: job[key] for key in ("document_id", "request_sha256", "reservation", "source_selection")})
    files = [REPO/"framework/knowledge_graph/research_records.py", REPO/"framework/knowledge_graph/research_extraction.py", Path(__file__).resolve()]
    report = {"scope": "M1_ten_paper_source_selected_research", "status": "prepared_budget_not_authorized", "model_calls": 0,
              "model": "deepseek-ai/DeepSeek-V4.1-Flash", "destination": "https://api.siliconflow.cn/v1",
              "selected_papers": len(jobs), "first_attempt_requests": len(jobs), "first_attempt_reserved_tokens": reserve,
              "at_most_one_transient_retry_bound": 2*reserve, "proposed_hard_caps": {"tokens": 500000, "attempts": 20, "concurrency": 2},
              "fits_proposed_retry_bound": 2*reserve <= 500000, "semantic_or_format_retries": 0,
              "external_benchmark_budget_used": False, "existing_budget_reset": False,
              "source_scope": "eight_chunks_per_document_partial_task_coverage_not_whole_paper_completion",
              "jobs": jobs, "implementation_hashes": {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    write(OUT/"extraction-preflight-v1.json", report)
    print(json.dumps({key: report[key] for key in ("status", "selected_papers", "first_attempt_reserved_tokens", "at_most_one_transient_retry_bound", "fits_proposed_retry_bound")}))


if __name__ == "__main__":
    main()
