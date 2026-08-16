"""专题模型数据库 V3.0 SQLAlchemy ORM 模型。

定义 V3.0 设计文档（专题模型数据库设计文档_V3.docx，2026-08-15）§8 的 15 张表：
注册表、执行日志、空间图层、地块几何、Model-1~Model-6 结果表、路由日志、
评估指标、排他规则、地块信息、版本历史。

命名规范（V3.0 §1.1/§6.2）：
- 字段名全面采用英文 snake_case，取消 V2.0 拼音缩写（SJD/YJZ/YTK 等）。
- 地块唯一编号统一为 parcel_id（取消 tybh）。
- 后缀规范：_membership / _weight / _obstacle_degree / _obstacle_grade /
  _abs / _rel / _content / _dosage。
- 索引名按表前缀化（PostgreSQL schema 内全局唯一）。
- 外键约束名：fk_<table>_<column>。

复用 framework.models.user 中的 Flask-SQLAlchemy db 对象，与 soil_data.py 同模式。
权威 DDL 参考：scripts/thematic_models_v3_ddl.sql（ORM db.create_all() 生成等价结构）。
"""
from .user import db
from geoalchemy2 import Geometry


class ThematicModelRegistry(db.Model):
    """专题模型注册表（V3.0 §8.1）。"""
    __tablename__ = "thematic_model_registry"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id = db.Column(db.String(32), nullable=False, comment="智能体标识（model-1 ~ model-6）")
    model_id = db.Column(db.String(64), nullable=False, comment="规范模型标识")
    name = db.Column(db.String(128), nullable=False, comment="模型中文名称")
    description = db.Column(db.Text, comment="模型描述")
    domain = db.Column(db.String(32), nullable=False, comment="领域标识")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（1~6）")
    analysis_scale = db.Column(db.String(16), nullable=False, comment="分析尺度（省/县/片区/地块）")
    data_type = db.Column(db.String(16), nullable=False, comment="数据类型（指标数据/评价结果/处方用量）")
    input_format = db.Column(db.String(16), nullable=False, server_default="shp", comment="输入格式（shp/csv/json）")
    output_format = db.Column(db.String(16), nullable=False, server_default="shp", comment="输出格式（shp/csv/json）")
    minimum_inputs = db.Column(db.JSON, comment="最小输入字段列表")
    runtime_requirement = db.Column(db.Text, comment="运行时前置条件")
    version = db.Column(db.String(16), nullable=False, server_default="1.0", comment="当前模型版本")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("agent_id", name="uk_thematic_model_registry_agent_id"),
        db.UniqueConstraint("model_id", name="uk_thematic_model_registry_model_id"),
        db.Index("idx_thematic_model_registry_question_type", "question_type"),
    )


class ModelExecutionLog(db.Model):
    """模型执行日志表（V3.0 §8.2，父表，被各结果表通过 execution_id 引用）。"""
    __tablename__ = "model_execution_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    trace_id = db.Column(db.String(64), nullable=False, comment="追溯ID（UUID）")
    agent_id = db.Column(db.String(32), db.ForeignKey("thematic_model_registry.agent_id", name="fk_model_execution_log_agent_id"), nullable=False, comment="关联 thematic_model_registry.agent_id")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（1~6）")
    user_id = db.Column(db.Integer, comment="用户ID")
    conversation_id = db.Column(db.Integer, comment="会话ID")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    layer_id = db.Column(db.BigInteger, db.ForeignKey("spatial_data_layer.id", name="fk_model_execution_log_layer_id"), comment="关联 spatial_data_layer.id")
    input_params = db.Column(db.JSON, comment="输入参数快照")
    output_result = db.Column(db.JSON, comment="输出结果快照")
    answer_text = db.Column(db.Text, comment="自然语言答复")
    evidence = db.Column(db.JSON, comment="证据列表")
    status = db.Column(db.String(16), nullable=False, comment="执行状态（ok/error/fallback/rejected）")
    routing_mode = db.Column(db.String(16), comment="路由模式（llm/keyword）")
    routing_status = db.Column(db.String(16), comment="路由状态")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    confidence = db.Column(db.Float, comment="置信度（0~1）")
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, comment="执行开始时间")
    completed_at = db.Column(db.DateTime(timezone=True), comment="执行完成时间")
    duration_ms = db.Column(db.Float, comment="执行耗时（毫秒）")
    error_message = db.Column(db.Text, comment="错误信息")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="记录创建时间")

    __table_args__ = (
        db.UniqueConstraint("trace_id", name="uk_model_execution_log_trace_id"),
        db.Index("idx_model_execution_log_agent_id", "agent_id"),
        db.Index("idx_model_execution_log_parcel_id", "parcel_id"),
        db.Index("idx_model_execution_log_layer_id", "layer_id"),
        db.Index("idx_model_execution_log_started_at", "started_at"),
    )


