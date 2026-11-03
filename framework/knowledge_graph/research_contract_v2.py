"""Task-focused, version-bound entity selection and relation decision contract.

This is an opt-in candidate contract. It does not change legacy records,
scientifically certify model decisions, publish claims or write graph stores.
"""
from __future__ import annotations

import re
from .contracts import sha256_text, stable_digest

VERSION = "task-evidence-extraction-v2"
ENTITY_TYPES = ("measure", "indicator", "soil", "crop", "condition", "location")
STUDY_KINDS = ("primary_experiment", "review_cited_study", "observational", "modeling", "unknown")
DIRECTIONS = ("increase", "decrease", "no_significant_change", "mixed", "uncertain", "not_reported")
QUALIFIERS = ("soil_type", "conditions", "dose", "duration", "effect_size", "unit", "negation", "uncertainty", "comparator")


def _keys(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ValueError("contract_field_set_mismatch")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("invalid_local_identifier")
    return value


def compile_bundle(source, enumeration, decision, *, provenance):
    """Validate two stages against the SAME immutable source packet.

    Span validity and rule conformance are machine checked. Whether the text
    supports the scientific interpretation remains explicitly unreviewed.
    """
    binding = {k: source.get(k) for k in ("document_id", "document_sha256", "parse_version", "chunk_set_version")}
    if type(binding["document_id"]) is not int or binding["document_id"] <= 0:
        raise ValueError("invalid_document_id")
    for key in ("document_sha256", "parse_version", "chunk_set_version"):
        if not isinstance(binding[key], str) or not re.fullmatch(r"[a-f0-9]{64}", binding[key]):
            raise ValueError("complete_version_binding_required")
    if not isinstance(source.get("chunks"), list) or not source["chunks"]:
        raise ValueError("source_chunks_required")
    chunks = {}
    for chunk in source["chunks"]:
        index = chunk.get("chunk_index")
        if type(index) is not int or index < 0 or index in chunks or type(chunk.get("page")) is not int or chunk["page"] <= 0 or not isinstance(chunk.get("content"), str) or not chunk["content"].strip():
            raise ValueError("invalid_or_duplicate_source_chunk")
        chunks[index] = chunk
    if (not isinstance(provenance, dict) or not isinstance(provenance.get("origin"), str) or not provenance["origin"].strip()
            or not isinstance(provenance.get("configuration_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", provenance["configuration_sha256"])):
        raise ValueError("extraction_provenance_required")

    def span(selection):
        _keys(selection, ("chunk_index", "start", "end", "quote"))
        i, start, end, quote = (selection[k] for k in ("chunk_index", "start", "end", "quote"))
        if any(type(v) is not int for v in (i, start, end)) or i not in chunks:
            raise ValueError("invalid_span_locator")
        chunk = chunks[i]
        if not isinstance(quote, str) or not quote.strip() or not 0 <= start < end <= len(chunk["content"]) or chunk["content"][start:end] != quote:
            raise ValueError("span_quote_mismatch")
        value = binding | dict(selection, page=chunk["page"], quote_sha256=sha256_text(quote))
        return value | {"id": "span:"+stable_digest(value)}

    def bounded(value, maximum):
        if not isinstance(value, list) or len(value) > maximum:
            raise ValueError("invalid_or_unbounded_array")
        return value

    _keys(enumeration, ("studies", "entities"))
    _keys(decision, ("relations",))
    studies, entities, relations = {}, {}, {}
    for item in bounded(enumeration["studies"], 40):
        _keys(item, ("id", "kind", "context", "attribution"))
        identifier = _identifier(item["id"])
        if identifier in studies or item["kind"] not in STUDY_KINDS:
            raise ValueError("invalid_or_duplicate_study")
        context = bounded(item["context"], 12)
        if not context:
            raise ValueError("study_context_evidence_required")
        attribution = None if item["attribution"] is None else span(item["attribution"])
        if item["kind"] == "review_cited_study" and attribution is None:
            raise ValueError("cited_study_attribution_required")
        studies[identifier] = {"local_id": identifier, "kind": item["kind"],
                               "context": [span(s) for s in context], "attribution": attribution}
    seen = set()
    for item in bounded(enumeration["entities"], 200):
        _keys(item, ("id", "study_id", "entity_type", "mention"))
        identifier = _identifier(item["id"])
        _identifier(item["study_id"])
        if identifier in entities or item["study_id"] not in studies or item["entity_type"] not in ENTITY_TYPES:
            raise ValueError("invalid_or_duplicate_entity")
        mention = span(item["mention"])
        key = (item["study_id"], item["entity_type"], mention["id"])
        if key in seen:
            raise ValueError("duplicate_entity_mention")
        seen.add(key)
        entities[identifier] = {"local_id": identifier, "study_id": item["study_id"],
                                "entity_type": item["entity_type"], "surface": mention["quote"], "mention": mention,
                                "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}}
    for item in bounded(decision["relations"], 200):
        _keys(item, ("id", "study_id", "relation_type", "source_id", "target_id", "result", "direction", "qualifiers"))
        identifier = _identifier(item["id"])
        for key in ("study_id", "source_id", "target_id"):
            _identifier(item[key])
        if identifier in relations or item["study_id"] not in studies or item["relation_type"] != "reports_effect" or item["direction"] not in DIRECTIONS:
            raise ValueError("invalid_or_duplicate_relation")
        subject, obj = entities.get(item["source_id"]), entities.get(item["target_id"])
        if not subject or not obj or subject["entity_type"] != "measure" or obj["entity_type"] != "indicator":
            raise ValueError("relation_endpoint_type_or_direction_invalid")
        if subject["study_id"] != item["study_id"] or obj["study_id"] != item["study_id"]:
            raise ValueError("cross_study_relation_forbidden")
        _keys(item["qualifiers"], QUALIFIERS)
        qualifiers = {name: {"status": "unknown", "evidence": None} if value is None
                      else {"status": "source_selected", "evidence": span(value)}
                      for name, value in item["qualifiers"].items()}
        result = span(item["result"])
        identity = stable_digest(binding | {"study": studies[item["study_id"]], "subject": subject,
                                             "object": obj, "result": result, "qualifiers": qualifiers,
                                             "direction": item["direction"]})
        if any(r["id"] == "research:"+identity for r in relations.values()):
            raise ValueError("duplicate_relation_fact")
        relations[identifier] = {"id": "research:"+identity, "local_id": identifier,
                                 "study_id": item["study_id"], "relation_type": "reports_effect",
                                 "source_id": item["source_id"], "target_id": item["target_id"],
                                 "result": result, "direction": item["direction"], "qualifiers": qualifiers,
                                 "review_status": "pending", "semantic_support": "unreviewed"}
    return {"schema_version": VERSION, "source": binding,
            "studies": list(studies.values()), "entities": list(entities.values()), "relations": list(relations.values()),
            "provenance": dict(provenance), "review_status": "pending", "published_claims_added": 0,
            "rule_validation": "passed", "semantic_support": "unreviewed",
            "identity": stable_digest({"version": VERSION, "source": binding, "enumeration": enumeration, "decision": decision})}


def schemas():
    def obj(properties):
        return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    identifier = {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"}
    selection = obj({"chunk_index": {"type": "integer", "minimum": 0}, "start": {"type": "integer", "minimum": 0},
                     "end": {"type": "integer", "minimum": 1}, "quote": {"type": "string", "minLength": 1}})
    optional = {"anyOf": [selection, {"type": "null"}]}
    study = obj({"id": identifier, "kind": {"enum": list(STUDY_KINDS)},
                 "context": {"type": "array", "minItems": 1, "maxItems": 12, "items": selection}, "attribution": optional})
    entity = obj({"id": identifier, "study_id": identifier, "entity_type": {"enum": list(ENTITY_TYPES)}, "mention": selection})
    relation = obj({"id": identifier, "study_id": identifier, "relation_type": {"const": "reports_effect"},
                    "source_id": identifier, "target_id": identifier, "result": selection,
                    "direction": {"enum": list(DIRECTIONS)}, "qualifiers": obj({key: optional for key in QUALIFIERS})})
    return {"schema_version": VERSION, "offsets": "zero_based_unicode_codepoints_end_exclusive",
            "enumeration": obj({"studies": {"type": "array", "maxItems": 40, "items": study},
                                "entities": {"type": "array", "maxItems": 200, "items": entity}}),
            "decision": obj({"relations": {"type": "array", "maxItems": 200, "items": relation}}),
            "identity_binding": ["document_id", "document_sha256", "parse_version", "chunk_set_version"],
            "semantic_review_required": True, "automatic_publication_allowed": False}
