"""Independent leased worker: outbox -> extraction -> reviewable candidates."""
import logging
import threading
from .adapters.live_graphrag import ExtractionBackendError
from .adapters.graphrag import GraphRagAdapterError
from .candidate_pipeline import CandidatePipeline, CandidatePipelineError, ExtractionInputBuilder
from .contracts import stable_digest
from .jobs import KnowledgeGraphOutboxDispatcher, SqlAlchemyGraphJobExecutor, utcnow_naive
from framework.models.document import Document
from framework.models.knowledge_graph import KnowledgeGraphExtractionJob

LOG = logging.getLogger(__name__)


class GraphExtractionWorker:
    def __init__(self, session_factory, backend, chunk_reader, *, worker_id,
                 lease_seconds=120, heartbeat_seconds=30, pipeline_factory=CandidatePipeline):
        if not worker_id or not 0 < heartbeat_seconds < lease_seconds:
            raise ValueError("worker identity and heartbeat shorter than lease are required")
        self.sessions, self.backend, self.reader = session_factory, backend, chunk_reader
        self.worker_id, self.lease_seconds = worker_id, lease_seconds
        self.heartbeat_seconds, self.pipeline_factory = heartbeat_seconds, pipeline_factory

    def _lock_owned_job(self, session, job_id):
        job = session.query(KnowledgeGraphExtractionJob).filter_by(id=job_id).with_for_update().one()
        if not SqlAlchemyGraphJobExecutor._owns_live_lease(job, self.worker_id, utcnow_naive()):
            raise ExtractionBackendError("lease_lost")
        return job

    def _heartbeat(self, job_id, stop, lost):
        while not stop.wait(self.heartbeat_seconds):
            try:
                with self.sessions() as session:
                    self._lock_owned_job(session, job_id)
                    if not SqlAlchemyGraphJobExecutor(session).renew(
                        worker_id=self.worker_id, job_id=str(job_id), lease_seconds=self.lease_seconds,
                    ):
                        lost.set()
                        return
                    session.commit()
            except Exception:
                lost.set()
                return

    def run_once(self):
        with self.sessions() as session:
            counts = KnowledgeGraphOutboxDispatcher(session).dispatch()
            session.commit()
            jobs = SqlAlchemyGraphJobExecutor(session).claim(
                worker_id=self.worker_id, limit=1, lease_seconds=self.lease_seconds,
            )
            job_id = jobs[0].id if jobs else None
            session.commit()
        if job_id is None:
            return dict(outbox=counts, processed=0)
        stop, lost = threading.Event(), threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(job_id, stop, lost), daemon=True)
        heartbeat.start()
        try:
            with self.sessions() as session:
                job = session.get(KnowledgeGraphExtractionJob, job_id)
                if (job.backend_name != self.backend.name or job.extractor_version != self.backend.version or
                        job.backend_config_digest != self.backend._config_digest):
                    raise ExtractionBackendError("backend_config_mismatch")
                request = ExtractionInputBuilder(session, self.reader).build(job)
            result = self.backend.extract(request)
            stop.set()
            heartbeat.join()
            if lost.is_set():
                raise ExtractionBackendError("lease_lost")
            with self.sessions() as session:
                job = self._lock_owned_job(session, job_id)
                # Serialize against deletion/reparse while validating and committing.
                session.query(Document).filter_by(id=job.document_id).with_for_update().one_or_none()
                report = self.pipeline_factory(session).process(job, request, result)
                if not SqlAlchemyGraphJobExecutor(session).complete(
                    worker_id=self.worker_id, job_id=str(job_id), result_digest=stable_digest(result.to_dict()),
                ):
                    raise ExtractionBackendError("lease_lost")
                session.commit()  # Candidates and completed state are one transaction.
            return dict(outbox=counts, processed=1, state="completed", issues=len(report.issues))
        except Exception as exc:
            if isinstance(exc, ExtractionBackendError):
                code, retryable = exc.code, exc.retryable
            elif isinstance(exc, CandidatePipelineError):
                code, retryable = exc.code, exc.code in {"chunk_count_mismatch"}
            elif isinstance(exc, GraphRagAdapterError):
                code, retryable = exc.code, False
            elif isinstance(exc, ValueError):
                code, retryable = "invalid_extraction_result", False
            else:
                code, retryable = "worker_processing_failed", True
            with self.sessions() as session:
                try:
                    self._lock_owned_job(session, job_id)
                except ExtractionBackendError:
                    return dict(outbox=counts, processed=1, state="lease_lost")
                SqlAlchemyGraphJobExecutor(session).fail(
                    worker_id=self.worker_id, job_id=str(job_id), error_code=code, retryable=retryable,
                )
                session.commit()
            LOG.warning("Graph extraction job %s: %s", job_id, code)
            return dict(outbox=counts, processed=1, state="failed", code=code)
        finally:
            stop.set()
            heartbeat.join()

    def run_forever(self, stop, *, poll_seconds=5):
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        while not stop.is_set():
            try:
                report = self.run_once()
            except Exception:
                LOG.error("Graph worker iteration failed; retrying after poll interval")
                report = {"processed": 0}
            if not report["processed"]:
                stop.wait(poll_seconds)
