"""调试 _identify_question_type_llm - 捕获 LLM 原始响应内容。

打印 LLM 返回的 raw content 和解析失败原因，
从而定位"总是返回 None"的根因。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from framework.config import Config
setattr(Config, "ROUTING_MODE", "llm")

from framework.agents import routing
from framework.agents.routing import (
    _identify_question_type_llm,
    _safe_parse_llm_result,
)
from framework.llm.service import llm_service


# 构造与 _identify_question_type_llm 完全相同的 prompt
def build_prompt(question: str, context=None) -> str:
    capability_lines = []
    for cap in routing.PROFESSIONAL_CAPABILITIES:
        capability_lines.append(
            f"- 类型 {cap.question_type}：{cap.name}（{cap.description}）"
        )
    capabilities_text = "\n".join(capability_lines)

    context_lines = []
    if context:
        for key in ("scale", "data_type", "business_task", "expected_output"):
            val = context.get(key)
            if val:
                context_lines.append(f"- {key}: {val}")
    context_text = "\n".join(context_lines) if context_lines else "(未提供)"

    return (
        "你是耕地质量与土壤改良领域的问题分类助手。请根据用户问题，判定它属于以下哪一类问题类型。\n\n"
        "问题类型清单：\n"
        f"{capabilities_text}\n\n"
        "用户问题：\n"
        f"{question}\n\n"
        "五维上下文：\n"
        f"{context_text}\n\n"
        "请仅输出严格 JSON，不要任何额外说明或 markdown 代码块：\n"
        '{"question_type": int(0..6, 0=知识性/RAG), '
        '"relevance": float(0..1), "reason": str(简短理由)}'
    )


TEST_QUESTIONS = [
    "希望提升土壤肥力",        # 期望 model-5
    "帮我出个施肥方案",        # 期望 model-5
    "这地酸了怎么治",          # 期望 model-4
    "提高有机质",              # 期望 model-5（原 keyword 命中）
]


def main():
    print("=" * 80)
    print("Debug _identify_question_type_llm - 捕获 LLM 原始响应")
    print("=" * 80)
    print(f"LLM available: {llm_service.is_available()}")
    print()

    for question in TEST_QUESTIONS:
        print("-" * 80)
        print(f"Q: {question}")
        prompt = build_prompt(question)
        print(f"Prompt length: {len(prompt)}")

        # 直接调用 llm_service.generate
        try:
            response = llm_service.generate(prompt, temperature=0.0)
            print(f"Response type: {type(response).__name__}")
            print(f"Response keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
            print(f"Response success: {response.get('success') if isinstance(response, dict) else 'N/A'}")
            content = response.get("content", "") if isinstance(response, dict) else ""
            print(f"Content type: {type(content).__name__}")
            print(f"Content length: {len(content) if isinstance(content, str) else 'N/A'}")
            print(f"Content repr (前 500 字符):")
            print(repr(content[:500]) if isinstance(content, str) else content)
            print()

            # 尝试 _safe_parse_llm_result
            parsed = _safe_parse_llm_result(content)
            print(f"_safe_parse_llm_result: {parsed}")
            if parsed is None:
                # 尝试 json.loads 直接解析
                try:
                    data = json.loads(content)
                    print(f"json.loads OK: {data}")
                    print(f"  question_type: {data.get('question_type')} (type: {type(data.get('question_type')).__name__})")
                except Exception as e:
                    print(f"json.loads FAILED: {type(e).__name__}: {e}")
                    # 尝试清理 markdown 代码块
                    cleaned = content.strip()
                    if cleaned.startswith("```"):
                        # 去掉 markdown 代码块
                        lines = cleaned.split("\n")
                        if lines[0].startswith("```"):
                            lines = lines[1:]
                        if lines and lines[-1].startswith("```"):
                            lines = lines[:-1]
                        cleaned = "\n".join(lines).strip()
                        try:
                            data = json.loads(cleaned)
                            print(f"  After strip markdown: json.loads OK: {data}")
                        except Exception as e2:
                            print(f"  After strip markdown FAILED: {e2}")
            print()
        except Exception as e:
            print(f"llm_service.generate raised: {type(e).__name__}: {e}")
        print()


if __name__ == "__main__":
    main()