class SpatialDataLayer(db.Model):
    """空间数据图层管理表（V3.0 §8.3）。"""
    __tablename__ = "spatial_data_layer"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    layer_name = db.Column(db.String(128), nullable=False, comment="图层名称")
    layer_type = db.Column(db.String(32), nullable=False, comment="图层类型（farmland_boundary/stability_result/diagnosis_result 等）")
    file_path = db.Column(db.Text, nullable=False, comment="Shapefile 文件路径")
    file_hash = db.Column(db.String(64), comment="文件哈希（SHA-256）")
    crs = db.Column(db.String(32), nullable=False, server_default="EPSG:4326", comment="坐标参考系（如 EPSG:4326）")
    feature_count = db.Column(db.Integer, comment="要素数量")
    extent = db.Column(Geometry("POLYGON", srid=4326), comment="图层空间范围（PostGIS 几何）")
    geometry_type = db.Column(db.String(16), comment="几何类型（Point/Polygon/MultiPolygon）")
    attribute_fields = db.Column(db.JSON, comment="属性字段列表 [{name, type}]")
    model_scope = db.Column(db.String(32), comment="适用模型（model-1/model-2/model-3/all）")
    upload_by = db.Column(db.Integer, comment="上传用户ID")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态（active/archived）")
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="上传时间")

    __table_args__ = (
        db.UniqueConstraint("file_hash", name="uk_spatial_data_layer_file_hash"),
        db.Index("idx_spatial_data_layer_layer_type", "layer_type"),
        db.Index("idx_spatial_data_layer_model_scope", "model_scope"),
        db.Index("idx_spatial_data_layer_status", "status"),
        db.Index("idx_spatial_data_layer_extent", "extent", postgresql_using="gist"),
    )


class ParcelGeometry(db.Model):
    """地块空间几何表（V3.0 §8.4，parcel_id 取代 V2.0 tybh）。"""
    __tablename__ = "parcel_geometry"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), nullable=False, comment="地块几何（PostGIS Polygon）")
    crs = db.Column(db.String(32), nullable=False, server_default="EPSG:4326", comment="坐标参考系")
    area_mu = db.Column(db.Float, comment="面积（亩）")
    area_sqm = db.Column(db.Float, comment="面积（平方米）")
    centroid_lon = db.Column(db.Float, comment="质心经度")
    centroid_lat = db.Column(db.Float, comment="质心纬度")
    layer_id = db.Column(db.BigInteger, db.ForeignKey("spatial_data_layer.id", name="fk_parcel_geometry_layer_id"), comment="关联 spatial_data_layer.id")
    properties = db.Column(db.JSON, comment="其他土壤指标属性快照")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", name="uk_parcel_geometry_parcel_id"),
        db.Index("idx_parcel_geometry_layer_id", "layer_id"),
        db.Index("idx_parcel_geometry_geom", "geom", postgresql_using="gist"),
    )


