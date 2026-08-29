"""文档解析后文本清洗：NFKC 规范化、去控制字符、合并空白、去重复页眉页脚。"""
from __future__ import annotations
import re
import unicodedata
from collections import Counter

# 不可见控制字符（保留 \t \n \r）
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# 连续空白（3+ 个）压成 2 个
_MULTI_WS_RE = re.compile(r"[ \t]{3,}")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """规范化文本：Unicode NFKC → 去控制字符 → 合并空白 → 去重复页眉页脚。

    纯函数，可独立单测。被 document_parser 各 _parse_* 出口调用。
    """
    if not text:
        return ""
    # 1. Unicode NFKC 规范化（全角→半角、兼容字符归一）
    text = unicodedata.normalize("NFKC", text)
    # 2. 去不可见控制字符
    text = _CONTROL_RE.sub("", text)
    # 3. 合并连续空白
    text = _MULTI_WS_RE.sub("  ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    # 4. 去重复页眉页脚
    text = _strip_repeated_header_footer(text)
    # 纯空白输入（含 \t \n \r）返回空；否则只去除首尾空格，保留 \t \n \r
    if not text.strip():
        return ""
    return text.strip(" ")


def _strip_repeated_header_footer(text: str) -> str:
    """跨页重复 ≥ 3 次的行视为页眉/页脚并去除。

    实现：按 \\n 切行，统计行内容 hash 频率；频次 ≥ 3 的非空行去除。
    保留单页内容（即使恰好与页眉相同也不去除，因为是页眉的话必然多次重复）。
    """
    lines = text.split("\n")
    if len(lines) < 6:
        return text
    freq = Counter(line.strip() for line in lines if line.strip())
    repeated = {h for h, c in freq.items() if c >= 3}
    if not repeated:
        return text
    return "\n".join(line for line in lines if line.strip() not in repeated)
