from .user import db
from .user import User
from .conversation import Conversation
from .message import Message
from .document import Document
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

try:
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
        ModelVersionHistory,
    )
except ImportError:
    # geoalchemy2 未安装时（如测试环境）跳过 thematic_model 导入
    pass
