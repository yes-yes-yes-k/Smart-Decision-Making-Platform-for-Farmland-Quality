from __future__ import annotations

from typing import Iterable, List

from framework.knowledge.taxonomy import (
    domain_metadata,
    expand_with_parent_domains,
    label_level,
    parent_domain,
)
from framework.models.document_label import DocumentLabel
from framework.models.user import db


def approved_label_codes(document_id: int) -> List[str]:
    rows = DocumentLabel.query.filter_by(
        document_id=document_id,
        review_status=DocumentLabel.STATUS_APPROVED,
    ).all()
    return sorted(row.label_code for row in rows)


def _upsert_assignment(
    document_id: int,
    label_code: str,
    *,
    status: str,
    source: str,
    actor_id: int,
    confidence=None,
    evidence=None,
) -> DocumentLabel:
    row = DocumentLabel.query.filter_by(
        document_id=document_id, label_code=label_code,
    ).first()
    if row is None:
        row = DocumentLabel(
            document_id=document_id,
            label_code=label_code,
            label_level=label_level(label_code),
            parent_code=parent_domain(label_code),
            review_status=status,
            assignment_source=source,
            create_by=actor_id,
        )
        db.session.add(row)
    elif row.review_status == DocumentLabel.STATUS_REJECTED and status == DocumentLabel.STATUS_PENDING:
        # A human rejection is sticky until a reviewer explicitly changes it.
        return row
    else:
        row.review_status = status
        row.assignment_source = source
    row.confidence = confidence
    row.evidence = list(evidence or [])
    return row


def assign_labels_for_ingestion(
    document_id: int,
    *,
    explicit_labels: Iterable[str],
    text: str,
    actor_id: int,
) -> List[str]:
    """Persist only labels explicitly supplied with the upload request.

    ``text`` remains in the signature for compatibility with existing callers,
    but ingestion deliberately does not classify it or create review candidates.
    """
    approved = expand_with_parent_domains(explicit_labels)
    for code in approved:
        _upsert_assignment(
            document_id,
            code,
            status=DocumentLabel.STATUS_APPROVED,
            source=DocumentLabel.SOURCE_MANUAL,
            actor_id=actor_id,
            confidence=1.0,
        )
    db.session.flush()
    return approved


def vector_access_metadata(visibility_scope: str, approved_labels: Iterable[str]):
    return {
        "visibility_scope": visibility_scope,
        **domain_metadata(approved_labels),
    }
