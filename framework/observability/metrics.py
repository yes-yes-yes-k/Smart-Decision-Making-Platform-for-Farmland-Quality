"""路由混淆矩阵计算（纯函数，无第三方依赖）。"""
from __future__ import annotations
from typing import Any, Dict, Sequence


def confusion_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    positive_label: str,
) -> Dict[str, Any]:
    """基于真实标签与预测结果计算二分类混淆矩阵统计。

    positive_label 为关注的正类（配对中的目标模型）。
    返回包含 tp/fp/fn/tn/total/accuracy/confusion_rate 的字典。
    """
    assert len(y_true) == len(y_pred), "y_true 与 y_pred 长度必须一致"
    tp = fp = fn = tn = 0
    for true, pred in zip(y_true, y_pred):
        if true == positive_label:
            if pred == positive_label:
                tp += 1
            else:
                fn += 1
        else:
            if pred == positive_label:
                fp += 1
            else:
                tn += 1
    total = len(y_true)
    return {
        "positive_label": positive_label,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "total": total,
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "confusion_rate": round((fp + fn) / total, 4) if total else 0.0,
    }