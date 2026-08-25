"""耕地领域同义词预处理：查询整词替换为规范术语。"""
from __future__ import annotations

import json
import os
import re
from typing import Dict

_SYNONYM_PATH = os.path.join(os.path.dirname(__file__), "soil_synonyms.json")
_ASCII_WORD = re.compile(r"[0-9A-Za-z_]")

_cache = None


def load_synonyms() -> Dict[str, list]:
    """读取词表 JSON 返回 {规范词: [同义词...]}；文件缺失/解析失败返回 {}，不抛异常。"""
    global _cache
    if _cache is not None:
        return _cache
    data: Dict[str, list] = {}
    try:
        with open(_SYNONYM_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        data = {}
    _cache = data
    return data


def _is_word_char(ch: str) -> bool:
    """整词边界：英文字母/数字/下划线视为"词内字符"，两侧出现时不做替换。"""
    return bool(_ASCII_WORD.match(ch))


def normalize_query(text: str) -> str:
    """整词同义词替换：同义词 → 规范词。

    - 词表为空或文本为空 → 原样返回
    - 长同义词优先匹配，避免子串误伤（如"水解性氮"先于"水解性"）
    - 仅整词匹配：同义词两侧若接英文字母/数字/下划线则跳过
    """
    synonyms = load_synonyms()
    if not synonyms or not text:
        return text

    pairs = []
    for canonical, alts in synonyms.items():
        for alt in alts:
            pairs.append((alt, canonical))
    pairs.sort(key=lambda p: -len(p[0]))

    result = text
    for alt, canonical in pairs:
        pattern = re.compile(re.escape(alt))
        current = result

        def _repl(m, current=current):
            start, end = m.start(), m.end()
            if start > 0 and _is_word_char(current[start - 1]):
                return m.group(0)
            if end < len(current) and _is_word_char(current[end]):
                return m.group(0)
            return canonical

        result = pattern.sub(_repl, current)
    return result