class StabilityRiskResult(db.Model):
    """稳定性风险评价结果表（Model-1，V3.0 §8.5）。"""
    __tablename__ = "stability_risk_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_stability_risk_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS，用于空间邻域分析）")
    grade_boundary_safety = db.Column(db.Float, comment="等级边界安全度")
    indicator_balance_abs = db.Column(db.Float, comment="指标支撑均衡度_绝对")
    indicator_balance_rel = db.Column(db.Float, comment="指标支撑均衡度_相对")
    critical_indicator = db.Column(db.Float, comment="关键临界指标")
    critical_indicator_degree_abs = db.Column(db.Float, comment="关键指标临界度_绝对")
    critical_indicator_degree_rel = db.Column(db.Float, comment="关键指标临界度_相对")
    spatial_consistency_abs = db.Column(db.Float, comment="空间邻域一致性_绝对")
    spatial_consistency_rel = db.Column(db.Float, comment="空间邻域一致性_相对")
    neighbor_count = db.Column(db.Integer, comment="邻域地块数")
    historical_slope = db.Column(db.Float, comment="历史年均变化斜率")
    historical_trend_abs = db.Column(db.Float, comment="历史变化趋势_绝对")
    historical_trend_rel = db.Column(db.Float, comment="历史变化趋势_相对")
    historical_trend_type = db.Column(db.String(64), comment="历史变化类型")
    historical_grade_change = db.Column(db.Float, comment="历史等级变化")
    grade_drop_count = db.Column(db.Integer, comment="历史掉级次数")
    grade_drop_risk_abs = db.Column(db.Float, comment="掉级风险_绝对")
    grade_drop_risk_rel = db.Column(db.Float, comment="掉级风险_相对")
    key_degradation_factor = db.Column(db.String(64), comment="关键退化因子")
    key_factor_risk_abs = db.Column(db.Float, comment="关键因子退化风险_绝对")
    key_factor_risk_rel = db.Column(db.Float, comment="关键因子退化风险_相对")
    neighbor_degradation_risk = db.Column(db.Float, comment="邻域平均退化风险")
    degradation_cluster_risk_abs = db.Column(db.Float, comment="退化空间集聚风险_绝对")
    degradation_cluster_risk_rel = db.Column(db.Float, comment="退化空间集聚风险_相对")
    low_quality_year_count = db.Column(db.Integer, comment="低质年份数")
    low_quality_ratio = db.Column(db.Float, comment="持续低质比例")
    persistent_low_risk_abs = db.Column(db.Float, comment="持续低质风险_绝对")
    persistent_low_risk_rel = db.Column(db.Float, comment="持续低质风险_相对")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照（含 terrain_position/topsoil_thickness/soil_ph 等41个标准输入字段）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_stability_risk_result_execution_id"),
        db.Index("idx_stability_risk_result_parcel_id", "parcel_id"),
        db.Index("idx_stability_risk_result_geom", "geom", postgresql_using="gist"),
    )


class QualityGradeResult(db.Model):
    """质量等级评价结果表（Model-2，V3.0 §8.6）。"""
    __tablename__ = "quality_grade_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_quality_grade_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS）")
    quality_grade = db.Column(db.String(4), nullable=False, comment="耕地质量等级（1~10）")
    composite_index = db.Column(db.Float, nullable=False, comment="综合指数（0~1）")
    composite_weight = db.Column(db.Float, comment="综合权重")
    indicators = db.Column(db.JSON, comment="指标列表 [{name, raw_value, membership, weight}]")
    obstacle_degree = db.Column(db.JSON, comment="障碍度排序 [{rank, indicator, degree}]")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照（含 terrain_position/soil_ph/organic_matter 等标准输入字段）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_quality_grade_result_execution_id"),
        db.Index("idx_quality_grade_result_parcel_id", "parcel_id"),
        db.Index("idx_quality_grade_result_quality_grade", "quality_grade"),
        db.Index("idx_quality_grade_result_geom", "geom", postgresql_using="gist"),
    )


