"""Opt-in PDF reading-order repair with glyph locations and versioned output.

No OCR, rewriting, dehyphenation, table inference or model calls. Uncertain
layouts remain explicit. Legacy parser output is never replaced in place.
"""
from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

from framework.knowledge_graph.contracts import stable_digest

PROFILE = "pdf-layout-v2"


def _order_blocks(blocks, width):
    mid = width / 2
    left = [b for b in blocks if b["bbox"][2] <= mid + 5 and b["bbox"][2]-b["bbox"][0] > width*.2]
    right = [b for b in blocks if b["bbox"][0] >= mid-5 and b["bbox"][2]-b["bbox"][0] > width*.2]
    if min(sum(len(b["text"]) for b in group) for group in (left, right)) < 400:
        return blocks, "native_blocks", ["column_layout_not_inferred"]
    spanning = sorted([b for b in blocks if b["bbox"][2]-b["bbox"][0] > width*.6], key=lambda b: b["bbox"][1])
    remaining = [b for b in blocks if b not in spanning]
    ordered = []
    # Full-width titles/captions form horizontal boundaries. Within each band
    # read the complete left column before the right, never alternate lines.
    for boundary in [*spanning, None]:
        before = [b for b in remaining if boundary is None or (b["bbox"][1]+b["bbox"][3])/2 < boundary["bbox"][1]]
        for right_side in (False, True):
            ordered.extend(sorted([b for b in before if ((b["bbox"][0]+b["bbox"][2])/2 >= mid) == right_side],
                                  key=lambda b: (b["bbox"][1], b["bbox"][0])))
        remaining = [b for b in remaining if b not in before]
        if boundary is not None:
            ordered.append(boundary)
    return ordered, "two_column_geometry", ["tables_and_figures_not_structurally_interpreted"]


def extract_page(page):
    """Return one page's text and one PDF rectangle per output codepoint."""
    rect = page.rect
    blocks, seen = [], set()
    duplicates, clipped = 0, 0
    warnings = []
    for raw in page.get_text("rawdict", clip=rect)["blocks"]:
        if raw.get("type") != 0:
            continue
        text, locations = [], []
        for line in raw.get("lines", []):
            if abs(line.get("dir", (1, 0))[1]) > .05:
                warnings.append("rotated_text_requires_review")
            line_chars, line_locations = [], []
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    box = char["bbox"]
                    if box[0] < rect.x0-1 or box[1] < rect.y0-1 or box[2] > rect.x1+1 or box[3] > rect.y1+1:
                        clipped += 1
                        continue
                    original = char["c"]
                    key = (original, round(box[0]*2), round(box[1]*2), round(box[2]*2), round(box[3]*2))
                    if key in seen:
                        duplicates += 1
                        continue
                    seen.add(key)
                    for normalized in unicodedata.normalize("NFKC", original):
                        if unicodedata.category(normalized) == "Cc":
                            continue
                        line_chars.append(normalized)
                        line_locations.append([round(v, 3) for v in box])
            if line_chars:
                text.extend(line_chars + ["\n"])
                locations.extend(line_locations + [None])
        if text:
            blocks.append({"bbox": list(raw["bbox"]), "text": "".join(text), "char_bboxes": locations})
    ordered, mode, layout_warnings = _order_blocks(blocks, rect.width)
    text, locations, ranges = "", [], []
    for block in ordered:
        start = len(text)
        text += block["text"] + "\n"
        locations.extend(block["char_bboxes"] + [None])
        ranges.append({"start": start, "end": len(text)-1, "bbox": block["bbox"]})
    if not text.strip():
        warnings.append("no_readable_text_OCR_not_run")
    return {"text": text, "char_bboxes": locations, "blocks": ranges, "reading_order": mode,
            "status": "readable_text_requires_semantic_review" if text.strip() else "unreadable",
            "warnings": sorted(set(warnings+layout_warnings)),
            "duplicate_glyphs_removed": duplicates, "out_of_page_glyphs_removed": clipped}


def parse_layout_pdf(path):
    import fitz
    source = Path(path)
    with source.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    with fitz.open(source) as pdf:
        pages = [dict(extract_page(page), page=i) for i, page in enumerate(pdf, 1)]
    configuration = {"profile": PROFILE, "pymupdf_version": fitz.VersionBind,
                     "normalization": "NFKC_per_glyph_with_bbox_no_dehyphenation",
                     "deduplication": "same_codepoint_and_bbox_half_point_grid",
                     "reading_order": "two_columns_when_both_have_400_chars_else_native_blocks"}
    version = stable_digest({"source_sha256": source_hash, "configuration": configuration,
                             "pages": [{"page": p["page"], "text": p["text"]} for p in pages]})
    return {"document_sha256": source_hash, "parse_version": version,
            "configuration": configuration, "pages": pages,
            "semantic_quality_certified": False}


def versioned_chunks(document, *, size=800, overlap=150):
    if type(size) is not int or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError("invalid_versioned_chunk_parameters")
    chunks = []
    for page in document["pages"]:
        if not page["text"].strip():
            continue
        for start in range(0, len(page["text"]), size-overlap):
            end = min(start+size, len(page["text"]))
            chunks.append({"chunk_index": len(chunks), "page": page["page"],
                           "page_start": start, "page_end": end, "content": page["text"][start:end]})
    identity = stable_digest({"parse_version": document["parse_version"], "size": size, "overlap": overlap,
                              "chunks": chunks})
    return {"chunk_set_version": identity, "size": size, "overlap": overlap, "chunks": chunks}


def map_old_chunks(old_chunks, document, chunk_set):
    """Only exact uniqueness authorizes an offset mapping; no fuzzy migration."""
    pages = {p["page"]: p["text"] for p in document["pages"]}
    result = []
    for old in old_chunks:
        text = pages.get(old["page"], "")
        quote = old["content"]
        start = text.find(quote)
        exact = start >= 0 and text.find(quote, start+1) < 0
        result.append({"old_chunk_index": old["chunk_index"], "page": old["page"],
                       "state": "exact_unique" if exact else "same_page_only_no_span_transfer",
                       "new_page_start": start if exact else None,
                       "new_page_end": start+len(quote) if exact else None,
                       "candidate_new_chunk_indexes": [c["chunk_index"] for c in chunk_set["chunks"]
                                                       if c["page"] == old["page"] and
                                                       (not exact or c["page_start"] < start+len(quote) and c["page_end"] > start)]})
    return result
