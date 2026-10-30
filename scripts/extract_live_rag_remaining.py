"""Extract newly executed live RAG cases from a combined result payload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _markdown(payload: dict) -> str:
    summary = payload["summary"]
    lines = [
        "# v0.3 正式 RAG 其余30题外部模型实测回复",
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
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    full_payload = json.loads(args.full.read_text(encoding="utf-8"))
    seed_payload = json.loads(args.seed.read_text(encoding="utf-8"))
    seed_ids = {item["id"] for item in seed_payload.get("results", [])}
    results = [item for item in full_payload["results"] if item["id"] not in seed_ids]
    supported = [item for item in results if item["expected_status"] == "supported"]
    unsupported = [item for item in results if item["expected_status"] == "unsupported"]

    payload = {
        **{key: value for key, value in full_payload.items() if key not in {"summary", "results"}},
        "subset": "remaining_questions_excluding_seed_results",
        "summary": {
            "question_count": len(results),
            "success_count": sum(item["success"] for item in results),
            "supported_question_count": len(supported),
            "supported_relation_hits": sum(
                item["relation_hit_at_5"] is True for item in supported
            ),
            "unsupported_question_count": len(unsupported),
            "unsupported_detected_count": sum(
                item["unsupported_detected"] is True for item in unsupported
            ),
            "average_elapsed_seconds": round(
                sum(item["elapsed_seconds"] for item in results) / max(len(results), 1), 3
            ),
        },
        "results": results,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