class ObstacleDiagnosisResult(db.Model):
    """障碍诊断结果表（Model-3，V3.0 §8.7，含 12 隶属度 + 12 障碍度 + 12 障碍等级）。"""
    __tablename__ = "obstacle_diagnosis_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_obstacle_diagnosis_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    # —— 12 隶属度（_membership）——
    soil_ph_membership = db.Column(db.Float, comment="酸碱度隶属度")
    organic_matter_membership = db.Column(db.Float, comment="有机质隶属度")
    available_p_membership = db.Column(db.Float, comment="有效磷隶属度")
    available_k_membership = db.Column(db.Float, comment="速效钾隶属度")
    soil_bulk_density_membership = db.Column(db.Float, comment="土壤容重隶属度")
    topsoil_texture_membership = db.Column(db.Float, comment="耕层质地隶属度")
    irrigation_capacity_membership = db.Column(db.Float, comment="灌溉能力隶属度")
    drainage_capacity_membership = db.Column(db.Float, comment="排水能力隶属度")
    terrain_position_membership = db.Column(db.Float, comment="地形部位隶属度")
    texture_profile_membership = db.Column(db.Float, comment="质地构型隶属度")
    effective_soil_depth_membership = db.Column(db.Float, comment="有效土层厚度隶属度")
    topsoil_thickness_membership = db.Column(db.Float, comment="耕层厚度隶属度")
    # —— 12 障碍度（_obstacle_degree）——
    ph_obstacle_degree = db.Column(db.Float, comment="pH障碍度")
    organic_matter_obstacle_degree = db.Column(db.Float, comment="有机质障碍度")
    available_p_obstacle_degree = db.Column(db.Float, comment="有效磷障碍度")
    available_k_obstacle_degree = db.Column(db.Float, comment="速效钾障碍度")
    bulk_density_obstacle_degree = db.Column(db.Float, comment="容重障碍度")
    texture_obstacle_degree = db.Column(db.Float, comment="耕层质地障碍度")
    irrigation_obstacle_degree = db.Column(db.Float, comment="灌溉能力障碍度")
    drainage_obstacle_degree = db.Column(db.Float, comment="排水能力障碍度")
    terrain_obstacle_degree = db.Column(db.Float, comment="地形部位障碍度")
    texture_profile_obstacle_degree = db.Column(db.Float, comment="质地构型障碍度")
    soil_depth_obstacle_degree = db.Column(db.Float, comment="有效土层障碍度")
    topsoil_thickness_obstacle_degree = db.Column(db.Float, comment="耕层厚度障碍度")
    # —— 12 障碍等级（_obstacle_grade）——
    ph_obstacle_grade = db.Column(db.Float, comment="pH障碍等级")
    organic_matter_obstacle_grade = db.Column(db.Float, comment="有机质障碍等级")
    available_p_obstacle_grade = db.Column(db.Float, comment="有效磷障碍等级")
    available_k_obstacle_grade = db.Column(db.Float, comment="速效钾障碍等级")
    bulk_density_obstacle_grade = db.Column(db.Float, comment="容重障碍等级")
    texture_obstacle_grade = db.Column(db.Float, comment="耕层质地障碍等级")
    irrigation_obstacle_grade = db.Column(db.Float, comment="灌溉能力障碍等级")
    drainage_obstacle_grade = db.Column(db.Float, comment="排水能力障碍等级")
    terrain_obstacle_grade = db.Column(db.Float, comment="地形部位障碍等级")
    texture_profile_obstacle_grade = db.Column(db.Float, comment="质地构型障碍等级")
    soil_depth_obstacle_grade = db.Column(db.Float, comment="有效土层障碍等级")
    topsoil_thickness_obstacle_grade = db.Column(db.Float, comment="耕层厚度障碍等级")
    # —— 汇总列 ——
    obstacle_type = db.Column(db.String(64), comment="障碍类型")
    primary_obstacle_factor = db.Column(db.String(64), comment="主要障碍因素")
    secondary_obstacle_factor = db.Column(db.String(64), comment="次要障碍因素")
    quality_grade = db.Column(db.String(64), comment="耕地质量等级")
    composite_weight = db.Column(db.Float, comment="综合权重")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_obstacle_diagnosis_result_execution_id"),
        db.Index("idx_obstacle_diagnosis_result_parcel_id", "parcel_id"),
        db.Index("idx_obstacle_diagnosis_result_obstacle_type", "obstacle_type"),
    )


