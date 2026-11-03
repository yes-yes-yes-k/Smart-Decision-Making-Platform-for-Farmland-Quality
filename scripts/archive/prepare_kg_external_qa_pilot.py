"""Freeze source-only QA inputs and deterministic nonfinal pilot membership."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from framework.knowledge_graph.external_qa_retrieval import make_index_inputs, sha
from framework.knowledge_graph.external_benchmark_data import dump_jsonl
from scripts.prepare_kg_external_benchmarks import write_json

OUT = REPO / "artifacts/knowledge_platform/external-benchmark-v1"
RUN = OUT / "runs/qa-pilot-v1"


def read(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def prepare():
    paths = [OUT/"splits/qasper/pilot.json", OUT/"splits/qasper/effective-roles-v2.json",
             OUT/"normalized/qasper-v2/train.corpus.jsonl", OUT/"normalized/qasper/train.questions.jsonl",
             OUT/"normalized/multihop-v2/calibration.corpus.jsonl", OUT/"normalized/multihop-v2/calibration.questions.jsonl",
             OUT/"references/multihop-v2/calibration.references.jsonl",
             REPO/"framework/knowledge_graph/external_qa_retrieval.py", Path(__file__).resolve(),
             REPO/"scripts/run_kg_external_qa_pilot.py"]
    hashes = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    config_path = RUN / "input-manifest.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if config["source_and_implementation_hashes"] != hashes:
            raise ValueError("QA_pilot_frozen_dependencies_changed_use_new_version")
        for name, expected in config["input_files"].items():
            if hashlib.sha256((RUN/name).read_bytes()).hexdigest() != expected:
                raise ValueError("QA_pilot_frozen_input_changed")
        return config
    seed = "external-QA-pilot-v1-20261030"
    q_ids = set(json.loads((OUT/"splits/qasper/pilot.json").read_text(encoding="utf-8"))["document_ids"])
    roles = json.loads((OUT/"splits/qasper/effective-roles-v2.json").read_text(encoding="utf-8"))["roles"]
    if not q_ids <= {row["id"] for row in roles if row["role"] == "development"}:
        raise ValueError("QASPER_pilot_has_inactive_or_non_development_source")
    q_docs = [row for row in read(OUT/"normalized/qasper-v2/train.corpus.jsonl") if row["id"] in q_ids]
    q_questions = [row for row in read(OUT/"normalized/qasper/train.questions.jsonl") if row["document_id"] in q_ids]
    m_docs = [{"id": row["id"], "title": row["native_article"]["title"],
               "blocks": [{"id": "body", "kind": "text", "text": row["native_article"]["body"]}]}
              for row in read(OUT/"normalized/multihop-v2/calibration.corpus.jsonl")]
    # Only public task-type metadata is used for stratification. Reference
    # answers and supporting facts never appear in the frozen candidate inputs.
    groups = defaultdict(list)
    for row in read(OUT/"references/multihop-v2/calibration.references.jsonl"):
        groups[row["question_type"]].append(row["id"])
    m_ids = set()
    for kind, identifiers in sorted(groups.items()):
        if len(identifiers) < 4:
            raise ValueError("pilot_question_type_support_less_than_four")
        m_ids.update(sorted(identifiers, key=lambda value: sha(seed+":"+value))[:4])
    m_questions = [row for row in read(OUT/"normalized/multihop-v2/calibration.questions.jsonl") if row["id"] in m_ids]
    if len(q_docs) != 5 or len(q_questions) != 10 or len(m_docs) != 57 or len(m_questions) != 16:
        raise ValueError("frozen_QA_pilot_size_changed")
    selection = {"schema": "external-QA-pilot-selection-v1", "frozen_before_predictions": True, "seed": seed,
                 "selection_uses_candidate_performance": False, "final_acceptance": False, "datasets": {}}
    summary, files = {}, []
    for name, docs, questions, partition in [("qasper", q_docs, q_questions, "development"), ("multihop_rag", m_docs, m_questions, "calibration")]:
        documents = [{"id": doc["id"], "title": doc["title"], "blocks": doc["blocks"]} for doc in docs]
        inputs = [{"id": row["id"], "question": row["question"]} for row in questions]
        chunks, units = make_index_inputs(documents, limit=4000)
        folder = RUN / name / "inputs"
        for filename, data in [("documents.jsonl", documents), ("questions.jsonl", inputs), ("chunks.jsonl", chunks), ("units.jsonl", units)]:
            path = folder / filename; dump_jsonl(path, data); files.append(path)
        selection["datasets"][name] = {"partition": partition, "document_ids": sorted(doc["id"] for doc in docs),
                                      "question_ids": sorted(row["id"] for row in questions)}
        summary[name] = {"documents": len(documents), "questions": len(inputs), "source_chunks": len(chunks), "graph_units": len(units),
                         "source_utf8_bytes": sum(len(chunk["text"].encode()) for chunk in chunks),
                         "input_modality": "source_text_headings_and_captions_no_image_pixels",
                         "references_present_in_candidate_inputs": False}
    write_json(RUN/"selection.json", selection); files.append(RUN/"selection.json")
    config = {"schema": "source-only-QA-pilot-inputs-v1", "datasets": summary,
              "source_and_implementation_hashes": hashes,
              "input_files": {str(path.relative_to(RUN)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
              "not_full_dataset_scores": True, "automatic_expansion": False}
    write_json(config_path, config)
    return config


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False))
