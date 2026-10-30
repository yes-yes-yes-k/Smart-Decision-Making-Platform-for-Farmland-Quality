"""Native QA/evidence scores with source validation and fixed denominators."""
from collections import Counter
import ast
import hashlib
import json
from pathlib import Path
import re

from .external_qasper_scoring import score_qasper, load_official


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def refusal(answer):
    value = re.sub(r"[^a-z0-9 ]", "", str(answer).lower()).strip()
    return value in {"unanswerable", "insufficient information", "not enough information", "unknown", "i dont know", "cannot answer"}


def first_predictions(predictions, expected):
    indexed, seen, invalid, duplicates = {}, set(), [], []
    for index, row in enumerate(predictions):
        if not isinstance(row, dict):
            invalid.append({"index": index, "reason": "invalid_record"}); continue
        identifier = row.get("question_id")
        if not isinstance(identifier, str) or identifier not in expected:
            invalid.append({"index": index, "reason": "wrong_source"}); continue
        if identifier in seen:
            duplicates.append(identifier); continue
        seen.add(identifier)
        if not isinstance(row.get("predicted_answer"), str) or not isinstance(row.get("predicted_evidence", []), list) or not all(isinstance(x, str) for x in row.get("predicted_evidence", [])):
            invalid.append({"index": index, "reason": "invalid_answer_or_evidence"}); continue
        indexed[identifier] = row
    return indexed, invalid, duplicates


def strict_f1(answer, gold):
    def tokens(value):
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", value.lower())).strip().split()
    a, b = tokens(answer), tokens(gold)
    same = sum((Counter(a) & Counter(b)).values())
    return 2*same/(len(a)+len(b)) if same else float(not a and not b)


def source_retrieval(row, blocks):
    """Resolve ranked pointers to real source; invalid ranks consume their slots."""
    resolved, invalid = [], []
    retrieval = row.get("retrieved", [])
    if not isinstance(retrieval, list):
        return [], [{"reason": "invalid_retrieved_list"}]
    for rank, candidate in enumerate(retrieval, 1):
        if not isinstance(candidate, dict):
            invalid.append({"rank": rank, "reason": "invalid_pointer"}); continue
        key = (candidate.get("document_id"), candidate.get("block_id"))
        if not all(isinstance(value, str) for value in key):
            invalid.append({"rank": rank, "reason": "invalid_pointer"}); continue
        source = blocks.get(key)
        if source is None:
            invalid.append({"rank": rank, "reason": "wrong_source_or_text"}); continue
        start, end = candidate.get("start", 0), candidate.get("end", len(source["text"]))
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["text"]):
            invalid.append({"rank": rank, "reason": "invalid_source_span"}); continue
        actual_text = source["text"][start:end]
        if "text" in candidate and candidate["text"] != actual_text:
            invalid.append({"rank": rank, "reason": "wrong_source_or_text"}); continue
        resolved.append({"document_id": key[0], "block_id": key[1], "text": actual_text, "start": start, "end": end, "rank": rank,
                         "kind": source.get("kind", "text")})
    return resolved, invalid


def judge_scores(judgments, expected, prediction_hash):
    if not judgments:
        return {"status": "inconclusive", "reason": "no_independent_semantic_judgments", "judged": 0, "required": len(expected)}
    seen, accepted = set(), []
    for row in judgments:
        request_ids = row.get("request_ids", [])
        if (row.get("question_id") not in expected or row.get("question_id") in seen
            or row.get("prediction_sha256") != prediction_hash
            or row.get("phase") != "independent_qa_semantic_judge"
            or row.get("state") != "completed" or not isinstance(request_ids, list)
            or len(request_ids) != 2 or not all(isinstance(value, str) and value for value in request_ids)
            or len(set(request_ids)) != 2):
            continue
        value = row.get("judgment", {})
        if any(value.get(key) not in {"supported", "unsupported", "insufficient"} for key in ("reference_support", "answer_support", "citation_support")):
            continue
        seen.add(row["question_id"]); accepted.append(value)
    # Unjudged items cannot increase the support rate.
    return {"status": "measured" if len(accepted) == len(expected) else "inconclusive", "judged": len(accepted),
            "required": len(expected), "answer_supported_rate_lower_bound": sum(x["answer_support"] == "supported" for x in accepted)/len(expected) if expected else None,
            "reference_supported_rate_lower_bound": sum(x["reference_support"] == "supported" for x in accepted)/len(expected) if expected else None,
            "citation_supported_rate_lower_bound": sum(x["citation_support"] == "supported" for x in accepted)/len(expected) if expected else None,
            "same_model_judge_bias": True, "expert_certified": False}


