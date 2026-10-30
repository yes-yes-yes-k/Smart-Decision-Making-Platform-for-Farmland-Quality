"""Bounded hybrid retrieval with authoritative current-source revalidation.

Query embedding is performed by the configured vector store during real use.
This module neither creates clients nor generates answers.

R1.3 keeps three answers apart: publication identity (which current source and
version produced the text), support (semantic support is never asserted here)
and conditions (an explicit surface match in the authorized chunk text only).
A condition term that is absent from a chunk is reported as unknown, never as
matching; a per-chunk mismatch cannot be derived from text, so mismatch stays
undetermined in this path and is only expressed by the structured record path.
"""
import re

from .research_service import ResearchError
from framework.vector_store.retrieval_policy import rank_documents

SOURCE_SCOPES = {
    "papers": ("academic_paper",),
    "standards": ("standard",),
    "guidelines": ("method_guideline",),
    "policies": ("policy",),
    "all_qualified": ("academic_paper", "standard", "policy", "method_guideline"),
}
CONDITION_FIELDS = ("measure", "indicator", "soil_type", "conditions")
REQUEST_FIELDS = {"query", "limit", "document_ids", "source_scope", "require_condition_match"} | set(CONDITION_FIELDS)


def locate_surface(text, value):
    """Locate an explicit, whitespace-tolerant surface occurrence.

    Returns codepoint offsets into the given text or None. This is a locator,
    not a semantic equivalence or applicability judgement.
    """
    tokens = [re.escape(part) for part in value.split()]
    if not tokens:
        return None
    match = re.search(r"\s+".join(tokens), text, re.IGNORECASE)
    return None if match is None else {"start": match.start(), "end": match.end(), "quote": match.group(0)}


def evaluate_conditions(request, text):
    """Three-valued condition report for one chunk: matched or unknown only."""
    requested = {field: request[field].strip() for field in CONDITION_FIELDS
                 if isinstance(request.get(field), str) and request[field].strip()}
    if not requested:
        return {"requested": {}, "fields": {}, "matched": [], "unknown": [], "evaluation": "not_requested",
                "mismatch_detection": "not_requested"}
    fields = {}
    for field, value in requested.items():
        hit = locate_surface(text, value)
        fields[field] = {"status": "matched" if hit else "unknown", "match": hit,
                         "basis": "explicit_surface_text_match" if hit else "filter_term_absent_from_this_chunk"}
    return {"requested": requested, "fields": fields,
            "matched": [field for field, value in fields.items() if value["status"] == "matched"],
            "unknown": [field for field, value in fields.items() if value["status"] == "unknown"],
            "evaluation": "explicit_surface_text_match",
            "mismatch_detection": "not_derivable_from_single_chunk_text"}


def _publication(document_id, live, scope):
    """Publication identity of the exact current source version, not support."""
    return {"document_id": document_id, "document_kind": live.get("document_kind"),
            "title": live.get("title"), "content_sha256": live.get("content_sha256"),
            "version": live.get("version"), "visibility_scope": live.get("visibility_scope"),
            "review_status": live.get("review_status"), "lifecycle_state": "completed",
            "source_bytes_valid": True, "revalidated_before_return": True, "requested_source_scope": scope}


def _support(conditions):
    """Semantic support is unreviewed; a surface condition match is not support."""
    return {"support_verified": False, "semantic_support": "unreviewed",
            "role": "unreviewed_candidate_not_support", "direct_support_claimed": False,
            "condition_surface_match_is_support": False,
            "evaluation": "not_performed" if not conditions["requested"] else "conditions_only_not_support"}


