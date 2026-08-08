"""路由看板：读取本地日志与混淆矩阵，输出文本看板，支持导出 Markdown。

读取路由日志计算漏调用率、参数完整率；从混淆矩阵 JSON（回归脚本输出）读取
正确率、混淆率。运行方式：
    python -m framework.observability.dashboard [--matrix logs/confusion_matrix.json] [--markdown]
"""
from __future__ import annotations
import argparse
import json
import sys
from typing import Any, Dict, List
from .routing_log import read_routing_logs


def compute_log_metrics(entries: List[Dict[str, Any]]) -> Dict[str, float]:
    """由日志条目计算漏调用率与参数完整率。"""
    total = len(entries)
    if total == 0:
        return {"total_calls": 0, "missed_call_rate": 0.0, "param_completeness_rate": 0.0}
    boundary = sum(1 for e in entries if e.get("routing_status") == "boundary_pending")
    complete = sum(
        1 for e in entries
        if e.get("data_version") is not None
        and e.get("agent_version") is not None
        and isinstance(e.get("params"), dict)
    )
    return {
        "total_calls": total,
        "missed_call_rate": round(boundary / total, 4),
        "param_completeness_rate": round(complete / total, 4),
    }


def format_dashboard(
    matrix: Dict[str, Dict[str, Any]],
    log_metrics: Dict[str, float],
    markdown: bool = False,
) -> str:
    """格式化看板为文本或 Markdown。"""
    if markdown:
        lines = ["# 路由观测看板", "",
                 "## 关键指标", "",
                 "| 指标 | 值 |", "| --- | --- |",
                 f"| 总调用数 | {log_metrics['total_calls']} |",
                 f"| 漏调用率 | {log_metrics['missed_call_rate']:.2%} |",
                 f"| 参数完整率 | {log_metrics['param_completeness_rate']:.2%} |",
                 "", "## 混淆矩阵", "",
                 "| 关注类 | TP | FP | FN | TN | 正确率 | 混淆率 |",
                 "| --- | --- | --- | --- | --- | --- | --- |"]
        for label, m in matrix.items():
            lines.append(
                f"| {label} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} "
                f"| {m['accuracy']:.2%} | {m['confusion_rate']:.2%} |"
            )
    else:
        lines = ["===== 路由观测看板 =====",
                 f"总调用数   : {log_metrics['total_calls']}",
                 f"漏调用率   : {log_metrics['missed_call_rate']:.2%}",
                 f"参数完整率 : {log_metrics['param_completeness_rate']:.2%}",
                 "----- 混淆矩阵（正确率 / 混淆率）-----"]
        for label, m in matrix.items():
            lines.append(
                f"{label}: TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']} "
                f"正确率={m['accuracy']:.2%} 混淆率={m['confusion_rate']:.2%}"
            )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="路由观测看板")
    parser.add_argument("--matrix", default="logs/confusion_matrix.json",
                        help="混淆矩阵 JSON 文件（回归脚本输出）")
    parser.add_argument("--log-dir", default="logs", help="路由日志目录")
    parser.add_argument("--markdown", action="store_true", help="导出 Markdown")
    parser.add_argument("--output", default=None, help="输出文件路径（默认打印到 stdout）")
    args = parser.parse_args(argv)

    entries = read_routing_logs(args.log_dir)
    log_metrics = compute_log_metrics(entries)

    matrix: Dict[str, Dict[str, Any]] = {}
    try:
        with open(args.matrix, "r", encoding="utf-8") as f:
            matrix = json.load(f)
    except FileNotFoundError:
        matrix = {}

    text = format_dashboard(matrix, log_metrics, markdown=args.markdown)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())