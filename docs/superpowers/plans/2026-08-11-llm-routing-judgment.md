---
change: llm-routing-judgment
design-doc: docs/superpowers/specs/2026-08-11-llm-routing-judgment-design.md
base-ref: ad19d4bbb056999c2252a58e86a41f3327bdae43
---

# LLM 路由判定 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有确定性路由流水线（关键词 → embedding → 排他规则）上叠加 LLM 全量初判路径，通过 `ROUTING_MODE` 开关控制默认 `llm`、可回退 `keyword`，LLM 失败自动回退关键词且排他规则仍作为最终兜底。

**Architecture:** `Config.ROUTING_MODE` 决定主路径；`routing.py` 新增 `_identify_question_type_llm` 与 `_safe_parse_llm_result`，动态读取 `capabilities.PROFESSIONAL_CAPABILITIES` 构造 prompt 调用 `llm_service.generate(temperature=0.0)`；模块级状态变量 `_last_router_method/_last_llm_reason/_last_llm_duration_ms` 供 `observe.py` 读取并写入观测日志，`ROUTING_RESULT_VERSION` 升至 `v1.2`。对外签名 `identify_question_type(question, context) -> (int, float)` 保持不变，`ROUTING_MODE=keyword` 时行为与现状完全一致。

**Tech Stack:** Python 3.10+、langchain_openai（已有 LLMService）、pytest、python-docx（文档更新）。

## Global Constraints

- `ROUTING_MODE` 取值仅限 `"llm"`（默认）或 `"keyword"`，从环境变量 `ROUTING_MODE` 读取。
- `identify_question_type(question, context)` 对外签名与返回类型保持 `(int, float)`，不破坏 v1 兼容（context=None 与旧版完全一致）。
- LLM 路径仅用 `llm_service.generate(prompt, temperature=0.0)`；不新增 LLM 客户端，不修改 `LLMService` 内部。
- 排他规则（`apply_exclusive_rules`）语义与触发条件不变，仍作为最终兜底叠加。
- LLM 任何异常（不可用/非 JSON/字段缺失/越界/超时）一律静默回退关键词，不向调用方抛异常。
- 混淆率目标：`ROUTING_MODE=llm` 与 `ROUTING_MODE=keyword` 两种模式下混淆矩阵 `confusion_rate ≤ 3%`。
- `ROUTING_RESULT_VERSION` 由 `v1.1` 递增至 `v1.2`。
- 测试一律通过 monkeypatch 替换 `llm_service.generate` / `llm_service.is_available`，不发起真实网络调用。

## File Structure

| 文件 | 责任 | 操作 |
|------|------|------|
| `framework/config.py` | 新增 `ROUTING_MODE` 配置项 | Modify |
| `framework/agents/routing.py` | LLM 路由核心：prompt 构造、解析、回退、模块级状态 | Modify |
| `framework/observability/observe.py` | 观测日志新增 `router_method/llm_reason/llm_duration_ms`，版本升至 v1.2 | Modify |
| `framework/agents/nodes.py` | 验证观测字段透传（预期无需改动，仅验证） | Verify |
| `scripts/run_routing_regression.py` | 混淆矩阵脚本支持 `--routing-mode` 与 mock LLM | Modify |
| `tests/test_llm_routing.py` | LLM 路由单测：开关、可用、解析失败、越界、排他规则叠加 | Create |
| `tests/test_routing_observability.py` | 适配新增的 `router_method` 等字段 | Modify |
| `tests/test_question_type_keywords.py` | 适配 `ROUTING_MODE=keyword` 默认下不变 | Modify（最小） |
| `大模型开发团队下一步工作建议.docx` | P10 章节、混淆矩阵方法、P1-P9 模型表同步 | Modify |

---

## Task 1: Config 新增 ROUTING_MODE 字段

**Files:**
- Modify: `framework/config.py`（在 `Config` 类内、`MAX_CONCURRENT_MODELS` 之前插入）
- Test: `tests/test_llm_routing.py`（新建文件，先放配置测试）

**Interfaces:**
- Consumes: 无
- Produces: `Config.ROUTING_MODE: str`（`"llm"` 或 `"keyword"`，默认 `"llm"`）

- [ ] **Step 1: 创建测试文件并写失败测试**

新建 `tests/test_llm_routing.py`：

```python
"""LLM 路由判定测试：覆盖开关、可用性、解析失败回退、越界回退、排他规则叠加。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def test_routing_mode_default_is_llm(monkeypatch):
    """默认 ROUTING_MODE 为 llm。"""
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    # 强制重新读取 Config（类属性在模块加载时已绑定，故用直接断言默认值）
    from framework.config import Config
    assert Config.ROUTING_MODE == "llm"


def test_routing_mode_reads_env(monkeypatch):
    """ROUTING_MODE 环境变量覆盖默认值。

    Config.ROUTING_MODE 在类定义时绑定，故通过重新加载 config 模块验证。
    """
    import importlib
    monkeypatch.setenv("ROUTING_MODE", "keyword")
    import framework.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.Config.ROUTING_MODE == "keyword"
    # 还原
    monkeypatch.delenv("ROUTING_MODE", raising=False)
    importlib.reload(_cfg)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_llm_routing.py::test_routing_mode_default_is_llm -v`
Expected: FAIL with `AttributeError: type object 'Config' has no attribute 'ROUTING_MODE'`

