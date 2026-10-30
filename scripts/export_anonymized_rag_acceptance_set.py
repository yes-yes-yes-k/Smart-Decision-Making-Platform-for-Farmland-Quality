"""Export a privacy-preserving, independent RAG acceptance set.

Only user-authored historical questions are read.  Raw database identifiers,
conversation identifiers, timestamps and unredacted text are never written.
The script prints aggregate counts only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from framework.knowledge_graph import (  # noqa: E402
    assess_graph_claim,
    entity_match_scores,
    rank_graph_evidence,
)
from framework.rag.knowledge_graph_retriever import KnowledgeGraphRetriever  # noqa: E402


REDACTIONS = (
    ("email", re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b"), "[邮箱]"),
    ("url", re.compile(r"(?i)https?://\S+"), "[网址]"),
    ("windows_path", re.compile(r"(?i)\b[a-z]:\\[^\s，。；]+"), "[本地路径]"),
    ("unix_path", re.compile(r"(?<!\w)/(?:home|Users|var|tmp)/[^\s，。；]+"), "[本地路径]"),
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证号]"),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    ("uuid", re.compile(r"(?i)\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b"), "[唯一标识]"),
    ("ipv4", re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"), "[IP地址]"),
    ("coordinates", re.compile(r"(?<!\d)\d{2,3}\.\d{4,}\s*[,，]\s*\d{1,3}\.\d{4,}(?!\d)"), "[坐标]"),
    ("parcel_id", re.compile(r"(?i)(?:(?:地块|宗地|图斑|样点)(?:编号|代码|ID)?[：:\s]*)[A-Z0-9_-]{5,}"), "[地块编号]"),
    ("labelled_name", re.compile(r"(?:姓名|联系人|我叫)[：:\s]*[\u4e00-\u9fff·]{2,8}"), "姓名：[姓名]"),
    ("labelled_address", re.compile(r"(?:地址|住址|详细位置)[：:\s]*[^，。；\n]{4,60}"), "地址：[地址]"),
    ("long_number", re.compile(r"(?<![\d.])\d{7,}(?![\d.])"), "[编号]"),
)

DOMAIN_TERMS = (
    "耕地质量", "耕地地力", "土壤", "障碍因素", "障碍诊断", "改良",
    "酸化", "盐渍", "板结", "有机质", "养分", "全氮", "有效磷",
    "速效钾", "阳离子交换", "排水", "灌溉", "耕层", "容重",
    "施肥", "绿肥", "秸秆还田", "客土", "深松", "深耕",
)

NON_QA_TERMS = (
    "git分支", "代码", "上传目录", "删除文件", "导出excel", "生成文档",
    "知识图谱下一步", "汇报报告", "后端", "数据库迁移",
)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def anonymize(text: str) -> tuple[str, Counter]:
    value = re.sub(r"\s+", " ", text or "").strip()
    counts: Counter = Counter()
    for name, pattern, replacement in REDACTIONS:
        value, count = pattern.subn(replacement, value)
        if count:
            counts[name] += count
    return value, counts


def _sqlite_questions(path: Path) -> list[str]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return [
            row[0] for row in connection.execute(
                "SELECT content FROM kb_message "
                "WHERE role='user' AND content IS NOT NULL "
                "AND length(trim(content)) BETWEEN 4 AND 300 "
                "ORDER BY create_time, id"
            )
        ]
    finally:
        connection.close()


def _postgres_questions() -> list[str]:
    import psycopg2

    connection = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "123456"),
        dbname=os.environ.get("DB_NAME", "db_enterprise_qa"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM kb_message "
                "WHERE role='user' AND content IS NOT NULL "
                "AND length(trim(content)) BETWEEN 4 AND 300 "
                "ORDER BY create_time, id"
            )
            return [row[0] for row in cursor.fetchall()]
    finally:
        connection.close()


def _routing_log_questions(logs_dir: Path) -> list[str]:
    questions: list[str] = []
    for path in sorted(logs_dir.glob("routing_calls_*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except (ValueError, TypeError):
                continue
            # question_type=0 is the production router's general/RAG path.
            if payload.get("question_type") == 0 and payload.get("question"):
                questions.append(str(payload["question"]))
    return questions


def _gold_questions(path: Path) -> list[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [item.get("question", "") for item in payload.get("questions", [])]


def _overlaps_gold(question: str, gold_questions: Iterable[str]) -> bool:
    normalized = _normalise(question)
    for gold in gold_questions:
        candidate = _normalise(gold)
        if normalized == candidate:
            return True
        if SequenceMatcher(None, normalized, candidate).ratio() >= 0.90:
            return True
    return False


def _slice_for(entity_ids: list[str], relation_types: list[str]) -> str:
    if any(value.startswith("standard:") for value in entity_ids):
        return "标准依据"
    if "characterized_by" in relation_types:
        return "障碍诊断"
    if any(value in relation_types for value in ("addresses", "improves_indicator")):
        return "改良措施"
    return "指标解释"


def _fallback_slice(question: str) -> str:
    compact = "".join((question or "").split())
    if any(term in compact for term in ("空间分布", "分布情况", "区域分布", "时空变化", "变化趋势")):
        return "空间统计回退"
    if any(term in compact for term in ("什么是", "是什么意思", "定义是什么", "含义是什么")):
        return "定义解释回退"
    return "宽泛问题回退"


def _is_non_qa(question: str) -> bool:
    if any(term in question for term in NON_QA_TERMS):
        return True
    if "试算" in question:
        return True
    if "生成" in question and "报告" in question:
        return True
    return False


def build_set(
    questions: Iterable[str], graph: dict, gold_questions: Iterable[str], *, max_items: int,
) -> tuple[list[dict], dict]:
    records = []
    seen = set()
    redaction_counts: Counter = Counter()
    stats: Counter = Counter()
    for raw_question in questions:
        stats["source_rows"] += 1
        question, counts = anonymize(raw_question)
        redaction_counts.update(counts)
        normalized = _normalise(question)
        if normalized in seen:
            stats["duplicate"] += 1
            continue
        seen.add(normalized)
        if _is_non_qa(question):
            stats["non_qa"] += 1
            continue
        entity_scores, _ = entity_match_scores(graph, question)
        if not entity_scores and not any(term in question for term in DOMAIN_TERMS):
            stats["out_of_scope"] += 1
            continue
        if _overlaps_gold(question, gold_questions):
            stats["gold_overlap"] += 1
            continue
        ranked = rank_graph_evidence(graph, question, top_k=5)
        claim = assess_graph_claim(graph, question)
        graph_eligible = bool(ranked) and KnowledgeGraphRetriever.supports_query_intent(question)
        if not graph_eligible:
            ranked = []
            claim = {"status": "indeterminate"}
        relation_ids = list(dict.fromkeys(row["relation_id"] for row in ranked))[:3]
        relation_types = list(dict.fromkeys(row["relation_type"] for row in ranked))[:3]
        locations = []
        for row in ranked:
            metadata = row.get("metadata") or {}
            location = {
                "document_id": metadata.get("document_id"),
                "page": metadata.get("page"),
            }
            if location not in locations:
                locations.append(location)
        records.append({
            "id": f"REAL-{len(records) + 1:03d}",
            "question": question,
            "slice": (
                _slice_for(sorted(entity_scores), relation_types)
                if graph_eligible else _fallback_slice(question)
            ),
            "expected": {
                "retrieval_mode": "graph_augmented" if graph_eligible else "vector_fallback",
                "matched_entity_ids": sorted(entity_scores),
                "claim_status": claim.get("status", "indeterminate"),
                "top_relation_ids": relation_ids,
                "top_relation_types": relation_types,
                "evidence_locations": locations[:3],
            },
            "acceptance": {
                "retrieval_hit_at_5": None,
                "answer_grounded": None,
                "citation_correct": None,
                "review_note": "",
            },
        })
        if len(records) >= max_items:
            break
    stats["retained"] = len(records)
    return records, {
        "counts": dict(stats),
        "redaction_counts": dict(sorted(redaction_counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", choices=("postgres", "sqlite", "routing-logs"), default="postgres",
    )
    parser.add_argument("--sqlite-path", type=Path, default=PROJECT_ROOT / "instance" / "development.db")
    parser.add_argument("--logs-dir", type=Path, default=PROJECT_ROOT / "logs")
    parser.add_argument("--graph", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json")
    parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "gold_qa_v0.3.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "real_question_acceptance_v0.1.json")
    parser.add_argument("--privacy-report", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg" / "real_question_acceptance_privacy_report_v0.1.json")
    parser.add_argument("--max-items", type=int, default=50)
    args = parser.parse_args()

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    if args.source == "postgres":
        questions = _postgres_questions()
    elif args.source == "sqlite":
        questions = _sqlite_questions(args.sqlite_path)
    else:
        questions = _routing_log_questions(args.logs_dir)
    records, audit = build_set(
        questions, graph, _gold_questions(args.gold), max_items=max(1, args.max_items),
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "cultivated-land-real-question-acceptance-v0.1",
        "generated_at": generated_at,
        "source": (
            "historical_user_messages_local_anonymized"
            if args.source in {"postgres", "sqlite"}
            else "historical_rag_routing_events_local_anonymized"
        ),
        "source_environment": args.source,
        "provenance_status": (
            "message_table" if args.source in {"postgres", "sqlite"}
            else "operational_log_human_origin_unverified"
        ),
        "independent_of": args.gold.name,
        "privacy": {
            "raw_identifiers_exported": False,
            "raw_conversation_ids_exported": False,
            "raw_user_ids_exported": False,
            "external_model_used": False,
        },
        "sample_size": len(records),
        "statistical_status": (
            "needs_data" if not records else
            "pilot" if len(records) < 30 else
            "acceptance"
        ),
        "questions": records,
    }
    privacy_report = {
        "schema_version": "acceptance-privacy-audit-v0.1",
        "generated_at": generated_at,
        "source_environment": args.source,
        **audit,
        "raw_text_persisted": False,
        "external_service_used": False,
        "limitations": [
            "结构化规则无法保证识别所有自由文本中的人名或隐含身份信息。",
            "历史消息表本身不能证明每条记录均由最终用户而非测试流程产生。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.privacy_report.write_text(
        json.dumps(privacy_report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({
        "sample_size": len(records),
        "statistical_status": payload["statistical_status"],
        "counts": audit["counts"],
        "redaction_counts": audit["redaction_counts"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