class AcidificationRemediationResult(db.Model):
    """酸化改良结果表（Model-4，V3.0 §8.8）。"""
    __tablename__ = "acidification_remediation_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_acidification_remediation_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    soil_ph = db.Column(db.Float, comment="酸碱度（土壤pH）")
    exchangeable_hydrogen = db.Column(db.Float, comment="土壤交换性氢离子")
    exchangeable_aluminum = db.Column(db.Float, comment="土壤交换性铝离子")
    rainfall_ph = db.Column(db.Float, comment="降水pH年均值")
    annual_rainfall = db.Column(db.Float, comment="年降水量")
    grain_yield = db.Column(db.Float, comment="籽粒产量")
    straw_yield = db.Column(db.Float, comment="秸秆产量")
    grain_p_content = db.Column(db.Float, comment="籽粒P含量")
    grain_k_content = db.Column(db.Float, comment="籽粒K含量")
    grain_ca_content = db.Column(db.Float, comment="籽粒Ca含量")
    grain_mg_content = db.Column(db.Float, comment="籽粒Mg含量")
    straw_p_content = db.Column(db.Float, comment="秸秆P含量")
    straw_k_content = db.Column(db.Float, comment="秸秆K含量")
    straw_ca_content = db.Column(db.Float, comment="秸秆Ca含量")
    straw_mg_content = db.Column(db.Float, comment="秸秆Mg含量")
    fertilizer_n = db.Column(db.Float, comment="施肥量以N元素计算")
    nitrogen_deposition = db.Column(db.Float, comment="N沉降")
    target_ph = db.Column(db.Float, comment="目标pH值")
    grain_n_content = db.Column(db.Float, comment="籽粒N含量")
    straw_n_content = db.Column(db.Float, comment="秸秆N含量")
    acid_deposition_input = db.Column(db.Float, comment="酸沉降产酸量")
    crop_uptake_acid = db.Column(db.Float, comment="植株吸收利用产H+量")
    nitrogen_cycle_acid = db.Column(db.Float, comment="氮循环净产酸量")
    agricultural_acid = db.Column(db.Float, comment="农业活动产酸量")
    background_soil_acid = db.Column(db.Float, comment="土壤本底酸量")
    soil_conditioner_dosage = db.Column(db.Float, comment="亿土康施加量")
    woody_peat_dosage = db.Column(db.Float, comment="木本泥炭施加量")
    model_version = db.Column(db.String(32), comment="模型版本（如 process_v2_20260801）")
    status = db.Column(db.String(16), nullable=False, server_default="ok", comment="执行状态（ok/rejected/fallback）")
    warning = db.Column(db.Text, comment="警告信息")
    reason = db.Column(db.Text, comment="拒绝原因")
    out_of_range_features = db.Column(db.JSON, comment="越界特征列表")
    simulated = db.Column(db.Boolean, nullable=False, server_default="false", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_acidification_remediation_result_execution_id"),
        db.Index("idx_acidification_remediation_result_parcel_id", "parcel_id"),
        db.Index("idx_acidification_remediation_result_status", "status"),
    )


class OrganicMatterResult(db.Model):
    """有机质培肥结果表（Model-5，V3.0 §8.9，县级分析，无 parcel_id）。"""
    __tablename__ = "organic_matter_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_organic_matter_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    soil_ph = db.Column(db.Float, comment="酸碱度（土壤pH）")
    available_potassium = db.Column(db.Float, comment="土壤速效钾含量")
    organic_matter = db.Column(db.Float, comment="土壤有机质含量")
    available_phosphorus = db.Column(db.Float, comment="土壤有效磷含量")
    total_phosphorus = db.Column(db.Float, comment="土壤总磷含量")
    total_potassium = db.Column(db.Float, comment="土壤总钾含量")
    total_nitrogen = db.Column(db.Float, comment="土壤总氮含量")
    organic_fertilizer_type = db.Column(db.String(64), comment="土壤有机肥料类型")
    om_improvement_target = db.Column(db.Float, comment="土壤有机质提升值")
    organic_fertilizer_dosage = db.Column(db.Float, comment="有机肥施用量")
    level = db.Column(db.String(8), comment="有机质等级（极低/低/中/高/极高）")
    potential_increase = db.Column(db.Float, comment="预期有机质提升量（g/kg）")
    simulated = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_organic_matter_result_execution_id"),
        db.Index("idx_organic_matter_result_level", "level"),
    )