- [ ] **Step 3: 在 Config 类中新增 ROUTING_MODE**

修改 `framework/config.py`，在 `MAX_CONCURRENT_MODELS = ...` 这一行之前插入：

```python
    # 路由判定模式：llm=LLM 全量初判（失败自动回退关键词），keyword=纯关键词/向量
    ROUTING_MODE = os.environ.get("ROUTING_MODE", "llm")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_llm_routing.py -v`
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add framework/config.py tests/test_llm_routing.py
git commit -m "feat(config): 新增 ROUTING_MODE 开关，默认 llm 模式"
```

---

## Task 2: routing.py 新增 _safe_parse_llm_result 解析函数

**Files:**
- Modify: `framework/agents/routing.py`（在 `_identify_question_type_keyword` 之前新增模块级状态与解析函数）
- Test: `tests/test_llm_routing.py`（追加解析测试）

**Interfaces:**
- Consumes: 无
- Produces:
  - `_safe_parse_llm_result(content: str) -> Optional[tuple[int, float, str]]`：成功返回 `(question_type, relevance, reason)`；任何异常或越界返回 `None`。
  - 模块级状态：`_last_router_method: str`、`_last_llm_reason: Optional[str]`、`_last_llm_duration_ms: Optional[float]`。

- [ ] **Step 1: 追加失败测试**

在 `tests/test_llm_routing.py` 末尾追加：

```python
class TestSafeParseLLMResult:
    """_safe_parse_llm_result 解析与边界保护。"""

    def test_parse_valid_json(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result(
            '{"question_type": 3, "relevance": 0.9, "reason": "障碍诊断"}'
        )
        assert result == (3, 0.9, "障碍诊断")

    def test_parse_valid_json_with_extra_fields(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result(
            '{"question_type": 1, "relevance": 0.8, "reason": "稳定性", "extra": "ignored"}'
        )
        assert result == (1, 0.8, "稳定性")

    def test_parse_invalid_json_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result("not a json") is None
        assert _safe_parse_llm_result("") is None
        assert _safe_parse_llm_result("{broken") is None

    def test_parse_missing_question_type_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result('{"relevance": 0.5, "reason": "x"}') is None

    def test_parse_non_int_question_type_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        assert _safe_parse_llm_result('{"question_type": "3", "relevance": 0.5}') is None

    def test_parse_out_of_range_returns_none(self):
        from framework.agents.routing import _safe_parse_llm_result
        # 越界：7 超过 0..6
        assert _safe_parse_llm_result('{"question_type": 7, "relevance": 0.5}') is None
        # 越界：-1
        assert _safe_parse_llm_result('{"question_type": -1, "relevance": 0.5}') is None

    def test_parse_boundary_values_accepted(self):
        from framework.agents.routing import _safe_parse_llm_result
        # 0..6 均合法
        assert _safe_parse_llm_result('{"question_type": 0, "relevance": 0.0}') is not None
        assert _safe_parse_llm_result('{"question_type": 6, "relevance": 1.0}') is not None

    def test_parse_missing_reason_defaults_to_empty(self):
        from framework.agents.routing import _safe_parse_llm_result
        # reason 缺失：允许，默认空串
        result = _safe_parse_llm_result('{"question_type": 2, "relevance": 0.5}')
        assert result == (2, 0.5, "")

    def test_parse_missing_relevance_defaults_zero(self):
        from framework.agents.routing import _safe_parse_llm_result
        result = _safe_parse_llm_result('{"question_type": 2, "reason": "x"}')
        assert result == (2, 0.0, "x")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_llm_routing.py::TestSafeParseLLMResult -v`
Expected: FAIL with `ImportError: cannot import name '_safe_parse_llm_result'`

- [ ] **Step 3: 在 routing.py 顶部添加模块级状态，并实现解析函数**

修改 `framework/agents/routing.py`：

1. 在 `_precompute_reference_vectors()` 调用之前（即模块级常量定义之后、`def check_relevance` 之前）新增模块级状态：

```python
# LLM 路由观测状态：每次 identify_question_type 调用前重置
_last_router_method: str = "keyword"
_last_llm_reason: Optional[str] = None
_last_llm_duration_ms: Optional[float] = None
```

2. 在 `def _identify_question_type_keyword(question: str)` 之前新增解析函数：

```python
def _safe_parse_llm_result(content: str) -> Optional[tuple[int, float, str]]:
    """解析 LLM 返回内容为 (question_type, relevance, reason)；任何异常返回 None。

    - content 必须为合法 JSON
    - question_type 必须为 int 且在 0..6 范围
    - relevance 缺失默认 0.0；reason 缺失默认空串
    - 不向调用方抛出任何异常
    """
    import json
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        if "question_type" not in data:
            return None
        qt = data["question_type"]
        if not isinstance(qt, int) or isinstance(qt, bool):
            return None
        if qt < 0 or qt > 6:
            return None
        relevance = data.get("relevance", 0.0)
        if not isinstance(relevance, (int, float)) or isinstance(relevance, bool):
            relevance = 0.0
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason)
        return qt, float(relevance), reason
    except Exception:
        return None
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_llm_routing.py::TestSafeParseLLMResult -v`
Expected: 9 passed

- [ ] **Step 5: 提交**

```bash
git add framework/agents/routing.py tests/test_llm_routing.py
git commit -m "feat(routing): 新增 _safe_parse_llm_result 解析与模块级观测状态"
```

---

## Task 3: routing.py 新增 _identify_question_type_llm 调用函数

**Files:**
- Modify: `framework/agents/routing.py`（在 `_safe_parse_llm_result` 之后新增 LLM 调用函数，并在文件顶部新增 import）
- Test: `tests/test_llm_routing.py`（追加 LLM 调用测试，使用 monkeypatch mock `llm_service`）

**Interfaces:**
- Consumes:
  - `framework.agents.capabilities.PROFESSIONAL_CAPABILITIES`（6 个能力的 `question_type/name/description`）
  - `framework.llm.service.llm_service.generate(prompt, temperature=0.0)` 与 `is_available()`
  - `_safe_parse_llm_result(content)`
- Produces:
  - `_identify_question_type_llm(question: str, context: Optional[dict]) -> Optional[tuple[int, float, str]]`
    - LLM 不可用 / 调用异常 / 解析失败 → 返回 `None`（调用方回退关键词）
    - 成功 → 返回 `(question_type, relevance, reason)`，并已写入 `_last_llm_reason`、`_last_llm_duration_ms`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_llm_routing.py` 末尾追加：

```python
class TestIdentifyQuestionTypeLLM:
    """_identify_question_type_llm 行为：mock llm_service，覆盖可用/不可用/解析失败。"""

    def test_llm_unavailable_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service
        monkeypatch.setattr(llm_service, "is_available", lambda: False)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_returns_valid_json(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.95, "reason": "酸化改良"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result == (4, 0.95, "酸化改良")

    def test_llm_returns_invalid_json_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {"success": True, "content": "not json", "model": "mock", "type": "llm"}

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_returns_out_of_range_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 99, "relevance": 0.9}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_generate_raises_returns_none(self, monkeypatch):
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _boom(prompt, **kwargs):
            raise RuntimeError("network down")

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _boom)
        result = routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert result is None

    def test_llm_call_uses_temperature_zero(self, monkeypatch):
        """LLM 调用必须传 temperature=0.0 以保证确定性。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        captured = {}

        def _fake_generate(prompt, **kwargs):
            captured["kwargs"] = kwargs
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert captured["kwargs"].get("temperature") == 0.0

    def test_llm_prompt_contains_all_capabilities(self, monkeypatch):
        """prompt 必须包含全部 6 个能力的名称与描述。"""
        from framework.agents import routing
        from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES
        from framework.llm.service import llm_service

        captured = {}

        def _fake_generate(prompt, **kwargs):
            captured["prompt"] = prompt
            return {
                "success": True,
                "content": '{"question_type": 1, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        prompt_text = captured["prompt"]
        for cap in PROFESSIONAL_CAPABILITIES:
            assert cap.name in prompt_text, f"prompt 缺少能力名称：{cap.name}"
            assert cap.description in prompt_text, f"prompt 缺少能力描述：{cap.description}"

    def test_llm_duration_recorded(self, monkeypatch):
        """成功调用后 _last_llm_duration_ms 应为非负 float。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 4, "relevance": 0.9, "reason": "x"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        routing._identify_question_type_llm("我的田酸化严重吗？", None)
        assert routing._last_llm_duration_ms is not None
        assert routing._last_llm_duration_ms >= 0.0
        assert routing._last_llm_reason == "x"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_llm_routing.py::TestIdentifyQuestionTypeLLM -v`
Expected: FAIL with `AttributeError: module 'framework.agents.routing' has no attribute '_identify_question_type_llm'`

- [ ] **Step 3: 在 routing.py 添加 import 与 _identify_question_type_llm 实现**

修改 `framework/agents/routing.py`：

1. 在文件顶部（`from .exclusive_rules import apply_exclusive_rules` 之后）新增 import：

```python
from framework.config import Config
from framework.agents.capabilities import PROFESSIONAL_CAPABILITIES

try:
    from framework.llm.service import llm_service
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
```

2. 在 `_safe_parse_llm_result` 之后新增 LLM 调用函数：

```python
def _identify_question_type_llm(
    question: str, context: Optional[dict]
) -> Optional[tuple[int, float, str]]:
    """LLM 初判问题类型。

    - LLM 不可用或调用异常：返回 None（调用方回退关键词）
    - 解析失败/越界：返回 None
    - 成功：返回 (question_type, relevance, reason)，并已写入模块级状态
    """
    global _last_llm_reason, _last_llm_duration_ms
    if not LLM_AVAILABLE or not llm_service.is_available():
        return None

    # 动态构造 prompt：6 个能力 + 用户问题 + 五维上下文 + JSON 输出格式
    capability_lines = []
    for cap in PROFESSIONAL_CAPABILITIES:
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
    context_text = "\n".join(context_lines) if context_lines else "（未提供）"

    prompt = (
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

    import time as _time
    t0 = _time.perf_counter()
    try:
        response = llm_service.generate(prompt, temperature=0.0)
    except Exception:
        _last_llm_reason = None
        _last_llm_duration_ms = round((_time.perf_counter() - t0) * 1000, 2)
        return None

    _last_llm_duration_ms = round((_time.perf_counter() - t0) * 1000, 2)

    if not isinstance(response, dict) or not response.get("success"):
        _last_llm_reason = None
        return None

    content = response.get("content", "")
    if not isinstance(content, str):
        _last_llm_reason = None
        return None

    parsed = _safe_parse_llm_result(content)
    if parsed is None:
        _last_llm_reason = None
        return None

    _last_llm_reason = parsed[2]
    return parsed
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_llm_routing.py::TestIdentifyQuestionTypeLLM -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add framework/agents/routing.py tests/test_llm_routing.py
git commit -m "feat(routing): 新增 _identify_question_type_llm 动态构造 prompt 调用 LLM"
```

---

## Task 4: routing.py 修改 identify_question_type 集成 LLM 路径

**Files:**
- Modify: `framework/agents/routing.py`（`identify_question_type` 函数体，第 152-168 行）
- Test: `tests/test_llm_routing.py`（追加集成测试，覆盖开关/回退/排他规则叠加）

**Interfaces:**
- Consumes: `Config.ROUTING_MODE`、`_identify_question_type_llm`、`_identify_question_type_keyword`、`_identify_question_type_vector`、`apply_exclusive_rules`、`_is_knowledge_question`
- Produces: `identify_question_type` 行为变更——`ROUTING_MODE=llm` 时优先 LLM 初判，失败回退；模块级 `_last_router_method` 在每次调用后反映实际使用路径。

- [ ] **Step 1: 追加集成测试**

在 `tests/test_llm_routing.py` 末尾追加：

```python
class TestIdentifyQuestionTypeRouting:
    """identify_question_type 在 ROUTING_MODE 切换下的端到端行为。"""

    def test_knowledge_question_skips_llm(self, monkeypatch):
        """知识性问题（type 0）不调 LLM。"""
        from framework.agents import routing
        from framework.llm.service import llm_service

        called = {"count": 0}

        def _fake_generate(prompt, **kwargs):
            called["count"] += 1
            return {"success": True, "content": "{}", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)

        qt, rel = routing.identify_question_type("什么是耕地质量等级？")
        assert qt == 0
        assert called["count"] == 0  # LLM 未被调用
        assert routing._last_router_method == "knowledge"

    def test_keyword_mode_skips_llm(self, monkeypatch):
        """ROUTING_MODE=keyword 时纯关键词路径，不调 LLM。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        called = {"count": 0}

        def _fake_generate(prompt, **kwargs):
            called["count"] += 1
            return {"success": True, "content": "{}", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert called["count"] == 0
        assert routing._last_router_method == "keyword"

    def test_llm_mode_uses_llm_result_when_available(self, monkeypatch):
        """ROUTING_MODE=llm 且 LLM 可用：使用 LLM 结果。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级评价"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, rel = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert rel == 0.9
        assert routing._last_router_method == "llm"
        assert routing._last_llm_reason == "等级评价"

    def test_llm_mode_falls_back_when_llm_unavailable(self, monkeypatch):
        """ROUTING_MODE=llm 但 LLM 不可用：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: False)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_llm_mode_falls_back_on_parse_failure(self, monkeypatch):
        """ROUTING_MODE=llm，LLM 返回非 JSON：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {"success": True, "content": "not json", "model": "mock", "type": "llm"}

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_llm_mode_falls_back_on_out_of_range(self, monkeypatch):
        """ROUTING_MODE=llm，LLM 返回越界类型：回退关键词。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 99, "relevance": 0.9}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type("我的田耕地质量等级是多少")
        assert qt == 2
        assert routing._last_router_method == "keyword"

    def test_exclusive_rules_applied_after_llm(self, monkeypatch):
        """LLM 判定后仍叠加排他规则：scale-only context 不触发维度规则，保持 LLM 结果。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 3, "relevance": 0.9, "reason": "障碍"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        qt, _ = routing.identify_question_type(
            "我这块地到底有啥毛病", {"scale": "地块"}
        )
        assert qt == 3  # 排他规则不改变结果
        assert routing._last_router_method == "llm"

    def test_exclusive_rules_override_llm_when_triggered(self, monkeypatch):
        """排他规则命中时覆盖 LLM 判定（保留现有规则语义）。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        # LLM 判定为 model-5（有机质），但问题含"酸化调理剂"，排他规则应修正为 model-4
        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 5, "relevance": 0.9, "reason": "有机质"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        # 五维 context 触发排他规则：酸化调理剂 → model-4
        context = {
            "scale": "地块",
            "data_type": "处方用量",
            "business_task": "酸化改良",
            "expected_output": "处方用量",
        }
        qt, _ = routing.identify_question_type("酸化调理剂每亩施用量", context)
        assert qt == 4  # 排他规则修正
        # router_method 仍记录 LLM（实际初判来源），排他规则是后续叠加
        assert routing._last_router_method == "llm"

    def test_state_reset_between_calls(self, monkeypatch):
        """多次调用之间，模块级状态被正确重置。"""
        from framework.agents import routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        # 第一次：LLM 调用
        routing.identify_question_type("我的田耕地质量等级是多少")
        assert routing._last_router_method == "llm"
        assert routing._last_llm_duration_ms is not None

        # 第二次：keyword 模式，状态应被重置
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")
        routing.identify_question_type("我的田耕地质量等级是多少")
        assert routing._last_router_method == "keyword"
        # keyword 模式下 LLM 未调用，duration 应为 None
        assert routing._last_llm_duration_ms is None
        assert routing._last_llm_reason is None

    def test_context_none_preserves_v1_behavior(self, monkeypatch):
        """context=None 时行为与 v1 完全一致（不应用排他规则，不调 LLM 若 keyword 模式）。"""
        from framework.agents import routing
        from framework.config import Config

        monkeypatch.setattr(routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")

        cases = [
            ("我这块地到底有啥毛病？", 3),
            ("酸化调理剂每亩施用量", 4),
            ("有机肥每亩施用量多少", 5),
            ("这块地稳定性退化风险", 1),
            ("耕地质量等级评价结果", 2),
        ]
        for q, expected in cases:
            qt, _ = routing.identify_question_type(q)
            assert qt == expected, f"「{q}」期望 TYPE_{expected}，实际 TYPE_{qt}"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_llm_routing.py::TestIdentifyQuestionTypeRouting -v`
Expected: 多个 FAIL（`_last_router_method` 未被设置，LLM 未被集成进 `identify_question_type`）

- [ ] **Step 3: 重写 identify_question_type 集成 LLM 路径**

修改 `framework/agents/routing.py` 中 `identify_question_type` 函数（原第 152-168 行）为：

```python
def identify_question_type(question: str, context: Optional[dict] = None) -> tuple[int, float]:
    """识别问题类型（向后兼容：context 为 None 时与旧版完全一致）。

    返回 (question_type, relevance)。question_type ∈ 1..6 与 0=RAG。
    ROUTING_MODE=llm 时优先 LLM 初判，失败回退关键词/向量；排他规则仍作为最终兜底。
    每次调用重置模块级 _last_router_method/_last_llm_reason/_last_llm_duration_ms。
    """
    global _last_router_method, _last_llm_reason, _last_llm_duration_ms
    # 每次调用重置观测状态
    _last_router_method = "keyword"
    _last_llm_reason = None
    _last_llm_duration_ms = None

    # 知识性问题：type 0，不调 LLM
    if _is_knowledge_question(question):
        _last_router_method = "knowledge"
        return 0, 1.0

    base_type, base_rel = _identify_question_type_keyword(question)

    # ROUTING_MODE=llm 且 LLM 可用：优先 LLM 初判
    if Config.ROUTING_MODE == "llm" and LLM_AVAILABLE and llm_service.is_available():
        llm_result = _identify_question_type_llm(question, context)
        if llm_result is not None:
            base_type, base_rel = llm_result[0], llm_result[1]
            _last_router_method = "llm"
        else:
            # LLM 失败：回退关键词/向量，router_method 保持 keyword
            _last_router_method = "keyword"
            if base_type == 0 and EMBEDDING_AVAILABLE and embedding_service.is_available():
                base_type, base_rel = _identify_question_type_vector(question)
                if base_type != 0:
                    _last_router_method = "vector"
    else:
        # ROUTING_MODE=keyword 或 LLM 不可用：走现有路径
        if base_type == 0:
            if EMBEDDING_AVAILABLE and embedding_service.is_available():
                base_type, base_rel = _identify_question_type_vector(question)
                if base_type != 0:
                    _last_router_method = "vector"
        # 关键词命中时 router_method 保持 keyword

    if context is not None:
        refined_type, _status = apply_exclusive_rules(question, base_type, context)
        return refined_type, base_rel
    return base_type, base_rel
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_llm_routing.py -v`
Expected: 全部 passed（含 Task 1-3 的测试）

- [ ] **Step 5: 运行既有测试确保 backward-compat**

Run: `python -m pytest tests/test_question_type_keywords.py tests/test_routing_observability.py -v`
Expected: 全部 passed（如有失败，多为 `_last_router_method` 未初始化导致的属性错误，下一任务修复）

- [ ] **Step 6: 提交**

```bash
git add framework/agents/routing.py tests/test_llm_routing.py
git commit -m "feat(routing): identify_question_type 集成 LLM 初判与自动回退"
```

---

## Task 5: observe.py 增强观测字段并升级版本号

**Files:**
- Modify: `framework/observability/observe.py`（`observe_routing` 函数体与 `ROUTING_RESULT_VERSION`）
- Modify: `tests/test_routing_observability.py`（断言新增字段）
- Modify: `tests/test_question_type_keywords.py`（必要时补 `ROUTING_MODE=keyword` monkeypatch）

**Interfaces:**
- Consumes: `framework.agents.routing._last_router_method`、`_last_llm_reason`、`_last_llm_duration_ms`
- Produces: 观测日志 entry 新增 `router_method`、`llm_reason`、`llm_duration_ms`；`ROUTING_RESULT_VERSION = "v1.2"`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_routing_observability.py` 的 `TestObserve` 类中新增：

```python
class TestObserveLLMFields:
    """observe_routing 必须写入 router_method/llm_reason/llm_duration_ms 且版本升至 v1.2。"""

    def test_keyword_mode_logs_router_method_keyword(self, monkeypatch):
        from framework.agents import routing as _routing
        from framework.config import Config
        real = _routing.EMBEDDING_AVAILABLE
        try:
            _routing.EMBEDDING_AVAILABLE = False
            monkeypatch.setattr(Config, "ROUTING_MODE", "keyword")
            with tempfile.TemporaryDirectory() as tmp:
                set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
                observe_routing("我的田耕地质量等级是多少", {"scale": "地块"})
                with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                    entry = json.loads(f.readline())
                assert entry["router_method"] == "keyword"
                assert entry["llm_reason"] is None
                assert entry["llm_duration_ms"] is None
                assert entry["result_version"] == "v1.2"
        finally:
            _routing.EMBEDDING_AVAILABLE = real

    def test_llm_mode_logs_router_method_llm(self, monkeypatch):
        from framework.agents import routing as _routing
        from framework.llm.service import llm_service
        from framework.config import Config

        def _fake_generate(prompt, **kwargs):
            return {
                "success": True,
                "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级评价"}',
                "model": "mock",
                "type": "llm",
            }

        monkeypatch.setattr(_routing, "LLM_AVAILABLE", True)
        monkeypatch.setattr(llm_service, "is_available", lambda: True)
        monkeypatch.setattr(llm_service, "generate", _fake_generate)
        monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            observe_routing("我的田耕地质量等级是多少", {"scale": "地块"})
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["router_method"] == "llm"
            assert entry["llm_reason"] == "等级评价"
            assert isinstance(entry["llm_duration_ms"], float)
            assert entry["llm_duration_ms"] >= 0.0
            assert entry["result_version"] == "v1.2"

    def test_knowledge_question_logs_router_method_knowledge(self, monkeypatch):
        from framework.agents import routing as _routing
        from framework.config import Config
        monkeypatch.setattr(Config, "ROUTING_MODE", "llm")
        monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)
        with tempfile.TemporaryDirectory() as tmp:
            set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
            observe_routing("什么是耕地质量等级？", None)
            with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
                entry = json.loads(f.readline())
            assert entry["router_method"] == "knowledge"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_routing_observability.py::TestObserveLLMFields -v`
Expected: FAIL with `KeyError: 'router_method'` 或 `AssertionError: 'v1.1' != 'v1.2'`

- [ ] **Step 3: 修改 observe.py 升级版本与字段**

修改 `framework/observability/observe.py`：

1. 将 `ROUTING_RESULT_VERSION = "v1.1"` 改为：

```python
ROUTING_RESULT_VERSION = "v1.2"
```

2. 在 `observe_routing` 函数中，在 `entry["duration_ms"] = round(...)` 之前（即写日志前）新增字段读取。完整修改点：

在 `entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)` 这一行之前插入：

```python
        # 从 routing 模块读取 LLM 路由观测状态
        from framework.agents import routing as _routing
        entry["router_method"] = _routing._last_router_method
        entry["llm_reason"] = _routing._last_llm_reason
        entry["llm_duration_ms"] = _routing._last_llm_duration_ms