def evaluate_qasper(root, partition, predictions, *, judgments=(), prediction_hash="", question_ids=None, document_ids=None):
    split = {"development": "train", "calibration": "dev", "final": "test"}[partition]
    role_rows = json.loads((root / "splits/qasper/effective-roles-v2.json").read_text(encoding="utf-8"))["roles"]
    active = {row["id"] for row in role_rows if row["role"] == partition}
    if document_ids is not None:
        if not set(document_ids) <= active:
            raise ValueError("corpus_selection_outside_partition")
        active &= set(document_ids)
    corpus = {row["id"]: row for row in rows(root / f"normalized/qasper-v2/{split}.corpus.jsonl") if row["id"] in active}
    questions = [row for row in rows(root / f"normalized/qasper/{split}.questions.jsonl") if row["document_id"] in active]
    native_question_count = len(questions)
    if question_ids is not None:
        if not set(question_ids) <= {row["id"] for row in questions}:
            raise ValueError("question_selection_outside_source_corpus")
        questions = [row for row in questions if row["id"] in set(question_ids)]
    references = {row["id"]: row for row in rows(root / f"references/qasper/{split}.references.jsonl") if row["document_id"] in active}
    references = {key: value for key, value in references.items() if key in {q["id"] for q in questions}}
    expected = {row["id"] for row in questions}
    indexed, invalid, duplicates = first_predictions(predictions, expected)
    native_papers = {}
    for identifier, ref in references.items():
        doc = native_papers.setdefault(ref["document_id"], {"qas": []})
        doc["qas"].append({"question_id": identifier, "answers": ref["native_answers"]})
    native_predictions = [{"question_id": identifier, "predicted_answer": row["predicted_answer"],
                           "predicted_evidence": row.get("predicted_evidence", [])} for identifier, row in indexed.items()]
    primary = score_qasper(root, native_papers, native_predictions)
    blocks = {(doc["id"], block["id"]): block for doc in corpus.values() for block in doc["blocks"]}
    from framework.knowledge_graph.external_qa_metadata import metadata_block
    blocks.update({(doc["id"], "source_metadata"): metadata_block(doc, "qasper") for doc in corpus.values()})
    mapping = {}
    for row in rows(root / f"adapters/qasper-evidence-v3/{split}.jsonl"):
        if row["id"] in expected:
            mapping.setdefault(row["id"], []).append(row)
    results = []
    for question in questions:
        identifier = question["id"]
        row = indexed.get(identifier, {})
        retrieved, errors = source_retrieval(row, blocks)
        # Reference may contain alternative annotations, so score coverage for
        # each annotation and use the native-style best alternative.
        annotations = {}
        unresolved = 0
        for evidence in mapping.get(identifier, []):
            group = annotations.setdefault(evidence["annotation_index"], [])
            hit = any(span["block_id"] == item["block_id"] and item["document_id"] == question["document_id"]
                      and item["start"] <= span["start"] and item["end"] >= span["end"]
                      for span in evidence["matching_source_spans"] for item in retrieved if item["rank"] <= 5)
            group.append(hit)
            unresolved += not evidence["matching_source_spans"]
        coverage = [sum(values)/len(values) for values in annotations.values() if values]
        answers = references[identifier]["native_answers"]
        statuses = {bool(answer["answer"]["unanswerable"]) for answer in answers}
        category = "unanswerable" if statuses == {True} else "answerable" if statuses == {False} else "mixed_reference"
        answer = row.get("predicted_answer", "")
        valid_answer = identifier in indexed and bool(answer.strip())
        source_quotes = [block["text"] for doc in corpus.values() if doc["id"] == question["document_id"] for block in doc["blocks"]]
        predicted_evidence = row.get("predicted_evidence", [])
        literal_citations = sum(any(quote and (quote in text or (quote.startswith("FLOAT SELECTED: ") and quote.removeprefix("FLOAT SELECTED: ") in text)) for text in source_quotes) for quote in predicted_evidence)
        results.append({"question_id": identifier, "document_group": question["document_id"], "category": category,
                        "completed": valid_answer, "refused": valid_answer and refusal(answer),
                        "evidence_recall_at_5": max(coverage) if coverage else None,
                        "unresolved_reference_evidence": unresolved, "invalid_retrieval": errors,
                        "citation_count": len(predicted_evidence), "literal_source_citations": literal_citations})
    return {"status": "inconclusive", "dataset": "qasper", "partition": partition, "official": primary["official"],
            "completion": primary, "invalid_records": invalid, "duplicate_predictions": duplicates,
            "items": results, "supplementary": aggregate(results),
            "semantic_support": judge_scores(judgments, expected, prediction_hash), "reference_changes": 0,
            "source_corpus_questions": native_question_count, "frozen_question_subset": question_ids is not None}


