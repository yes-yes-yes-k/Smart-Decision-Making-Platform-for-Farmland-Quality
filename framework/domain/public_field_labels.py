"""面向用户的专业字段中文名称与文本转换。

模型计算和 API 结构化字段继续使用稳定的内部代码；只有自然语言回复、报告等
面向用户的文本在出口处转换，避免内部缩写泄漏到界面。
"""
from __future__ import annotations

import re
from typing import Any


# 所有会进入专题模型提示词或结果摘要的业务字段都在这里维护。映射值使用业务
# 界面采用的标准中文名称，不把内部代码附加在中文名称后面。
PUBLIC_FIELD_LABELS: dict[str, str] = {
    # 耕地质量评价与障碍诊断（Model-2 / Model-3）
    "SJD": "土壤酸碱度",
    "YJZ": "有机质",
    "YXL": "有效磷",
    "SXJ": "速效钾",
    "TRRZ": "土壤容重",
    "GCZD": "耕层质地",
    "GGNL": "灌溉能力",
    "PSNL": "排水能力",
    "DXBW": "地形部位",
    "ZDGX": "质地构型",
    "YXTCHD": "有效土层厚度",
    "GCHD": "耕层厚度",
    # 酸化改良（Model-4）
    "JHX": "交换性氢",
    "JLA": "交换性铝",
    "YTK": "土壤调理剂（亿土康）",
    "MBNT": "木本泥炭",
    # 有机质培肥（Model-5）
    "SOCbe": "初始土壤有机碳",
    "SOMbe": "初始土壤有机质",
    "SOC": "土壤有机碳",
    "TN": "全氮",
    "TP": "全磷",
    "TK": "全钾",
    "AP": "有效磷",
    "AK": "速效钾",
    "Gap": "有机质提升目标",
    "Dose": "建议施用量",
    "TD": "全氮",
    "TL": "全磷",
    "TJ": "全钾",
    "YJZTSZ": "有机质提升目标",
    "YJFLX": "肥料类型",
    "Fertilizer type": "肥料类型",
    "pH": "土壤酸碱度",
}


# 面向非技术业务用户的标准术语解释。只有在最终答复文本中实际出现该术语时才
# 追加，且同一解释不会重复追加，保证答复出口幂等。
PUBLIC_TERM_EXPLANATIONS: dict[str, str] = {
    "综合指数": "耕地质量综合指数，是 0~1 之间的综合得分，越接近 1 表示耕地质量越好",
    "耕地质量等级": "按综合指数划分的 1~10 等，数字越小表示质量越好",
    "有机肥建议施用量": "模型估算的每亩有机肥用量（公斤/亩），实际用量需结合田间试验核定",
    "土壤有机碳预测值": "模型预测的土壤有机碳含量（g/kg），是反映土壤有机质水平的核心指标",
    "障碍因素": "限制耕地质量提升的土壤或管理因素，分为主要和次要障碍因素",
}


_SOURCE_WORD_CHAR = re.compile(r"[A-Za-z0-9_-]")
_TERMS_BY_LENGTH = tuple(
    sorted(PUBLIC_FIELD_LABELS, key=lambda item: (-len(item), item.casefold()))
)


def _is_source_word_char(char: str | None) -> bool:
    return bool(char and _SOURCE_WORD_CHAR.fullmatch(char))


class PublicTextStreamTranslator:
    """跨流式分片转换专业字段，能够处理 ``GG`` + ``NL`` 这类拆分。"""

    def __init__(self) -> None:
        self._buffer = ""
        self._previous_source_char: str | None = None

    def feed(self, value: Any, *, final: bool = False) -> str:
        if value is not None:
            self._buffer += str(value)

        rendered: list[str] = []
        while self._buffer:
            # 字段必须从独立词边界开始，避免修改 GGNLcode、XGGNL 等机器标识。
            at_left_boundary = not _is_source_word_char(self._previous_source_char)
            folded = self._buffer.casefold()

            if at_left_boundary:
                # 当前分片可能只是较长字段的前缀，非终止状态下先等待后续字符。
                if not final and any(
                    len(self._buffer) < len(term)
                    and term.casefold().startswith(folded)
                    for term in _TERMS_BY_LENGTH
                ):
                    break

                matched = None
                for term in _TERMS_BY_LENGTH:
                    if folded.startswith(term.casefold()):
                        matched = term
                        break
                if matched is not None:
                    if len(self._buffer) == len(matched) and not final:
                        # 还需要一个字符才能确认右边界。
                        break
                    right_char = (
                        self._buffer[len(matched)]
                        if len(self._buffer) > len(matched)
                        else None
                    )
                    if not _is_source_word_char(right_char):
                        rendered.append(PUBLIC_FIELD_LABELS[matched])
                        self._previous_source_char = matched[-1]
                        self._buffer = self._buffer[len(matched):]
                        continue

            source_char = self._buffer[0]
            rendered.append(source_char)
            self._previous_source_char = source_char
            self._buffer = self._buffer[1:]

        return "".join(rendered)

    def flush(self) -> str:
        return self.feed(None, final=True)


def public_field_label(value: Any) -> str:
    """返回单个内部字段的中文名称；未知字段原样返回。"""
    text = str(value)
    direct = PUBLIC_FIELD_LABELS.get(text)
    if direct is not None:
        return direct
    folded = text.casefold()
    return next(
        (label for term, label in PUBLIC_FIELD_LABELS.items() if term.casefold() == folded),
        text,
    )


def translate_public_text(value: Any) -> str:
    """将自然语言文本中的独立专业字段代码转换为标准中文名称。"""
    translator = PublicTextStreamTranslator()
    return translator.feed(value) + translator.flush()


_TERM_SECTION = "\n\n术语说明：\n"


def append_term_explanations(value: Any) -> str:
    """在文本末尾追加实际出现术语的标准解释。

    空文本原样返回；只追加正文中已出现的术语，且若解释原文已存在于文本中则
    跳过。已有术语说明区时只补缺失条目，因此重复调用保持幂等。
    """
    text = "" if value is None else str(value)
    if not text.strip():
        return text
    body, marker, existing = text.partition(_TERM_SECTION)
    explained = {
        line.strip()[2:].split("：", 1)[0]
        for line in existing.splitlines()
        if line.strip().startswith("- ") and "：" in line.strip()
    } if marker else set()
    missing = [
        f"- {term}：{explanation}"
        for term, explanation in PUBLIC_TERM_EXPLANATIONS.items()
        if term in body and term not in explained and explanation not in text
    ]
    if not missing:
        return text
    if marker:
        return text.rstrip() + "\n" + "\n".join(missing)
    return text.rstrip() + _TERM_SECTION + "\n".join(missing)


__all__ = [
    "PUBLIC_FIELD_LABELS",
    "PUBLIC_TERM_EXPLANATIONS",
    "PublicTextStreamTranslator",
    "append_term_explanations",
    "public_field_label",
    "translate_public_text",
]
