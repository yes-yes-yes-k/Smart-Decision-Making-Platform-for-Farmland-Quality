"""Call the pinned official QASPER evaluator and retain full denominators."""
import hashlib
import importlib.util
import json
from pathlib import Path


def load_official(root: Path):
    source = root / "sources/qasper/scripts/evaluator.py"
    snapshot = json.loads((root / "sources/qasper/snapshot.json").read_text(encoding="utf-8"))
    expected = next(row["sha256"] for row in snapshot["files"]
                    if row["path"].replace("\\", "/").endswith("scripts/evaluator.py"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise ValueError("qasper_official_scorer_hash_changed")
    spec = importlib.util.spec_from_file_location("pinned_official_qasper", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score_qasper(root: Path, native_papers: dict, predictions: list[dict]):
    official = load_official(root)
    references = official.get_answers_and_evidence(native_papers, text_evidence_only=False)
    parsed, invalid, duplicates, seen = {}, [], [], set()
    for index, row in enumerate(predictions):
        if not isinstance(row, dict):
            invalid.append({"index": index, "reason": "invalid_prediction"}); continue
        identifier = row.get("question_id")
        if not isinstance(identifier, str) or identifier not in references:
            invalid.append({"index": index, "reason": "wrong_source"}); continue
        if identifier in seen:
            # Repeated answers cannot select the better candidate after scoring.
            duplicates.append(identifier)
            continue
        seen.add(identifier)
        answer, evidence = row.get("predicted_answer"), row.get("predicted_evidence")
        if not isinstance(answer, str) or not isinstance(evidence, list) or not all(isinstance(text, str) for text in evidence):
            invalid.append({"index": index, "reason": "invalid_prediction"}); continue
        parsed[identifier] = {"answer": answer, "evidence": evidence}
    official_result = official.evaluate(references, parsed)
    # Supplementary per-type completion includes missing predictions; the native
    # evaluator's Answer F1 by type omits missing answers from its type means.
    by_type = {}
    for identifier, options in references.items():
        for answer_type in {row["type"] for row in options}:
            counts = by_type.setdefault(answer_type, {"reference_questions": 0, "completed": 0})
            counts["reference_questions"] += 1
            counts["completed"] += identifier in parsed
    return {"official": official_result, "questions": len(references), "completed": len(parsed),
            "completion_rate": len(parsed)/len(references) if references else 0.,
            "invalid_records": invalid, "duplicates_first_record_wins": duplicates,
            "completion_by_native_answer_type": by_type, "text_evidence_only": False,
            "exclusion_rate": 0., "status": "inconclusive", "final_acceptance": False}
