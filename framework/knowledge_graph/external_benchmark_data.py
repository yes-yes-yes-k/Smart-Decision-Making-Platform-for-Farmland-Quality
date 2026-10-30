"""Lossless native input/reference separation for external benchmarks."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_jsonl(path: Path, rows: list[dict]) -> None:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError(f"refusing_materialized_snapshot_overwrite:{path}")
    path.write_text(payload, encoding="utf-8")


def redocred_document(doc: dict, split: str) -> tuple[dict, dict]:
    sents = doc["sents"]
    sentences, positions = [], []
    offset = 0
    for tokens in sents:
        sentence = " ".join(tokens)
        starts = []
        cursor = offset
        for token in tokens:
            starts.append((cursor, cursor + len(token)))
            cursor += len(token) + 1
        sentences.append(sentence)
        positions.append(starts)
        offset += len(sentence) + 1
    text = "\n".join(sentences)
    clusters = []
    for cluster_id, mentions in enumerate(doc["vertexSet"]):
        materialized = []
        for mention in mentions:
            sent = mention["sent_id"]
            start, end = mention["pos"]
            if not 0 <= sent < len(sents) or not 0 <= start < end <= len(sents[sent]):
                raise ValueError("invalid_native_mention_position")
            a, b = positions[sent][start][0], positions[sent][end - 1][1]
            if text[a:b] != " ".join(sents[sent][start:end]):
                raise ValueError("native_mention_reconstruction_failed")
            materialized.append({"surface": text[a:b], "start": a, "end": b, "native": mention})
        clusters.append({"id": cluster_id, "mentions": materialized})
    relations = doc.get("labels", [])
    for rel in relations:
        if not 0 <= rel["h"] < len(clusters) or not 0 <= rel["t"] < len(clusters):
            raise ValueError("native_relation_endpoint_out_of_range")
    identifier = "redocred:" + digest(doc["title"] + "\n" + text)
    inputs = {"id": identifier, "dataset": "redocred", "native_split": split,
              "task": "given_entity_document_relation", "title": doc["title"],
              "text": text, "sents": sents, "given_entity_clusters": clusters,
              "text_sha256": digest(text)}
    reference = {"id": identifier, "title": doc["title"], "native_split": split,
                 "relations": relations, "native_vertexSet": doc["vertexSet"],
                 "evidence_status": "native_only_not_independently_revalidated"}
    return inputs, reference


def qasper_paper(identifier: str, paper: dict, split: str) -> tuple[dict, list[dict], list[dict]]:
    # Keep paragraph/caption identity and original content; answers never enter corpus.
    blocks = [{"id": "abstract", "kind": "abstract", "text": paper.get("abstract", "")}]
    for section_id, section in enumerate(paper.get("full_text", [])):
        for paragraph_id, paragraph in enumerate(section.get("paragraphs", [])):
            blocks.append({"id": f"s{section_id}:p{paragraph_id}", "kind": "text",
                           "section": section.get("section_name", ""), "text": paragraph})
    for index, item in enumerate(paper.get("figures_and_tables", [])):
        blocks.append({"id": f"figure_table:{index}", "kind": "caption",
                       "text": item.get("caption", ""), "native": item})
    corpus = {"id": "qasper:" + identifier, "dataset": "qasper", "native_split": split,
              "title": paper["title"], "blocks": blocks,
              "text_sha256": digest("\n".join(block["text"] for block in blocks))}
    inputs, references = [], []
    for qa in paper.get("qas", []):
        qid = "qasper:" + str(qa["question_id"])
        inputs.append({"id": qid, "document_id": corpus["id"], "native_split": split,
                       "question": qa["question"]})
        evidence_matches = []
        for answer in qa.get("answers", []):
            evidence = answer.get("answer", {}).get("evidence", [])
            evidence_matches.append([{"text": quote,
                                      "matching_blocks": [block["id"] for block in blocks if block["text"] == quote]}
                                     for quote in evidence])
        references.append({"id": qid, "document_id": corpus["id"], "native_split": split,
                           "native_answers": qa.get("answers", []), "evidence_matches": evidence_matches})
    return corpus, inputs, references


def split_audit(inputs_by_split: dict[str, list[dict]]) -> dict:
    seen_id, seen_text = {}, {}
    conflicts, duplicates = [], []
    for split, rows in inputs_by_split.items():
        for row in rows:
            for value, seen, category in [(row["id"], seen_id, "document_id"),
                                           (row["text_sha256"], seen_text, "exact_input")]:
                if value in seen:
                    old_split, old_id = seen[value]
                    record = {"kind": category, "left": old_id, "right": row["id"],
                              "left_split": old_split, "right_split": split}
                    (conflicts if old_split != split else duplicates).append(record)
                else:
                    seen[value] = (split, row["id"])
    return {"cross_split_conflicts": conflicts, "within_split_duplicates": duplicates,
            "near_duplicate_review": "pending", "release_ready": False}
