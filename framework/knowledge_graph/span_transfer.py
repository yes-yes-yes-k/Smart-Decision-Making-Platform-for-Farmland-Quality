"""Map a frozen M1 span onto the current re-parsed chunk set (R2.1 follow-up).

The page-level ``legacy_mapping`` says which new chunks sit on the same page but
explicitly transfers no offsets. This module does the transfer: exact text
first, then whitespace/punctuation-insensitive matching, then a bounded
character alignment. Nothing is guessed silently — every result carries the
method and score, and an unmappable span stays unmapped.
"""
from __future__ import annotations

from difflib import SequenceMatcher

VERSION = "span-transfer-v1"
MIN_ALIGNMENT_RATIO = 0.90
MIN_ALIGNMENT_CHARS = 20
_PUNCTUATION = set("，。、；：？！“”‘’（）《》【】—…·,.;:?!\"'()[]<>/\\|-_=+*&^%$#@~`　")


def _normalize(text: str):
    """Drop whitespace, fold punctuation, keep an index back to the original."""
    kept, index = [], []
    for position, character in enumerate(text):
        if character.isspace():
            continue
        kept.append("|" if character in _PUNCTUATION else character)
        index.append(position)
    return "".join(kept), index


def _span_from_normalized(match, index, offset):
    start = index[offset]
    end = index[offset + match - 1] + 1
    return start, end


def _segments(quote: str) -> list[str]:
    """Sentence-ish pieces; a frozen quote may join text from several chunks."""
    pieces, buffer = [], []
    for character in quote:
        buffer.append(character)
        if character in ".。;；!?！？\n":
            piece = "".join(buffer).strip()
            if len(piece) >= 20:
                pieces.append(piece)
            buffer = []
    tail = "".join(buffer).strip()
    if len(tail) >= 20:
        pieces.append(tail)
    return pieces


def _segment_transfer(quote: str, ordered: list[dict]):
    """Map the longest mappable segments and report coverage, never silent."""
    segments = _segments(quote)
    if not segments:
        return None
    hits, covered = [], 0
    for segment in segments:
        found = None
        for chunk in ordered:
            content = chunk.get("content") or ""
            position = content.find(segment)
            if position >= 0:
                found = {"chunk_index": chunk["chunk_index"], "start": position,
                         "end": position + len(segment), "exact": True}
                break
        if found is None:
            segment_norm, _ = _normalize(segment)
            for chunk in ordered:
                content_norm, index = _normalize(chunk.get("content") or "")
                hit = content_norm.find(segment_norm)
                if hit >= 0:
                    start, end = _span_from_normalized(len(segment_norm), index, hit)
                    found = {"chunk_index": chunk["chunk_index"], "start": start, "end": end,
                             "exact": False}
                    break
        if found:
            found["segment"] = segment
            hits.append(found)
            covered += len(segment)
    if not hits:
        return None
    coverage = round(covered / len(quote), 4)
    first = hits[0]
    method = "segment" if coverage >= 0.8 else "partial"
    return {"method": method, "chunk_index": first["chunk_index"], "start": first["start"],
            "end": first["end"], "score": coverage, "coverage": coverage,
            "segments": len(hits), "segment_exact": all(h["exact"] for h in hits),
            "mapped": coverage >= 0.8}


def transfer_span(quote: str, page: int, new_chunks: list[dict], candidates: list[int] | None = None):
    """Locate ``quote`` on ``page`` inside the new chunks.

    Returns ``{method, chunk_index, start, end, score}`` or ``None`` when the
    quote cannot be placed on that page. Candidates are page-scoped so a quote
    that also appears elsewhere cannot silently move to another page.
    """
    if not isinstance(quote, str) or not quote.strip():
        return None
    ordered = [chunk for chunk in new_chunks if chunk.get("page") == page]
    if candidates:
        allowed = set(candidates)
        scoped = [chunk for chunk in ordered if chunk.get("chunk_index") in allowed]
        ordered = scoped or ordered

    for chunk in ordered:
        content = chunk.get("content") or ""
        position = content.find(quote)
        if position >= 0:
            return {"method": "exact", "chunk_index": chunk["chunk_index"],
                    "start": position, "end": position + len(quote), "score": 1.0}

    quote_norm, _ = _normalize(quote)
    if not quote_norm:
        return None
    for chunk in ordered:
        content_norm, index = _normalize(chunk.get("content") or "")
        hit = content_norm.find(quote_norm)
        if hit >= 0:
            start, end = _span_from_normalized(len(quote_norm), index, hit)
            return {"method": "normalized", "chunk_index": chunk["chunk_index"],
                    "start": start, "end": end, "score": 1.0}

    best = None
    for chunk in ordered:
        content_norm, index = _normalize(chunk.get("content") or "")
        if len(content_norm) < MIN_ALIGNMENT_CHARS:
            continue
        matcher = SequenceMatcher(None, quote_norm, content_norm, autojunk=False)
        if matcher.real_quick_ratio() < MIN_ALIGNMENT_RATIO or matcher.quick_ratio() < MIN_ALIGNMENT_RATIO:
            continue
        blocks = [b for b in matcher.get_matching_blocks() if b.size]
        covered = sum(b.size for b in blocks)
        ratio = covered / len(quote_norm)
        if not blocks or ratio < MIN_ALIGNMENT_RATIO:
            continue
        start = index[blocks[0].b]
        end = index[blocks[-1].b + blocks[-1].size - 1] + 1
        if best is None or ratio > best["score"]:
            best = {"method": "aligned", "chunk_index": chunk["chunk_index"],
                    "start": start, "end": end, "score": round(ratio, 4)}
    if best:
        return best
    return _segment_transfer(quote, ordered)


def transfer_references(references: list[dict], chunks_by_document: dict[int, list[dict]],
                        mapping_by_document: dict[int, dict[int, dict]]):
    """Transfer every reference and report mapped, exact and unmapped counts."""
    rows = []
    for reference in references:
        document_id = reference["document_id"]
        old_chunk = reference["chunk_index"]
        entry = (mapping_by_document.get(document_id) or {}).get(old_chunk) or {}
        page = entry.get("page") or reference.get("page_one_based")
        result = transfer_span(reference.get("quote", ""), page,
                               chunks_by_document.get(document_id, []),
                               entry.get("candidate_new_chunk_indexes"))
        row = {"document_id": document_id, "old_chunk_index": old_chunk,
               "page": page, "quote_sha256_input": reference.get("chunk_text_sha256"),
               "mapped": bool(result and result.get("mapped", True))}
        if result:
            row.update(result)
            row["position_changed"] = (result["chunk_index"] != old_chunk
                                       or result["start"] != reference.get("start"))
            row["old_start"] = reference.get("start")
            row["old_end"] = reference.get("end")
        rows.append(row)
    summary = {"total": len(rows), "mapped": sum(r["mapped"] for r in rows),
               "exact": sum(1 for r in rows if r.get("method") == "exact"),
               "normalized": sum(1 for r in rows if r.get("method") == "normalized"),
               "aligned": sum(1 for r in rows if r.get("method") == "aligned"),
               "segment": sum(1 for r in rows if r.get("method") == "segment"),
               "partial": sum(1 for r in rows if r.get("method") == "partial"),
               "unmapped": sum(1 for r in rows if not r["mapped"])}
    return {"version": VERSION, "summary": summary, "rows": rows}
