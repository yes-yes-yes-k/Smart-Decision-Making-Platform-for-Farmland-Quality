"""Unit tests for R2.7 bounded graph expansion."""
from __future__ import annotations

from flask import Flask

from framework.knowledge_graph.candidate_store import write_bundle
from framework.knowledge_graph.graph_expander import BoundedGraphExpander
from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
from framework.models.document import Document
from framework.models.user import User, db
from scripts.migrate_knowledge_graph_platform import ensure_knowledge_graph_platform_schema

SHA = "a" * 64


def _span(doc_id, quote="Cd在水稻"):
    return {
        "document_id": doc_id, "document_sha256": SHA, "parse_version": SHA,
        "chunk_set_version": SHA, "chunk_index": 0,
        "start": 0, "end": len(quote), "quote": quote, "page": 1,
        "quote_sha256": SHA, "id": f"span:{doc_id}",
    }


def _bundle(doc_id, *, measure_surface="Cd", indicator_surface="rice Cd"):
    span = _span(doc_id, measure_surface + "在")
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


class _Store:
    def __init__(self, items):
        self.items = items

    def hybrid_search(self, query, n_results=20, filters=None, **kwargs):
        return {"results": self.items[:n_results], "retrieval": {"mode": "hybrid"}}

    def get_by_references(self, references, *, filters=None, n_results=20):
        return []


class _Sources:
    def __init__(self, eligible_ids):
        self.eligible_ids = set(eligible_ids)

    def lookup_many(self, ids, owner_id, require_academic=False):
        return {
            doc_id: {
                "title": f"doc {doc_id}", "document_kind": "academic_paper",
                "content_sha256": SHA, "version": "v1",
                "visibility_scope": "public", "review_status": "approved",
                "completed": True, "source_bytes_valid": True,
            }
            for doc_id in ids if doc_id in self.eligible_ids
        }


def _chunk(doc_id, index=0):
    return {
        "content": "Cd在水稻", "retrieval_ranks": {"vector": index + 1},
        "metadata": {"document_id": doc_id, "document_kind": "academic_paper",
                     "content_sha256": SHA, "chunk_index": index, "page": 1},
    }


def _setup(tmp_path, *, eligible_docs=(100, 200)):
    app = Flask("graph-expander-test")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'graph.db'}",
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
    # Write bundles: doc 100 and doc 200 share measure="Cd" and indicator="rice Cd"
    write_bundle(_bundle(100))
    write_bundle(_bundle(200))
    return _Sources(eligible_docs)


def test_graph_expansion_adds_related_document(tmp_path):
    sources = _setup(tmp_path)
    store = _Store([_chunk(100)])  # baseline only finds doc 100
    expander = BoundedGraphExpander()
    search = PublishedCorpusSearch(store, sources, graph_expander=expander)
    response = search.search(1, {"query": "Cd", "graph": True})
    assert response["graph"]["state"] == "used"
    assert response["graph"]["contributing_hits"] == 1
    assert response["graph"]["hop"] == 1
    assert response["graph"]["schema_version"] == "task-evidence-extraction-v2"
    doc_ids = [d["document_id"] for d in response["documents"]]
    assert 100 in doc_ids
    assert 200 in doc_ids  # graph-expanded
    expanded = [d for d in response["documents"] if d.get("graph_expanded")]
    assert len(expanded) == 1 and expanded[0]["document_id"] == 200


def test_graph_off_keeps_placeholder(tmp_path):
    sources = _setup(tmp_path)
    store = _Store([_chunk(100)])
    expander = BoundedGraphExpander()
    search = PublishedCorpusSearch(store, sources, graph_expander=expander)
    response = search.search(1, {"query": "Cd"})  # no graph=True
    assert response["graph"]["state"] == "not_used_in_corpus_baseline"
    assert response["graph"]["contributing_hits"] == 0


def test_ineligible_source_excluded_from_expansion(tmp_path):
    # Doc 200 exists in DB with candidates but is NOT in eligible sources.
    sources = _setup(tmp_path, eligible_docs=(100,))
    store = _Store([_chunk(100)])
    expander = BoundedGraphExpander()
    search = PublishedCorpusSearch(store, sources, graph_expander=expander)
    response = search.search(1, {"query": "Cd", "graph": True})
    # Doc 200 found by graph but rejected by source check.
    assert response["graph"]["state"] == "not_used"
    assert response["graph"]["contributing_hits"] == 0
    doc_ids = [d["document_id"] for d in response["documents"]]
    assert 200 not in doc_ids


def test_no_matching_surfaces_returns_not_used(tmp_path):
    sources = _setup(tmp_path, eligible_docs=(100, 200, 300))
    # Write a third doc with non-matching surfaces and add it to kb_document.
    db.session.add(Document(
        id=300, doc_name="paper-300.pdf", file_path="300.pdf",
        file_type="pdf", chunk_count=1, status=Document.STATUS_COMPLETED,
        processing_stage="completed", review_status=Document.REVIEW_APPROVED,
        visibility_scope="public", document_kind="academic_paper",
        file_hash=SHA, create_by=1,
    ))
    db.session.commit()
    write_bundle(_bundle(300, measure_surface="pH", indicator_surface="yield"))
    store = _Store([_chunk(300)])  # baseline only finds doc 300
    expander = BoundedGraphExpander()
    search = PublishedCorpusSearch(store, sources, graph_expander=expander)
    response = search.search(1, {"query": "pH", "graph": True})
    # Doc 300 has pH/yield surfaces; docs 100/200 have Cd/rice Cd — no match.
    assert response["graph"]["state"] == "not_used"
    assert response["graph"]["contributing_hits"] == 0
