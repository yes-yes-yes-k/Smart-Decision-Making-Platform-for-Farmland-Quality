"""Read-only candidate attribution helpers; never change retrieval ranks."""
from __future__ import annotations

import hashlib


def pointer(item):
    meta = item.get("metadata", item)
    text = item.get("content", item.get("text", ""))
    value = {"document_id": meta.get("document_id"), "content_sha256": meta.get("content_sha256"),
             "chunk_index": meta.get("chunk_index"), "page": meta.get("page"),
             "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
    scores = item.get("retrieval", item)
    for key in ("distance", "score", "rrf_score", "retrieval_ranks"):
        if key in scores:
            value[key] = scores[key]
    return value


def signature(item):
    return tuple(item.get(k) for k in ("document_id", "content_sha256", "chunk_index", "page", "text_sha256"))


def valid_paper(item, live):
    """Mirror the frozen baseline predicate for diagnostics, not authorization."""
    meta = item["metadata"]
    return bool(live and live.get("visibility_scope") == "public" and live.get("review_status") == "approved"
                and live.get("completed") and live.get("source_bytes_valid") is True
                and live.get("content_sha256") and live["content_sha256"] == meta.get("content_sha256")
                and live.get("document_kind") == "academic_paper" and meta.get("document_kind") == "academic_paper")


def target_summary(document_id, stages, *, limit=20, source_checks_verified=True):
    """Ranks below are chunk ranks; first-seen paper order is diagnostic only."""
    ranks = {}
    for name, candidates in stages.items():
        positions = [i for i, c in enumerate(candidates, 1) if c["document_id"] == document_id]
        papers = list(dict.fromkeys(c["document_id"] for c in candidates))
        ranks[name] = {"chunk_ranks": positions, "best_chunk_rank": positions[0] if positions else None,
                       "first_seen_paper_order": papers.index(document_id)+1 if document_id in papers else None,
                       "candidate_count": len(candidates)}
    present = lambda name: bool(ranks[name]["chunk_ranks"])
    if present("returned"):
        loss = "returned"
    elif not present("vector") and not present("lexical"):
        loss = "absent_from_both_top60_not_proof_of_corpus_absence"
    elif not present("fused_full"):
        loss = "unexpected_fusion_identity_loss"
    elif not present("fused_top60"):
        loss = "fusion_top60_truncation"
    elif not source_checks_verified:
        loss = "current_source_stage_unresolved"
    elif not present("after_source_checks"):
        loss = "current_source_validation_filtered"
    else:
        loss = "final_top"+str(limit)+"_truncation"
    return {"document_id": document_id, "stages": ranks, "loss_stage": loss,
            "ranking_unit": "chunk; paper order is first occurrence, not a new document ranking algorithm"}
