from __future__ import annotations

from flask import Flask

from framework.knowledge_graph.job_benchmark import (
    cleanup_job_benchmark, run_job_conservation_benchmark,
)
from framework.models.document import Document
from framework.models.knowledge_graph import (
    KnowledgeGraphExtractionJob, KnowledgeGraphOutboxEvent,
)
from framework.models.user import db


def test_small_isolated_smoke_run_proves_conservation_but_not_production_scale(tmp_path):
    database = tmp_path / "kg-job-benchmark.db"
    app = Flask("kg-job-benchmark")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{database}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        Document.__table__.create(db.engine)
        KnowledgeGraphExtractionJob.__table__.create(db.engine)
        KnowledgeGraphOutboxEvent.__table__.create(db.engine)

        report = run_job_conservation_benchmark(
            db.engine, namespace="synthetic-job-smoke", job_count=20,
            worker_concurrency=1, batch_size=7, require_postgresql=False,
        )

        assert report["unique_jobs"] == 20
        assert report["succeeded"] == 20
        assert report["failed"] == 0 and report["dead_letter"] == 0
        assert report["duplicate_business_effects"] == 0
        assert report["duplicate_delivery"]["reused"] == 20
        assert report["worker_restart_tested"] is True
        assert report["production_eligible"] is False

        cleaned = cleanup_job_benchmark(db.engine, namespace="synthetic-job-smoke")
        assert cleaned == {"jobs": 20, "events": 20, "documents": 20}
