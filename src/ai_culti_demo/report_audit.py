"""报告生成后的数字审计。

报告章节由语言模型生成，提示词层面的“不得编造”不足以保证输出只引用输入事实。
本模块在报告拼接前对语言模型章节做机器可验证的检查：

1. 从报告上下文与数据章节构建数值白名单；
2. 抽取带单位或预测性语义的定量表述；
3. 无法在白名单中追溯的数值替换为“暂无可靠估计”，并记录问题清单。

审计不做语义判断，也不调用语言模型，结果可复现。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

#: 问题码：报告中出现输入不存在的定量内容。
UNGROUNDED_QUANTITATIVE_CLAIM = "UNGROUNDED_QUANTITATIVE_CLAIM"

#: 无依据时的统一表述。
FALLBACK_TEXT = "暂无可靠估计"

#: 带单位即视为敏感定量表述（长单位在前，避免被短单位截断）。
_SENSITIVE_NUMBER = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|％|g/kg|mg/kg|kg/亩|kg/ha|t/ha|吨/亩|吨|万元/亩|元/亩|kg|万元|元|倍|亩|cm)"
)

#: pH 数值本身没有单位，单独识别。
_PH_NUMBER = re.compile(r"pH\s*(?:值)?\s*[:：]?\s*(?P<num>\d+(?:\.\d+)?)", re.IGNORECASE)

#: 没有单位，但在预测性句子里出现的时长（如“预计 1-2 年见效”）。
_BARE_NUMBER = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>年|个月|月)")

_PREDICTIVE_VERBS = ("提升", "增产", "提高", "增幅", "增效", "效益", "见效", "提高至", "预计", "可达到", "达到")

_TAG = re.compile(r"<[^>]*>")
_TAG_SPLIT = re.compile(r"(<[^>]*>)")


@dataclass(frozen=True)
class _Claim:
    """一处待审的定量表述；``start``/``end`` 为替换范围。"""

    text: str
    value: float
    start: int
    end: int


def _iter_numbers(value: Any) -> Iterable[float]:
    """递归抽取任意结构中的数值（字符串中的数字也计入）。"""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, str):
        for match in re.finditer(r"-?\d+(?:\.\d+)?", value):
            token = match.group()
            # 字符串里的孤立数字通常是编号或版本的一部分（如 "v2"），
            # 只有长度 >= 3 或带小数点的数值才纳入白名单。
            if len(token.lstrip("-")) < 3 and "." not in token:
                continue
            try:
                yield float(token)
            except ValueError:  # pragma: no cover - 正则保证可解析
                continue
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_numbers(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_numbers(item)


def collect_allowed_numbers(*sources: Any) -> list[float]:
    """收集允许出现在报告中的数值（上下文 + 数据章节 HTML）。"""
    allowed: list[float] = []
    for source in sources:
        allowed.extend(_iter_numbers(source))
    return allowed


def is_grounded(value: float, allowed: Iterable[float]) -> bool:
    """数值是否能在白名单中追溯。

    允许 1% 相对误差与 0.05 绝对误差，覆盖四舍五入和单位换算后的展示差异。
    """
    for candidate in allowed:
        if abs(value - candidate) <= max(0.05, abs(candidate) * 0.01):
            return True
    return False


def _extract_claims(text: str) -> list[_Claim]:
    """抽取需要审计的定量表述，按位置排序并去除重叠。"""
    claims: list[_Claim] = []
    for match in _SENSITIVE_NUMBER.finditer(text):
        claims.append(_Claim(
            text=match.group(0).strip(),
            value=float(match.group("num")),
            start=match.start(),
            end=match.end(),
        ))
    for match in _PH_NUMBER.finditer(text):
        # 只替换数值本身，保留“pH”这一说明文字。
        claims.append(_Claim(
            text=match.group(0).strip(),
            value=float(match.group("num")),
            start=match.start("num"),
            end=match.end("num"),
        ))
    if any(verb in text for verb in _PREDICTIVE_VERBS):
        for match in _BARE_NUMBER.finditer(text):
            claims.append(_Claim(
                text=match.group(0).strip(),
                value=float(match.group("num")),
                start=match.start(),
                end=match.end(),
            ))

    claims.sort(key=lambda item: item.start)
    merged: list[_Claim] = []
    for claim in claims:
        if merged and claim.start < merged[-1].end:
            continue
        merged.append(claim)
    return merged


def audit_section(
    heading: str,
    html: str,
    allowed: list[float],
) -> tuple[str, dict[str, Any]]:
    """审计单个章节，返回（净化后的 HTML, 本章节审计结果）。"""
    checked = 0
    grounded = 0
    issues: list[dict[str, Any]] = []

    # 按标签切分，只在文本片段内检索与替换，避免命中标签属性里的数字。
    parts = _TAG_SPLIT.split(html or "")
    for index, part in enumerate(parts):
        if not part or part.startswith("<"):
            continue
        claims = _extract_claims(part)
        if not claims:
            continue
        rebuilt: list[str] = []
        cursor = 0
        for claim in claims:
            checked += 1
            if is_grounded(claim.value, allowed):
                grounded += 1
                continue
            issues.append({
                "code": UNGROUNDED_QUANTITATIVE_CLAIM,
                "section": heading,
                "claim": claim.text,
                "message": f"数值 {claim.text} 未出现在报告输入中，已按“{FALLBACK_TEXT}”处理。",
            })
            rebuilt.append(part[cursor:claim.start])
            rebuilt.append(FALLBACK_TEXT)
            cursor = claim.end
        if rebuilt:
            rebuilt.append(part[cursor:])
            parts[index] = "".join(rebuilt)

    return "".join(parts), {
        "checked_claims": checked,
        "grounded_claims": grounded,
        "issues": issues,
    }


def audit_report_sections(
    sections: Iterable[Mapping[str, Any]],
    allowed: list[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """审计全部语言模型章节。

    Args:
        sections: 每项包含 ``heading`` 与 ``content``。
        allowed: 数值白名单。

    Returns:
        （净化后的章节列表, 汇总审计信息）。
    """
    sanitized: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    checked = 0
    grounded = 0

    for section in sections:
        heading = str(section.get("heading") or "")
        content, result = audit_section(heading, str(section.get("content") or ""), allowed)
        checked += result["checked_claims"]
        grounded += result["grounded_claims"]
        issues.extend(result["issues"])
        sanitized.append({**section, "content": content})

    summary = {
        "checked_claims": checked,
        "grounded_claims": grounded,
        "ungrounded_claims": len(issues),
        "issues": issues,
    }
    return sanitized, summary


def collect_imputed_inputs(*sources: Any) -> dict[str, list[str]]:
    """从上下文收集被回填或被默认的输入字段，按来源分类。

    支持 ``imputed_features``、``imputed_inputs`` 与 ``provenance`` 三类键。
    """
    collected: dict[str, set[str]] = {"imputed_features": set(), "imputed_inputs": set(), "provenance": set()}

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in {"imputed_features", "imputed_inputs"} and isinstance(value, (list, tuple, set)):
                    for item in value:
                        if item:
                            collected[key].add(str(item))
                elif key == "provenance" and isinstance(value, Mapping):
                    for field, source in value.items():
                        if str(source) in {"region_mean_backfill", "default"}:
                            collected["provenance"].add(f"{field}（{source}）")
                else:
                    walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    for source in sources:
        walk(source)
    return {key: sorted(values) for key, values in collected.items() if values}


def strip_tags(html: str) -> str:
    """去掉 HTML 标签，保留纯文本（供测试与日志使用）。"""
    return _TAG.sub("", html or "")
