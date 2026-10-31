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
    "invalid_selection_shape": "selection must be a quote string or an object with a quote",
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


def _collapse(text: str):
    """Drop whitespace and keep an index back to the original text."""
    kept, index = [], []
    for position, character in enumerate(text):
        if not character.isspace():
            kept.append(character)
            index.append(position)
    return "".join(kept), index


def _occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    """Exact first; whitespace-insensitive only as a transcription tolerance.

    The returned offsets always address the ORIGINAL text, so the record stores
    the real source substring, never the model's spacing.
    """
    exact = occurrences(text, quote)
    if exact:
        return exact
    collapsed_text, index = _collapse(text)
    collapsed_quote, _ = _collapse(quote)
    if not collapsed_quote:
        return []
    found, start = [], 0
    while True:
        hit = collapsed_text.find(collapsed_quote, start)
        if hit < 0:
            return found
        found.append((index[hit], index[hit + len(collapsed_quote) - 1] + 1))
        start = hit + 1


def _quote_of(selection) -> str:
    if isinstance(selection, str):
        return selection
    if isinstance(selection, dict):
        value = selection.get("quote")
        return value if isinstance(value, str) else ""
    raise SelectionError("invalid_selection_shape")


def resolve_unique_quote(packet: dict, selection) -> dict:
    """Resolve a quote-only selection; duplicates are rejected, never guessed.

    A bare string, or an object without ``chunk_index``, is resolved across the
    supplied chunks — accepted only when the quote occurs exactly once in the
    whole packet, so the location stays unambiguous.
    """
    quote = _quote_of(selection)
    if not quote.strip():
        raise SelectionError("quote_not_found")
    chunk_index = selection.get("chunk_index") if isinstance(selection, dict) else None
    if chunk_index is not None:
        candidates = [(chunk_index, _chunk_text(packet, chunk_index))]
    else:
        candidates = [(chunk["chunk_index"], chunk["content"]) for chunk in packet.get("chunks", [])]
    hits = []
    for index, text in candidates:
        for start, end in _occurrences(text, quote):
            hits.append((index, start, end, text[start:end]))
    if not hits:
        raise SelectionError("quote_not_found")
    if len(hits) > 1:
        raise SelectionError("ambiguous_quote_requires_position")
    index, start, end, exact_text = hits[0]
    return {"chunk_index": index, "start": start, "end": end, "quote": exact_text}


def resolve_bundle_quote_only(packet: dict, enumeration: dict, decision: dict) -> dict:
    """Stage-1/2 payloads that carry quotes without offsets (model quotes only)."""
    studies, entities, ledger = [], [], {}
    for study in enumeration.get("studies", []):
        context = [resolve_unique_quote(packet, item) for item in study.get("context", [])]
        attribution = study.get("attribution")
        studies.append(dict(study, context=context,
                            attribution=None if attribution is None else
                            resolve_unique_quote(packet, attribution)))
    for entity in enumeration.get("entities", []):
        mention = resolve_unique_quote(packet, entity.get("mention", {}))
        entities.append(dict(entity, mention=mention))
        ledger[entity.get("id")] = {"study_id": entity.get("study_id"),
                                    "entity_type": entity.get("entity_type"), "span": mention}
    relations = resolve_decision(packet, {"relations": [
        dict(relation, result=resolve_unique_quote(packet, relation.get("result", {})),
             qualifiers={name: (None if value is None else resolve_unique_quote(packet, value))
                         for name, value in (relation.get("qualifiers") or {}).items()})
        for relation in decision.get("relations", [])]}, ledger)
    return {"enumeration": {"studies": studies, "entities": entities},
            "decision": {"relations": relations}, "ledger": ledger}


def compile_selection_quote_only(packet: dict, enumeration: dict, decision: dict, *, provenance: dict) -> dict:
    """Quote-only variant of :func:`compile_selection`; offsets are derived server-side."""
    resolved = resolve_bundle_quote_only(packet, enumeration, decision)
    return contract.compile_bundle(packet, resolved["enumeration"], resolved["decision"],
                                   provenance=provenance)


