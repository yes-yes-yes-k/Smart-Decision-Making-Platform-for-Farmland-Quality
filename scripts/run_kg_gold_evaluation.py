"""Run real GraphRAG against published source snapshots for the reviewed gold."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=ROOT / "artifacts/minimal_kg/extraction_gold_v1.jsonl")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--siliconflow", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--retry-transient", action="store_true", help="retry at most once cached provider failures with zero reported tokens")
    parser.add_argument('--literal-evidence', action='store_true', help='experimental v7 source-quote extraction; not production-qualified')
    args = parser.parse_args()
    if args.literal_evidence:
        os.environ['KG_EXTRACTION_LITERAL_EVIDENCE']='true'
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1..4")
    if args.siliconflow:
        os.environ.update(KG_EXTRACTION_BASE_URL="https://api.siliconflow.cn/v1",
            KG_EXTRACTION_ALLOW_SILICONFLOW="true",
            KG_EXTRACTION_MODEL=os.environ.get("SILICONFLOW_CHAT_MODEL", "deepseek-ai/DeepSeek-V4-Flash"))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from framework.config import Config
    from framework.models.document import Document
    from framework.knowledge_graph.chunk_reader import WorkerPublishedChunkReader
    from framework.knowledge_graph.contracts import ExtractionRequest, SourceChunk, sha256_text, stable_digest
    from framework.knowledge_graph.schema import load_graph_schema
    from framework.knowledge_graph.adapters.live_graphrag import LiveMicrosoftGraphRagBackend
    from framework.knowledge_graph.candidate_pipeline import CanonicalEntityCatalog, DEFAULT_GRAPH_PATH
    from framework.knowledge_graph.conformance import evaluate_extraction_backend
    from framework.knowledge_graph.gold_evaluation import prediction_rows, entity_scores, source_locator_score, retry_transient_record
    from scripts.evaluate_kg_extraction_backend import read_jsonl, evaluate_rows
    args.run_dir.mkdir(parents=True, exist_ok=True)
    gold = read_jsonl(args.gold)
    schema = load_graph_schema()
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, connect_args={"connect_timeout": 5})
    with sessionmaker(bind=engine)() as session:
        sources = {}
        for did in sorted({row["evidence"]["document_id"] for row in gold}):
            doc = session.get(Document, did)
            if (doc is not None and doc.status == Document.STATUS_COMPLETED and
                    doc.review_status == Document.REVIEW_APPROVED and doc.visibility_scope == "public"):
                sources[did] = dict(name=doc.doc_name, file_sha256=doc.file_hash, kind=doc.document_kind)
    engine.dispose()
    reader = WorkerPublishedChunkReader(Config.CHROMA_PERSIST_DIR)
    requests, issues, page_cache = {}, [], {}
    covered_rows = 0
    for index, row in enumerate(gold):
        evidence = row["evidence"]
        did, page = evidence["document_id"], evidence["page"]
        if did not in sources:
            issues.append(dict(row=index, code="source_not_approved_public"))
            continue
        key = (did, page)
        if key not in page_cache:
            page_cache[key] = reader._read({"$and": [{"document_id":did}, {"page":page}, {"visibility_scope":"public"}]}, 64)
        selected = [item for item in page_cache[key] if evidence.get("chunk_index") is None
                    or item["metadata"].get("chunk_index") == evidence["chunk_index"]]
        literal = [item for item in selected if evidence["quote"] in item["content"]]
        if evidence.get('source_chunk_sha256'):
            bound = [item for item in selected if sha256_text(item['content']) == evidence['source_chunk_sha256']
                     and item['content'][evidence['span_start']:evidence['span_end']] == evidence['quote']]
            if not bound:
                raise ValueError(f'versioned gold source binding changed at row {index}')
        if not literal:
            issues.append(dict(row=index, document_id=did, page=page, code="gold_quote_not_literal_in_locator"))
        else:
            covered_rows += 1
        # A page-only gold locator supplies every published chunk on that page.
        # Never choose an input chunk by whether it makes a prediction correct.
        for item in selected:
            meta = item["metadata"]
            chunk = SourceChunk(did, sha256_text(item["content"]), int(meta["chunk_index"]), item["content"], int(meta["page"]))
            request = ExtractionRequest(f"gold-eval:{did}:{chunk.chunk_index}", did,
                chunk.content_sha256, schema.schema_version, (chunk,))
            requests[(did, chunk.chunk_index, chunk.page)] = request
    manifest = dict(schema="kg-gold-input-snapshots-v1", gold_sha256=hashlib.sha256(args.gold.read_bytes()).hexdigest(),
        gold_rows=len(gold), literal_source_covered_rows=covered_rows, source_documents=len(sources),
        request_count=len(requests), issues=issues,
        content_binding="evaluation-only published single-chunk text SHA-256; not asserted to be original file SHA-256",
        answers_in_prompt=False, requests=[asdict(r) for r in requests.values()], source_metadata=sources)
    write_json(args.run_dir / "input-manifest.json", manifest)
    progress = dict(state="preflight_complete", expected_gold_rows=len(gold), literal_source_covered_rows=covered_rows,
                    request_count=len(requests), completed_requests=0, failed_requests=0, source_issues=issues)
    write_json(args.output.with_name("graphrag-gold-progress-v1.json"), progress)
    print(json.dumps({key:value for key,value in progress.items() if key!="source_issues"}), flush=True)
    if args.preflight_only:
        return int(bool(issues))
    if not requests:
        parser.error("no trustworthy published source chunks were found")
    python = os.environ.get("KG_GRAPHRAG_PYTHON") or str(ROOT / ".tools/graphrag-runtime/Scripts/python.exe")
    backend = LiveMicrosoftGraphRagBackend(python)
    backend.provider.check_runtime()
    records = []
    def extract(request):
        local = LiveMicrosoftGraphRagBackend(python)
        cache = args.run_dir / "responses" / f"{stable_digest([asdict(request),local._config_digest])}.json"
        previous = None
        if cache.exists():
            record = json.loads(cache.read_text(encoding="utf-8"))
            retry = retry_transient_record(record, args.retry_transient)
            if not retry:
                record["reused_cache"] = True
                return record
            previous = record
            write_json(args.run_dir / "failed-attempts" / cache.name, previous)
        start = time.monotonic()
        try:
            result = local.extract(request)
            record = dict(state="completed", result=result.to_dict())
        except Exception as exc:
            record = dict(state="failed", code=getattr(exc, "code", "backend_exception"))
        record.update(request_key=request.request_key, document_id=request.document_id,
            chunk_index=request.chunks[0].chunk_index, elapsed_seconds=time.monotonic()-start,
            usage=local.provider.last_usage, backend_config_digest=local._config_digest)
        if previous:
            record["prior_attempt"] = {key: previous.get(key) for key in ("state", "code", "usage", "elapsed_seconds")}
        write_json(cache, record)
        return record
    start = time.monotonic()
    progress["state"] = "running"
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(extract, request) for request in requests.values()]
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            progress["completed_requests"] += 1
            progress["failed_requests"] += int(record["state"] == "failed")
            write_json(args.output.with_name("graphrag-gold-progress-v1.json"), progress)
            print(json.dumps(dict(completed=progress["completed_requests"], total=len(requests), failed=progress["failed_requests"])), flush=True)
    elapsed = time.monotonic()-start
    inference_seconds = sum(record["elapsed_seconds"] + (record.get("prior_attempt") or {}).get("elapsed_seconds",0) for record in records)
    catalog = CanonicalEntityCatalog.from_json()
    predictions, raw_predictions, entities, raw_entities = [], [], [], []
    usage = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0, repair_requests=0)
    for record in records:
        for key in usage:
            usage[key] += int((record.get("usage") or {}).get(key, 0))
        if record["state"] != "completed":
            continue
        rows, items = prediction_rows(record["result"], catalog)
        predictions.extend(rows); entities.extend(items)
        rows, items = prediction_rows(record["result"])
        raw_predictions.extend(rows); raw_entities.extend(items)
    for name, rows in (("graphrag-predictions-v1.jsonl", predictions), ("graphrag-raw-predictions-v1.jsonl", raw_predictions)):
        args.output.with_name(name).write_text("".join(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n" for row in rows),encoding="utf-8")
    options = dict(backend_name=backend.name, backend_version=backend.version, elapsed_seconds=inference_seconds,
        input_documents=len({r.document_id for r in requests.values()}), cost_usd=None,
        cost_source="provider token usage recorded; billed monetary amount unavailable, not assumed zero",
        evaluation_mode="live_backend_predictions")
    report = evaluate_rows(gold, predictions, **options)
    report["metrics"]["entities"] = entity_scores(gold, entities)
    report["performance"].update(measurement="sum of per-request inference times; serial-equivalent throughput",
        wall_seconds_this_invocation=elapsed, workers=args.workers,
        cached_requests=sum(bool(record.get("reused_cache")) for record in records),
        transient_retries=sum(bool(record.get("prior_attempt")) for record in records),
        request_count=len(records), scope="selected gold-source chunks, not full-document ingestion")
    report["raw_metrics"] = evaluate_rows(gold, raw_predictions, **options)["metrics"]
    report["raw_metrics"]["entities"] = entity_scores(gold, raw_entities)
    report.update(token_usage=usage, model=os.environ.get("KG_EXTRACTION_MODEL"),
        gold_sha256=manifest['gold_sha256'], gold_path=str(args.gold), gold_rows=len(gold),
        failed_request_summaries=[{key:record.get(key) for key in ("document_id","chunk_index","code","usage")}
            for record in records if record["state"] != "completed"],
        backend_config_digest=backend._config_digest, source_preflight={key:val for key,val in progress.items() if key!="state"},
        canonicalization=dict(mode="existing runtime entity aliases only; no gold relation hints", catalog_sha256=hashlib.sha256(DEFAULT_GRAPH_PATH.read_bytes()).hexdigest()),
        source_locator_score=source_locator_score(gold,predictions),
        caveats=["Closed-world comparison to reviewed positive facts; unannotated facts may be scored false positive.",
                 "Exact evidence metric requires the original quote hash; page/chunk coverage is separately reported.",
                 "Legacy null chunk indices are retained in the strict legacy scorer; source locator supplement treats them as unspecified."],
        production_approved=False)
    if issues or progress["failed_requests"]:
        report["status"] = "completed_with_source_or_backend_gaps"
    write_json(args.output, report)
    # This is two NEW real calls, not a cached or gold-fixture replay.
    conformance_usage = []
    class MeasuredBackend:
        name, version = backend.name, backend.version
        def extract(self, request):
            try:
                return backend.extract(request)
            finally:
                conformance_usage.append(backend.provider.last_usage)
    conformance = evaluate_extraction_backend(MeasuredBackend(), next(iter(requests.values())), schema)
    write_json(args.output.with_name("graphrag-conformance-v1.json"), dict(backend_name=conformance.backend_name,
        backend_version=conformance.backend_version, passed=conformance.passed,
        evaluation_mode="two_uncached_live_calls", issues=[asdict(issue) for issue in conformance.issues],
        token_usage_by_call=conformance_usage,
        backend_config_digest=backend._config_digest, generated_at=datetime.now(UTC).isoformat()))
    progress["state"] = report["status"]
    write_json(args.output.with_name("graphrag-gold-progress-v1.json"), progress)
    print(json.dumps(dict(status=report["status"],metrics=report["metrics"],usage=usage,
        conformance_passed=conformance.passed,source_issues=len(issues)),ensure_ascii=False),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
