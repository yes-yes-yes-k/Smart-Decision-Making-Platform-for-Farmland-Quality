"""Separate supporting-document hits from exact supporting-fact coverage."""
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from framework.knowledge_graph.external_qa_evaluation import rows, source_retrieval, first_predictions
from framework.knowledge_graph.external_qa_metadata import metadata_block
from scripts.prepare_kg_external_benchmarks import write_json

ROOT = REPO / "artifacts/knowledge_platform/external-benchmark-v1"


def fact_coverage(evidence, retrieved, docs):
    """Literal source-span diagnostic, not semantic entailment or native score."""
    hits, gaps = 0, 0
    for fact in evidence:
        candidates = [doc for doc in docs if doc["native_article"]["url"] == fact["url"]]
        spans = []
        for doc in candidates:
            text, start = doc["native_article"]["body"], 0
            while fact["fact"] and (start := text.find(fact["fact"], start)) >= 0:
                spans.append((doc["id"], start, start+len(fact["fact"])))
                start += 1
        gaps += not bool(spans)
        supported = False
        for document_id, start, end in spans:
            covered = start
            for chunk in sorted((row for row in retrieved if row["rank"] <= 5 and row["document_id"] == document_id and row["block_id"] == "body"), key=lambda row: row["start"]):
                if chunk["start"] <= covered < chunk["end"]:
                    covered = chunk["end"]
            supported |= covered >= end
        hits += supported
    return {"facts": len(evidence), "hits": hits, "source_gaps": gaps,
            "recall": hits/len(evidence) if evidence else None}


def main():
    from framework.knowledge_graph.external_benchmark_freeze import require_mutable
    require_mutable(ROOT, ROOT/"reports/QA-evidence-granularity-v2.json")
    docs = rows(ROOT/"normalized/multihop-v2/calibration.corpus.jsonl")
    blocks = {(doc["id"], "body"): {"text": doc["native_article"]["body"]} for doc in docs}
    blocks.update({(doc["id"], "source_metadata"): metadata_block(doc, "multihop_rag") for doc in docs})
    references = {row["id"]: row for row in rows(ROOT/"references/multihop-v2/calibration.references.jsonl")}
    report = {"status": "inconclusive", "metric": "exact_body_fact_span_recall_at_5_diagnostic_not_native_or_semantic",
              "metadata_only_hits_do_not_count_as_body_fact_hits": True, "missing_predictions_count_as_zero": True, "runs": {}}
    for name in ("qa-pilot-v1", "qa-pilot-v2-metadata"):
        run = ROOT/"runs"/name
        expected = set(json.loads((run/"selection.json").read_text(encoding="utf-8"))["datasets"]["multihop_rag"]["question_ids"])
        arms = {}
        for arm in ("vector", "graphrag"):
            path = run/"multihop_rag"/arm/"predictions.jsonl"
            if not path.exists():
                arms[arm] = {"state": "not_completed"}; continue
            predicted, _, _ = first_predictions(rows(path), expected)
            items = []
            for identifier in sorted(expected):
                retrieved, invalid = source_retrieval(predicted.get(identifier, {}), blocks)
                items.append({"question_id": identifier, **fact_coverage(references[identifier]["native_evidence_list"], retrieved, docs),
                              "invalid_retrieval": invalid})
            supported = [item for item in items if item["facts"]]
            arms[arm] = {"questions": len(expected), "questions_with_native_facts": len(supported), "items": items,
                         "macro_exact_fact_recall_at_5": sum(item["recall"] for item in supported)/len(supported) if supported else None,
                         "reference_source_gaps": sum(item["source_gaps"] for item in items)}
        report["runs"][name] = arms
    # Verify literal source authenticity against the actual retrieved blocks,
    # including metadata. This is separate from QASPER's question-paper scope
    # and from semantic support for the answer.
    report["v2_retrieved_citation_authenticity"] = {}
    run = ROOT/"runs/qa-pilot-v2-metadata"
    for dataset in ("qasper", "multihop_rag"):
        input_docs = rows(run/dataset/"inputs/documents.jsonl")
        source_blocks = {(doc["id"], block["id"]): block for doc in input_docs for block in doc["blocks"]}
        report["v2_retrieved_citation_authenticity"][dataset] = {}
        for arm in ("vector", "graphrag"):
            count, authentic = 0, 0
            for prediction in rows(run/dataset/arm/"predictions.jsonl"):
                retrieved, _ = source_retrieval(prediction, source_blocks)
                for quote in prediction["predicted_evidence"]:
                    count += 1
                    authentic += any(quote and (quote in source["text"] or
                        (source["kind"] == "caption" and quote.startswith("FLOAT SELECTED: ") and quote.removeprefix("FLOAT SELECTED: ") in source["text"])) for source in retrieved)
            report["v2_retrieved_citation_authenticity"][dataset][arm] = {"citations": count, "authentic": authentic,
                 "rate": authentic/count if count else None, "semantic_support": "reported_separately_by_independent_judge"}
    write_json(ROOT/"reports/QA-evidence-granularity-v2.json", report)
    print(json.dumps({name: {arm: value.get("macro_exact_fact_recall_at_5") for arm, value in arms.items()} for name, arms in report["runs"].items()}))


if __name__ == "__main__":
    main()
