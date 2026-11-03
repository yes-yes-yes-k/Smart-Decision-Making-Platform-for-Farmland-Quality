"""Normalize record separators without changing entity/relation semantics."""
import re
import json


async def complete_graph_records(create, *, messages, options, schema, usage, max_repairs=2, source_text=None, accepted_relations=None, trace=None, validate_payload=None):
    """Bounded model correction; every response must pass the same strict gate."""
    conversation = list(messages)
    for attempt in range(max_repairs+1):
        response = await create(messages=conversation, **options)
        if response.usage:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage[key] += int(getattr(response.usage, key, 0) or 0)
        choice = response.choices[0]
        entry = dict(attempt=attempt, content=choice.message.content, finish_reason=choice.finish_reason, accepted=False)
        if trace is not None:
            trace.append(entry)
        if choice.finish_reason != "stop" or not choice.message.content:
            raise ValueError("incomplete_model_response")
        try:
            records = json_to_graph_records(choice.message.content, schema, source_text=source_text)
            if validate_payload is not None:
                validate_payload(json.loads(choice.message.content))
            entry.update(accepted=True, records=records)
            if accepted_relations is not None:
                accepted_relations[:] = json.loads(choice.message.content)['relationships']
            return records
        except ValueError as exc:
            entry['error'] = str(exc)
            if attempt == max_repairs:
                raise
            usage["repair_requests"] = usage.get("repair_requests", 0)+1
            conversation = [*conversation, {"role": "assistant", "content": choice.message.content},
                {"role": "user", "content": (
                    "The candidate JSON failed the domain validation: " + str(exc) + ". "
                    "Recheck each endpoint against its declared entity type and the directed rules. "
                    "Use the exact permitted enum IDs. Correct the JSON using only explicit source facts. "
                    "Do not invent types or reverse a fact merely to pass validation. Omit unsupported "
                    "relations; isolated valid entities and empty arrays are allowed. Return JSON only.") }]


def graph_response_schema(schema, *, evidence=False):
    entity = {"type": "object", "properties": {
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": sorted(schema.entity_type_ids)}},
        "required": ["name", "type"], "additionalProperties": False}
    relation = {"type": "object", "properties": {
        "source": {"type": "string", "minLength": 1},
        "target": {"type": "string", "minLength": 1},
        "relation_type": {"type": "string", "enum": sorted(schema.relation_type_ids)}},
        "required": ["source", "target", "relation_type"], "additionalProperties": False}
    if evidence:
        relation['properties']['quote'] = {'type':'string','minLength':1}
        relation['required'].append('quote')
    return {"type": "json_schema", "json_schema": {"name": "cultivated_land_candidates", "strict": True,
        "schema": {"type": "object", "properties": {
            "entities": {"type": "array", "items": entity},
            "relationships": {"type": "array", "items": relation}},
            "required": ["entities", "relationships"], "additionalProperties": False}}}


def json_to_graph_records(text, schema, *, source_text=None):
    """Validate typed JSON before converting transport to GraphRAG records."""
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        raise ValueError("invalid_model_output") from None
    if not isinstance(payload, dict) or set(payload) != {"entities", "relationships"}:
        raise ValueError("invalid_model_output")
    if not all(isinstance(payload[key], list) for key in payload):
        raise ValueError("invalid_model_output")
    records, entities = [], {}
    def name(value):
        if not isinstance(value, str) or not value.strip() or any(t in value for t in ("<|>", "##", "\n", "\r")):
            raise ValueError("invalid_model_output")
        return value.strip()
    for row in payload["entities"]:
        if not isinstance(row, dict) or set(row) != {"name", "type"}:
            raise ValueError("invalid_model_output")
        mention = name(row["name"])
        kind = row["type"]
        if not isinstance(kind, str) or kind not in schema.entity_type_ids:
            raise ValueError("unknown_entity_type")
        if mention in entities and entities[mention] != kind:
            raise ValueError("ambiguous_entity_types")
        entities[mention] = kind
        records.append(f'("entity"<|>{mention}<|>{kind}<|>source entity)')
    for row in payload["relationships"]:
        fields = {"source", "target", "relation_type"} | ({'quote'} if source_text is not None else set())
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("invalid_model_output")
        if source_text is not None and (not isinstance(row['quote'],str) or not row['quote'].strip()
                or row['quote'] not in source_text):
            raise ValueError('invalid_evidence_quote')
        source, target = name(row["source"]), name(row["target"])
        kind = row["relation_type"]
        if not isinstance(kind, str) or kind not in schema.relation_type_ids:
            raise ValueError("unknown_relation_type")
        if source not in entities or target not in entities:
            raise ValueError("missing_relation_endpoint")
        if not schema.allows(kind, entities[source], entities[target]):
            raise ValueError("invalid_relation_direction")
        records.append(f'("relationship"<|>{source}<|>{target}<|>{kind}<|>1)')
    return "##".join(records) + ("##" if records else "") + "<|COMPLETE|>"


def normalize_graph_records(text):
    value = text.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    if not value:
        raise ValueError("invalid_model_output")
    # Some compatible models spell GraphRAG's completion marker using its
    # tuple delimiter. Both represent transport termination, never a fact.
    value = re.sub(r"(?:##)?\s*<\|>?COMPLETE\|>\s*$", "", value).strip()
    if not value:
        return "<|COMPLETE|>"
    records = []
    for raw in re.split(r"##|\n(?=\s*[（(]\"(?:entity|relationship)\")", value):
        record = raw.strip()
        if not record:
            continue
        if record[0] not in "(（" or record[-1] not in ")）":
            raise ValueError("invalid_model_output")
        # Chinese responses may use full-width tuple punctuation. Normalize
        # only the structural outer pair, never names or quoted evidence.
        record = "(" + record[1:-1] + ")"
        fields = record[1:-1].split("<|>")
        kind = fields[0].strip()
        if kind not in {'"entity"', '"relationship"'} or len(fields) != (4 if kind == '"entity"' else 5):
            raise ValueError("invalid_model_output")
        records.append(record)
    if not records:
        raise ValueError("invalid_model_output")
    return "##".join(records) + "##<|COMPLETE|>"