def compile_partial_quote_only(packet: dict, enumeration: dict, decision: dict, *, provenance: dict) -> dict:
    """Compile what is verifiable; reject individual items with reason codes.

    A single unlocatable quote must not discard a whole paper: each selection is
    resolved on its own, failures are reported per item, and only the surviving
    subset reaches the frozen contract.
    """
    rejected, reasons = [], {}

    def note(kind, identifier, error):
        rejected.append({"kind": kind, "id": identifier} | error.as_dict())
        reasons[error.code] = reasons.get(error.code, 0) + 1

    studies, kept_studies = [], set()
    for study in enumeration.get("studies", []):
        context = []
        for item in study.get("context", []):
            try:
                context.append(resolve_unique_quote(packet, item))
            except SelectionError as error:
                note("study_context", study.get("id"), error)
        if not context:
            reasons["study_context_unresolved"] = reasons.get("study_context_unresolved", 0) + 1
            rejected.append({"kind": "study", "id": study.get("id"), "status": "rejected",
                             "code": "study_context_unresolved"})
            continue
        attribution = None
        if study.get("attribution") is not None:
            try:
                attribution = resolve_unique_quote(packet, study["attribution"])
            except SelectionError as error:
                note("study_attribution", study.get("id"), error)
        studies.append(dict(study, context=context, attribution=attribution))
        kept_studies.add(study.get("id"))

    entities, kept_entities = [], {}
    for entity in enumeration.get("entities", []):
        if entity.get("study_id") not in kept_studies:
            rejected.append({"kind": "entity", "id": entity.get("id"), "status": "rejected",
                             "code": "study_not_retained"})
            reasons["study_not_retained"] = reasons.get("study_not_retained", 0) + 1
            continue
        try:
            mention = resolve_unique_quote(packet, entity.get("mention", {}))
        except SelectionError as error:
            note("entity_mention", entity.get("id"), error)
            continue
        entities.append(dict(entity, mention=mention))
        kept_entities[entity.get("id")] = {"study_id": entity.get("study_id"),
                                           "entity_type": entity.get("entity_type"), "span": mention}

    relations = []
    seen_identities = set()
    for relation in decision.get("relations", []):
        source, target = kept_entities.get(relation.get("source_id")), kept_entities.get(relation.get("target_id"))
        if not source or not target:
            rejected.append({"kind": "relation", "id": relation.get("id"), "status": "rejected",
                             "code": "unknown_relation_endpoint"})
            reasons["unknown_relation_endpoint"] = reasons.get("unknown_relation_endpoint", 0) + 1
            continue
        if source["study_id"] != relation.get("study_id") or target["study_id"] != relation.get("study_id"):
            rejected.append({"kind": "relation", "id": relation.get("id"), "status": "rejected",
                             "code": "cross_study_relation_forbidden"})
            reasons["cross_study_relation_forbidden"] = reasons.get("cross_study_relation_forbidden", 0) + 1
            continue
        try:
            result = resolve_unique_quote(packet, relation.get("result", {}))
            qualifiers = {}
            for name, value in (relation.get("qualifiers") or {}).items():
                qualifiers[name] = None if value is None else resolve_unique_quote(packet, value)
        except SelectionError as error:
            note("relation_evidence", relation.get("id"), error)
            continue
        candidate = dict(relation, result=result, qualifiers=qualifiers)
        identity = (candidate.get("source_id"), candidate.get("target_id"), result["chunk_index"],
                    result["start"], candidate.get("direction"))
        if identity in seen_identities:
            rejected.append({"kind": "relation", "id": relation.get("id"), "status": "rejected",
                             "code": "duplicate_relation_fact"})
            reasons["duplicate_relation_fact"] = reasons.get("duplicate_relation_fact", 0) + 1
            continue
        seen_identities.add(identity)
        relations.append(candidate)

    bundle = contract.compile_bundle(packet, {"studies": studies, "entities": entities},
                                     {"relations": relations}, provenance=provenance)
    return {"candidates": bundle, "rejected": rejected, "reason_counts": reasons,
            "accepted_counts": {"studies": len(studies), "entities": len(entities),
                                "relations": len(relations)}}


def compile_selection(packet: dict, enumeration: dict, decision: dict, *, provenance: dict) -> dict:
    """Resolve selections first, then run the frozen v2 contract on exact spans."""
    resolved = resolve_bundle(packet, enumeration, decision)
    return contract.compile_bundle(packet, resolved["enumeration"], resolved["decision"],
                                   provenance=provenance)
