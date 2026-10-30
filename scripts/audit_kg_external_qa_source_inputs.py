"""Rebuild frozen QA source inputs from pinned native corpora, without APIs."""
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts.prepare_kg_external_qa_pilot_v2 import RUN, OUT, read
from framework.knowledge_graph.external_qa_metadata import metadata_block, make_index_inputs
from scripts.prepare_kg_external_benchmarks import write_json


def main():
    original = json.loads((OUT/"reports/task-input-coverage-v2.json").read_text(encoding="utf-8"))
    report = {**original, "scope": "faithful_native_metadata_and_body_v3", "datasets": dict(original["datasets"]),
              "frozen_run_manifest_sha256": hashlib.sha256((OUT/"reports/qa-pilot-result-manifest-v2.json").read_bytes()).hexdigest()}
    for dataset, source in (("qasper", "normalized/qasper-v2/train.corpus.jsonl"),
                            ("multihop_rag", "normalized/multihop-v2/calibration.corpus.jsonl")):
        native = {doc["id"]: doc for doc in read(OUT/source)}
        documents = read(RUN/dataset/"inputs/documents.jsonl")
        for document in documents:
            if set(document) != {"id", "title", "blocks"}:
                raise ValueError("candidate_document_unexpected_fields")
            source_doc = native[document["id"]]
            expected_body = source_doc["blocks"] if dataset == "qasper" else [{"id": "body", "kind": "text", "text": source_doc["native_article"]["body"]}]
            if document["blocks"] != [*expected_body, metadata_block(source_doc, dataset)]:
                raise ValueError("candidate_source_not_exact_native_body_plus_metadata")
        chunks, units = make_index_inputs(documents)
        if chunks != read(RUN/dataset/"inputs/chunks.jsonl") or units != read(RUN/dataset/"inputs/units.jsonl"):
            raise ValueError("candidate_chunks_or_units_not_rebuildable")
        old_units = read(OUT/"runs/qa-pilot-v1"/dataset/"inputs/units.jsonl")
        rebuilt = {unit["id"]: unit for unit in units}
        if any(rebuilt.get(unit["id"]) != unit for unit in old_units):
            raise ValueError("old_body_unit_changed")
        if any(set(row) != {"id", "question"} for row in read(RUN/dataset/"inputs/questions.jsonl")):
            raise ValueError("reference_fields_in_candidate_questions")
        report["datasets"][dataset] = {**original["datasets"][dataset], "source_blocks": sum(len(doc["blocks"]) for doc in documents),
              "source_metadata_blocks": len(documents), "source_chunks": len(chunks), "graph_units": len(units),
              "all_source_blocks_exact_native": True, "source_spans_rebuilt": True,
              "reference_fields_in_candidate_inputs": False, "old_body_units_preserved": len(old_units),
              "metadata_fields": ["title"] if dataset == "qasper" else ["title", "author", "source", "published_at", "category", "url"]}
    write_json(OUT/"reports/task-input-coverage-v3.json", report)
    print(json.dumps({"source_audit": "passed", "model_calls": 0, "datasets": {key: report["datasets"][key]["source_blocks"] for key in ("qasper", "multihop_rag")}}))


if __name__ == "__main__":
    main()
