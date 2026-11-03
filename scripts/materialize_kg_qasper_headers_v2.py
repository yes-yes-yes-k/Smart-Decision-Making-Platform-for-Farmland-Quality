"""Preserve source section headings that are valid native QASPER evidence."""
from collections import Counter
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import dump_jsonl, digest
from scripts.prepare_kg_external_benchmarks import write_json
from scripts.resolve_kg_external_data_gates import ROOT, read_jsonl


def main():
    original = {}
    for archive in ("qasper-train-dev-v0.3.tgz", "qasper-test-and-evaluator-v0.3.tgz"):
        with tarfile.open(ROOT / "sources/qasper" / archive, "r:gz") as stream:
            for member in stream.getmembers():
                for split in ("train", "dev", "test"):
                    if member.isfile() and Path(member.name).name == f"qasper-{split}-v0.3.json":
                        original[split] = json.load(stream.extractfile(member))
    report = {"status": "inconclusive", "scope": "source_evidence_mapping_only_not_QA_quality", "splits": {}}
    for split in ("train", "dev", "test"):
        docs = read_jsonl(ROOT / f"normalized/qasper/{split}.corpus.jsonl")
        by_id = {}
        for doc in docs:
            paper = original[split][doc["id"].removeprefix("qasper:")]
            # Headers are source data and are added for all sections, independent
            # of whether any reference happens to select the heading.
            headers = [{"id": f"s{index}:heading", "kind": "section_header", "text": section["section_name"]}
                       for index, section in enumerate(paper["full_text"]) if section.get("section_name")]
            by_section = {block["id"].split(":")[0]: block for block in headers}
            blocks, emitted = [], set()
            for block in doc["blocks"]:
                key = block["id"].split(":")[0]
                if key in by_section and key not in emitted:
                    blocks.append(by_section[key]); emitted.add(key)
                blocks.append(block)
            # Preserve empty sections as well.
            blocks.extend(block for key, block in by_section.items() if key not in emitted)
            doc = {**doc, "blocks": blocks, "input_version": "qasper-source-headers-v2",
                   "text_sha256": digest("\n".join(block["text"] for block in blocks))}
            by_id[doc["id"]] = doc
        dump_jsonl(ROOT / f"normalized/qasper-v2/{split}.corpus.jsonl", list(by_id.values()))
        counts, mappings = Counter(), []
        for ref in read_jsonl(ROOT / f"references/qasper/{split}.references.jsonl"):
            blocks = by_id[ref["document_id"]]["blocks"]
            for ai, answer in enumerate(ref["native_answers"]):
                for ei, text in enumerate(answer["answer"].get("evidence", [])):
                    exact = [block for block in blocks if block["text"] == text]
                    floats = [block for block in blocks if block["kind"] == "caption" and "FLOAT SELECTED: " + block["text"] == text]
                    matched = exact or floats
                    kind = "source_section_heading" if exact and all(block["kind"] == "section_header" for block in exact) else "literal_source" if exact else "native_float_caption" if floats else "unmatched"
                    counts[kind] += 1
                    mappings.append({"id": ref["id"], "annotation_index": ai, "evidence_index": ei,
                                     "native_evidence": text, "mapping_kind": kind,
                                     "matching_blocks": [block["id"] for block in matched]})
        dump_jsonl(ROOT / f"adapters/qasper-evidence-v2/{split}.jsonl", mappings)
        report["splits"][split] = {"documents": len(docs), "evidence": dict(counts)}
    write_json(ROOT / "reports/qasper-source-mapping-v2.json", report)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
