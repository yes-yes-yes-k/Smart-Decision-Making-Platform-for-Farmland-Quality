"""验证 _safe_parse_llm_result 修复后的行为。"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from framework.agents.routing import _safe_parse_llm_result

# 测试 1：带 markdown 代码块的 JSON（LLM 实际返回格式）
content1 = '```json\n{"question_type": 3, "relevance": 0.9, "reason": "test"}\n```'
result1 = _safe_parse_llm_result(content1)
print(f"Test 1 (markdown json): {result1}")
assert result1 == (3, 0.9, "test"), f"FAIL: expected (3, 0.9, 'test'), got {result1}"

# 测试 2：纯 JSON（理想情况）
content2 = '{"question_type": 5, "relevance": 1.0, "reason": "ok"}'
result2 = _safe_parse_llm_result(content2)
print(f"Test 2 (plain json): {result2}")
assert result2 == (5, 1.0, "ok"), f"FAIL: expected (5, 1.0, 'ok'), got {result2}"

# 测试 3：仅 ``` 包裹（无 json 标记）
content3 = '```\n{"question_type": 0, "relevance": 0.5, "reason": "rag"}\n```'
result3 = _safe_parse_llm_result(content3)
print(f"Test 3 (plain markdown): {result3}")
assert result3 == (0, 0.5, "rag"), f"FAIL: expected (0, 0.5, 'rag'), got {result3}"

# 测试 4：越界类型（应返回 None）
content4 = '```json\n{"question_type": 9, "relevance": 0.9, "reason": "bad"}\n```'
result4 = _safe_parse_llm_result(content4)
print(f"Test 4 (out of range): {result4}")
assert result4 is None, f"FAIL: expected None, got {result4}"

# 测试 5：非 JSON 字符串（应返回 None）
content5 = "这不是 JSON"
result5 = _safe_parse_llm_result(content5)
print(f"Test 5 (not json): {result5}")
assert result5 is None, f"FAIL: expected None, got {result5}"

print("\n[PASS] All 5 tests passed")
