"""Screen actual external inputs for document and lexical split conflicts."""
from collections import Counter
from pathlib import Path
import json
import re
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_kg_external_benchmarks import write_json
from resolve_kg_external_data_gates import ROOT, read_jsonl


def documents(effective_version=1):
    version = f"v{effective_version}"
    roles = json.loads((ROOT / f"splits/redocred/effective-roles-{version}.json").read_text(encoding="utf-8"))["roles"]
    mapping = {(row["native_split"], row["id"]): row["role"] for row in roles}
    result = {"redocred": [], "qasper": [], "multihop_rag": []}
    for split in ("train", "dev", "test"):
        for row in read_jsonl(ROOT / f"normalized/redocred/{split}.inputs.jsonl"):
            role = mapping[(split, row["id"])]
            if not role.startswith("inactive_"):
                result["redocred"].append({"id": row["id"], "partition": role, "text": row["text"], "title": row["title"]})
        qasper_path = f"normalized/qasper-v2/{split}.corpus.jsonl" if effective_version == 2 else f"normalized/qasper/{split}.corpus.jsonl"
        q_roles = json.loads((ROOT / "splits/qasper/effective-roles-v2.json").read_text(encoding="utf-8"))["roles"] if effective_version == 2 else []
        q_map = {row["id"]: row["role"] for row in q_roles}
        for row in read_jsonl(ROOT / qasper_path):
            if q_map.get(row["id"], "").startswith("inactive_"):
                continue
            result["qasper"].append({"id": row["id"], "partition": q_map.get(row["id"], split),
                                      "text": "\n".join(block["text"] for block in row["blocks"]), "title": row["title"]})
    for split in ("development", "calibration", "final"):
        for row in read_jsonl(ROOT / f"normalized/multihop-{version}/{split}.corpus.jsonl"):
            result["multihop_rag"].append({"id": row["id"], "partition": split,
                                            "text": row["native_article"]["body"], "title": row["native_article"]["title"]})
    return result


def screen(rows):
    from sklearn.feature_extraction.text import TfidfVectorizer
    normalized = [re.sub(r"\s+", " ", row["text"]).casefold().strip() for row in rows]
    # Exact char 5-grams, not embeddings or model-based semantic adjudication.
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(5, 5), min_df=2, norm="l2", dtype="float32")
    import numpy as np
    vectorizer.dtype = np.float32
    matrix = vectorizer.fit_transform(normalized)
    candidates, cross = [], []
    for start in range(0, len(rows), 64):
        similarity = (matrix[start:start + 64] @ matrix.T).tocoo()
        for local, right, value in zip(similarity.row, similarity.col, similarity.data):
            left = start + int(local)
            right = int(right)
            if right <= left or value < .90:
                continue
            entry = {"left": rows[left]["id"], "right": rows[right]["id"],
                     "left_title": rows[left]["title"], "right_title": rows[right]["title"],
                     "left_partition": rows[left]["partition"], "right_partition": rows[right]["partition"],
                     "cosine": float(value), "exact_normalized_text": normalized[left] == normalized[right]}
            candidates.append(entry)
            if entry["left_partition"] != entry["right_partition"]:
                cross.append(entry)
    return {"documents": len(rows), "partitions": dict(Counter(row["partition"] for row in rows)),
            "vocabulary": len(vectorizer.vocabulary_), "candidate_pairs": candidates,
            "cross_partition_candidates": cross,
            "detector": "casefold_whitespace_collapsed_char5_tfidf_min_df2_cosine>=0.90",
            "semantic_deduplication_certified": False,
            "release_gate": "blocked_pending_source_adjudication" if cross else "lexical_screen_clear_not_semantic_certification"}


def main(effective_version=1):
    result = {"status": "inconclusive", "scope": "effective_partitions_lexical_screen", "datasets": {}}
    for name, rows in documents(effective_version).items():
        result["datasets"][name] = screen(rows)
        write_json(ROOT / f"reports/isolation-screen-v{effective_version}.json", result)
        print(json.dumps({"dataset": name, "documents": len(rows),
                          "cross_partition_candidates": len(result["datasets"][name]["cross_partition_candidates"])}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--effective-version", type=int, choices=(1, 2), default=1)
    main(parser.parse_args().effective_version)
