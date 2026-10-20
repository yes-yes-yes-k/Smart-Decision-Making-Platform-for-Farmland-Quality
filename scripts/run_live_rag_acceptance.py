"""Run selected designed questions through the real external RAG chain."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.config import Config  # noqa: E402
from framework.rag.chain import RAGChain  # noqa: E402


DEFAULT_IDS = (
    "措施-04", "措施-09",
    "诊断-01", "诊断-03",
    "指标改善-01",
    "标准指标-07",
    "检测-06",
    "依据-01",
    "反事实-01", "反事实-02",
)


def _trace_rows(results: list[dict[str, Any]], document_titles: dict[int, str]) -> list[dict[str, Any]]:
    traces = []
    for row in results:
        metadata = row.get("metadata") or {}
        document_id = metadata.get("document_id")
        traces.append({
            "rank": len(traces) + 1,
            "retrieval_source": metadata.get("retrieval_source", "hybrid_vector_bm25"),
            "relation_id": metadata.get("relation_id"),
            "relation_ids": metadata.get("relation_ids") or (
                [metadata.get("relation_id")] if metadata.get("relation_id") else []
            ),
            "relation_type": metadata.get("relation_type"),
            "source_entity": metadata.get("source_entity"),
            "target_entity": metadata.get("target_entity"),
            "document_id": document_id,
            "document_title": document_titles.get(document_id) or metadata.get("doc_name") or metadata.get("source"),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "graph_claim_status": metadata.get("graph_claim_status"),
        })
    return traces


def _keyword_result(answer: str, keywords: list[str]) -> dict[str, Any]:
    matched = [item for item in keywords if item.lower() in (answer or "").lower()]
    return {
        "expected": keywords,
        "matched": matched,
        "recall": round(len(matched) / len(keywords), 4) if keywords else 1.0,
    }


def run(selected: list[dict[str, Any]], graph: dict[str, Any]) -> list[dict[str, Any]]:
    rag = RAGChain()
    document_titles = {
        int(item["document_id"]): item["title"] for item in graph.get("corpus", [])
    }
    records = []
    for index, item in enumerate(selected, 1):
        captured: dict[str, Any] = {}
        original_retrieve = rag._retrieve_documents

        def capture(query, valid_doc_names, *, user_id=None):
            result = original_retrieve(query, valid_doc_names, user_id=user_id)
            captured.update(result)
            return result

        rag._retrieve_documents = capture
        started = time.perf_counter()
        try:
            response = rag.chat(item["question"], user_id=None)
        finally:
            rag._retrieve_documents = original_retrieve
        elapsed = round(time.perf_counter() - started, 3)
        traces = _trace_rows(captured.get("results") or [], document_titles)
        actual_relation_ids = {
            relation_id
            for row in traces
            for relation_id in row.get("relation_ids", [])
            if relation_id
        }
        expected_relation_id = item.get("expected_relation_id")
        relation_hit = (
            expected_relation_id in actual_relation_ids
            if expected_relation_id else None
        )
        unsupported_detected = any(
            row.get("graph_claim_status") == "unsupported" for row in traces
        )
        keyword_result = _keyword_result(response.get("answer", ""), item.get("answer_keywords") or [])
        records.append({
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "expected_answer": item["expected_answer"],
            "expected_status": item["expected_status"],
            "expected_relation_id": expected_relation_id,
            "live_answer": response.get("answer", ""),
            "success": bool(response.get("success")),
            "model": response.get("model"),
            "elapsed_seconds": elapsed,
            "retrieved_count": captured.get("count", 0),
            "graph_hit_count": sum(
                str(row.get("retrieval_source") or "").startswith("knowledge_graph_")
                for row in traces
            ),
            "relation_hit_at_5": relation_hit,
            "unsupported_detected": unsupported_detected if item["expected_status"] == "unsupported" else None,
            "answer_keyword_check": keyword_result,
            "retrieval_trace": traces,
            "manual_review_required": True,
        })
        print(json.dumps({
            "progress": f"{index}/{len(selected)}",
            "id": item["id"],
            "success": records[-1]["success"],
            "model": records[-1]["model"],
            "elapsed_seconds": elapsed,
            "graph_hit_count": records[-1]["graph_hit_count"],
            "relation_hit_at_5": relation_hit,
            "unsupported_detected": records[-1]["unsupported_detected"],
        }, ensure_ascii=False), flush=True)
    return records


def _markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    graph_version = str(payload.get("graph_schema_version") or "knowledge-graph")
    graph_version = graph_version.rsplit("-", 1)[-1]
    lines = [
        f"# {graph_version} 正式 RAG 外部模型实测回复",
        "",
        f"- 执行时间：{payload['generated_at']}",
        f"- 对话模型：`{payload['models']['chat']}`",
        f"- 向量模型：`{payload['models']['embedding']}`",
        f"- 重排模型：`{payload['models']['reranker']}`",
        f"- 实测题数：{summary['question_count']}",
        f"- 外部模型成功：{summary['success_count']}/{summary['question_count']}",
        f"- 支持类预期关系命中：{summary['supported_relation_hits']}/{summary['supported_question_count']}",
        f"- 反事实约束触发：{summary['unsupported_detected_count']}/{summary['unsupported_question_count']}",
        f"- 平均耗时：{summary['average_elapsed_seconds']} 秒",
        "",
        "> 以下均为真实外部模型返回内容，未做人工润色。自动指标只作为辅助，最终答案质量仍需人工复核。",
        "",
    ]
    for index, item in enumerate(payload["results"], 1):
        lines.extend([
            f"## {index}. {item['id']}｜{item['category']}",
            "",
            f"**问题**：{item['question']}",
            "",
            f"**预期答案**：{item['expected_answer']}",
            "",
            f"**真实回复**：{item['live_answer']}",
            "",
            f"**模型与耗时**：`{item['model']}`，{item['elapsed_seconds']} 秒",
            "",
            f"**自动检查**：关系命中={item['relation_hit_at_5']}；反事实约束={item['unsupported_detected']}；关键词召回={item['answer_keyword_check']['recall']}",
            "",
            "**检索来源**：",
            "",
        ])
        for row in item["retrieval_trace"]:
            relation = (
                f"；关系 `{row['relation_type']}` / `{row['relation_id']}`"
                if row.get("relation_id") else ""
            )
            lines.append(
                f"- Top {row['rank']}：{row.get('document_title') or '未知文档'}，"
                f"第 {row.get('page') or '—'} 页，来源 `{row['retrieval_source']}`{relation}"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "rag_acceptance_designed_v0.1.json")
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "live_rag_responses_v0.1.json")
    parser.add_argument("--report", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "live_rag_responses_v0.1.md")
    parser.add_argument(
        "--seed-results", type=Path,
        help="复用已完成的真实回复，只调用尚未出现的题目ID。",
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--ids", nargs="*", default=list(DEFAULT_IDS))
    args = parser.parse_args()

    acceptance = json.loads(args.acceptance.read_text(encoding="utf-8"))
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in acceptance["questions"]}
    requested = acceptance["questions"] if args.all else [by_id[item_id] for item_id in args.ids]
    seed_results = []
    if args.seed_results:
        seed_payload = json.loads(args.seed_results.read_text(encoding="utf-8"))
        seed_results = list(seed_payload.get("results") or [])
    completed_ids = {item["id"] for item in seed_results}
    selected = [item for item in requested if item["id"] not in completed_ids]
    new_results = run(selected, graph)
    combined = {item["id"]: item for item in [*seed_results, *new_results]}
    results = [combined[item["id"]] for item in requested if item["id"] in combined]
    supported = [item for item in results if item["expected_status"] == "supported"]
    unsupported = [item for item in results if item["expected_status"] == "unsupported"]
    payload = {
        "schema_version": "live-external-rag-responses-v0.1",
        "generated_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "execution_mode": "real_external_models",
        "input_set": args.acceptance.name,
        "graph_schema_version": graph.get("schema_version"),
        "models": {
            "chat": Config.SILICONFLOW_CHAT_MODEL,
            "embedding": Config.SILICONFLOW_EMBED_MODEL,
            "reranker": Config.RERANK_MODEL if Config.RERANK_ENABLED else None,
        },
        "summary": {
            "question_count": len(results),
            "success_count": sum(item["success"] for item in results),
            "supported_question_count": len(supported),
            "supported_relation_hits": sum(item["relation_hit_at_5"] is True for item in supported),
            "unsupported_question_count": len(unsupported),
            "unsupported_detected_count": sum(item["unsupported_detected"] is True for item in unsupported),
            "average_elapsed_seconds": round(sum(item["elapsed_seconds"] for item in results) / max(len(results), 1), 3),
        },
        "results": results,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False), flush=True)
    return 0 if payload["summary"]["success_count"] == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
