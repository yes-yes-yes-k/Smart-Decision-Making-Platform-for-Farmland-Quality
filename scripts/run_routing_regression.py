"""路由回归自动化。

对 model-1/5、model-2/3 两组易混淆对各 ≥20 条正反例运行完整路由判定，
输出混淆矩阵与分类性能统计，退出码反映目标达成（混淆率 ≤ 3%）。
结果矩阵写入 logs/confusion_matrix.json 供看板读取。

用法：
    python scripts/run_routing_regression.py [--output logs/confusion_matrix.json]
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_question_type_keywords import (  # noqa: E402
    MODEL1_STEMS, MODEL5_STEMS, MODEL2_STEMS, MODEL3_STEMS,
    PREFIXES, SUFFIXES, _expand,
)
from framework.agents.exclusive_rules import apply_exclusive_rules  # noqa: E402
from framework.observability.metrics import confusion_metrics  # noqa: E402

# 混淆率目标（spec：重叠 Agent 混淆率不高于 3%）
CONFUSION_RATE_TARGET = 0.03

# 每个正例集：(pair_label, stems, expected_model, base_qtype)
SETS = [
    ("model-1-vs-model-5", MODEL1_STEMS, "model-1", 5),  # 现状评价 → model-1
    ("model-1-vs-model-5", MODEL5_STEMS, "model-5", 1),  # 质量等级评价 → model-5
    ("model-2-vs-model-3", MODEL2_STEMS, "model-2", 3),  # 酸化调理剂 → model-2
    ("model-2-vs-model-3", MODEL3_STEMS, "model-3", 3),  # 有机质 → model-3
]

PAIR_POSITIVE = {
    "model-1-vs-model-5": "model-1",
    "model-2-vs-model-3": "model-2",
}


def _predict_model(question: str, base_qtype: int) -> str:
    """完整路由判定：apply_exclusive_rules，返回最终 model_id。"""
    final_type, _ = apply_exclusive_rules(question, base_qtype, {"scale": "地块"})
    return f"model-{final_type}" if final_type in (1, 2, 3, 4, 5) else "unknown"


def write_metrics_to_db(matrix: dict, evaluation_mode: str) -> None:
    """批量写入 model_evaluation_metrics 表。

    matrix 格式：{pair_label: {tp, fp, fn, tn, total, accuracy, confusion_rate}}
    每对插入一条记录，positive_label 来自 PAIR_POSITIVE 映射。

    DB 写入失败时 rollback 并告警，不抛出（保留 JSON 文件输出）。
    """
    from framework.models import db, ModelEvaluationMetrics
    try:
        for pair_label, m in matrix.items():
            record = ModelEvaluationMetrics(
                model_pair=pair_label,
                positive_label=PAIR_POSITIVE.get(pair_label, ""),
                tp=m["tp"], fp=m["fp"], fn=m["fn"], tn=m["tn"],
                total=m["total"], accuracy=m["accuracy"],
                confusion_rate=m["confusion_rate"],
                evaluation_mode=evaluation_mode,
                sample_count=m["total"],
            )
            db.session.add(record)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        warnings.warn(f"[regression] model_evaluation_metrics DB 写入失败: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="路由回归自动化（输出混淆矩阵）")
    parser.add_argument("--output", default="logs/confusion_matrix.json",
                        help="混淆矩阵 JSON 输出路径")
    parser.add_argument("--target", type=float, default=CONFUSION_RATE_TARGET,
                        help="混淆率目标（默认 0.03）")
    args = parser.parse_args(argv)

    pair_true: dict = defaultdict(list)
    pair_pred: dict = defaultdict(list)
    for pair_label, stems, model, base in SETS:
        qs = _expand(stems, PREFIXES, SUFFIXES)
        pair_true[pair_label].extend([model] * len(qs))
        pair_pred[pair_label].extend([_predict_model(q, base) for q in qs])

    matrix = {}
    failed = False
    for pair_label in PAIR_POSITIVE:
        true = pair_true[pair_label]
        pred = pair_pred[pair_label]
        m = confusion_metrics(true, pred, PAIR_POSITIVE[pair_label])
        matrix[pair_label] = m
        print(f"[{pair_label}] 样本数={m['total']} "
              f"TP={m['tp']} FP={m['fp']} FN={m['fn']} TN={m['tn']} "
              f"正确率={m['accuracy']:.2%} 混淆率={m['confusion_rate']:.2%}")
        if m["confusion_rate"] > args.target:
            failed = True

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    print(f"混淆矩阵已写入 {args.output}")
    print("目标达成" if not failed else "未达成：存在混淆率超目标的对")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())