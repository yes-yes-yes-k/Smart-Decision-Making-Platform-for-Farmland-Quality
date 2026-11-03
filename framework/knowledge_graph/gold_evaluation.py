"""Evaluation-only conversion; gold labels never become extraction prompts."""
from .contracts import EntityCandidate


def retry_transient_record(record, enabled):
    return bool(enabled and record["state"] == "failed" and
        record.get("code") in {"extraction_backend_failed", "model_rate_limited"} and
        not (record.get("usage") or {}).get("total_tokens") and not record.get("prior_attempt"))


def prediction_rows(result, catalog=None):
    entities = {}
    for item in result["entities"]:
        name = item["mention"]
        canonical_id = None
        if catalog is not None:
            resolution = catalog.resolve(EntityCandidate(**item))
            if resolution.status == "resolved":
                name, canonical_id = resolution.canonical_name, resolution.canonical_id
        entities[item["candidate_id"]] = dict(type=item["entity_type"], name=name, id=canonical_id)
    rows = []
    for item in result["relations"]:
        for evidence in item["evidence"]:
            rows.append(dict(relation=dict(type=item["relation_type"],
                source=entities[item["source_candidate_id"]], target=entities[item["target_candidate_id"]]),
                evidence={**evidence, "review_status": "unreviewed"}))
    return rows, list(entities.values())


def source_locator_score(gold, predictions):
    """Supplementary page/chunk coverage, never substituted for exact spans."""
    from scripts.evaluate_kg_extraction_backend import _relation_key
    covered = 0
    for expected in gold:
        ev = expected["evidence"]
        if any(_relation_key(expected) == _relation_key(predicted)
            and ev["document_id"] == predicted["evidence"]["document_id"]
            and ev["page"] == predicted["evidence"]["page"]
            and (ev.get("chunk_index") is None or ev["chunk_index"] == predicted["evidence"]["chunk_index"])
            for predicted in predictions):
            covered += 1
    return dict(expected=len(gold), covered=covered, recall=round(covered/len(gold), 6) if gold else 0,
                scope="relation + document + page + optional chunk; not exact quote/span")


def entity_scores(gold, predicted_entities):
    from scripts.evaluate_kg_extraction_backend import _entity_keys, _scores, _normalize
    return _scores(_entity_keys(gold), {(_normalize(e["type"]), _normalize(e["name"])) for e in predicted_entities})


def source_span_coverage(gold, predictions):
    """Supplement exact-quote hashes with character overlap, without changing them."""
    from scripts.evaluate_kg_extraction_backend import _relation_key
    total, covered, rows = 0, 0, 0
    for expected in gold:
        ev = expected['evidence']
        if 'span_start' not in ev or 'span_end' not in ev:
            continue
        total += ev['span_end'] - ev['span_start']
        positions = set()
        for predicted in predictions:
            pe = predicted['evidence']
            if (_relation_key(expected) == _relation_key(predicted)
                and all(ev.get(k) == pe.get(k) for k in ('document_id','page','chunk_index'))):
                start = max(ev['span_start'],pe['span_start'])
                end = min(ev['span_end'],pe['span_end'])
                positions.update(range(start,max(start,end)))
        covered += len(positions)
        rows += bool(positions)
    return dict(expected_characters=total, covered_characters=covered,
        character_recall=round(covered/total,6) if total else 0, gold_rows_with_overlap=rows,
        scope='supplementary matching-fact span overlap; not exact-quote recall or semantic adjudication')