class PublishedCorpusSearch:
    def __init__(self, vector_store, current_sources, *, enhance_recall=True):
        self.vector_store, self.current_sources = vector_store, current_sources
        self.enhance_recall = enhance_recall

    def search(self, owner_id, request):
        if not isinstance(request, dict):
            raise ResearchError("invalid_corpus_request")
        query, limit = request.get("query"), request.get("limit", 20)
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or type(limit) is not int or not 1 <= limit <= 30:
            raise ResearchError("invalid_corpus_query_or_limit")
        if set(request)-REQUEST_FIELDS:
            raise ResearchError("invalid_comparison_request")
        for field in CONDITION_FIELDS:
            value = request.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 300):
                raise ResearchError("invalid_research_filter")
        strict = request.get("require_condition_match", False)
        if type(strict) is not bool:
            raise ResearchError("invalid_research_filter")
        requested_conditions = [field for field in CONDITION_FIELDS
                                if isinstance(request.get(field), str) and request[field].strip()]
        if strict and not requested_conditions:
            raise ResearchError("invalid_research_filter")
        scope = request.get("source_scope", "papers")
        if not isinstance(scope, str) or scope not in SOURCE_SCOPES:
            raise ResearchError("invalid_corpus_source_scope")
        kinds = SOURCE_SCOPES[scope]
        require_academic = kinds == ("academic_paper",)
        where = {"$and": [{"visibility_scope": "public"}, {"document_kind": {"$in": list(kinds)}}]}
        identifiers = request.get("document_ids")
        if identifiers is not None:
            if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 1000 or any(type(value) is not int or value <= 0 for value in identifiers):
                raise ResearchError("invalid_corpus_document_scope")
            where = {"$and": [where, {"document_id": {"$in": identifiers}}]}
        budget = min(90, limit*3)
        try:
            options = {"domain_expansion": True} if self.enhance_recall else {}
            result = self.vector_store.hybrid_search(query, n_results=budget, filters=where, **options)
            candidates = result["results"][:budget]
            trace = result.get("retrieval", {"mode": "unknown"})
        except Exception:
            raise ResearchError("corpus_retrieval_unavailable", 503) from None
        if not candidates and (trace.get("mode") in {"degraded", "unknown"} or trace.get("state") in {"failed", "unavailable"}):
            raise ResearchError("corpus_retrieval_unavailable", 503)
        ids = sorted({item["metadata"].get("document_id") for item in candidates if type(item["metadata"].get("document_id")) is int})
        try:
            current = self.current_sources.lookup_many(ids, owner_id, require_academic=require_academic)
        except Exception:
            raise ResearchError("current_source_verification_unavailable", 503) from None
        def valid(item, live):
            meta = item["metadata"]
            return bool(live and live.get("visibility_scope") == "public" and live.get("review_status") == "approved" and live.get("completed")
                and live.get("source_bytes_valid") is True and live.get("content_sha256") == meta.get("content_sha256")
                and live.get("content_sha256") and live.get("document_kind") in kinds
                and meta.get("document_kind") == live.get("document_kind"))
        accepted = [item for item in candidates if valid(item, current.get(item["metadata"].get("document_id")))]
        returned_ids = sorted({item["metadata"]["document_id"] for item in accepted})
        try:
            final = self.current_sources.lookup_many(returned_ids, owner_id, require_academic=require_academic)
        except Exception:
            raise ResearchError("current_source_verification_unavailable", 503) from None
        values = []
        survived = excluded_unknown = matched_candidates = unknown_candidates = 0
        for item in accepted:
            meta = item["metadata"]; live = final.get(meta["document_id"])
            if not valid(item, live):
                continue
            survived += 1
            conditions = evaluate_conditions(request, item["content"])
            if conditions["requested"]:
                if conditions["unknown"]:
                    unknown_candidates += 1
                    if strict:
                        excluded_unknown += 1
                        continue
                else:
                    matched_candidates += 1
            values.append({"document_id": meta["document_id"], "title": live["title"],
                "content_sha256": live["content_sha256"],
                "chunk_index": meta.get("chunk_index"), "page": meta.get("page"), "text": item["content"],
                "retrieval": {key: item[key] for key in ("distance", "rrf_score", "retrieval_ranks") if key in item},
                "publication": _publication(meta["document_id"], live, scope), "support": _support(conditions),
                "conditions": conditions})
        rejected = len(candidates)-survived
        documents = rank_documents(values)
        return {"state": "completed" if not rejected and trace.get("mode") == "hybrid" else "partial", "sources": values[:limit],
            "documents": documents[:limit], "document_ranking": "document_rrf_over_current_verified_candidates",
            "document_candidates": len(documents), "evidence_ranking": "chunk_rrf_not_semantic_support",
            "scope": "current_eligible_published_corpus", "source_scope": scope,
            "source_scope_kinds": list(kinds),
            "retrieval_backend": ("hybrid_with_current_source_checks" if trace.get("mode") == "hybrid"
                                  else "degraded_or_single_path_with_current_source_checks"), "retrieval": trace,
            "graph": {"state": "not_used_in_corpus_baseline", "contributing_hits": 0},
            "generation_performed": False, "candidate_budget": budget, "candidates_read": len(candidates),
            "filtered_unverified_or_stale": rejected, "truncated_by_limit": max(0, len(values)-limit),
            "conditions_structurally_evaluated": True,
            "condition_filter": {"policy": "explicit_surface_text_match", "strict": strict,
                "requested": {field: request[field].strip() for field in requested_conditions},
                "matched_candidates": matched_candidates, "unknown_candidates": unknown_candidates,
                "excluded_unknown": excluded_unknown,
                "mismatch_detection": "not_derivable_from_single_chunk_text",
                "unknown_not_treated_as_match": True},
            "comparison_scope_is_separate": True}

    def read_chunk(self, owner_id, document_id, index, expected_sha):
        live = self.current_sources.lookup_many([document_id], owner_id, require_academic=False).get(document_id)
        if not live or not live.get("completed") or live.get("visibility_scope") != "public" or live.get("review_status") != "approved" or not live.get("source_bytes_valid") or expected_sha != live.get("content_sha256"):
            raise ResearchError("source_version_or_permissions_changed", 409)
        where = {"$and": [{"visibility_scope": "public"}, {"content_sha256": expected_sha}]}
        values = self.vector_store.get_by_references([{"document_id": document_id, "chunk_index": index}], filters=where, n_results=1)
        final = self.current_sources.lookup_many([document_id], owner_id, require_academic=False).get(document_id)
        if not final or not final.get("completed") or final.get("visibility_scope") != "public" or final.get("review_status") != "approved" or not final.get("source_bytes_valid") or expected_sha != final.get("content_sha256"):
            raise ResearchError("source_version_or_permissions_changed", 409)
        if not values:
            raise ResearchError("source_chunk_not_found", 404)
        item = values[0]
        return {"document_id": document_id, "content_sha256": expected_sha, "chunk_index": index,
                "page": item["metadata"].get("page"), "text": item["content"]}
