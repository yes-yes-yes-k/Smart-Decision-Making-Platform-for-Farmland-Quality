"""Build native inputs/references and audit actual datasets, without model calls."""
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import (
    digest, dump_jsonl, qasper_paper, redocred_document, split_audit,
)
from prepare_kg_external_benchmarks import write_json

ROOT = Path("artifacts/knowledge_platform/external-benchmark-v1")


def materialize_redocred():
    folder = ROOT / "sources/redocred/data"
    if not all((folder / f"{split}_revised.json").exists() for split in ("train", "dev", "test")):
        return {"state": "pending_download"}
    counts, all_inputs, relation_types = {}, {}, Counter()
    for split in ("train", "dev", "test"):
        docs = json.loads((folder / f"{split}_revised.json").read_text(encoding="utf-8"))
        inputs, references = [], []
        types = Counter()
        for doc in docs:
            item, ref = redocred_document(doc, split)
            inputs.append(item)
            references.append(ref)
            types.update(rel["r"] for rel in ref["relations"])
        all_inputs[split] = inputs
        relation_types.update(types)
        dump_jsonl(ROOT / f"normalized/redocred/{split}.inputs.jsonl", inputs)
        dump_jsonl(ROOT / f"references/redocred/{split}.references.jsonl", references)
        counts[split] = {"documents": len(inputs), "relations": sum(types.values()),
                         "relation_types": dict(sorted(types.items())),
                         "entity_clusters": sum(len(row["given_entity_clusters"]) for row in inputs)}
    pilot = sorted(all_inputs["train"], key=lambda row: digest("external-v1-pilot-20261029:" + row["id"]))[:12]
    write_json(ROOT / "splits/redocred/pilot.json", {"source_split": "train", "seed": "external-v1-pilot-20261029",
               "selection": "sha256_rank_first_12_no_label_filter", "ids": [row["id"] for row in pilot]})
    return {"state": "materialized_not_evaluated", "native_task": "given_entity_relation",
            "splits": counts, "pilot_documents": len(pilot), "isolation": split_audit(all_inputs),
            "official_scorer_parity": "pending", "final_thresholds": "unconfirmed"}


def materialize_qasper():
    folder = ROOT / "sources/qasper"
    archives = [folder / name for name in ("qasper-train-dev-v0.3.tgz", "qasper-test-and-evaluator-v0.3.tgz")]
    if not all(path.exists() for path in archives):
        return {"state": "pending_download"}
    data = {}
    for archive in archives:
        with tarfile.open(archive, "r:gz") as stream:
            for member in stream.getmembers():
                if not member.isfile():
                    continue
                for split in ("train", "dev", "test"):
                    if Path(member.name).name == f"qasper-{split}-v0.3.json":
                        if split in data:
                            raise ValueError("duplicate_qasper_archive_split")
                        data[split] = json.load(stream.extractfile(member))
    if set(data) != {"train", "dev", "test"}:
        raise ValueError("missing_qasper_native_split")
    counts, all_corpus = {}, {}
    for split, papers in data.items():
        corpus, questions, references = [], [], []
        unmatched, total_evidence, impossible_answers, caption_blocks = 0, 0, 0, 0
        for paper_id, paper in papers.items():
            doc, qs, refs = qasper_paper(paper_id, paper, split)
            corpus.append(doc)
            questions.extend(qs)
            references.extend(refs)
            caption_blocks += sum(block["kind"] == "caption" for block in doc["blocks"])
            for ref in refs:
                for answer in ref["native_answers"]:
                    impossible_answers += bool(answer["answer"].get("unanswerable"))
                for annotation in ref["evidence_matches"]:
                    for evidence in annotation:
                        total_evidence += 1
                        unmatched += not evidence["matching_blocks"]
        dump_jsonl(ROOT / f"normalized/qasper/{split}.corpus.jsonl", corpus)
        dump_jsonl(ROOT / f"normalized/qasper/{split}.questions.jsonl", questions)
        dump_jsonl(ROOT / f"references/qasper/{split}.references.jsonl", references)
        all_corpus[split] = corpus
        counts[split] = {"documents": len(corpus), "questions": len(questions),
                         "unanswerable_answer_annotations": impossible_answers, "caption_blocks": caption_blocks,
                         "evidence_strings": total_evidence, "unmatched_exact_evidence": unmatched}
    pilot = sorted(all_corpus["train"], key=lambda row: digest("external-v1-pilot-20261029:" + row["id"]))[:5]
    write_json(ROOT / "splits/qasper/pilot.json", {"source_split": "train", "selection": "sha256_rank_first_5_papers_all_questions",
               "seed": "external-v1-pilot-20261029", "document_ids": [row["id"] for row in pilot]})
    return {"state": "materialized_not_evaluated", "splits": counts, "isolation": split_audit(all_corpus),
            "evidence_mapping": "exact_only_unmatched_retained_not_excluded", "official_scorer_parity": "pending"}


def inspect_multihop():
    folder = ROOT / "sources/multihop_rag/huggingface"
    if not all((folder / name).exists() for name in ("MultiHopRAG.json", "corpus.json")):
        return {"state": "pending_download"}
    questions = json.loads((folder / "MultiHopRAG.json").read_text(encoding="utf-8"))
    corpus = json.loads((folder / "corpus.json").read_text(encoding="utf-8"))
    # Audit connected support groups before any custom split; do not force apart
    # questions sharing supporting source documents to achieve sample counts.
    parent = list(range(len(questions)))
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    seen, missing = {}, []
    for index, qa in enumerate(questions):
        for evidence in qa.get("evidence_list", []):
            url = evidence.get("url")
            if not url:
                missing.append(index)
                continue
            if url in seen:
                parent[find(index)] = find(seen[url])
            else:
                seen[url] = index
    groups = {}
    for index in range(len(questions)):
        groups.setdefault(find(index), []).append(index)
    write_json(ROOT / "splits/multihop_rag/support-components.json", {
        "status": "audit_only_not_partitioned", "components": list(groups.values()),
        "known_local_content_exposure": [0], "missing_support_url_question_indices": sorted(set(missing)),
        "note": "Question 0 inspected before partitioning; its entire component must remain development."})
    return {"state": "source_audited_partition_pending", "questions": len(questions),
            "corpus_records": len(corpus), "corpus_record_fields": list(corpus[0]) if isinstance(corpus, list) and corpus else [],
            "question_types": dict(Counter(row["question_type"] for row in questions)),
            "support_components": len(groups), "largest_component_questions": max(map(len, groups.values()), default=0),
            "official_split": "none_declared_in_data_card", "missing_support_url": len(set(missing))}


def main():
    report = {"status": "inconclusive", "model_calls": 0, "datasets": {}}
    for name, fn in [("redocred", materialize_redocred), ("qasper", materialize_qasper), ("multihop_rag", inspect_multihop)]:
        try:
            report["datasets"][name] = fn()
        except Exception as exc:
            report["datasets"][name] = {"state": "blocked_materialization", "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps({"dataset": name, "state": report["datasets"][name]["state"]}), flush=True)
    write_json(ROOT / "reports/materialization.json", report)


if __name__ == "__main__":
    main()
