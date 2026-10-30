"""Position-first selection protocol (R2.3).

Every quoted selection is resolved to explicit Unicode codepoint offsets
*before* any relation is judged. Matching is exact substring only: no case
folding, whitespace collapsing, normalization or fuzzy scoring. Rejections are
reported with stable reason codes instead of being silently dropped.

The frozen v2 contract (``research_contract_v2``) still performs the final
schema/identity checks; this module only decides *which* bytes a quote refers
to and refuses ambiguous input.
"""
from __future__ import annotations

from . import research_contract_v2 as contract

VERSION = "selection-protocol-v2"

# Selections that identify study context may be resolved automatically when the
# quote is unique inside its chunk. Result and qualifier quotes are evidence for
# a scientific statement, so they always need explicit offsets.
AUTO_RESOLVE_KINDS = ("study_context", "entity_mention")
EXPLICIT_POSITION_KINDS = ("relation_result", "relation_qualifier", "study_attribution")

REASON_CODES = {
    "unknown_source_chunk": "chunk_index not present in the frozen source packet",
    "invalid_offsets": "offsets are not integers within the chunk bounds",
    "span_quote_mismatch": "content[start:end] differs from the submitted quote",
    "quote_not_found": "quote does not occur in the declared chunk",
    "ambiguous_quote_requires_position": "quote occurs more than once; explicit start/end required",
    "unknown_relation_endpoint": "relation references an entity outside the frozen selection",
    "cross_study_relation_forbidden": "relation endpoints belong to different studies",
    "duplicate_entity_mention": "the same entity mention span is selected twice",
    "duplicate_relation_fact": "the same relation fact is asserted twice",
    "unsupported_relation_pending": "relation has no verifiable support in the selected span",
}


class SelectionError(ValueError):
    """Rejected selection with a stable reason code."""

    def __init__(self, code: str):
        if code not in REASON_CODES:
            raise ValueError(f"unknown reason code: {code}")
        self.code = code
        super().__init__(code)

    def as_dict(self) -> dict:
        return {"status": "rejected", "code": self.code, "message": REASON_CODES[self.code]}


def _chunk_text(packet: dict, chunk_index):
    chunks = {c.get("chunk_index"): c for c in packet.get("chunks", [])}
    if type(chunk_index) is not int or chunk_index not in chunks:
        raise SelectionError("unknown_source_chunk")
    return chunks[chunk_index]["content"]


def occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    """All exact occurrences, left to right. No normalization of any kind."""
    found, start = [], 0
    while True:
        index = text.find(quote, start)
        if index < 0:
            return found
        found.append((index, index + len(quote)))
        start = index + 1


def resolve_quote(packet: dict, *, chunk_index, quote, start=None, end=None, kind: str) -> dict:
    """Resolve one quote to offsets, or raise :class:`SelectionError`.

    ``start``/``end`` are optional for context and entity mentions (unique quote
    required) and mandatory for relation evidence.
    """
    if not isinstance(quote, str) or not quote.strip():
        raise SelectionError("quote_not_found")
    text = _chunk_text(packet, chunk_index)

    if start is None and end is None:
        if kind in EXPLICIT_POSITION_KINDS:
            raise SelectionError("ambiguous_quote_requires_position")
        found = occurrences(text, quote)
        if not found:
            raise SelectionError("quote_not_found")
        if len(found) > 1:
            raise SelectionError("ambiguous_quote_requires_position")
        start, end = found[0]
    elif type(start) is not int or type(end) is not int:
        raise SelectionError("invalid_offsets")

    if not 0 <= start < end <= len(text):
        raise SelectionError("invalid_offsets")
    if text[start:end] != quote:
        raise SelectionError("span_quote_mismatch")
    return {"chunk_index": chunk_index, "start": start, "end": end, "quote": quote}


def resolve_mention(packet: dict, selection: dict, *, kind: str = "entity_mention") -> dict:
    """Resolve an entity/context selection that may omit offsets."""
    if not isinstance(selection, dict):
        raise SelectionError("invalid_offsets")
    chunk_index = selection.get("chunk_index")
    quote = selection.get("quote")
    return resolve_quote(packet, chunk_index=chunk_index, quote=quote,
                         start=selection.get("start"), end=selection.get("end"), kind=kind)