def aggregate(items):
    answerable = [row for row in items if row["category"] == "answerable"]
    unanswerable = [row for row in items if row["category"] == "unanswerable"]
    recalls = [row["evidence_recall_at_5"] for row in items if row["evidence_recall_at_5"] is not None]
    citations = sum(row["citation_count"] for row in items)
    return {"questions": len(items), "answerable_questions": len(answerable), "unanswerable_questions": len(unanswerable),
            "mixed_reference_questions": sum(row["category"] == "mixed_reference" for row in items),
            "evidence_recall_at_5": sum(recalls)/len(recalls) if recalls else None, "evidence_recall_denominator": len(recalls),
            "answerable_completion_rate": sum(row["completed"] and not row["refused"] for row in answerable)/len(answerable) if answerable else None,
            "correct_refusal_rate": sum(row["completed"] and row["refused"] for row in unanswerable)/len(unanswerable) if unanswerable else None,
            "literal_citation_rate_not_semantic_support": sum(row["literal_source_citations"] for row in items)/citations if citations else None,
            "unresolved_reference_evidence": sum(row["unresolved_reference_evidence"] for row in items),
            "invalid_retrieval_records": sum(len(row["invalid_retrieval"]) for row in items), "model_exclusions": 0}


def qa_intervals(items, *, resamples=1000, seed=20261029):
    import numpy as np
    groups = {}
    for item in items:
        groups.setdefault(item["document_group"], []).append(item)
    values = list(groups.values())
    if not values:
        return {"status": "inconclusive", "groups": 0}
    generator = np.random.default_rng(seed)
    measures = {key: [] for key in ("evidence_recall_at_5", "answerable_completion_rate", "correct_refusal_rate")}
    for _ in range(resamples):
        sample = [row for index in generator.integers(0, len(values), size=len(values)) for row in values[index]]
        result = aggregate(sample)
        for key in measures:
            if result[key] is not None:
                measures[key].append(result[key])
    return {"groups": len(values), "resamples": resamples, "seed": seed,
            "unit": "document_or_connected_support_group", "confidence": .95,
            "intervals": {key: np.quantile(value, [.025, .975]).tolist() if value else None for key, value in measures.items()}}


