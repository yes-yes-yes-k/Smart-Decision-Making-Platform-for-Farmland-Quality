"""路由回归自动化。

对 model-3/2、model-4/5 两组易混淆对各 ≥20 条正反例运行完整路由判定，
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
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_question_type_keywords import (  # noqa: E402
    MODEL3_STEMS, MODEL2_STEMS, MODEL4_STEMS, MODEL5_STEMS,
    PREFIXES, SUFFIXES, _expand,
)
from framework.agents.exclusive_rules import apply_exclusive_rules  # noqa: E402
from framework.observability.metrics import confusion_metrics  # noqa: E402
from framework.agents.routing import identify_question_type  # noqa: E402
from framework.config import Config  # noqa: E402

# 混淆率目标（spec：重叠 Agent 混淆率不高于 3%）
CONFUSION_RATE_TARGET = 0.03

# 每个正例集：(pair_label, stems, expected_model, base_qtype)
SETS = [
    ("model-3-vs-model-2", MODEL3_STEMS, "model-3", 2),  # 障碍诊断 → model-3
    ("model-3-vs-model-2", MODEL2_STEMS, "model-2", 3),  # 质量等级评价 → model-2
    ("model-4-vs-model-5", MODEL4_STEMS, "model-4", 5),  # 酸化调理剂 → model-4
    ("model-4-vs-model-5", MODEL5_STEMS, "model-5", 5),  # 有机质 → model-5
]

# mock LLM 输出表：将问题文本映射到固定类型（用于回归验证 LLM 路径与 keyword 路径一致）
MOCK_LLM_QTYPE_MAP = {
    "model-3": 3, "model-2": 2, "model-4": 4, "model-5": 5,
}


def _install_mock_llm(monkeypatch_target=None):
    """安装 mock LLM：根据问题命中的关键词返回固定类型。

    返回 dict，便于恢复。仅在 --mock-llm 启用时调用。
    """
    from framework.llm.service import llm_service
    from framework.agents import routing as _routing

    def _fake_generate(prompt, **kwargs):
        # 反向匹配：prompt 含能力描述则返回对应类型
        for model_id, qt in MOCK_LLM_QTYPE_MAP.items():
            if f"类型 {qt}：" in prompt:
                return {
                    "success": True,
                    "content": f'{{"question_type": {qt}, "relevance": 0.9, "reason": "mock"}}',
                    "model": "mock",
                    "type": "llm",
                }
        return {
            "success": True,
            "content": '{"question_type": 0, "relevance": 0.5, "reason": "未命中"}',
            "model": "mock",
            "type": "llm",
        }

    llm_service.generate = _fake_generate
    llm_service.is_available = lambda: True
    _routing.LLM_AVAILABLE = True

PAIR_POSITIVE = {
    "model-3-vs-model-2": "model-3",
    "model-4-vs-model-5": "model-4",
}


def _predict_model(question: str, base_qtype: int) -> str:
    """完整路由判定：apply_exclusive_rules，返回最终 model_id。"""
    final_type, _ = apply_exclusive_rules(question, base_qtype, {"scale": "地块"})
    return f"model-{final_type}" if final_type in (1, 2, 3, 4, 5, 6) else "unknown"


def _predict_model_full(question: str, context: Optional[dict]) -> str:
    """完整路由判定：经 identify_question_type（含 LLM 与排他规则），返回最终 model_id。"""
    qt, _ = identify_question_type(question, context)
    return f"model-{qt}" if qt in (1, 2, 3, 4, 5, 6) else "unknown"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="路由回归自动化（输出混淆矩阵）")
    parser.add_argument("--output", default="logs/confusion_matrix.json",
                        help="混淆矩阵 JSON 输出路径")
    parser.add_argument("--target", type=float, default=CONFUSION_RATE_TARGET,
                        help="混淆率目标（默认 0.03）")
    parser.add_argument("--routing-mode", choices=("llm", "keyword"), default="keyword",
                        help="路由模式（默认 keyword，与历史行为一致）")
    parser.add_argument("--mock-llm", action="store_true",
                        help="安装 mock LLM（仅在 --routing-mode=llm 时生效）")
    args = parser.parse_args(argv)

    # 设置路由模式
    Config.ROUTING_MODE = args.routing_mode
    if args.routing_mode == "llm" and args.mock_llm:
        _install_mock_llm()
        print("[regression] 已安装 mock LLM，路由模式 = llm")
    else:
        print(f"[regression] 路由模式 = {args.routing_mode}（无 LLM）")

    # 选择预测函数
    if args.routing_mode == "llm":
        # LLM 模式：完整路由（identify_question_type 内部已含排他规则）
        _predict = lambda q, base: _predict_model_full(q, {"scale": "地块"})
    else:
        # keyword 模式：保持历史行为（apply_exclusive_rules）
        _predict = _predict_model

    pair_true: dict = defaultdict(list)
    pair_pred: dict = defaultdict(list)
    for pair_label, stems, model, base in SETS:
        qs = _expand(stems, PREFIXES, SUFFIXES)
        pair_true[pair_label].extend([model] * len(qs))
        pair_pred[pair_label].extend([_predict(q, base) for q in qs])

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
    suffix = f".{args.routing_mode}" if args.routing_mode != "keyword" else ""
    output_path = args.output if not suffix else args.output.replace(
        ".json", f"{suffix}.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2)
    print(f"混淆矩阵已写入 {output_path}")
    print("目标达成" if not failed else "未达成：存在混淆率超目标的对")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())