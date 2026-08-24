from __future__ import annotations
from typing import List

from framework.config import Config


def split_text(text: str, size: int = None, overlap: int = None) -> List[str]:
    """滑动窗口分块，参数缺省读 Config.CHUNK_SIZE / Config.CHUNK_OVERLAP。

    - size <= 0 或文本为空/纯空白 → 返回 []
    - len(text) <= size → 返回单个完整块
    - step = size - overlap；overlap >= size 时退化为 step = size（无重叠）
    - 末块不足 size 仍保留
    """
    if size is None:
        size = Config.CHUNK_SIZE
    if overlap is None:
        overlap = Config.CHUNK_OVERLAP

    if not text or not text.strip() or size <= 0:
        return []
    if len(text) <= size:
        return [text]

    step = size - overlap
    if step <= 0:
        step = size  # overlap >= size 时退化为无重叠，避免无限循环

    chunks: List[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks