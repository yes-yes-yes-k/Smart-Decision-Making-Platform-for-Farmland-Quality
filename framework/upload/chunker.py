from __future__ import annotations
from typing import List, Tuple

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


def split_text_with_pages(
    pages: List[Tuple[int, str]],
    size: int = None,
    overlap: int = None,
) -> List[Tuple[str, int]]:
    """按页切分文本，返回 (chunk_text, page_num) 列表。

    - pages: [(page_num, page_text)]，page_num 通常从 1 开始
    - 切分逻辑：把每页文本视为独立段，对每页用 split_text 切，跨页不合并
      （保留页码语义清晰，避免 chunk 跨页导致 page 字段歧义）
    - 跨页 chunk 不拼接：每页独立切分后顺序输出
    - 末块不足 size 仍保留
    """
    if not pages:
        return []
    if size is None:
        size = Config.CHUNK_SIZE
    if overlap is None:
        overlap = Config.CHUNK_OVERLAP
    result: List[Tuple[str, int]] = []
    for page_num, page_text in pages:
        if not page_text:
            continue
        chunks = split_text(page_text, size=size, overlap=overlap)
        for c in chunks:
            result.append((c, page_num))
    return result