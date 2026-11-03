"""Apply conservative source-overlap groups, preserving official source files."""
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.resolve_kg_external_data_gates import ROOT, read_jsonl
from scripts.prepare_kg_external_benchmarks import write_json
from framework.knowledge_graph.external_benchmark_data import dump_jsonl


def main():
    screen = json.loads((ROOT / "reports/isolation-screen-v1.json").read_text(encoding="utf-8"))["datasets"]
    decisions = []
    reasons = {"redocred": "Different villages share most of the same history template; conservatively isolate overlapping content despite distinct subjects.",
               "qasper": "Related graph-clustering studies share extensive source content; conservatively treat as one source family.",
               "multihop_rag": "Black Friday/Cyber Monday article updates reuse substantial product-list content; isolate as one content family."}
    for dataset, result in screen.items():
        for pair in result["cross_partition_candidates"]:
            decisions.append({"dataset": dataset, **pair, "decision": "same_isolation_group_conservative_content_overlap",
                              "reviewer": "Codex_AI_source_read", "reason": reasons[dataset],
                              "expert_certified": False, "reference_labels_used": False})
    original = json.loads((ROOT / "splits/redocred/effective-roles-v1.json").read_text(encoding="utf-8"))
    roles = original["roles"]
    redocred_pairs = screen["redocred"]["cross_partition_candidates"]
    for pair in redocred_pairs:
        for row in roles:
            if row["id"] == pair["left"] and row["role"] == "calibration":
                row.update(role="inactive_related_to_final", isolation_group_anchor=pair["right"])
    write_json(ROOT / "splits/redocred/effective-roles-v2.json", {
        "status": "source_grouped_custom_calibration_official_final_unchanged", "roles": roles,
        "pilot_ids": original["pilot_ids"], "active_counts": dict(Counter(row["role"] for row in roles)),
        "official_dev_documents": 500, "effective_calibration_documents": 499,
        "official_dev_score": "all500_only_as_native_diagnostic_not_isolated_calibration_score"})
    qasper_roles = []
    related_train = {pair["left"] for pair in screen["qasper"]["cross_partition_candidates"]}
    for split, role in [("train", "development"), ("dev", "calibration"), ("test", "final")]:
        for row in read_jsonl(ROOT / f"normalized/qasper-v2/{split}.corpus.jsonl"):
            qasper_roles.append({"id": row["id"], "native_split": split,
                                 "role": "inactive_related_to_calibration" if row["id"] in related_train else role})
    write_json(ROOT / "splits/qasper/effective-roles-v2.json", {"roles": qasper_roles,
               "active_counts": dict(Counter(row["role"] for row in qasper_roles)), "official_files_changed": False})
    # Union every question in the old support component with its overlapping
    # exposed development article; never split individual questions from it.
    components = json.loads((ROOT / "splits/multihop_rag/support-components.json").read_text(encoding="utf-8"))["components"]
    source_corpus = {}
    question_rows, reference_rows = {}, {}
    for role in ("development", "calibration", "final"):
        for row in read_jsonl(ROOT / f"normalized/multihop-v1/{role}.corpus.jsonl"):
            source_corpus[row["id"]] = row
        for row in read_jsonl(ROOT / f"normalized/multihop-v1/{role}.questions.jsonl"):
            question_rows[row["native_index"]] = row
        for row in read_jsonl(ROOT / f"references/multihop-v1/{role}.references.jsonl"):
            reference_rows[row["id"]] = row
    urls = set()
    for pair in screen["multihop_rag"]["cross_partition_candidates"]:
        urls.update(source_corpus[pair[side]]["native_article"]["url"] for side in ("left", "right"))
    overlapping = {index for index, row in question_rows.items()
                   if any(e["url"] in urls for e in reference_rows[row["id"]]["native_evidence_list"])}
    moved = set()
    for group in components:
        if set(group) & overlapping:
            for index in group:
                if question_rows[index]["partition"] != "development":
                    moved.add(index)
                question_rows[index]["partition"] = "development"
    doc_roles = {}
    for row in question_rows.values():
        for evidence in reference_rows[row["id"]]["native_evidence_list"]:
            url = evidence["url"]
            if url in doc_roles and doc_roles[url] != row["partition"]:
                raise ValueError("support_group_not_closed")
            doc_roles[url] = row["partition"]
    summary = {}
    for role in ("development", "calibration", "final"):
        qs = sorted([row for row in question_rows.values() if row["partition"] == role], key=lambda row: row["native_index"])
        refs = [reference_rows[row["id"]] for row in qs]
        docs = [{**row, "partition": role} for row in source_corpus.values()
                if doc_roles.get(row["native_article"]["url"], "development") == role]
        dump_jsonl(ROOT / f"normalized/multihop-v2/{role}.questions.jsonl", qs)
        dump_jsonl(ROOT / f"normalized/multihop-v2/{role}.corpus.jsonl", docs)
        dump_jsonl(ROOT / f"references/multihop-v2/{role}.references.jsonl", refs)
        summary[role] = {"questions": len(qs), "documents": len(docs),
                         "question_types": dict(Counter(row["question_type"] for row in refs))}
    write_json(ROOT / "splits/multihop_rag/custom-partition-v2.json", {
        "status": "custom_protocol_not_official_full_dataset_score", "splits": summary,
        "questions_moved_to_development_by_source_group": sorted(moved), "questions_retained": len(question_rows),
        "documents_retained": len(source_corpus), "sampling_by_model_performance": False,
        "limitations": "Largest exposed support group dominates development; custom final is not representative of the full native dataset."})
    write_json(ROOT / "reports/source-group-decisions-v2.json", {"decisions": decisions, "reference_changes": 0,
               "official_files_changed": False, "reviewer": "Codex_AI_not_expert_certification"})
    print(json.dumps({"source_groups_reviewed": len(decisions), "multihop": summary}))


if __name__ == "__main__":
    main()
