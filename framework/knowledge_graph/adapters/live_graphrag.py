"""Pinned, isolated GraphRAG extraction using an explicitly allowed endpoint."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
from .graphrag import (GraphRagArtifactBundle, GraphRagEntityRecord,
                       GraphRagRelationshipRecord, GraphRagTextUnitRecord, MicrosoftGraphRagBackend)
from ..extraction_config import backend_config_digest, model_endpoint
from ..schema import load_graph_schema


class ExtractionBackendError(RuntimeError):
    def __init__(self, code, *, retryable=False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


class LiveGraphRagProvider:
    def __init__(self, python, *, timeout=900, run=subprocess.run):
        self.python, self.timeout, self.run = str(python), timeout, run
        self.last_usage = None
        self.runner = Path(__file__).resolve().parents[3] / "scripts" / "graphrag_extract.py"

    def check_runtime(self):
        try:
            result = self.run([self.python, str(self.runner), "--check"],
                              capture_output=True, text=True, timeout=60)
            payload = json.loads(result.stdout)
            if result.returncode or payload != dict(runtime="graphrag", version="3.3.0", ready=True):
                raise ValueError("not ready")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            raise ExtractionBackendError("extraction_runtime_unavailable") from None

    def load(self, request):
        model_endpoint()
        try:
            process = self.run([self.python, str(self.runner)],
                input=json.dumps(asdict(request), ensure_ascii=False), text=True, encoding="utf-8",
                capture_output=True, timeout=self.timeout,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            raise ExtractionBackendError("extraction_timeout", retryable=True) from None
        except OSError:
            raise ExtractionBackendError("extraction_runtime_unavailable") from None
        if process.returncode:
            code, retryable = "extraction_backend_failed", True
            try:
                failure = json.loads(process.stdout)
                self.last_usage = failure.get("usage")
                if failure.get("code") in {"runtime_version_mismatch", "model_not_configured",
                        "unknown_relation_type", "invalid_model_output", "model_authentication_failed",
                        "model_permission_denied", "model_request_rejected", "unknown_entity_type",
                        "ambiguous_entity_types", "missing_relation_endpoint", "invalid_relation_direction", "invalid_evidence_quote"}:
                    code, retryable = failure["code"], False
                elif failure.get("code") in {"model_rate_limited", "incomplete_model_response"}:
                    code = failure["code"]
            except (ValueError, AttributeError):
                pass
            raise ExtractionBackendError(code, retryable=retryable)
        try:
            payload = json.loads(process.stdout)
            self.last_usage = payload.get("usage")
            return GraphRagArtifactBundle(
                entities=tuple(GraphRagEntityRecord(**r) for r in payload["entities"]),
                relationships=tuple(GraphRagRelationshipRecord(**r) for r in payload["relationships"]),
                text_units=tuple(GraphRagTextUnitRecord(**r) for r in payload["text_units"]))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ExtractionBackendError("invalid_extraction_output") from None


class LiveMicrosoftGraphRagBackend(MicrosoftGraphRagBackend):
    def __init__(self, python, *, timeout=900, provider=None):
        model_endpoint()
        schema = load_graph_schema()
        super().__init__(provider=provider or LiveGraphRagProvider(python, timeout=timeout),
                         schema=schema, version="3.3.0")
        self._config_digest = backend_config_digest(self.name, self.version, schema.schema_version)
