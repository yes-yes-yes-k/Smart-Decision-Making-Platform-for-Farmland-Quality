"""Native relation keys; fixed denominators and explicit invalid predictions."""
from collections import Counter


def relation_key(row):
    return row["title"], row["r"], row["h_idx"], row["t_idx"]


def score_relations(gold_documents, predictions, *, completed_titles=()):
    titles = {doc["title"]: doc for doc in gold_documents}
    if len(titles) != len(gold_documents):
        raise ValueError("ambiguous_native_document_title")
    gold = {(doc["title"], rel["r"], rel["h"], rel["t"])
            for doc in gold_documents for rel in doc["labels"]}
    predicted, invalid, duplicates = set(), [], 0
    for index, row in enumerate(predictions):
        try:
            key = relation_key(row)
            if not isinstance(row["r"], str) or not row["r"]:
                raise ValueError("invalid_relation_type")
            if type(row["h_idx"]) is not int or type(row["t_idx"]) is not int:
                raise ValueError("invalid_endpoint_type")
            if row["title"] not in titles:
                raise ValueError("wrong_source")
            clusters = titles[row["title"]]["vertexSet"]
            if not (0 <= row["h_idx"] < len(clusters) and 0 <= row["t_idx"] < len(clusters)):
                raise ValueError("endpoint_out_of_range")
            if key in predicted:
                duplicates += 1
            predicted.add(key)
        except (KeyError, TypeError, ValueError) as exc:
            invalid.append({"index": index, "error": str(exc)})
    tp = len(gold & predicted)
    # Invalid records remain false positives; identical valid duplicates are
    # deduplicated in accordance with native DocRED relation scoring.
    denominator = len(predicted) + len(invalid)
    precision = tp / denominator if denominator else 0.
    recall = tp / len(gold) if gold else 0.
    completed = set(completed_titles) & titles.keys()
    by_document = []
    for title in titles:
        expected = {key for key in gold if key[0] == title}
        actual = {key for key in predicted if key[0] == title}
        correct = len(expected & actual)
        p = correct / len(actual) if actual else 0.
        r = correct / len(expected) if expected else 0.
        by_document.append({"title": title, "tp": correct, "fp": len(actual - expected),
                            "fn": len(expected - actual), "f1": 2*p*r/(p+r) if p+r else 0.})
    return {"precision": precision, "recall": recall,
            "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.,
            "tp": tp, "fp": denominator - tp, "fn": len(gold - predicted), "expected": len(gold),
            "invalid_predictions": invalid, "duplicate_predictions": duplicates,
            "documents": len(titles), "completed_documents": len(completed),
            "completion_rate": len(completed)/len(titles) if titles else 0., "exclusion_rate": 0.,
            "document_macro_f1": sum(row["f1"] for row in by_document)/len(by_document) if by_document else 0.,
            "by_document": by_document,
            "evidence_support": "not_scored_native_evidence_not_revalidated"}
