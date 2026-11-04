from .user import db
from .user import User
from .conversation import Conversation
from .message import Message
from .acidification_measurement import AcidificationMeasurement
from .cd_trial import CdTrial
from .document import Document
from .document_label import DocumentLabel
from .ingestion import IngestionBatch, IngestionItem
from .knowledge_graph import (
    KnowledgeGraphCandidateEvidence,
    KnowledgeGraphClaimCandidate,
    KnowledgeGraphClaimEvidence,
    KnowledgeGraphEntityCandidate,
    KnowledgeGraphExtractionJob,
    KnowledgeGraphOutboxEvent,
    KnowledgeGraphRelationCandidate,
    KnowledgeGraphRelease,
    KnowledgeGraphReleaseChange,
    KnowledgeGraphReviewDecision,
    KnowledgeGraphStudyCandidate,
)
from .data_file import DataFile
from .soil_data import (
    ThirdSurveyTopsoil,
    ThirdSurveyProfile,
    ThirdSurveySiteCondition,
    ThirdSurveyBulkDensity,
    SecondSurveyPoint,
    FormulaFertilization,
    AgriChemicalization,
    GrainYield,
)
from .report import Report
from .cd_prediction import (
    CdCropPredictionResult,
    CdEffectivePredictionResult,
    CdPortedParcelTownship,
)
from .thematic_model import (
    ThematicModelRegistry,
    ModelExecutionLog,
    SpatialDataLayer,
    ParcelGeometry,
    StabilityRiskResult,
    QualityGradeResult,
    ObstacleDiagnosisResult,
    AcidificationRemediationResult,
    OrganicMatterResult,
    ComprehensiveFertilityResult,
    RoutingDecisionLog,
    ModelEvaluationMetrics,
    ExclusiveRuleConfig,
    ParcelInfo,
    ParcelHistorySnapshot,
    ModelVersionHistory,
    VersionedModelResult,
    AreaCodeRegionMap,
    SpatialRegionCatalog,
    FarmlandRegionParcelArea,
    FarmlandRegionPrecomputeState,
)
