"""Versioned source-selected research records; no free generated field values."""
from dataclasses import asdict
from typing import Mapping

from .contracts import EvidenceReference, SourceChunk, stable_digest

VERSION = "source-selected-research-record-v1"
FIELDS = ("measure", "indicator", "result", "soil_type", "conditions", "dose", "duration",
          "effect_size", "unit", "negation", "uncertainty", "study_context")
REQUIRED = {"measure", "indicator", "result"}


def compile_record(document_id: int, content_sha256: str, selection: Mapping, chunks: Mapping[int, SourceChunk], *, provenance: Mapping):
    if set(selection) != set(FIELDS):
        raise ValueError("research_field_set_mismatch")
    values = {}
    for name in FIELDS:
        selected = selection[name]
        if selected is None:
            if name in REQUIRED:
                raise ValueError("missing_required_research_field:"+name)
            values[name] = {"value": None, "status": "unknown", "evidence": None}
            continue
        if not isinstance(selected, dict) or set(selected) != {"chunk_index", "quote"}:
            raise ValueError("field_must_be_source_selection")
        index, quote = selected["chunk_index"], selected["quote"]
        if type(index) is not int or index not in chunks or not isinstance(quote, str) or not quote.strip():
            raise ValueError("invalid_research_source_selection")
        chunk = chunks[index]
        if chunk.document_id != document_id or chunk.content_sha256 != content_sha256:
            raise ValueError("cross_document_research_field")
        # Ambiguous selections require a wider exact quote, never a guessed offset.
        start = chunk.content.find(quote)
        if start < 0 or chunk.content.find(quote, start+1) >= 0:
            raise ValueError("research_quote_missing_or_ambiguous")
        evidence = EvidenceReference.from_chunk(chunk, start, start+len(quote))
        values[name] = {"value": quote, "status": "source_selected", "evidence": asdict(evidence)}
    identity = stable_digest({"version": VERSION, "document_id": document_id, "content_sha256": content_sha256, "fields": values})
    if not provenance.get("origin") or not provenance.get("configuration_sha256"):
        raise ValueError("research_provenance_required")
    return {"id": "research:"+identity, "schema_version": VERSION, "document_id": document_id,
            "content_sha256": content_sha256, "review_status": "pending", "fields": values,
            "provenance": dict(provenance)}


def validate_record(record, chunks):
    """Reconstruct references and identity rather than trusting a stored payload."""
    selected = {name: None if value["value"] is None else {"chunk_index": value["evidence"]["chunk_index"], "quote": value["value"]}
                for name, value in record["fields"].items()}
    expected = compile_record(record["document_id"], record["content_sha256"], selected, chunks, provenance=record["provenance"])
    if record != expected:
        raise ValueError("research_record_changed_or_not_pending")
    return expected


def selection_schema():
    item = {"type": "object", "properties": {"chunk_index": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["chunk_index", "quote"], "additionalProperties": False}
    fields = {name: item if name in REQUIRED else {"anyOf": [item, {"type": "null"}]} for name in FIELDS}
    record = {"type": "object", "properties": fields, "required": list(FIELDS), "additionalProperties": False}
    return {"type": "object", "properties": {"records": {"type": "array", "maxItems": 8, "items": record}},
            "required": ["records"], "additionalProperties": False}