def publisher_multi(root, filename, names):
    source = root / "sources/multihop_rag/reviewed" / filename
    metadata = json.loads(source.with_name(source.name+".source.json").read_text(encoding="utf-8"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("multihop_publisher_scorer_changed")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if len(functions) != len(names):
        raise ValueError("multihop_scorer_interface_changed")
    namespace = {"re": re}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


def evaluate_multihop(root, partition, predictions, *, judgments=(), prediction_hash="", question_ids=None, document_ids=None):
    questions = rows(root / f"normalized/multihop-v2/{partition}.questions.jsonl")
    native_question_count = len(questions)
    if question_ids is not None:
        if not set(question_ids) <= {row["id"] for row in questions}:
            raise ValueError("question_selection_outside_partition")
        questions = [row for row in questions if row["id"] in set(question_ids)]
    references = {row["id"]: row for row in rows(root / f"references/multihop-v2/{partition}.references.jsonl")}
    references = {key: value for key, value in references.items() if key in {q["id"] for q in questions}}
    docs = rows(root / f"normalized/multihop-v2/{partition}.corpus.jsonl")
    if document_ids is not None:
        if not set(document_ids) <= {row["id"] for row in docs}:
            raise ValueError("corpus_selection_outside_partition")
        docs = [row for row in docs if row["id"] in set(document_ids)]
    blocks = {(row["id"], "body"): {"text": row["native_article"]["body"]} for row in docs}
    from framework.knowledge_graph.external_qa_metadata import metadata_block
    blocks.update({(doc["id"], "source_metadata"): metadata_block(doc, "multihop_rag") for doc in docs})
    urls = {row["id"]: row["native_article"]["url"] for row in docs}
    expected = {row["id"] for row in questions}
    indexed, invalid, duplicates = first_predictions(predictions, expected)
    qa = publisher_multi(root, "qa_evaluate.py", {"has_intersection", "extract_answer", "calculate_metrics"})
    retrieval = publisher_multi(root, "retrieval_evaluate.py", {"calculate_metrics"})
    answers, gold_answers, retrieved_lists, gold_lists, results, exacts, token_scores = [], [], [], [], [], [], []
    for question in questions:
        identifier = question["id"]
        reference = references[identifier]
        row = indexed.get(identifier, {})
        retrieved, errors = source_retrieval(row, blocks)
        answer = qa["extract_answer"](row.get("predicted_answer", ""))
        gold = reference["answer"]
        answers.append(answer); gold_answers.append(gold)
        exacts.append(answer.strip().casefold() == gold.strip().casefold())
        token_scores.append(strict_f1(answer, gold))
        support_urls = {item["url"] for item in reference["native_evidence_list"]}
        hit_urls = {urls[item["document_id"]] for item in retrieved if item["rank"] <= 5} & support_urls
        if reference["question_type"] != "null_query":
            # Fill invalid/missing ranked slots with empty text so bad pointers
            # cannot promote later results into a better rank.
            ranks = {item["rank"]: item["text"] for item in retrieved}
            ranked = row.get("retrieved", [])
            retrieved_lists.append([ranks.get(rank, "") for rank in range(1, min(11, len(ranked) if isinstance(ranked, list) else 0)+1)])
            gold_lists.append([item["fact"] for item in reference["native_evidence_list"]])
        evidence = row.get("predicted_evidence", [])
        text_sources = [item["text"] for item in retrieved]
        literal = sum(any(quote and quote in text for text in text_sources) for quote in evidence)
        results.append({"question_id": identifier, "document_group": "multihop-support:"+hashlib.sha256("|".join(sorted(support_urls)).encode()).hexdigest(),
                        "question_type": reference["question_type"],
                        "category": "unanswerable" if reference["question_type"] == "null_query" else "answerable",
                        "completed": identifier in indexed and bool(answer.strip()), "refused": identifier in indexed and refusal(answer),
                        "evidence_recall_at_5": len(hit_urls)/len(support_urls) if support_urls else None,
                        "unresolved_reference_evidence": 0, "invalid_retrieval": errors,
                        "citation_count": len(evidence), "literal_source_citations": literal})
    primary = qa["calculate_metrics"](answers, gold_answers)
    # Questions sharing any supporting article form one uncertainty unit.
    parent = list(range(len(results)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    source_owner = {}
    for index, question in enumerate(questions):
        for evidence in references[question["id"]]["native_evidence_list"]:
            url = evidence["url"]
            if url in source_owner:
                parent[find(index)] = find(source_owner[url])
            else:
                source_owner[url] = index
    for index, item in enumerate(results):
        item["document_group"] = "multihop-connected:" + str(find(index))
    safe_retrieval = [(r, g) for r, g in zip(retrieved_lists, gold_lists) if g]
    original_retrieval = retrieval["calculate_metrics"]([row[0] for row in safe_retrieval], [row[1] for row in safe_retrieval]) if safe_retrieval else None
    return {"status": "inconclusive", "dataset": "multihop_rag", "partition": partition,
            "protocol": "custom_source_grouped_v2_not_official_full_dataset_score", "questions": len(expected),
            "official_formula_on_fixed_partition": {"any_token_overlap": primary[3], "retrieval": original_retrieval,
               "retrieval_questions": len(safe_retrieval), "null_queries_excluded_from_native_retrieval_only": sum(ref["question_type"] == "null_query" for ref in references.values()),
               "quirks": ["Answer metric accepts any whitespace token overlap; it is not exact accuracy.", "Publisher retrieval MAP examines 11 ranks and uses its own nonstandard formula; preserved unchanged."]},
            "supplementary_exact_match": sum(exacts)/len(exacts) if exacts else 0.,
            "supplementary_token_f1": sum(token_scores)/len(token_scores) if token_scores else 0.,
            "invalid_records": invalid, "duplicate_predictions": duplicates, "items": results, "supplementary": aggregate(results),
            "semantic_support": judge_scores(judgments, expected, prediction_hash), "reference_changes": 0,
            "source_corpus_questions": native_question_count, "frozen_question_subset": question_ids is not None}
