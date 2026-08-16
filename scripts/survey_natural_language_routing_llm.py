"""专题模型自然语言提问路由调研脚本（LLM 辅助模式）。

为 model-1 ~ model-5 各设计多组自然语言问题，调用 identify_question_type
获取路由结果，输出 JSON 供报告生成使用。

运行模式：LLM 模式（默认 ROUTING_MODE=llm），LLM 优先初判 + 失败回退关键词。
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 启用 LLM 模式（默认），保留向量匹配作为回退
from framework.config import Config
# 显式声明使用 LLM 模式（如 Config 已有该字段则覆盖，否则设置类属性）
setattr(Config, "ROUTING_MODE", "llm")

from framework.agents import routing
# 保留 EMBEDDING_AVAILABLE 作为回退路径，不强制关闭
from framework.agents.nodes import identify_question_type


# 问题设计：每个模型覆盖「经典专业」「口语化」「带地块上下文」「边界」四类
QUESTIONS_BY_MODEL = {
    "model-1": {
        "expected_type": 1,
        "name": "耕地质量稳定性与退化风险评价",
        "questions": [
            ("classic",     "查询区域内耕地质量等级整体稳定吗？"),
            ("classic",     "查询区域内哪些高等级耕地存在退化风险？"),
            ("colloquial",  "我的这块田质量等级稳不稳？"),
            ("colloquial",  "这地块会不会掉级"),
            ("with-parcel", "@001地块 稳定性怎么样，有没有退化风险"),
            ("boundary",    "全省耕地质量怎么样"),
        ],
    },
    "model-2": {
        "expected_type": 2,
        "name": "耕地质量等级评价",
        "questions": [
            ("classic",     "我的田耕地质量等级是多少？"),
            ("classic",     "查询地块的综合指数和障碍度排序"),
            ("colloquial",  "这块地质量怎么样"),
            ("colloquial",  "这块地肥力怎么样"),
            ("colloquial",  "这块地肥力如何"),
            ("with-parcel", "@001地块 帮我看看等级评价"),
            ("boundary",    "今天天气怎么样"),
        ],
    },
    "model-3": {
        "expected_type": 3,
        "name": "耕地质量主要问题与障碍诊断",
        "questions": [
            ("classic",     "全省耕地质量存在哪些问题？"),
            ("classic",     "查询区域内耕地主要障碍因素有哪些"),
            ("colloquial",  "我这块地到底有啥毛病？"),
            ("colloquial",  "这块地有什么问题"),
            ("with-parcel", "@001地块 帮我诊断一下有哪些障碍"),
            ("boundary",    "全省耕地质量怎么样"),
        ],
    },
    "model-4": {
        "expected_type": 4,
        "name": "耕地土壤酸化改良",
        "questions": [
            ("classic",     "查询区域内农用地土壤酸化程度如何？"),
            ("classic",     "我的田酸化了，pH是5.0，我要施加多少碱性调理剂可以治理好？"),
            ("colloquial",  "我的田酸化严重吗？"),
            ("colloquial",  "这地酸了怎么治"),
            ("with-parcel", "@001地块 酸化了吗，要下多少石灰"),
            ("boundary",    "我的田质量怎么样"),
        ],
    },
    "model-5": {
        "expected_type": 5,
        "name": "耕地土壤有机质培肥提升",
        "questions": [
            ("classic",     "为了提升耕地土壤有机质，有机肥或者秸秆每亩施用量多少？"),
            ("classic",     "全省耕地土壤有机质含量如何？"),
            ("colloquial",  "提高有机质"),
            ("colloquial",  "希望提升土壤肥力"),
            ("colloquial",  "帮我出个施肥方案"),
            ("with-parcel", "@001地块 有机质太低了，想培肥"),
            ("boundary",    "我的田酸化严重吗"),
        ],
    },
}


def run_survey():
    results = []
    for model_id, spec in QUESTIONS_BY_MODEL.items():
        expected = spec["expected_type"]
        for q_type, question in spec["questions"]:
            # 重置 last_router_method 以便记录每次实际使用的路由方法
            routing._last_router_method = None
            qt, rel = identify_question_type(question)
            # 取出本次调用实际使用的路由方法
            method_used = routing._last_router_method or "unknown"
            hit = (qt == expected)
            if q_type == "boundary":
                verdict = "boundary-sample"
            elif hit:
                verdict = "HIT"
            elif qt == 0:
                verdict = "MISS-RAG"
            else:
                verdict = f"WRONG-model-{qt}"
            results.append({
                "model_id": model_id,
                "model_name": spec["name"],
                "expected_type": expected,
                "question_category": q_type,
                "question": question,
                "actual_type": qt,
                "relevance": round(rel, 3) if rel else 0,
                "hit": hit,
                "verdict": verdict,
                "router_method": method_used,
            })
    return results


def main():
    results = run_survey()
    output_path = PROJECT_ROOT / "docs" / "superpowers" / "reports" / "natural-language-routing-survey-llm.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    # 打印 ASCII 摘要
    print("=" * 90)
    print("Natural Language Routing Survey (LLM-assisted mode)")
    print("=" * 90)
    current_model = None
    for r in results:
        if r["model_id"] != current_model:
            current_model = r["model_id"]
            print(f"\n[{r['model_id']}] {r['model_name']} (expected type={r['expected_type']})")
            print("-" * 80)
        print(f"  [{r['question_category']:12s}] type={r['actual_type']} rel={r['relevance']:.3f} method={r['router_method']:8s}  {r['verdict']}")
        print(f"    Q: {r['question']}")
    # 统计
    hit_cases = [r for r in results if r["question_category"] != "boundary" and r["hit"]]
    total_cases = [r for r in results if r["question_category"] != "boundary"]
    method_count = {}
    for r in results:
        m = r["router_method"]
        method_count[m] = method_count.get(m, 0) + 1
    print("\n" + "=" * 90)
    pct = len(hit_cases) / len(total_cases) * 100 if total_cases else 0
    print(f"Hit rate (non-boundary): {len(hit_cases)}/{len(total_cases)} = {pct:.1f}%")
    print(f"Router methods used: {method_count}")
    print(f"JSON written: {output_path}")
    print("=" * 90)


if __name__ == "__main__":
    main()