class ComprehensiveFertilityResult(db.Model):
    """综合地力改良提升结果表（Model-6 占位，V3.0 §8.10；业务逻辑尚未实现）。"""
    __tablename__ = "comprehensive_fertility_result"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    execution_id = db.Column(db.BigInteger, db.ForeignKey("model_execution_log.id", name="fk_comprehensive_fertility_result_execution_id"), nullable=False, comment="关联 model_execution_log.id")
    parcel_id = db.Column(db.String(64), comment="地块唯一编号")
    fertility_score = db.Column(db.Float, comment="综合地力得分")
    fertility_level = db.Column(db.String(8), comment="综合地力等级")
    improvement_plan = db.Column(db.JSON, comment="综合改良方案（整合酸化改良+有机质培肥建议）")
    input_snapshot = db.Column(db.JSON, comment="输入参数快照")
    simulated = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否模拟数据")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.UniqueConstraint("execution_id", name="uk_comprehensive_fertility_result_execution_id"),
        db.Index("idx_comprehensive_fertility_result_parcel_id", "parcel_id"),
    )


class RoutingDecisionLog(db.Model):
    """路由决策日志表（V3.0 §8.11，无 FK）。"""
    __tablename__ = "routing_decision_log"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    trace_id = db.Column(db.String(64), nullable=False, comment="追溯ID（UUID）")
    question = db.Column(db.Text, nullable=False, comment="用户原始问题")
    question_type = db.Column(db.SmallInteger, nullable=False, comment="问题类型（0~6）")
    relevance = db.Column(db.Float, comment="相关性得分（0~1）")
    routing_status = db.Column(db.String(16), nullable=False, server_default="normal", comment="路由状态")
    router_method = db.Column(db.String(16), nullable=False, comment="路由方法（keyword/llm/knowledge/vector）")
    candidate_agents = db.Column(db.JSON, comment="候选智能体列表")
    hit_exclusive_rules = db.Column(db.JSON, comment="命中的排他规则")
    llm_reason = db.Column(db.Text, comment="LLM 路由理由")
    llm_duration_ms = db.Column(db.Float, comment="LLM 路由耗时（毫秒）")
    total_duration_ms = db.Column(db.Float, comment="路由总耗时（毫秒）")
    degradation = db.Column(db.Text, comment="降级说明")
    five_dim_context = db.Column(db.JSON, comment="五维上下文 {scale, data_type, business_task, expected_output}")
    data_version = db.Column(db.String(32), comment="数据版本")
    agent_version = db.Column(db.String(32), comment="智能体版本")
    result_version = db.Column(db.String(16), server_default="v1.2", comment="路由算法版本")
    failure_reason = db.Column(db.Text, comment="失败原因")
    logged_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="日志记录时间")

    __table_args__ = (
        db.UniqueConstraint("trace_id", name="uk_routing_decision_log_trace_id"),
        db.Index("idx_routing_decision_log_question_type", "question_type"),
        db.Index("idx_routing_decision_log_router_method", "router_method"),
        db.Index("idx_routing_decision_log_routing_status", "routing_status"),
        db.Index("idx_routing_decision_log_logged_at", "logged_at"),
    )


