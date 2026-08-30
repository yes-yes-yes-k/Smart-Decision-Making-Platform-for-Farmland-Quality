"""Stable domain errors for analysis-context workflows."""


class AnalysisContextError(Exception):
    code = "analysis_context_error"
    http_status = 422

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AnalysisContextConflict(AnalysisContextError):
    code = "analysis_context_conflict"
    http_status = 409


class AnalysisObjectInvalid(AnalysisContextError):
    code = "analysis_object_invalid"
    http_status = 422


class LegacyIdentifierAmbiguity(AnalysisContextError):
    code = "legacy_identifier_ambiguity"
    http_status = 422


class AnalysisObjectValidationUnavailable(AnalysisContextError):
    code = "analysis_object_validation_unavailable"
    http_status = 503
