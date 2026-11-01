"""Audit reviewed references against public snapshots; never rewrite gold labels."""
import argparse
from collections import Counter
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def locate_quote(content, quote):
    start = content.find(quote)
    if start >= 0:
        return dict(kind="literal", span_start=start, span_end=start+len(quote), quote=quote)
    offsets = [i for i, character in enumerate(content) if not character.isspace()]
    folded = "".join(content[i] for i in offsets)
    wanted = "".join(character for character in quote if not character.isspace())
    index = folded.find(wanted) if wanted else -1
    if index >= 0:
        start, end = offsets[index], offsets[index+len(wanted)-1]+1
        return dict(kind="whitespace_only_equivalent", span_start=start, span_end=end, quote=content[start:end])
    return None


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=ROOT / "artifacts/minimal_kg/extraction_gold_v1.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    gold = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines() if line.strip()]
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout":5})
    with sessionmaker(bind=engine)() as session:
        allowed = {doc.id for doc in session.query(Document).filter(Document.id.in_({r["evidence"]["document_id"] for r in gold}),
            Document.status==Document.STATUS_COMPLETED, Document.visibility_scope=="public", Document.review_status==Document.REVIEW_APPROVED)}
    engine.dispose()
    reader = WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR)
    cache, entries = {}, []
    for index, item in enumerate(gold):
        evidence = item["evidence"]
        did, page = evidence["document_id"], evidence["page"]
        entry = dict(row=index, relation_id=item["relation"]["id"], document_id=did, page=page,
            original_chunk_index=evidence.get("chunk_index"), original_quote=evidence["quote"],
            original_quote_sha256=evidence["quote_sha256"], candidates=[])
        if did not in allowed:
            entry["status"] = "source_not_approved_public"
            entries.append(entry)
            continue
        key=(did,page)
        if key not in cache:
            cache[key]=reader._read({"$and":[{"document_id":did},{"page":page},{"visibility_scope":"public"}]},64)
        for chunk in cache[key]:
            match=locate_quote(chunk["content"],evidence["quote"])
            if match:
                entry["candidates"].append(dict(chunk_index=chunk["metadata"]["chunk_index"], **match,
                    source_chunk_sha256=hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest()))
        preferred=[c for c in entry["candidates"] if c["chunk_index"]==evidence.get("chunk_index")]
        candidates=preferred or entry["candidates"]
        if candidates:
            entry["status"] = "literal_verified" if any(c["kind"]=="literal" for c in candidates) else "whitespace_equivalent_verified"
            if evidence.get("chunk_index") is None:
                entry["locator_note"] = "legacy chunk index unspecified; candidate locations retained without choosing an answer"
            elif not preferred:
                entry["locator_note"] = "declared chunk differs; candidate locator requires review"
        else:
            entry["status"] = "requires_source_review"
            if cache[key]:
                closest=max(cache[key],key=lambda c:SequenceMatcher(None,evidence["quote"],c["content"],autojunk=False).find_longest_match().size)
                match=SequenceMatcher(None,evidence["quote"],closest["content"],autojunk=False).find_longest_match()
                entry["nearby_source"] = dict(chunk_index=closest["metadata"]["chunk_index"],
                    excerpt=closest["content"][max(0,match.b-100):match.b+match.size+150],
                    note="review aid only; not an approved replacement")
        entries.append(entry)
    report=dict(schema="kg-gold-source-audit-v1", gold_sha256=hashlib.sha256(args.gold.read_bytes()).hexdigest(),
        gold_rows=len(gold), counts=dict(Counter(entry["status"] for entry in entries)),
        original_gold_modified=False, production_data_modified=False, entries=entries)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({key:value for key,value in report.items() if key!="entries"},ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
