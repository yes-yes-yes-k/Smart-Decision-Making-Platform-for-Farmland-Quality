"""Pure domain contracts for calculation analysis context."""

from .contracts import (
    AnalysisContext,
    AnalysisObject,
    CalculationMode,
    ContextAction,
    GuardDecision,
    ObjectType,
    ParentPathItem,
)
from .errors import (
    AnalysisContextConflict,
    AnalysisContextError,
    AnalysisObjectInvalid,
    AnalysisObjectValidationUnavailable,
    LegacyIdentifierAmbiguity,
)
from .legacy import LegacyAnalysisContextAdapter, LegacyResolution
from .resolvers import (
    AnalysisObjectAccessPolicy,
    RegisteredDataAccessPolicy,
    SpatialObjectResolverRegistry,
)

__all__ = [
    "AnalysisContext",
    "AnalysisContextConflict",
    "AnalysisContextError",
    "AnalysisObject",
    "AnalysisObjectInvalid",
    "AnalysisObjectValidationUnavailable",
    "CalculationMode",
    "ContextAction",
    "GuardDecision",
    "LegacyIdentifierAmbiguity",
    "LegacyAnalysisContextAdapter",
    "LegacyResolution",
    "ObjectType",
    "ParentPathItem",
    "AnalysisObjectAccessPolicy",
    "RegisteredDataAccessPolicy",
    "SpatialObjectResolverRegistry",
]