def resolve_evidence(packet: dict, selection: dict, *, kind: str = "relation_result") -> dict:
    """Resolve relation evidence; explicit offsets are always required."""
    if not isinstance(selection, dict):
        raise SelectionError("invalid_offsets")
    return resolve_quote(packet, chunk_index=selection.get("chunk_index"), quote=selection.get("quote"),
                         start=selection.get("start"), end=selection.get("end"), kind=kind)


def resolve_enumeration(packet: dict, enumeration: dict) -> tuple[dict, dict]:
    """Stage 1: freeze study context and entity mentions to explicit spans.

    Returns ``(resolved_enumeration, ledger)`` where ``ledger`` maps entity local
    ids to their immutable selection. Raises :class:`SelectionError` on the first
    ambiguous, out-of-bounds or duplicated selection.
    """
    resolved = {"studies": [], "entities": []}
    ledger: dict[str, dict] = {}
    seen_spans: set[tuple] = set()

    for study in enumeration.get("studies", []):
        context = [resolve_mention(packet, item, kind="study_context") for item in study.get("context", [])]
        attribution = study.get("attribution")
        resolved_study = dict(study, context=context,
                              attribution=None if attribution is None else
                              resolve_evidence(packet, attribution, kind="study_attribution"))
        resolved["studies"].append(resolved_study)

    for entity in enumeration.get("entities", []):
        mention = resolve_mention(packet, entity.get("mention", {}), kind="entity_mention")
        key = (entity.get("study_id"), entity.get("entity_type"), mention["chunk_index"],
               mention["start"], mention["end"])
        if key in seen_spans:
            raise SelectionError("duplicate_entity_mention")
        seen_spans.add(key)
        resolved["entities"].append(dict(entity, mention=mention))
        ledger[entity.get("id")] = {"study_id": entity.get("study_id"),
                                    "entity_type": entity.get("entity_type"),
                                    "span": mention}

    return resolved, ledger


def resolve_decision(packet: dict, decision: dict, ledger: dict) -> list[dict]:
    """Stage 2: relations may only reference frozen entities; evidence needs offsets."""
    studies = set()
    for entity in ledger.values():
        studies.add(entity["study_id"])

    resolved = []
    for relation in decision.get("relations", []):
        study_id = relation.get("study_id")
        for endpoint in ("source_id", "target_id"):
            entity = ledger.get(relation.get(endpoint))
            if entity is None:
                raise SelectionError("unknown_relation_endpoint")
            if study_id not in studies or entity["study_id"] != study_id:
                raise SelectionError("cross_study_relation_forbidden")
        item = dict(relation)
        item["result"] = resolve_evidence(packet, relation.get("result", {}), kind="relation_result")
        item["qualifiers"] = {name: (None if value is None else
                                     resolve_evidence(packet, value, kind="relation_qualifier"))
                              for name, value in (relation.get("qualifiers") or {}).items()}
        resolved.append(item)
    return resolved


def resolve_bundle(packet: dict, enumeration: dict, decision: dict) -> dict:
    """Resolve both stages and return payloads accepted by the v2 contract."""
    resolved_enumeration, ledger = resolve_enumeration(packet, enumeration)
    return {"enumeration": resolved_enumeration,
            "decision": {"relations": resolve_decision(packet, decision, ledger)},
            "ledger": ledger}


def adjudicate_resolution(packet: dict, enumeration: dict, decision: dict) -> dict:
    """Resolve without raising; report accepted, pending and rejected items."""
    try:
        resolved, ledger = resolve_enumeration(packet, enumeration)
    except SelectionError as error:
        return {"status": "rejected", "accepted": [], "pending": [], "rejected": [error.as_dict()],
                "ledger": {}}

    accepted, rejected = [], []
    for relation in decision.get("relations", []):
        try:
            accepted.extend(resolve_decision(packet, {"relations": [relation]}, ledger))
        except SelectionError as error:
            rejected.append({"relation_id": relation.get("id")} | error.as_dict())

    pending = [r for r in accepted if r.get("direction") in {"uncertain", "not_reported"}]
    return {"status": "accepted" if not rejected else "partially_rejected",
            "accepted": [r for r in accepted if r not in pending], "pending": pending,
            "rejected": rejected, "ledger": ledger}


def compile_selection(packet: dict, enumeration: dict, decision: dict, *, provenance: dict) -> dict:
    """Resolve selections first, then run the frozen v2 contract on exact spans."""
    resolved = resolve_bundle(packet, enumeration, decision)
    return contract.compile_bundle(packet, resolved["enumeration"], resolved["decision"],
                                   provenance=provenance)
