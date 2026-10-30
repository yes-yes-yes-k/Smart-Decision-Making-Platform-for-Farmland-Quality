"""Deterministic text repair for parsed PDF chunks.

Handles three defects seen in the frozen corpus: running headers/footers that
repeat on every page, letter-spaced words ("E c o t o x i c o l o g y"), and
page-number-only lines. It never rewrites body wording: unknown fragments such
as "ethodology," are left untouched and reported instead of being guessed.
"""
from __future__ import annotations

import re
from collections import Counter

VERSION = "text-cleanup-v1"

_SPACED_LETTERS = re.compile(r"(?:\b[A-Za-z]\s){5,}[A-Za-z]\b")
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s*)?\d{1,4}\s*$", re.I)
_HAS_LETTER = re.compile(r"[A-Za-z\u4e00-\u9fff]")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _normalized(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().casefold()


def _looks_like_sentence(line: str) -> bool:
    """A long line ending in punctuation is body text, even if it repeats."""
    stripped = line.strip()
    if len(stripped.split()) < 8:
        return False
    return stripped.endswith((".", "!", "?", "。", "！", "？"))


def repeated_lines(texts: list[str], *, minimum_pages: int = 3, ratio: float = 0.3) -> set[str]:
    """Running headers/footers: repeated lines that sit at a chunk edge.

    A body sentence can repeat by chance; a header repeats at the top or bottom
    of the page. Requiring an edge position keeps repeated body text intact.
    """
    counts: Counter[str] = Counter()
    edges: Counter[str] = Counter()
    for text in texts:
        lines = [line for line in _lines(text) if len(_normalized(line)) >= 8]
        if not lines:
            continue
        counts.update({_normalized(line) for line in lines})
        edge_lines = {_normalized(lines[0]), _normalized(lines[-1])}
        edges.update({line for line in edge_lines if not _looks_like_sentence(line)})
    threshold = max(minimum_pages, int(len(texts) * ratio))
    return {line for line, count in edges.items()
            if count >= threshold and count / counts[line] >= 0.6}


def collapse_spaced_letters(text: str) -> tuple[str, int]:
    """Join words that the layout split into single letters."""
    total = 0

    def join(match: re.Match) -> str:
        nonlocal total
        total += 1
        return re.sub(r"\s+", "", match.group(0))

    return _SPACED_LETTERS.sub(join, text), total


def clean_text(text: str, headers: set[str] | None = None) -> tuple[str, dict]:
    """Repair one chunk; returns the cleaned text and a small audit record."""
    dropped = 0
    spaced_headers = 0
    kept = []
    for line in _lines(text):
        key = _normalized(line)
        if len(_SPACED_LETTERS.findall(line)) and len(re.findall(r"\b[A-Za-z]\b", line)) >= 8:
            # A run of single letters is a letter-spaced running header; body text never is.
            dropped += 1
            spaced_headers += 1
            continue
        if headers and key in headers:
            dropped += 1
            continue
        if _PAGE_NUMBER.match(line) and not _HAS_LETTER.search(line):
            dropped += 1
            continue
        kept.append(line)
    joined, spaced = collapse_spaced_letters("\n".join(kept))
    cleaned = "\n".join(_MULTI_SPACE.sub(" ", line).rstrip() for line in joined.splitlines())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, {"dropped_lines": dropped, "spaced_headers": spaced_headers,
                     "collapsed_words": spaced,
                     "characters_before": len(text), "characters_after": len(cleaned)}


def clean_chunks(chunks: list[dict], *, field: str = "content") -> tuple[list[dict], dict]:
    """Clean a document's chunks with headers detected across the whole document."""
    headers = repeated_lines([chunk.get(field) or "" for chunk in chunks])
    cleaned, totals = [], {"chunks": len(chunks), "dropped_lines": 0, "spaced_headers": 0,
                           "collapsed_words": 0, "changed_chunks": 0,
                           "headers_removed": len(headers)}
    for chunk in chunks:
        text, audit = clean_text(chunk.get(field) or "", headers)
        totals["dropped_lines"] += audit["dropped_lines"]
        totals["spaced_headers"] += audit["spaced_headers"]
        totals["collapsed_words"] += audit["collapsed_words"]
        if text != (chunk.get(field) or ""):
            totals["changed_chunks"] += 1
        cleaned.append(dict(chunk, **{field: text}))
    totals["version"] = VERSION
    return cleaned, totals


def unmatched_fragments(chunks: list[dict], *, field: str = "content", minimum: int = 1) -> list[dict]:
    """Report very short or obviously truncated chunks instead of repairing them."""
    problems = []
    for chunk in chunks:
        text = (chunk.get(field) or "").strip()
        words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", text)
        if len(text) < 40 or (text and not text[0].isupper() and text[0].islower()
                              and len(words) <= 3):
            problems.append({"chunk_index": chunk.get("chunk_index"), "length": len(text),
                             "preview": text[:40]})
    return problems
