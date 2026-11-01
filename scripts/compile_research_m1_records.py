"""Validate real model selections against frozen source spans; no repairs."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_research_m1_pilot import OUT, write
from framework.knowledge_graph.contracts import SourceChunk
from framework.knowledge_graph.research_records import compile_record


def main():
    selected = json.loads((OUT/"selection.json").read_text(encoding="utf-8"))["documents"]
    summaries, records = [], []
    for item in selected:
        identifier = item["id"]
        document = json.loads((OUT/"corpus"/(str(identifier)+".json")).read_text(encoding="utf-8"))
        response = json.loads((OUT/"responses"/(str(identifier)+".json")).read_text(encoding="utf-8"))
        chunks = {row["chunk_index"]: SourceChunk(**row) for row in document["chunks"]}
        valid, rejected = [], []
        if response["state"] == "completed":
            for index, candidate in enumerate(response["selection"]["records"]):
                try:
                    valid.append(compile_record(identifier, document["content_sha256"], candidate, chunks, provenance={
                        "origin": "model_source_selection", "configuration_sha256": response["request_sha256"],
                        "model_request_id": response["request_id"], "model": response["returned_model"]}))
                except (ValueError, KeyError, TypeError) as exc:
                    rejected.append({"selection_index": index, "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
        write(OUT/"records"/(str(identifier)+".json"), valid)
        records.extend(valid)
        summaries.append({"document_id": identifier, "request_state": response["state"], "valid_records": len(valid), "invalid_selections": rejected,
                          "empty_output": response["state"] == "completed" and not response["selection"]["records"]})
    report = {"selected_documents": len(selected), "saved_documents": len(summaries), "source_grounded_records": len(records),
              "review_status": "pending", "published_claims_added": 0, "semantic_truth_certified": False,
              "partial_task_coverage": True, "model_calls_during_compile": 0, "documents": summaries}
    write(OUT/"record-compilation-v1.json", report)
    print(json.dumps({key: report[key] for key in ("selected_documents", "source_grounded_records", "published_claims_added")}))


if __name__ == "__main__":
    main()
