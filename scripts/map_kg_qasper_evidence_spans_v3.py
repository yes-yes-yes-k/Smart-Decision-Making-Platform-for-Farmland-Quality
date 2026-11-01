"""Locate native evidence as exact source spans, retaining true source gaps."""
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from framework.knowledge_graph.external_benchmark_data import dump_jsonl
from scripts.resolve_kg_external_data_gates import ROOT, read_jsonl
from scripts.prepare_kg_external_benchmarks import write_json


def main():
    report = {"scope": "native_evidence_source_span_mapping", "source_version": "qasper-source-headers-v2",
              "reference_changes": 0, "fuzzy_matching": False, "splits": {}}
    for split in ("train", "dev", "test"):
        docs = {row["id"]: row for row in read_jsonl(ROOT / f"normalized/qasper-v2/{split}.corpus.jsonl")}
        refs = {row["id"]: row for row in read_jsonl(ROOT / f"references/qasper/{split}.references.jsonl")}
        rows, counts = [], Counter()
        for prior in read_jsonl(ROOT / f"adapters/qasper-evidence-v2/{split}.jsonl"):
            blocks = docs[refs[prior["id"]]["document_id"]]["blocks"]
            evidence = prior["native_evidence"]
            spans = []
            for block in blocks:
                quote, kind = evidence, "exact_source_substring"
                if block["kind"] == "caption" and evidence.startswith("FLOAT SELECTED: "):
                    quote = evidence.removeprefix("FLOAT SELECTED: ")
                    kind = "native_float_caption"
                if not quote:
                    continue
                start = block["text"].find(quote)
                while start >= 0:
                    end = start + len(quote)
                    if block["text"][start:end] != quote:
                        raise ValueError("source_span_reconstruction_failed")
                    spans.append({"block_id": block["id"], "start": start, "end": end,
                                  "quote": quote, "kind": kind})
                    start = block["text"].find(quote, end)
            rows.append({**prior, "matching_source_spans": spans,
                         "span_status": "located" if spans else "source_gap"})
            counts["located" if spans else "source_gap"] += 1
        dump_jsonl(ROOT / f"adapters/qasper-evidence-v3/{split}.jsonl", rows)
        report["splits"][split] = dict(counts)
    write_json(ROOT / "reports/qasper-source-spans-v3.json", report)
    print(report)


if __name__ == "__main__":
    main()
