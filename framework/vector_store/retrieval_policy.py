"""Versioned, bounded query vocabulary and independent document ranking.

Vocabulary contains concepts, never source identifiers, titles or answer labels.
It expands lexical lookup only; the original query still owns its vector.
"""
import re

VERSION = "soil-concepts-context-v3"
MEASURES = (
    ("生物炭", "biochar"),
    ("石灰", "lime", "liming"),
    ("粪肥", "畜禽粪", "manure"),
    ("稻草", "rice straw"),
    ("紫云英", "Chinese milk vetch", "milk vetch", "Astragalus sinicus"),
    ("堆肥", "compost"),
    ("石膏", "gypsum"),
    ("磷肥", "phosphate fertilizer"),
    ("氮肥", "nitrogen fertilizer"),
)
INDICATORS = (
    ("有机碳", "organic carbon", "SOC"),
    ("镉", "cadmium", "Cd"),
    ("产量", "yield"),
    ("物理性质", "physical properties", "physical", "aggregation", "porosity", "bulk density"),
    ("酸碱度", "pH"),
    ("铅", "lead", "Pb"),
    ("砷", "arsenic"),
    ("有效磷", "available phosphorus"),
)
CONTEXT = (
    ("长期", "long term", "long-term", "longterm"),
    ("酸性", "acidic", "acid"),
    ("碱性", "alkaline"),
    ("水稻", "稻田", "稻米", "rice", "paddy"),
    ("小麦", "wheat"),
    ("玉米", "maize", "corn"),
)


def _mentions(query, aliases):
    return any((alias.casefold() in query.casefold() if not alias.isascii() else
                re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", query, re.I))
               for alias in aliases)


def lexical_concept_groups(query):
    """AND mentioned concepts; OR only the aliases of the same concept.

    No recognized measure means no expansion. Recognized crop, acidity and
    duration constrain lexical matching, never certify condition applicability.
    The original leg preserves all other wording, negation and unknown context.
    """
    measures = [list(aliases) for aliases in MEASURES if _mentions(query, aliases)]
    indicators = [list(aliases) for aliases in INDICATORS if _mentions(query, aliases)]
    context = [list(aliases) for aliases in CONTEXT if _mentions(query, aliases)]
    return measures + indicators + context if measures else []


def interleave_unique(left, right, limit):
    values, seen = [], set()
    for index in range(max(len(left), len(right))):
        for leg, items in (("original", left), ("concepts", right)):
            if index >= len(items):
                continue
            item = items[index]
            meta = item["metadata"]
            key = ((meta["document_id"], meta.get("content_sha256"), meta["chunk_index"])
                   if meta.get("document_id") is not None and meta.get("chunk_index") is not None
                   else (meta.get("source"), item.get("content")))
            if key in seen:
                continue
            seen.add(key)
            values.append(dict(item, lexical_origin=leg))
            if len(values) == limit:
                return values
    return values


def rank_documents(chunks, k=60):
    """RRF of first document occurrence in each leg, without chunk-count votes.

    Only already-authorized chunks may be supplied. Keep every evidence locator
    in each document; document rank is not semantic support or evidence rank.
    """
    groups = {}
    for item in chunks:
        key = (item["document_id"], item["content_sha256"])
        groups.setdefault(key, []).append(item)
    leg_ranks = {key: {} for key in groups}
    for leg in ("vector", "lexical"):
        best = {}
        for key, items in groups.items():
            ranks = [item["retrieval"].get("retrieval_ranks", {}).get(leg) for item in items]
            ranks = [rank for rank in ranks if type(rank) is int and rank > 0]
            if ranks:
                best[key] = min(ranks)
        for rank, key in enumerate(sorted(best, key=lambda key: (best[key], key)), 1):
            leg_ranks[key][leg] = rank
    result = []
    for key, items in groups.items():
        ranks = leg_ranks[key]
        evidence = [{field: item.get(field) for field in ("chunk_index", "page", "retrieval", "conditions")}
                    for item in items]
        summary = {}
        for item in items:
            for field, value in (item.get("conditions") or {}).get("fields", {}).items():
                counts = summary.setdefault(field, {"matched": 0, "unknown": 0})
                counts[value["status"]] += 1
        entry = {"document_id": key[0], "content_sha256": key[1], "title": items[0]["title"],
                 "retrieval": {"method": "document_rrf", "k": k, "ranks": ranks,
                               "score": sum(1/(k+rank) for rank in ranks.values())},
                 "evidence_candidates": evidence, "support_verified": False}
        if items[0].get("publication") is not None:
            entry["publication"] = items[0]["publication"]
        if items[0].get("support") is not None:
            entry["support"] = items[0]["support"]
        if summary:
            entry["condition_summary"] = summary
        result.append(entry)
    return sorted(result, key=lambda item: -item["retrieval"]["score"])