class ModelEvaluationMetrics(db.Model):
    """模型评估指标表（V3.0 §8.12，无 FK）。"""
    __tablename__ = "model_evaluation_metrics"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    model_pair = db.Column(db.String(32), nullable=False, comment="易混淆模型对标识")
    positive_label = db.Column(db.String(32), nullable=False, comment="正类标签")
    tp = db.Column(db.Integer, nullable=False, server_default="0", comment="真阳性")
    fp = db.Column(db.Integer, nullable=False, server_default="0", comment="假阳性")
    fn = db.Column(db.Integer, nullable=False, server_default="0", comment="假阴性")
    tn = db.Column(db.Integer, nullable=False, server_default="0", comment="真阴性")
    total = db.Column(db.Integer, nullable=False, server_default="0", comment="样本总数")
    accuracy = db.Column(db.Float, nullable=False, server_default="0", comment="正确率")
    confusion_rate = db.Column(db.Float, nullable=False, server_default="0", comment="混淆率")
    evaluation_mode = db.Column(db.String(16), nullable=False, comment="评估模式（keyword/llm）")
    sample_count = db.Column(db.Integer, comment="评估样本数")
    evaluated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="评估时间")

    __table_args__ = (
        db.Index("idx_model_evaluation_metrics_model_pair", "model_pair"),
        db.Index("idx_model_evaluation_metrics_evaluation_mode", "evaluation_mode"),
    )


class ExclusiveRuleConfig(db.Model):
    """排他规则配置表（V3.0 §8.13，无 FK）。"""
    __tablename__ = "exclusive_rule_config"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    rule_name = db.Column(db.String(64), nullable=False, comment="规则名称")
    rule_pair = db.Column(db.JSON, nullable=False, comment="易混淆模型对")
    discriminator = db.Column(db.String(128), nullable=False, comment="判别维度描述")
    condition = db.Column(db.String(64), comment="关键词条件名")
    target = db.Column(db.String(32), nullable=False, comment="目标模型ID")
    dimension_conditions = db.Column(db.JSON, comment="维度条件")
    enabled = db.Column(db.Boolean, nullable=False, server_default="true", comment="是否启用")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("rule_name", name="uk_exclusive_rule_config_rule_name"),
        db.Index("idx_exclusive_rule_config_target", "target"),
        db.Index("idx_exclusive_rule_config_enabled", "enabled"),
    )


class ParcelInfo(db.Model):
    """地块信息表（V3.0 §8.14，无 FK）。"""
    __tablename__ = "parcel_info"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    parcel_id = db.Column(db.String(64), nullable=False, comment="地块唯一编号")
    geom = db.Column(Geometry("POLYGON", srid=4326), comment="地块几何（PostGIS）")
    area_code = db.Column(db.String(32), comment="区域编码")
    centroid_lon = db.Column(db.Float, comment="质心经度")
    centroid_lat = db.Column(db.Float, comment="质心纬度")
    land_type = db.Column(db.String(16), comment="土地利用类型（upland/paddy）")
    fertilizer_type = db.Column(db.String(32), comment="肥料类型")
    target_ph = db.Column(db.Float, comment="目标pH值")
    soil_indicators = db.Column(db.JSON, comment="结构化土壤指标快照（terrain_position/topsoil_thickness/soil_ph 等）")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        db.UniqueConstraint("parcel_id", name="uk_parcel_info_parcel_id"),
        db.Index("idx_parcel_info_area_code", "area_code"),
        db.Index("idx_parcel_info_geom", "geom", postgresql_using="gist"),
    )


class ModelVersionHistory(db.Model):
    """模型版本历史表（V3.0 §8.15，FK → thematic_model_registry.agent_id）。"""
    __tablename__ = "model_version_history"

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True, comment="主键")
    agent_id = db.Column(db.String(32), db.ForeignKey("thematic_model_registry.agent_id", name="fk_model_version_history_agent_id"), nullable=False, comment="关联 thematic_model_registry.agent_id")
    version = db.Column(db.String(16), nullable=False, comment="版本号")
    change_description = db.Column(db.Text, comment="变更描述")
    parameters = db.Column(db.JSON, comment="版本参数快照")
    status = db.Column(db.String(16), nullable=False, server_default="active", comment="状态")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=db.func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        db.Index("idx_model_version_history_agent_id", "agent_id"),
        db.Index("idx_model_version_history_version", "version"),
    )
