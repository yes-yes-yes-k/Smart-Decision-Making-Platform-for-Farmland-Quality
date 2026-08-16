"""验证 context 增强路由 - 模拟用户在地图上选中地块的真实场景。

对比有无 parcel_id 时的路由结果，验证 context 增强的实际效果。
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from framework.config import Config
setattr(Config, "ROUTING_MODE", "llm")

from framework.agents.routing import identify_question_type


# 模拟用户在地图上选中地块后的真实场景
SCENARIOS = [
    # (描述, 问题, context)
    ("无地块-施肥方案",   "帮我出个施肥方案",     None),
    ("有地块-施肥方案",   "帮我出个施肥方案",     {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}),
    ("无地块-提升肥力",   "希望提升土壤肥力",     None),
    ("有地块-提升肥力",   "希望提升土壤肥力",     {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}),
    ("无地块-这块地怎么样", "这块地怎么样",        None),
    ("有地块-这块地怎么样", "这块地怎么样",        {"scale": "地块", "data_type": "评价结果", "parcel_id": "001"}),
    ("无地块-培肥",       "我想培肥这块地",       None),
    ("有地块-培肥",       "我想培肥这块地",       {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}),
    ("无地块-酸化",       "这地酸了怎么治",       None),
    ("有地块-酸化",       "这地酸了怎么治",       {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}),
    ("无地块-障碍",       "这块地有什么问题",     None),
    ("有地块-障碍",       "这块地有什么问题",     {"scale": "地块", "data_type": "评价结果", "parcel_id": "001"}),
    ("无地块-天气",       "今天天气怎么样",       None),
    ("有地块-天气",       "今天天气怎么样",       {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}),
]


def main():
    print("=" * 90)
    print("Context 增强路由对比验证")
    print("=" * 90)
    print(f"{'场景':<22} {'问题':<22} {'无地块 type':>12} {'有地块 type':>12} {'差异':>8}")
    print("-" * 90)

    for desc, question, ctx in SCENARIOS:
        # 拆分无地块/有地块对比
        if "无地块" not in desc:
            continue
        # 无地块
        qt_no, _ = identify_question_type(question, context=None)
        # 有地块
        ctx_with_parcel = {"scale": "地块", "data_type": "指标数据", "parcel_id": "001"}
        qt_yes, _ = identify_question_type(question, context=ctx_with_parcel)
        diff = "→" if qt_no != qt_yes else "="
        print(f"{desc:<22} {question:<22} {qt_no:>12} {qt_yes:>12} {diff:>8}")

    print("=" * 90)


if __name__ == "__main__":
    main()
