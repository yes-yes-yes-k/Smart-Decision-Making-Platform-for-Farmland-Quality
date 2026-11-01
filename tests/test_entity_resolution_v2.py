"""Unit tests for entity catalog and canonical matching."""
from __future__ import annotations

from framework.knowledge_graph.entity_catalog import (
    CANONICAL_ENTITIES,
    SURFACE_ALIASES,
    resolve_surface,
)


def test_all_31_surfaces_have_canonical_mapping():
    """Every surface in the alias table maps to a valid canonical entity."""
    for surface, canonical_id in SURFACE_ALIASES.items():
        assert canonical_id in CANONICAL_ENTITIES, f"{canonical_id} not in catalog (surface={surface!r})"


def test_within_document_dedup_pairs():
    """Three surface pairs share the same canonical (within-document dedup)."""
    assert resolve_surface("不同种植时间")[0] == resolve_surface("种植时间在80 d 左右")[0] == "planting_time"
    assert resolve_surface("根部组织中的铅")[0] == resolve_surface("根组织中的铅浓度")[0] == "root_tissue_pb"
    assert resolve_surface("吸收和累积量")[0] == resolve_surface("植物对铅的累积")[0] == "pb_accumulation"


def test_resolution_status():
    assert resolve_surface("水稻Cd浓度") == ("rice_cd_concentration", "rice Cd concentration", "resolved")
    assert resolve_surface("unknown surface") == (None, None, "unresolved")


def test_canonical_entity_type_consistency():
    """Each canonical entity has a valid entity type from the v2 contract."""
    valid_types = {"measure", "indicator", "soil", "crop", "condition", "location"}
    for cid, (name, etype) in CANONICAL_ENTITIES.items():
        assert etype in valid_types, f"{cid} has invalid type {etype}"


def test_no_cross_document_canonical_matches():
    """Currently no canonical is shared across documents (papers study different topics)."""
    from framework.knowledge_graph.entity_catalog import cross_document_canonical_matches
    assert cross_document_canonical_matches() == {}


def test_canonical_match_enables_graph_expansion(tmp_path):
    """Two documents with the same canonical_entity_id should match in graph expansion."""
    from flask import Flask
    from framework.knowledge_graph.candidate_store import write_bundle
    from framework.knowledge_graph.graph_expander import BoundedGraphExpander
    from framework.models.document import Document
    from framework.models.user import User, db
    from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema

    SHA = "a" * 64

    def _span(doc_id, quote="Cd"):
        return {"document_id": doc_id, "document_sha256": SHA, "parse_version": SHA,
                "chunk_set_version": SHA, "chunk_index": 0, "start": 0, "end": len(quote),
                "quote": quote, "page": 1, "quote_sha256": SHA, "id": f"span:{doc_id}"}

    def _bundle(doc_id, measure_surface, indicator_surface):
        span = _span(doc_id)
        return {
            "schema_version": "task-evidence-extraction-v2",
            "source": {"document_id": doc_id, "document_sha256": SHA,
                        "parse_version": SHA, "chunk_set_version": SHA},
            "provenance": {"origin": "test", "configuration_sha256": SHA},
            "studies": [{"local_id": "s1", "kind": "observational",
                          "context": [span], "attribution": None}],
            "entities": [
                {"local_id": "e_src", "study_id": "s1", "entity_type": "measure",
                 "surface": measure_surface, "mention": span,
                 "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}},
                {"local_id": "e_tgt", "study_id": "s1", "entity_type": "indicator",
                 "surface": indicator_surface, "mention": span,
                 "normalization": {"status": "unresolved", "canonical_id": None, "canonical_name": None}},
            ],
            "relations": [{
                "id": f"research:{doc_id}", "local_id": "r1", "study_id": "s1",
                "relation_type": "reports_effect", "source_id": "e_src", "target_id": "e_tgt",
                "result": span, "direction": "increase",
                "qualifiers": {"dose": {"status": "unknown", "evidence": None}},
                "review_status": "pending", "semantic_support": "unreviewed",
            }],
            "review_status": "pending", "published_claims_added": 0,
            "rule_validation": "passed", "semantic_support": "unreviewed",
            "identity": f"identity-{doc_id}",
        }

    app = Flask("canonical-match-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'canonical.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    context = app.app_context()
    context.push()
    User.__table__.create(db.engine)
    Document.__table__.create(db.engine)
    ensure_knowledge_graph_platform_schema(db.engine)
    db.session.add(User(id=1, username="admin", password="x", role="admin"))
    for doc_id in (100, 200):
        db.session.add(Document(
            id=doc_id, doc_name=f"paper-{doc_id}.pdf", file_path=f"{doc_id}.pdf",
            file_type="pdf", chunk_count=1, status=Document.STATUS_COMPLETED,
            processing_stage="completed", review_status=Document.REVIEW_APPROVED,
            visibility_scope="public", document_kind="academic_paper",
            file_hash=SHA, create_by=1,
        ))
    db.session.commit()

    # Doc 100: surface "Cd施用" → canonical "cadmium_application" (measure)
    # Doc 200: surface "Cd添加" → canonical "cadmium_application" (measure, DIFFERENT surface, SAME canonical)
    write_bundle(_bundle(100, "Cd施用", "水稻Cd"))
    write_bundle(_bundle(200, "Cd添加", "水稻Cd"))

    # Manually set canonical_entity_id (simulating entity resolution)
    from framework.models.knowledge_graph import KnowledgeGraphEntityCandidate
    for ent in db.session.query(KnowledgeGraphEntityCandidate).all():
        if ent.mention == "Cd施用" or ent.mention == "Cd添加":
            ent.canonical_entity_id = "cadmium_application"
            ent.canonical_name = "cadmium application"
            ent.resolution_status = "resolved"
    db.session.commit()

    # Graph expansion should find doc 200 via canonical match
    expander = BoundedGraphExpander()

    class _Sources:
        def lookup_many(self, ids, owner_id, require_academic=False):
            return {doc_id: {"title": f"doc {doc_id}", "document_kind": "academic_paper",
                             "content_sha256": SHA, "visibility_scope": "public",
                             "review_status": "approved", "completed": True,
                             "source_bytes_valid": True} for doc_id in ids}

    expanded_ids, trace = expander.expand(
        [100], current_sources=_Sources(), owner_id=1, kinds=("academic_paper",)
    )
    assert 200 in expanded_ids, f"doc 200 should be found via canonical match, got {expanded_ids}"
    assert trace["state"] == "used"
    assert trace["contributing_hits"] >= 1
    context.pop()
