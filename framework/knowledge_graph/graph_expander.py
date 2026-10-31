"""Bounded one-hop graph expansion over persisted relation candidates.

R2.7. After the baseline hybrid retrieval settles, this module expands the
result set by one hop: documents that report effects of the same
``measure`` surface on the same ``indicator`` surface as a baseline
document. Expansion is bounded (hop-1 only, capped document count), shares
the same source/permission/version checks as the baseline, and records a
``graph`` trace that replaces the ``not_used_in_corpus_baseline``
placeholder.

Domain rule enforced by the v2 contract: relation source type is always
``measure``, target type is always ``indicator``, and the direction is
known.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import bindparam, text

from framework.models.knowledge_graph import (
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphRelationCandidate,
)
from framework.models.user import db

GRAPH_SCHEMA_VERSION = "task-evidence-extraction-v2"
MAX_HOP1_DOCUMENTS = 5


class BoundedGraphExpander:
    """One-hop expansion over pending relation candidates.

    The expander is optional: when not wired into ``PublishedCorpusSearch``
    the baseline graph placeholder remains untouched.
    """

    def __init__(self, session=None, *, max_hop1_documents: int = MAX_HOP1_DOCUMENTS):
        self.session = session or db.session
        self.max_hop1_documents = max_hop1_documents

    def _latest_job_for_document(self, document_id: int) -> KnowledgeGraphExtractionJob | None:
        return (
            self.session.query(KnowledgeGraphExtractionJob)
            .filter_by(document_id=document_id, schema_version=GRAPH_SCHEMA_VERSION)
            .order_by(KnowledgeGraphExtractionJob.id.desc())
            .first()
        )

    def _measure_indicator_surfaces(self, job_id: int) -> list[tuple[str, str]]:
        """Return (measure_surface, indicator_surface) and canonical pairs for a job's relations."""
        relations = (
            self.session.query(KnowledgeGraphRelationCandidate)
            .filter_by(job_id=job_id)
            .all()
        )
        if not relations:
            return []
        entity_ids = set()
        for rel in relations:
            entity_ids.add(rel.source_candidate_id)
            entity_ids.add(rel.target_candidate_id)
        entities = (
            self.session.query(KnowledgeGraphEntityCandidate)
            .filter(KnowledgeGraphEntityCandidate.id.in_(entity_ids))
            .all()
        )
        by_id = {e.id: e for e in entities}
        pairs = []
        for rel in relations:
            src = by_id.get(rel.source_candidate_id)
            tgt = by_id.get(rel.target_candidate_id)
            if src and tgt and src.entity_type == "measure" and tgt.entity_type == "indicator":
                # Use canonical_entity_id when available, fall back to surface.
                measure_key = src.canonical_entity_id or src.mention
                indicator_key = tgt.canonical_entity_id or tgt.mention
                pairs.append((measure_key, indicator_key))
        return pairs

    def _documents_with_matching_surfaces(
        self, surfaces: Sequence[tuple[str, str]], exclude_ids: set[int]
    ) -> list[int]:
        """Find document ids whose jobs have entities matching the surfaces or canonical IDs.

        Matching checks both surface text (e.mention) and canonical entity
        ID (e.canonical_entity_id) so that resolved entities match across
        documents even when surface text differs.
        """
        if not surfaces:
            return []
        measure_keys = list({s[0] for s in surfaces})
        indicator_keys = list({s[1] for s in surfaces})
        exclude_list = list(exclude_ids) if exclude_ids else []
        clause = (
            "SELECT DISTINCT j.document_id "
            "FROM kg_entity_candidate e "
            "JOIN kg_extraction_job j ON e.job_id = j.id "
            "WHERE ((e.entity_type = 'measure' "
            "        AND (e.mention IN :measures OR e.canonical_entity_id IN :measures)) "
            "   OR (e.entity_type = 'indicator' "
            "       AND (e.mention IN :indicators OR e.canonical_entity_id IN :indicators)))"
        )
        params: dict[str, Any] = {
            "measures": measure_keys,
            "indicators": indicator_keys,
        }
        if exclude_list:
            clause += " AND j.document_id NOT IN :exclude"
            params["exclude"] = exclude_list
        statement = text(clause).bindparams(
            bindparam("measures", expanding=True),
            bindparam("indicators", expanding=True),
        )
        if exclude_list:
            statement = statement.bindparams(bindparam("exclude", expanding=True))
        rows = self.session.execute(statement, params).scalars().all()
        return [int(r) for r in rows]

    def expand(
        self,
        baseline_document_ids: Sequence[int],
        *,
        current_sources,
        owner_id: int,
        kinds: Sequence[str],
    ) -> tuple[list[int], dict[str, Any]]:
        """Return (expanded_document_ids, graph_trace).

        ``current_sources`` must implement ``lookup_many(document_ids,
        owner_id, require_academic=...)`` returning the same mapping used by
        the baseline. Only documents that pass the shared source check are
        included in the expansion.
        """
        if not baseline_document_ids:
            return [], self._trace("not_used", 0, matched_surfaces=[])

        # Collect measure/indicator surfaces from baseline documents.
        baseline_set = set(baseline_document_ids)
        all_surfaces: list[tuple[str, str]] = []
        for doc_id in baseline_document_ids:
            job = self._latest_job_for_document(doc_id)
            if job is None:
                continue
            all_surfaces.extend(self._measure_indicator_surfaces(job.id))

        if not all_surfaces:
            return [], self._trace("not_used", 0, matched_surfaces=[])

        candidate_ids = self._documents_with_matching_surfaces(all_surfaces, baseline_set)
        if not candidate_ids:
            return [], self._trace("not_used", 0, matched_surfaces=all_surfaces)

        # Verify source eligibility for every candidate document.
        require_academic = tuple(kinds) == ("academic_paper",)
        try:
            verified = current_sources.lookup_many(
                candidate_ids, owner_id, require_academic=require_academic
            )
        except Exception:
            return [], self._trace("not_used", 0, matched_surfaces=all_surfaces, error="source_check_failed")

        def _eligible(live):
            return bool(
                live and live.get("visibility_scope") == "public"
                and live.get("review_status") == "approved"
                and live.get("completed")
                and live.get("source_bytes_valid") is True
                and live.get("document_kind") in kinds
            )

        accepted = [
            doc_id for doc_id in candidate_ids
            if _eligible(verified.get(doc_id))
        ]
        accepted = accepted[: self.max_hop1_documents]
        if not accepted:
            return [], self._trace("not_used", 0, matched_surfaces=all_surfaces)

        return accepted, self._trace("used", len(accepted), matched_surfaces=all_surfaces)

    @staticmethod
    def _trace(
        state: str, contributing_hits: int, *, matched_surfaces, error: str | None = None
    ) -> dict[str, Any]:
        trace: dict[str, Any] = {
            "state": state,
            "contributing_hits": contributing_hits,
            "hop": 1,
            "schema_version": GRAPH_SCHEMA_VERSION,
            "domain_rule": "source=measure, target=indicator, direction known",
            "matched_surfaces": len(matched_surfaces),
        }
        if error:
            trace["error"] = error
        return trace
