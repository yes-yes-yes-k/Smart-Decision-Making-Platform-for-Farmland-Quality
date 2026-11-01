"""Build the auditable cultivated-land minimal graph pilot from persisted chunks."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import chromadb

from framework.knowledge_graph import PilotDocument, build_pilot_graph


PILOT_CORPUS = (
    PilotDocument(3, "耕地地力调查与质量评价技术规程 NY/T 1634-2008", "standard"),
    PilotDocument(4, "耕地质量等级 GB/T 33469-2016", "standard"),
    PilotDocument(11, "补充耕地质量鉴定技术规范 试行", "standard"),
    PilotDocument(13, "广东省补充耕地质量验收细则 试行", "policy"),
    PilotDocument(14, "广东省补充耕地质量鉴定技术规范 试行", "standard"),
    PilotDocument(15, "主要红壤区坡耕地土壤质量评价与障碍因子识别", "research"),
    PilotDocument(16, "云贵高原耕地质量评估 障碍因子及产能提升潜力分析", "research"),
    PilotDocument(17, "县域耕地质量评价方法比选与优化研究", "research"),
    PilotDocument(21, "岭南山地丘陵区耕地质量评价指标体系研究", "research"),
    PilotDocument(23, "基于耕地综合质量的高标准农田建设与监测研究", "research"),
    PilotDocument(24, "富锦市耕地质量评价与提升对策研究", "research"),
    PilotDocument(27, "新疆耕地质量等级评价及障碍因素诊断研究", "research"),
    PilotDocument(28, "罗定市耕地质量时空分异特征及障碍因素诊断", "research"),
    PilotDocument(29, "耕地质量等级提升的土地整治项目设计关键技术研究", "research"),
    PilotDocument(30, "酸性红壤地区耕地健康评价及定向培育研究", "research"),
)


def load_chunks(chroma_dir: Path) -> list[dict]:
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection("kb_cultivated_land_quality")
    data = collection.get(include=["documents", "metadatas"])
    selected_ids = {doc.document_id for doc in PILOT_CORPUS}
    chunks = []
    for content, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
        if int(metadata.get("document_id") or 0) not in selected_ids:
            continue
        chunks.append({
            "document_id": int(metadata["document_id"]),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "content": content,
        })
    return chunks


def write_validation_report(graph: dict, path: Path) -> None:
    metrics = graph["validation"]
    entities = {entity["id"]: entity for entity in graph["entities"]}
    by_type = defaultdict(list)
    for relation in graph["relations"]:
        by_type[relation["type"]].append(relation)

    lines = [
        "# 耕地质量最小知识图谱验证报告",
        "",
        "## 验证范围",
        "",
        f"- 代表性资料：{metrics['corpus_document_count']} 份",
        "- 节点类型：耕地质量指标、障碍因素、改良措施、标准依据",
        "- 关系类型：影响、治理、定义、支持",
        "- 当前状态：候选图谱，关系在专家确认前不得作为强制性结论",
        "",
        "## 自动检查结果",
        "",
        f"- 实际命中资料：{metrics['covered_document_count']} 份",
        f"- 实体：{metrics['entity_count']} 个，分布 {json.dumps(metrics['entity_counts'], ensure_ascii=False)}",
        f"- 关系：{metrics['relation_count']} 条，分布 {json.dumps(metrics['relation_counts'], ensure_ascii=False)}",
        f"- 证据片段：{metrics['evidence_count']} 条",
        f"- 关系证据完整率：{metrics['relations_with_evidence_ratio']:.0%}",
        f"- 证据页码定位率：{metrics['evidence_with_page_ratio']:.0%}",
        "",
        "## 优先人工核验的候选关系",
        "",
        "| 关系 | 主体 | 客体 | 支持文档数 | 置信度 |",
        "|---|---|---|---:|---:|",
    ]
    priority = sorted(
        graph["relations"],
        key=lambda item: (-item["supporting_document_count"], item["type"], item["source"]),
    )[:30]
    relation_labels = {"affects": "影响", "addresses": "治理", "defines": "定义", "supports": "支持"}
    for relation in priority:
        lines.append(
            f"| {relation_labels[relation['type']]} | {entities[relation['source']]['name']} | "
            f"{entities[relation['target']]['name']} | {relation['supporting_document_count']} | "
            f"{relation['confidence']:.2f} |"
        )
    lines += [
        "",
        "## 通过条件",
        "",
        "1. 四类节点边界由土壤所确认，别名不产生重复实体。",
        "2. 每条保留关系至少有一条可定位到文档页码的原文证据。",
        "3. 抽取样本中实体准确率和关系准确率分别达到 85% 和 75%。",
        "4. 三类问题可返回答案、来源文档、页码和证据原文。",
        "5. 未通过专家确认的关系保持 candidate 状态，不进入正式问答结论。",
        "",
        "## 后续动作",
        "",
        "从候选关系中抽取不少于 100 条形成金标准，完成专家确认后再写入正式图数据库。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroma-dir", type=Path, default=PROJECT_ROOT / "chroma_db")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "artifacts" / "minimal_kg")
    args = parser.parse_args()
    chunks = load_chunks(args.chroma_dir)
    if not chunks:
        raise SystemExit("选定的代表性资料没有可用知识片段")
    graph = build_pilot_graph(PILOT_CORPUS, chunks)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = args.output_dir / "cultivated_land_minimal_graph_v0.1.json"
    report_path = args.output_dir / "validation_report.md"
    graph_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    write_validation_report(graph, report_path)
    print(json.dumps({"graph": str(graph_path), "report": str(report_path), **graph["validation"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