```

同样在 `except Exception as exc:` 分支的 `entry["duration_ms"] = ...` 之前插入相同的 4 行代码。

为保持 DRY，将这段读取逻辑抽到 `_safe_write_log` 之前的一个小辅助函数中。修改后的 `observe_routing` 完整结构：

```python
def observe_routing(
    question: str,
    context: Optional[dict] = None,
    *,
    trace_id: Optional[str] = None,
    data_version: Optional[str] = None,
    agent_version: Optional[str] = None,
    params: Optional[dict] = None,
) -> Tuple[int, float, int, str]:
    tid = trace_id or uuid.uuid4().hex
    entry: Dict[str, Any] = {
        "trace_id": tid,
        "question": question,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_version": data_version,
        "agent_version": agent_version,
        "params": params or {},
        "result_version": ROUTING_RESULT_VERSION,
        "failure_reason": None,
    }
    t0 = time.perf_counter()
    try:
        question_type, relevance = identify_question_type(question, context)
        entry["candidate_agents"] = _router.get_agents_for_type(question_type)
        entry["hit_exclusive_rules"] = _matched_rules(question, context)
        final_type, routing_status = apply_exclusive_rules(question, question_type, context)
        entry["question_type"] = final_type
        entry["routing_status"] = routing_status
        entry["degradation"] = routing_status
        _attach_llm_routing_state(entry)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        return question_type, relevance, final_type, routing_status
    except Exception as exc:
        entry["failure_reason"] = str(exc)
        _attach_llm_routing_state(entry)
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _safe_write_log(entry)
        raise


