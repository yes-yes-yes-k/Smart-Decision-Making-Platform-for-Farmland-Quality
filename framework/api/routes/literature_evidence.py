"""Authenticated product routes; service is explicitly configured, never migrated here."""
from dataclasses import dataclass

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy.exc import SQLAlchemyError

from framework.knowledge_graph.research_service import ResearchError

literature_evidence_bp = Blueprint("literature_evidence", __name__)


@dataclass(frozen=True)
class EvidenceActor:
    id: int
    role: str
    active: bool = True


def default_actor(identity):
    from framework.models.user import User, db
    try:
        user = db.session.get(User, int(identity))
    except (TypeError, ValueError):
        return None
    return EvidenceActor(user.id, user.role, user.status == 1) if user else None


def context():
    resolver = current_app.extensions.get("literature_evidence_actor_resolver", default_actor)
    try:
        actor = resolver(get_jwt_identity())
    except Exception:
        raise ResearchError("identity_verification_unavailable", 503) from None
    if actor is None or not actor.active:
        raise ResearchError("active_authenticated_user_required", 403)
    service = current_app.extensions.get("literature_evidence_service")
    if service is None:
        raise ResearchError("literature_evidence_not_configured", 503)
    try:
        service.store.require_schema()
    except ValueError:
        raise ResearchError("literature_evidence_explicit_migration_required", 503) from None
    return actor, service


@literature_evidence_bp.errorhandler(ResearchError)
def handle_error(error):
    return jsonify({"status": "error", "error_code": error.code}), error.status


@literature_evidence_bp.errorhandler(SQLAlchemyError)
def handle_storage_error(error):
    return jsonify({"status": "error", "error_code": "literature_evidence_storage_unavailable"}), 503


@literature_evidence_bp.post("/search")
@jwt_required()
def search():
    actor, service = context()
    return jsonify(service.search(actor.id, request.get_json(silent=True)))


@literature_evidence_bp.post("/comparisons")
@jwt_required()
def submit():
    actor, service = context()
    job, reused = service.submit(actor.id, request.get_json(silent=True))
    return jsonify(job | {"reused": reused}), 200 if job["state"] == "completed" else 202


@literature_evidence_bp.get("/comparisons/<identifier>")
@jwt_required()
def comparison(identifier):
    actor, service = context()
    return jsonify(service.get(actor.id, identifier))


@literature_evidence_bp.delete("/comparisons/<identifier>")
@jwt_required()
def cancel(identifier):
    actor, service = context()
    return jsonify(service.cancel(actor.id, identifier))


@literature_evidence_bp.get("/sources")
@jwt_required()
def source_catalog():
    actor, service = context()
    identifiers = service.store.source_ids()
    if not identifiers:
        return jsonify({"sources": []})
    snapshot, _, problems, _ = service.snapshot(actor.id, {"document_ids": identifiers})
    values = [{"document_id": did, "title": item["stored"]["payload"]["title"],
               "content_sha256": item["stored"]["content_sha256"],
               "extraction": item["stored"]["payload"].get("extraction_summary")} for did, item in snapshot.items()]
    return jsonify({"sources": values, "source_problems": problems, "scope": "registered_M1_papers"})


@literature_evidence_bp.get("/sources/<int:document_id>/chunks/<int:index>")
@jwt_required()
def source_chunk(document_id, index):
    actor, service = context()
    return jsonify(service.read_chunk(actor.id, document_id, index, request.args.get("content_sha256")))


@literature_evidence_bp.post("/records/<path:record_id>/reject")
@jwt_required()
def reject_record(record_id):
    actor, service = context()
    if actor.role != "admin":
        raise ResearchError("reviewer_required", 403)
    service.store.reject_record(record_id)
    return jsonify({"status": "rejected_or_already_absent", "record_id": record_id})


def create_evidence_app(service, actor_resolver, *, jwt_secret):
    """Lightweight instance using the same blueprint; no app startup migrations."""
    from flask import Flask
    from flask_jwt_extended import JWTManager
    app = Flask("literature-evidence")
    app.config["JWT_SECRET_KEY"] = jwt_secret
    JWTManager(app)
    app.extensions["literature_evidence_service"] = service
    app.extensions["literature_evidence_actor_resolver"] = actor_resolver
    app.register_blueprint(literature_evidence_bp, url_prefix="/api/v1/literature-evidence")
    return app


def configure_evidence_service(app):
    """Opt-in only. Missing configuration never creates a database or schema."""
    uri = app.config.get("LITERATURE_EVIDENCE_DATABASE_URI")
    if not uri:
        return
    import sqlalchemy as sa
    from pathlib import Path
    from framework.knowledge_graph.research_store import ResearchStore
    from framework.knowledge_graph.research_service import ResearchService
    from framework.knowledge_graph.research_sources import PublishedResearchSources
    engine = sa.create_engine(uri)
    try:
        if engine.dialect.name == "sqlite" and (not engine.url.database or not Path(engine.url.database).is_file()):
            raise ValueError("research_database_must_be_explicitly_prepared")
        store = ResearchStore(engine)
        store.require_schema()
        source = PublishedResearchSources(app.config["SQLALCHEMY_DATABASE_URI"], app.config["UPLOAD_FOLDER"])
        from framework.knowledge_graph.research_retrieval import PublishedCorpusSearch
        from framework.vector_store.chroma_store import vector_store
        app.extensions["literature_evidence_service"] = ResearchService(store, source, corpus_search=PublishedCorpusSearch(
            vector_store, source, enhance_recall=app.config.get("LITERATURE_EVIDENCE_DOMAIN_EXPANSION", True)))
        app.extensions["literature_evidence_source_adapter"] = source
    except (ValueError, SQLAlchemyError):
        engine.dispose()
        app.extensions["literature_evidence_service"] = None
        app.extensions["literature_evidence_configuration_error"] = "explicit_configuration_or_migration_required"
