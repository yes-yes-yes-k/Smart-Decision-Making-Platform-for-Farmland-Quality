"""Record auditable source/split resolutions without changing official data."""
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import digest, dump_jsonl
from prepare_kg_external_benchmarks import write_json

ROOT = Path("artifacts/knowledge_platform/external-benchmark-v1")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def caption_map():
    totals = {}
    for split in ("train", "dev", "test"):
        corpus = {row["id"]: row for row in read_jsonl(ROOT / f"normalized/qasper/{split}.corpus.jsonl")}
        mappings, counts = [], Counter()
        for reference in read_jsonl(ROOT / f"references/qasper/{split}.references.jsonl"):
            blocks = corpus[reference["document_id"]]["blocks"]
            for ann_index, answer in enumerate(reference["native_answers"]):
                for evidence_index, text in enumerate(answer["answer"].get("evidence", [])):
                    literal = [block["id"] for block in blocks if block["text"] == text]
                    native_float = text.startswith("FLOAT SELECTED: ")
                    caption = [block["id"] for block in blocks
                               if block["kind"] == "caption" and "FLOAT SELECTED: " + block["text"] == text] if native_float else []
                    matches = literal or caption
                    kind = "literal" if literal else "native_float_caption_marker" if caption else "unmatched"
                    counts[kind] += 1
                    mappings.append({"id": reference["id"], "annotation_index": ann_index,
                                     "evidence_index": evidence_index, "native_evidence": text,
                                     "matching_blocks": matches, "mapping_kind": kind})
        dump_jsonl(ROOT / f"adapters/qasper-evidence-v1/{split}.jsonl", mappings)
        totals[split] = dict(counts)
    return {"state": "supplemental_mapping_complete_unmatched_retained", "counts": totals,
            "rule": "Only exact source equality or exact caption with native FLOAT SELECTED prefix; no fuzzy repair; official evidence strings unchanged."}


def effective_redocred_roles():
    report = json.loads((ROOT / "reports/materialization.json").read_text(encoding="utf-8"))
    conflicts = report["datasets"]["redocred"]["isolation"]["cross_split_conflicts"]
    heldout = {row["right"] for row in conflicts if row["right_split"] in {"dev", "test"}}
    roles = []
    for split, role in [("train", "development"), ("dev", "calibration"), ("test", "final")]:
        for row in read_jsonl(ROOT / f"normalized/redocred/{split}.inputs.jsonl"):
            roles.append({"id": row["id"], "native_split": split,
                          "role": "inactive_heldout_alias" if split == "train" and row["id"] in heldout else role})
    development = [row for row in roles if row["role"] == "development"]
    pilot = sorted(development, key=lambda row: digest("external-v1-pilot-20261029:" + row["id"]))[:12]
    write_json(ROOT / "splits/redocred/effective-roles-v1.json", {
        "status": "provisional_pending_near_duplicate_audit", "roles": roles,
        "resolution": "Keep official dev/test complete; duplicated train occurrence inactive for local development and model input; original official files unchanged.",
        "inactive_train_alias_ids": sorted(heldout), "pilot_ids": [row["id"] for row in pilot]})
    return {"inactive_train_aliases": len(heldout), "effective_roles": dict(Counter(row["role"] for row in roles)),
            "near_duplicate_audit": "pending", "model_exposure_to_conflicting_document": "no_calls_in_new_scope"}


def multihop_partition():
    folder = ROOT / "sources/multihop_rag/huggingface"
    questions = json.loads((folder / "MultiHopRAG.json").read_text(encoding="utf-8"))
    corpus = json.loads((folder / "corpus.json").read_text(encoding="utf-8"))
    components = json.loads((ROOT / "splits/multihop_rag/support-components.json").read_text(encoding="utf-8"))["components"]
    development = next(group for group in components if 0 in group)
    unseen = sorted([group for group in components if group is not development],
                    key=lambda group: digest("multihop-v1-20261029:" + str(min(group))))
    # Allocate complete support components, never split the large exposed group.
    target = max(1, round(sum(map(len, unseen)) * 0.2))
    assigned, calibration_count = {}, 0
    for index in development:
        assigned[index] = "development"
    for group in unseen:
        role = "calibration" if calibration_count < target else "final"
        if role == "calibration":
            calibration_count += len(group)
        for index in group:
            assigned[index] = role
    urls = {}
    for index, qa in enumerate(questions):
        for evidence in qa["evidence_list"]:
            url = evidence["url"]
            if url in urls and urls[url] != assigned[index]:
                raise ValueError("cross_partition_support_url")
            urls[url] = assigned[index]
    by_url = {}
    for article in corpus:
        if article["url"] in by_url:
            raise ValueError("duplicate_corpus_url_requires_review")
        by_url[article["url"]] = article
    missing = sorted(set(urls) - set(by_url))
    if missing:
        raise ValueError(f"missing_support_documents:{len(missing)}")
    stats = {}
    for role in ("development", "calibration", "final"):
        qs, refs, docs = [], [], []
        for index, qa in enumerate(questions):
            if assigned[index] != role:
                continue
            identifier = "multihop:" + str(index) + ":" + digest(qa["query"])
            qs.append({"id": identifier, "native_index": index, "question": qa["query"], "partition": role})
            refs.append({"id": identifier, "answer": qa["answer"], "question_type": qa["question_type"],
                         "native_evidence_list": qa["evidence_list"]})
        for article in corpus:
            # Unreferenced documents remain development distractors, not dropped.
            if urls.get(article["url"], "development") == role:
                docs.append({"id": "multihopdoc:" + digest(article["url"]), "partition": role,
                             "native_article": article, "text_sha256": digest(article["body"])})
        dump_jsonl(ROOT / f"normalized/multihop-v1/{role}.questions.jsonl", qs)
        dump_jsonl(ROOT / f"normalized/multihop-v1/{role}.corpus.jsonl", docs)
        dump_jsonl(ROOT / f"references/multihop-v1/{role}.references.jsonl", refs)
        stats[role] = {"questions": len(qs), "documents": len(docs),
                       "question_types": dict(Counter(row["question_type"] for row in refs))}
    result = {"status": "provisional_custom_partition_not_official_score", "seed": "multihop-v1-20261029",
              "splits": stats, "support_document_cross_conflicts": 0,
              "near_duplicate_audit": "pending", "locally_exposed_component_role": "development",
              "full_official_dataset_questions": len(questions),
              "limitations": ["Largest connected component assigned development after question 0 inspection.",
                              "Final subset is not representative of entire official corpus; report original and custom protocols separately."]}
    write_json(ROOT / "splits/multihop_rag/custom-partition-v1.json", result)
    return result


def main():
    results = {}
    for key, fn in [("qasper_evidence", caption_map), ("redocred_roles", effective_redocred_roles), ("multihop_partition", multihop_partition)]:
        try:
            results[key] = fn()
        except Exception as exc:
            results[key] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}"}
    write_json(ROOT / "reports/data-resolutions-v1.json", results)
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