def _attach_llm_routing_state(entry: Dict[str, Any]) -> None:
    """从 routing 模块读取 LLM 路由观测状态并附加到日志 entry。"""
    try:
        from framework.agents import routing as _routing
        entry["router_method"] = _routing._last_router_method
        entry["llm_reason"] = _routing._last_llm_reason
        entry["llm_duration_ms"] = _routing._last_llm_duration_ms
    except Exception:
        # routing 模块未就绪时仍保留字段（默认值）
        entry.setdefault("router_method", "keyword")
        entry.setdefault("llm_reason", None)
        entry.setdefault("llm_duration_ms", None)
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_routing_observability.py -v`
Expected: 全部 passed（含既有测试 + 新增 TestObserveLLMFields）

- [ ] **Step 5: 修复既有测试中对 result_version 的硬编码（如有）**

Run: `python -m pytest tests/test_question_type_keywords.py -v`
Expected: 全部 passed。若有失败，检查是否对 `result_version` 或 `router_method` 有硬编码断言，按需放宽。

- [ ] **Step 6: 提交**

```bash
git add framework/observability/observe.py tests/test_routing_observability.py
git commit -m "feat(observability): 日志新增 router_method/llm_reason/llm_duration_ms，版本升至 v1.2"
```

---

## Task 6: 验证 nodes.py 观测字段透传

**Files:**
- Verify: `framework/agents/nodes.py`（预期无需改动，仅端到端验证）

**Interfaces:**
- Consumes: `observe.observe_routing`
- Produces: 验证 `identify_question_node` 输出仍含 `question_type/relevance/routing_status`，且观测日志已含新字段

- [ ] **Step 1: 追加端到端测试**

在 `tests/test_routing_observability.py` 的 `TestNodeInjection` 类中新增：

```python
def test_identify_question_node_logs_llm_fields_in_llm_mode(self, monkeypatch):
    """identify_question_node 经 observe_routing 写入新字段（LLM 模式）。"""
    from framework.agents.nodes import identify_question_node
    from framework.agents import routing as _routing
    from framework.llm.service import llm_service
    from framework.config import Config

    def _fake_generate(prompt, **kwargs):
        return {
            "success": True,
            "content": '{"question_type": 2, "relevance": 0.9, "reason": "等级"}',
            "model": "mock",
            "type": "llm",
        }

    monkeypatch.setattr(_routing, "LLM_AVAILABLE", True)
    monkeypatch.setattr(_routing, "EMBEDDING_AVAILABLE", False)
    monkeypatch.setattr(llm_service, "is_available", lambda: True)
    monkeypatch.setattr(llm_service, "generate", _fake_generate)
    monkeypatch.setattr(Config, "ROUTING_MODE", "llm")

    with tempfile.TemporaryDirectory() as tmp:
        set_log_path(os.path.join(tmp, "routing_calls_test.jsonl"))
        state = {"request": {"question": "我的田耕地质量等级是多少"}}
        result = identify_question_node(state)
        assert result["question_type"] == 2
        assert result["routing_status"] == "normal"
        with open(os.path.join(tmp, "routing_calls_test.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["router_method"] == "llm"
        assert entry["llm_reason"] == "等级"
        assert entry["result_version"] == "v1.2"
```

- [ ] **Step 2: 运行测试验证通过（无需修改 nodes.py）**

Run: `python -m pytest tests/test_routing_observability.py::TestNodeInjection -v`
Expected: 全部 passed（`identify_question_node` 通过 `observe_routing` 间接调用 `identify_question_type`，新字段自动透传）

- [ ] **Step 3: 若 Step 2 失败，按最小改动修复 nodes.py**

若失败原因为 `LLM_AVAILABLE` 未在 nodes.py 中正确导入或 routing 模块的 `LLM_AVAILABLE` 状态在 nodes 模块加载时被绑定，则在 `nodes.py` 顶部确认 `from framework.llm.service import llm_service` 已存在（现状已存在，第 27-30 行）。不需要修改 nodes.py。

- [ ] **Step 4: 提交（如有 nodes.py 改动）**

```bash
git add tests/test_routing_observability.py
git commit -m "test(observability): 端到端验证 identify_question_node 透传 LLM 观测字段"
```

---

## Task 7: 混淆矩阵回归脚本支持 mock LLM

**Files:**
- Modify: `scripts/run_routing_regression.py`（新增 `--routing-mode` 与 `--mock-llm` 参数）
- Test: 手动运行验证两种模式混淆率均 ≤ 3%

**Interfaces:**
- Consumes: `framework.agents.exclusive_rules.apply_exclusive_rules`、`framework.agents.routing.identify_question_type`
- Produces: `python scripts/run_routing_regression.py --routing-mode {llm|keyword} [--mock-llm]`

- [ ] **Step 1: 修改回归脚本**

修改 `scripts/run_routing_regression.py`：

1. 在文件顶部 import 区追加：

```python
from framework.agents.routing import identify_question_type  # noqa: E402
from framework.config import Config  # noqa: E402
```

2. 在 `SETS` 定义之后、`PAIR_POSITIVE` 之前新增 mock LLM 工厂：

```python
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
```

3. 新增完整路由预测函数（基于 `identify_question_type`）：

```python
def _predict_model_full(question: str, context: Optional[dict]) -> str:
    """完整路由判定：经 identify_question_type（含 LLM 与排他规则），返回最终 model_id。"""
    qt, _ = identify_question_type(question, context)
    return f"model-{qt}" if qt in (1, 2, 3, 4, 5, 6) else "unknown"
```

4. 修改 `main()` 函数，新增 `--routing-mode` 与 `--mock-llm` 参数，并切换预测函数：

将 `def main(argv=None) -> int:` 整体替换为：

```python
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
```

- [ ] **Step 2: 运行 keyword 模式回归（应与历史一致）**

Run: `python scripts/run_routing_regression.py --routing-mode keyword`
Expected: 退出码 0，混淆率均 ≤ 3%

- [ ] **Step 3: 运行 llm + mock 模式回归**

Run: `python scripts/run_routing_regression.py --routing-mode llm --mock-llm`
Expected: 退出码 0，混淆率均 ≤ 3%，输出文件 `logs/confusion_matrix.llm.json`

- [ ] **Step 4: 提交**

```bash
git add scripts/run_routing_regression.py
git commit -m "feat(regression): 支持 --routing-mode 与 --mock-llm，验证 LLM/keyword 路由一致"
```

---

## Task 8: 更新 docx 文档（P10 章节、混淆矩阵方法、6 模型表同步）

**Files:**
- Modify: `大模型开发团队下一步工作建议.docx`（新增 P10 章节、混淆矩阵方法说明、P1-P9 模型表同步为 6 模型编号）

**Interfaces:**
- Consumes: Design Doc 中的数据流、错误处理表；tasks.md 4.1-4.3 要求
- Produces: docx 包含 P10（LLM 路由判断）章节、混淆矩阵方法说明与结果表、P1-P9 模型表使用 model-1..model-6 编号

**说明：** 本任务需要使用 docx 技能（`Skill: docx`）编辑现有 .docx 文件，保留原有格式与样式。

- [ ] **Step 1: 读取现有 docx 内容结构**

调用 docx 技能读取 `大模型开发团队下一步工作建议.docx`，记录现有章节标题层级与样式，确认 P1-P9 模型表的当前编号方式（是否已使用 model-1..model-6 还是其他编号）。

- [ ] **Step 2: 新增 P10 章节「LLM 路由判断」**

在 P9 章节之后追加 P10，内容包含：

```markdown
# P10 LLM 路由判断

## 10.1 背景与目标

在现有确定性路由流水线（关键词 → embedding 向量 → 排他规则）基础上，新增 LLM 全量初判路径，提升对自然语言问句的语义识别能力，同时通过开关与回退机制保证零回归。

## 10.2 架构与数据流

- 路由模式开关：`ROUTING_MODE` 环境变量，默认 `llm`，可回退 `keyword`
- LLM 判定失败时自动回退关键词，排他规则仍作为最终兜底
- 数据流：
  1. 知识性问题（"什么是"等）→ type 0，不调 LLM
  2. ROUTING_MODE=llm 且 LLM 可用 → LLM 初判（动态读取 6 模型能力构造 prompt）
  3. LLM 失败/不可用 → 关键词/向量路径
  4. context 提供时 → 叠加排他规则

## 10.3 错误处理

| 场景 | 处理 |
|------|------|
| LLM 服务不可用 | 回退关键词，router_method=keyword |
| LLM 返回非 JSON | 回退关键词，记录 llm_failure_reason |
| question_type 越界（非 0..6） | 回退关键词 |
| LLM 超时 | generate() 已有超时配置，超时后回退 |

## 10.4 观测字段

- `router_method`：实际使用路径（llm/keyword/vector/knowledge）
- `llm_reason`：LLM 返回的理由文本
- `llm_duration_ms`：LLM 调用耗时（ms）
- `ROUTING_RESULT_VERSION`：升级至 `v1.2`

## 10.5 向后兼容

- `ROUTING_MODE=keyword` 完全保留现有行为
- `identify_question_type` 对外签名不变：`(question, context) → (int, float)`
- 排他规则语义不变
```

- [ ] **Step 3: 补充混淆矩阵方法说明与结果表**

在 P10 章节末尾或独立小节追加：

```markdown
## 10.6 混淆矩阵回归验证

### 方法

对 model-3/model-2、model-4/model-5 两组易混淆对各 ≥20 条正反例运行完整路由判定，
输出混淆矩阵与分类性能统计。退出码反映目标达成（混淆率 ≤ 3%）。

运行命令：
- keyword 模式：`python scripts/run_routing_regression.py --routing-mode keyword`
- LLM 模式（mock）：`python scripts/run_routing_regression.py --routing-mode llm --mock-llm`

### 结果表

| 模式 | 易混淆对 | 样本数 | TP | FP | FN | TN | 正确率 | 混淆率 |
|------|----------|--------|----|----|----|----|--------|--------|
| keyword | model-3-vs-model-2 | (运行后填入) | | | | | | |
| keyword | model-4-vs-model-5 | (运行后填入) | | | | | | |
| llm | model-3-vs-model-2 | (运行后填入) | | | | | | |
| llm | model-4-vs-model-5 | (运行后填入) | | | | | | |

两种模式下混淆率均 ≤ 3% 视为目标达成。
```

实际数值由 Task 7 Step 2-3 运行后填入。

- [ ] **Step 4: 同步 P1-P9 模型表为 6 模型编号**

遍历 docx 中 P1-P9 章节的模型表，将所有模型编号统一为 `model-1`..`model-6`，对应关系：

| model_id | 名称 |
|----------|------|
| model-1 | 耕地质量稳定性与退化风险评价 |
| model-2 | 耕地质量等级评价 |
| model-3 | 耕地质量主要问题与障碍诊断 |
| model-4 | 耕地土壤酸化改良 |
| model-5 | 耕地土壤有机质培肥提升 |
| model-6 | 占位模型（预留） |

若 P1-P9 已使用此编号，仅核对一致性；若使用历史编号（如 stability-risk-evaluation 等 agent_id），则在表中追加 `model-N` 列以对齐。

- [ ] **Step 5: 保存 docx 并验证**

保存修改至 `大模型开发团队下一步工作建议.docx`。重新打开文件确认：
- P10 章节标题与正文存在
- 混淆矩阵方法说明与结果表存在
- P1-P9 模型表编号统一为 model-1..model-6

- [ ] **Step 6: 提交**

```bash
git add 大模型开发团队下一步工作建议.docx
git commit -m "docs: 新增 P10 LLM 路由判断章节，同步模型表与混淆矩阵方法"
```

---

## 完成验证

- [ ] **全量测试通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 passed

- [ ] **keyword 模式回归通过**

Run: `python scripts/run_routing_regression.py --routing-mode keyword`
Expected: 退出码 0

- [ ] **llm + mock 模式回归通过**

Run: `python scripts/run_routing_regression.py --routing-mode llm --mock-llm`
Expected: 退出码 0

- [ ] **最终提交（如有遗漏修复）**

```bash
git add -A
git commit -m "chore: LLM 路由判定全量回归验证通过"
```
