"""Unit tests for R2.8 span integrity re-verification."""
from __future__ import annotations

import hashlib

from scripts.verify_r2_8_file_link import _sha256_text, _verify_span_integrity


def _span(quote="Cd在水稻", start=0, end=5):
    return {
        "chunk_index": 0, "start": start, "end": end, "quote": quote,
        "quote_sha256": _sha256_text(quote), "page": 1,
        "document_id": 1, "document_sha256": "a" * 64,
        "parse_version": "a" * 64, "chunk_set_version": "a" * 64,
        "id": "span:test",
    }


def _bundle(spans):
    """Build a minimal bundle with the given spans placed in a relation."""
    result_span, qualifier_span = spans
    return {
        "studies": [{"local_id": "s1", "kind": "observational",
                      "context": [spans[0]], "attribution": None}],
        "entities": [
            {"local_id": "e1", "study_id": "s1", "entity_type": "measure",
             "surface": "Cd", "mention": spans[0], "normalization": {}},
        ],
        "relations": [{
            "local_id": "r1", "study_id": "s1", "relation_type": "reports_effect",
            "source_id": "e1", "target_id": "e1", "result": result_span,
            "direction": "increase",
            "qualifiers": {"soil_type": {"status": "source_selected", "evidence": qualifier_span}},
        }],
    }


def test_valid_spans_pass_reverification():
    span = _span()
    bundle = _bundle((span, span))
    checked, rejected = _verify_span_integrity(bundle)
    # context(1) + entity mention(1) + result(1) + qualifier(1) = 4
    assert checked == 4
    assert rejected == 0


def test_corrupted_quote_sha256_rejected():
    span = _span()
    span["quote_sha256"] = "0" * 64  # wrong hash
    bundle = _bundle((span, _span()))
    checked, rejected = _verify_span_integrity(bundle)
    assert rejected >= 1
    assert checked >= 2


def test_invalid_offsets_rejected():
    span = _span(start=5, end=3)  # start > end
    bundle = _bundle((span, _span()))
    checked, rejected = _verify_span_integrity(bundle)
    assert rejected >= 1


def test_empty_quote_rejected():
    span = _span(quote="")
    bundle = _bundle((span, _span()))
    checked, rejected = _verify_span_integrity(bundle)
    assert rejected >= 1
