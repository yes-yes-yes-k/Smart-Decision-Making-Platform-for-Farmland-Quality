from framework.knowledge import service
from framework.models.document_label import DocumentLabel


def test_ingestion_persists_only_explicit_labels(monkeypatch):
    calls = []

    def fake_upsert(document_id, label_code, **kwargs):
        calls.append((document_id, label_code, kwargs))

    monkeypatch.setattr(service, "_upsert_assignment", fake_upsert)
    monkeypatch.setattr(service.db.session, "flush", lambda: None)

    approved = service.assign_labels_for_ingestion(
        12,
        explicit_labels=["cultivated_land_quality"],
        text="镉污染、重金属、粮食安全、粮食产能",
        actor_id=7,
    )

    assert approved == ["cultivated_land_quality"]
    assert len(calls) == 1
    document_id, label_code, kwargs = calls[0]
    assert document_id == 12
    assert label_code == "cultivated_land_quality"
    assert kwargs["status"] == DocumentLabel.STATUS_APPROVED
    assert kwargs["source"] == DocumentLabel.SOURCE_MANUAL
    assert kwargs["confidence"] == 1.0


def test_ingestion_with_no_explicit_labels_creates_no_assignments(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service, "_upsert_assignment", lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(service.db.session, "flush", lambda: None)

    approved = service.assign_labels_for_ingestion(
        13,
        explicit_labels=[],
        text="耕地质量、重金属、粮食安全",
        actor_id=7,
    )

    assert approved == []
    assert calls == []
