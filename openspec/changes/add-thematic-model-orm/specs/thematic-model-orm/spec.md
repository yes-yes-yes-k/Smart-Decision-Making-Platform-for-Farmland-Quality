## Purpose

定义专题模型数据库 V3.0 的 15 张设计表的 SQLAlchemy ORM 契约，支持 `db.create_all()` 一次性创建全部新表，覆盖专题模型注册、执行日志、空间数据图层、地块几何与信息、稳定性/质量等级/障碍诊断/酸化改良/有机质/综合地力等评价结果持久化、路由决策日志、模型评估指标、排他规则配置和模型版本历史。

**V3.0 命名规范**（来源：`专题模型数据库设计文档_V3.docx` §1.1/§6.2）：
- 字段名全面使用英文 snake_case，取消 V2.0 拼音缩写（SJD/YJZ/YTK 等）
- 地块唯一编号使用 `parcel_id`，取消 V2.0 的 `tybh`/TYBH 命名
- 后缀规范：`_membership`（隶属度）、`_weight`（权重）、`_obstacle_degree`（障碍度）、`_obstacle_grade`（障碍等级）、`_abs`/`_rel`（绝对/相对）、`_content`（含量）、`_dosage`（施用量）
- 显式外键约束（取代 V2.0 弱关联）
- 每列添加 `comment=` 参数（与 V3.0 §8 COMMENT ON COLUMN 对应）
- 索引名按表前缀化（PostgreSQL 全局唯一）

## ADDED Requirements

### Requirement: 专题模型注册表

系统 SHALL 提供 `thematic_model_registry` 表的 ORM 模型，用于注册专题模型元数据。模型 SHALL 包含字段：`agent_id`（字符串）、`model_id`（字符串）、`name`（字符串）、`description`（文本）、`domain`（字符串）、`question_type`（小整数）、`analysis_scale`（字符串）、`data_type`（字符串）、`input_format`（字符串）、`output_format`（字符串）、`minimum_inputs`（JSON）、`runtime_requirement`（文本）、`version`（字符串）、`status`（字符串）、`created_at`（带时区日期时间）、`updated_at`（带时区日期时间）。

#### Scenario: 注册表字段完整性
- **WHEN** `thematic_model_registry` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `minimum_inputs` 字段 SHALL 使用 JSON 类型存储数组结构
- **AND** 每个字段 SHALL 携带 V3.0 §8.1 定义的中文 `comment`
- **AND** SHALL 创建 `uk_thematic_model_registry_agent_id` UNIQUE 索引、`uk_thematic_model_registry_model_id` UNIQUE 索引、`idx_thematic_model_registry_question_type` BTREE 索引

### Requirement: 模型执行日志

系统 SHALL 提供 `model_execution_log` 表的 ORM 模型，记录每次专题模型执行的完整上下文。模型 SHALL 包含字段：`trace_id`（字符串）、`agent_id`（字符串）、`question_type`（小整数）、`user_id`（整数）、`conversation_id`（整数）、`parcel_id`（字符串，V3.0 地块编号）、`layer_id`（大整数）、`input_params`（JSON）、`output_result`（JSON）、`answer_text`（文本）、`evidence`（JSON）、`status`（字符串）、`routing_mode`（字符串）、`routing_status`（字符串）、`simulated`（布尔）、`confidence`（浮点）、`started_at`（带时区日期时间）、`completed_at`（带时区日期时间）、`duration_ms`（浮点）、`error_message`（文本）、`created_at`（带时区日期时间）。

#### Scenario: 执行日志字段完整性
- **WHEN** `model_execution_log` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `input_params`、`output_result`、`evidence` 字段 SHALL 使用 JSON 类型
- **AND** `agent_id` SHALL 通过 FK `fk_model_execution_log_agent_id` 引用 `thematic_model_registry.agent_id`
- **AND** `layer_id` SHALL 通过 FK `fk_model_execution_log_layer_id` 引用 `spatial_data_layer.id`
- **AND** SHALL 创建 `uk_model_execution_log_trace_id` UNIQUE 索引和 `idx_model_execution_log_agent_id`/`idx_model_execution_log_parcel_id`/`idx_model_execution_log_layer_id`/`idx_model_execution_log_started_at` BTREE 索引

### Requirement: 空间数据图层管理

系统 SHALL 提供 `spatial_data_layer` 表的 ORM 模型，管理上传的空间数据图层。模型 SHALL 包含字段：`layer_name`（字符串）、`layer_type`（字符串）、`file_path`（文本）、`file_hash`（字符串）、`crs`（字符串）、`feature_count`（整数）、`extent`（Geometry 多边形 SRID=4326）、`geometry_type`（字符串）、`attribute_fields`（JSON）、`model_scope`（字符串）、`upload_by`（整数）、`status`（字符串）、`uploaded_at`（带时区日期时间）。

#### Scenario: 图层管理字段完整性
- **WHEN** `spatial_data_layer` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `extent` 字段 SHALL 使用 GeoAlchemy2 的 Geometry 类型（POLYGON, SRID=4326）
- **AND** `attribute_fields` 字段 SHALL 使用 JSON 类型
- **AND** SHALL 创建 `uk_spatial_data_layer_file_hash` UNIQUE 索引、`idx_spatial_data_layer_extent` GIST 索引、`idx_spatial_data_layer_layer_type`/`idx_spatial_data_layer_model_scope`/`idx_spatial_data_layer_status` BTREE 索引

### Requirement: 地块空间几何

系统 SHALL 提供 `parcel_geometry` 表的 ORM 模型，存储地块空间几何数据。模型 SHALL 包含字段：`parcel_id`（字符串，V3.0 取代 tybh）、`geom`（Geometry 多边形 SRID=4326，非空）、`crs`（字符串）、`area_mu`（浮点，亩）、`area_sqm`（浮点，平方米）、`centroid_lon`（浮点）、`centroid_lat`（浮点）、`layer_id`（大整数）、`properties`（JSON）、`created_at`（带时区日期时间）。

#### Scenario: 地块几何字段完整性
- **WHEN** `parcel_geometry` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `geom` 字段 SHALL 使用 GeoAlchemy2 的 Geometry 类型且非空
- **AND** `layer_id` SHALL 通过 FK `fk_parcel_geometry_layer_id` 引用 `spatial_data_layer.id`
- **AND** SHALL 创建 `uk_parcel_geometry_parcel_id` UNIQUE 索引、`idx_parcel_geometry_geom` GIST 索引、`idx_parcel_geometry_layer_id` BTREE 索引

### Requirement: 稳定性风险评价结果持久化

系统 SHALL 提供 `stability_risk_result` 表的 ORM 模型，持久化 Model-1 稳定性风险评价结果。模型 SHALL 包含 V3.0 §8.5 定义的全部字段：`execution_id`、`parcel_id`、`geom`、`grade_boundary_safety`、`indicator_balance_abs`、`indicator_balance_rel`、`critical_indicator`、`critical_indicator_degree_abs`、`critical_indicator_degree_rel`、`spatial_consistency_abs`、`spatial_consistency_rel`、`neighbor_count`、`historical_slope`、`historical_trend_abs`、`historical_trend_rel`、`historical_trend_type`、`historical_grade_change`、`grade_drop_count`、`grade_drop_risk_abs`、`grade_drop_risk_rel`、`key_degradation_factor`、`key_factor_risk_abs`、`key_factor_risk_rel`、`neighbor_degradation_risk`、`degradation_cluster_risk_abs`、`degradation_cluster_risk_rel`、`low_quality_year_count`、`low_quality_ratio`、`persistent_low_risk_abs`、`persistent_low_risk_rel`、`input_snapshot`（JSON）、`simulated`、`created_at`。

#### Scenario: 稳定性结果字段完整性
- **WHEN** `stability_risk_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段（共 33 列，全部 V3.0 英文 snake_case 命名）
- **AND** `geom` 字段 SHALL 使用 Geometry 类型，`input_snapshot` 字段 SHALL 使用 JSON 类型
- **AND** `execution_id` SHALL 通过 FK `fk_stability_risk_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_stability_risk_result_execution_id` UNIQUE 索引、`idx_stability_risk_result_geom` GIST 索引、`idx_stability_risk_result_parcel_id` BTREE 索引

### Requirement: 质量等级评价结果持久化

系统 SHALL 提供 `quality_grade_result` 表的 ORM 模型，持久化 Model-2 质量等级评价结果。模型 SHALL 包含字段：`execution_id`、`parcel_id`、`geom`、`quality_grade`、`composite_index`、`composite_weight`、`indicators`（JSON）、`obstacle_degree`（JSON）、`input_snapshot`（JSON）、`simulated`、`created_at`。

#### Scenario: 质量等级结果字段完整性
- **WHEN** `quality_grade_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `indicators`、`obstacle_degree`、`input_snapshot` 字段 SHALL 使用 JSON 类型
- **AND** `execution_id` SHALL 通过 FK `fk_quality_grade_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_quality_grade_result_execution_id` UNIQUE 索引、`idx_quality_grade_result_geom` GIST 索引、`idx_quality_grade_result_parcel_id`/`idx_quality_grade_result_quality_grade` BTREE 索引

### Requirement: 障碍诊断结果持久化

系统 SHALL 提供 `obstacle_diagnosis_result` 表的 ORM 模型，持久化 Model-3 障碍诊断结果。模型 SHALL 包含 V3.0 §8.7 定义的字段：`execution_id`、`parcel_id`、12 项隶属度字段（`soil_ph_membership`、`organic_matter_membership`、`available_p_membership`、`available_k_membership`、`soil_bulk_density_membership`、`topsoil_texture_membership`、`irrigation_capacity_membership`、`drainage_capacity_membership`、`terrain_position_membership`、`texture_profile_membership`、`effective_soil_depth_membership`、`topsoil_thickness_membership`）、12 项障碍度字段（`ph_obstacle_degree`、`organic_matter_obstacle_degree`、`available_p_obstacle_degree`、`available_k_obstacle_degree`、`bulk_density_obstacle_degree`、`texture_obstacle_degree`、`irrigation_obstacle_degree`、`drainage_obstacle_degree`、`terrain_obstacle_degree`、`texture_profile_obstacle_degree`、`soil_depth_obstacle_degree`、`topsoil_thickness_obstacle_degree`）、12 项障碍等级字段（`ph_obstacle_grade`、`organic_matter_obstacle_grade`、`available_p_obstacle_grade`、`available_k_obstacle_grade`、`bulk_density_obstacle_grade`、`texture_obstacle_grade`、`irrigation_obstacle_grade`、`drainage_obstacle_grade`、`terrain_obstacle_grade`、`texture_profile_obstacle_grade`、`soil_depth_obstacle_grade`、`topsoil_thickness_obstacle_grade`）、`obstacle_type`、`primary_obstacle_factor`、`secondary_obstacle_factor`、`quality_grade`、`composite_weight`、`input_snapshot`（JSON）、`simulated`、`created_at`。

#### Scenario: 障碍诊断结果字段完整性
- **WHEN** `obstacle_diagnosis_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段（共 43 列：12 隶属度 + 12 障碍度 + 12 障碍等级 + 7 汇总 + id/execution_id/parcel_id/input_snapshot/simulated/created_at）
- **AND** 字段名 SHALL 严格使用 V3.0 后缀规范（`_membership`/`_obstacle_degree`/`_obstacle_grade`）
- **AND** `input_snapshot` 字段 SHALL 使用 JSON 类型
- **AND** `execution_id` SHALL 通过 FK `fk_obstacle_diagnosis_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_obstacle_diagnosis_result_execution_id` UNIQUE 索引、`idx_obstacle_diagnosis_result_parcel_id`/`idx_obstacle_diagnosis_result_obstacle_type` BTREE 索引

### Requirement: 酸化改良结果持久化

系统 SHALL 提供 `acidification_remediation_result` 表的 ORM 模型，持久化 Model-4 酸化改良结果。模型 SHALL 包含 V3.0 §8.8 定义的字段：`execution_id`、`parcel_id`、`soil_ph`、`exchangeable_hydrogen`、`exchangeable_aluminum`、`rainfall_ph`、`annual_rainfall`、`grain_yield`、`straw_yield`、`grain_p_content`、`grain_k_content`、`grain_ca_content`、`grain_mg_content`、`straw_p_content`、`straw_k_content`、`straw_ca_content`、`straw_mg_content`、`fertilizer_n`、`nitrogen_deposition`、`target_ph`、`grain_n_content`、`straw_n_content`、`acid_deposition_input`、`crop_uptake_acid`、`nitrogen_cycle_acid`、`agricultural_acid`、`background_soil_acid`、`soil_conditioner_dosage`、`woody_peat_dosage`、`model_version`、`status`、`warning`、`reason`、`out_of_range_features`（JSON）、`simulated`、`created_at`。

#### Scenario: 酸化改良结果字段完整性
- **WHEN** `acidification_remediation_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段（共 36 列）
- **AND** 含量类字段 SHALL 使用 `_content` 后缀（如 `grain_p_content`），施用量类字段 SHALL 使用 `_dosage` 后缀（如 `soil_conditioner_dosage`）
- **AND** `out_of_range_features` 字段 SHALL 使用 JSON 类型
- **AND** `execution_id` SHALL 通过 FK `fk_acidification_remediation_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_acidification_remediation_result_execution_id` UNIQUE 索引、`idx_acidification_remediation_result_parcel_id`/`idx_acidification_remediation_result_status` BTREE 索引

### Requirement: 有机质培肥结果持久化

系统 SHALL 提供 `organic_matter_result` 表的 ORM 模型，持久化 Model-5 有机质培肥结果。模型 SHALL 包含字段：`execution_id`、`soil_ph`、`available_potassium`、`organic_matter`、`available_phosphorus`、`total_phosphorus`、`total_potassium`、`total_nitrogen`、`organic_fertilizer_type`、`om_improvement_target`、`organic_fertilizer_dosage`、`level`、`potential_increase`、`simulated`、`created_at`。**该表无 `parcel_id` 列**（Model-5 是县级分析，无地块关联）。

#### Scenario: 有机质结果字段完整性
- **WHEN** `organic_matter_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段（共 15 列，无 `parcel_id`）
- **AND** `execution_id` SHALL 通过 FK `fk_organic_matter_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_organic_matter_result_execution_id` UNIQUE 索引、`idx_organic_matter_result_level` BTREE 索引

### Requirement: 综合地力改良提升结果持久化

系统 SHALL 提供 `comprehensive_fertility_result` 表的 ORM 模型，持久化 Model-6 综合地力改良提升结果。模型 SHALL 包含字段：`execution_id`、`parcel_id`、`fertility_score`、`fertility_level`、`improvement_plan`（JSON）、`input_snapshot`（JSON）、`simulated`、`created_at`。

#### Scenario: 综合地力结果字段完整性
- **WHEN** `comprehensive_fertility_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `improvement_plan`、`input_snapshot` 字段 SHALL 使用 JSON 类型
- **AND** `execution_id` SHALL 通过 FK `fk_comprehensive_fertility_result_execution_id` 引用 `model_execution_log.id`
- **AND** SHALL 创建 `uk_comprehensive_fertility_result_execution_id` UNIQUE 索引、`idx_comprehensive_fertility_result_parcel_id` BTREE 索引

### Requirement: 路由决策日志

系统 SHALL 提供 `routing_decision_log` 表的 ORM 模型，记录路由决策全过程。模型 SHALL 包含字段：`trace_id`、`question`（文本）、`question_type`、`relevance`（浮点）、`routing_status`、`router_method`、`candidate_agents`（JSON）、`hit_exclusive_rules`（JSON）、`llm_reason`（文本）、`llm_duration_ms`（浮点）、`total_duration_ms`（浮点）、`degradation`（文本）、`five_dim_context`（JSON）、`data_version`、`agent_version`、`result_version`、`failure_reason`（文本）、`logged_at`（带时区日期时间）。

#### Scenario: 路由日志字段完整性
- **WHEN** `routing_decision_log` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `candidate_agents`、`hit_exclusive_rules`、`five_dim_context` 字段 SHALL 使用 JSON 类型
- **AND** SHALL 创建 `uk_routing_decision_log_trace_id` UNIQUE 索引、`idx_routing_decision_log_question_type`/`idx_routing_decision_log_router_method`/`idx_routing_decision_log_routing_status`/`idx_routing_decision_log_logged_at` BTREE 索引

### Requirement: 模型评估指标

系统 SHALL 提供 `model_evaluation_metrics` 表的 ORM 模型，存储模型评估指标。模型 SHALL 包含字段：`model_pair`、`positive_label`、`tp`、`fp`、`fn`、`tn`、`total`、`accuracy`（浮点）、`confusion_rate`（浮点）、`evaluation_mode`、`sample_count`、`evaluated_at`（带时区日期时间）。

#### Scenario: 评估指标字段完整性
- **WHEN** `model_evaluation_metrics` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** SHALL 创建 `idx_model_evaluation_metrics_model_pair`/`idx_model_evaluation_metrics_evaluation_mode` BTREE 索引

### Requirement: 排他规则配置

系统 SHALL 提供 `exclusive_rule_config` 表的 ORM 模型，存储排他规则配置。模型 SHALL 包含字段：`rule_name`、`rule_pair`（JSON）、`discriminator`、`condition`、`target`、`dimension_conditions`（JSON）、`enabled`（布尔）、`created_at`、`updated_at`。

#### Scenario: 排他规则字段完整性
- **WHEN** `exclusive_rule_config` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `rule_pair`、`dimension_conditions` 字段 SHALL 使用 JSON 类型
- **AND** SHALL 创建 `uk_exclusive_rule_config_rule_name` UNIQUE 索引、`idx_exclusive_rule_config_target`/`idx_exclusive_rule_config_enabled` BTREE 索引

### Requirement: 地块信息

系统 SHALL 提供 `parcel_info` 表的 ORM 模型，存储地块基础信息。模型 SHALL 包含字段：`parcel_id`（V3.0 取代 tybh）、`geom`（Geometry 多边形 SRID=4326）、`area_code`、`centroid_lon`、`centroid_lat`、`land_type`、`fertilizer_type`、`target_ph`、`soil_indicators`（JSON）、`created_at`、`updated_at`。

#### Scenario: 地块信息字段完整性
- **WHEN** `parcel_info` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `geom` 字段 SHALL 使用 Geometry 类型，`soil_indicators` 字段 SHALL 使用 JSON 类型
- **AND** SHALL 创建 `uk_parcel_info_parcel_id` UNIQUE 索引、`idx_parcel_info_geom` GIST 索引、`idx_parcel_info_area_code` BTREE 索引

### Requirement: 模型版本历史

系统 SHALL 提供 `model_version_history` 表的 ORM 模型，记录模型版本变更历史。模型 SHALL 包含字段：`agent_id`、`version`、`change_description`（文本）、`parameters`（JSON）、`status`、`created_at`。

#### Scenario: 版本历史字段完整性
- **WHEN** `model_version_history` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `parameters` 字段 SHALL 使用 JSON 类型
- **AND** `agent_id` SHALL 通过 FK `fk_model_version_history_agent_id` 引用 `thematic_model_registry.agent_id`
- **AND** SHALL 创建 `idx_model_version_history_agent_id`/`idx_model_version_history_version` BTREE 索引

### Requirement: 专题模型表一次性建表

系统 SHALL 在 `framework/models/thematic_model.py` 中定义全部 15 张表的 ORM 模型，并通过 `framework/models/__init__.py` 导入触发模型注册，使 `db.create_all()` 能一次性创建全部新表。

#### Scenario: db.create_all 创建全部 15 张表
- **WHEN** `init_db.py` 运行 `db.create_all()`
- **THEN** 系统 SHALL 创建全部 15 张新表：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`

#### Scenario: 模型导入触发注册
- **WHEN** `framework/models/__init__.py` 被导入
- **THEN** `thematic_model.py` 中定义的全部 15 个模型类 SHALL 被 SQLAlchemy 注册
- **AND** `db.create_all()` SHALL 能发现并创建全部 15 张表

#### Scenario: V3.0 英文 snake_case 字段命名
- **WHEN** ORM 模型字段被定义
- **THEN** 字段名 SHALL 全部使用 V3.0 英文 snake_case（如 `soil_ph`、`organic_matter`、`available_potassium`、`exchangeable_hydrogen`、`parcel_id` 等）
- **AND** 字段命名 SHALL 与数据库设计文档 V3.0 §8 DDL 保持完全一致
- **AND** SHALL NOT 使用 V2.0 拼音缩写（`sjd`/`yjz`/`ytk`/`tybh`/`hex`/`alex` 等）
- **AND** 地块唯一编号字段 SHALL 统一为 `parcel_id`（V3.0 §6.2 明确取消 TYBH/tybh 命名）

#### Scenario: V3.0 后缀规范遵循
- **WHEN** ORM 模型定义隶属度/权重/障碍度/障碍等级/绝对/相对/含量/施用量类字段
- **THEN** 隶属度字段 SHALL 使用 `_membership` 后缀（如 `soil_ph_membership`）
- **AND** 权重字段 SHALL 使用 `_weight` 后缀
- **AND** 障碍度字段 SHALL 使用 `_obstacle_degree` 后缀
- **AND** 障碍等级字段 SHALL 使用 `_obstacle_grade` 后缀
- **AND** 绝对/相对值字段 SHALL 使用 `_abs`/`_rel` 后缀
- **AND** 含量字段 SHALL 使用 `_content` 后缀（如 `grain_p_content`）
- **AND** 施用量字段 SHALL 使用 `_dosage` 后缀（如 `soil_conditioner_dosage`）

#### Scenario: 外键约束（V3.0 显式 FK）
- **WHEN** ORM 模型定义 `execution_id`/`agent_id`/`layer_id` 等关联字段
- **THEN** 这些字段 SHALL 通过 `db.ForeignKey()` 显式定义外键约束
- **AND** FK 约束名 SHALL 命名为 `fk_<table_name>_<column_name>`（如 `fk_stability_risk_result_execution_id`）
- **AND** 系统 SHALL 在 PostgreSQL 创建全部 10 个外键约束（V3.0 §8 DDL 列出）

#### Scenario: COMMENT ON COLUMN 通过 comment 参数
- **WHEN** ORM 模型定义每个字段
- **THEN** 该字段 SHALL 通过 `comment=` 参数携带 V3.0 §8 定义的中文注释
- **AND** 注释内容 SHALL 与 V3.0 §8 `COMMENT ON COLUMN` 一一对应

#### Scenario: 索引按表前缀化命名
- **WHEN** ORM 模型在 `__table_args__` 中定义索引
- **THEN** 索引名 SHALL 按表名前缀化（如 `uk_parcel_geometry_parcel_id`、`uk_parcel_info_parcel_id`、`idx_stability_risk_result_geom`）
- **AND** 跨表的同名索引 SHALL 通过表前缀避免 PostgreSQL 全局命名冲突

#### Scenario: 空间几何列使用 Geometry 类型
- **WHEN** ORM 模型定义空间几何列（`geom`、`extent`）
- **THEN** 该列 SHALL 使用 GeoAlchemy2 的 `Geometry` 类型，指定 `geometry_type='POLYGON'` 和 `srid=4326`
- **AND** 该列 SHALL 创建 GIST 索引

#### Scenario: JSONB 列使用 JSON 类型
- **WHEN** ORM 模型定义 JSONB 列（如 `input_params`、`output_result`、`minimum_inputs`、`indicators`、`obstacle_degree`、`input_snapshot`、`improvement_plan`、`candidate_agents`、`hit_exclusive_rules`、`five_dim_context`、`rule_pair`、`dimension_conditions`、`soil_indicators`、`parameters`、`out_of_range_features`、`attribute_fields`、`properties`、`evidence`）
- **THEN** 该列 SHALL 使用 SQLAlchemy 的 `JSON` 类型（PostgreSQL 后端自动映射为 JSONB）

### Requirement: V3.0 视图创建

系统 SHALL 在 `scripts/v3_views.sql` 中提供 V3.0 §5 定义的 3 个视图 DDL，并通过 `init_db.py` 在 `db.create_all()` 之后执行。

#### Scenario: 3 个视图创建成功
- **WHEN** `init_db.py` 完成 `db.create_all()` 后执行 `scripts/v3_views.sql`
- **THEN** 系统 SHALL 创建 3 个视图：`v_model_execution_summary`、`v_parcel_stability_spatial`、`v_confusion_matrix_latest`
- **AND** 视图 SHALL 使用 `CREATE OR REPLACE VIEW` 容错
- **AND** 视图依赖的表 SHALL 已通过 `db.create_all()` 创建

#### Scenario: 模型执行汇总视图
- **WHEN** 查询 `v_model_execution_summary`
- **THEN** 视图 SHALL 返回 `agent_id`、`model_name`、`question_type`、`total_executions`、`success_count`、`error_count`、`simulated_count`、`avg_duration_ms`、`avg_confidence`、`last_execution_time` 字段
- **AND** 视图 SHALL 通过 `thematic_model_registry` LEFT JOIN `model_execution_log` 聚合

#### Scenario: 地块稳定性空间视图
- **WHEN** 查询 `v_parcel_stability_spatial`
- **THEN** 视图 SHALL 返回 `parcel_id`、`geom`、`area_mu`、`centroid_lon`、`centroid_lat`、`grade_boundary_safety`、`grade_drop_risk_abs`、`grade_drop_risk_rel`、`key_degradation_factor`、`degradation_cluster_risk_abs`、`persistent_low_risk_abs`、`created_at` 字段
- **AND** 视图 SHALL 通过 `parcel_geometry` JOIN `stability_risk_result` ON `parcel_id` 关联

#### Scenario: 最新混淆矩阵视图
- **WHEN** 查询 `v_confusion_matrix_latest`
- **THEN** 视图 SHALL 返回 `model_evaluation_metrics` 全部字段
- **AND** 视图 SHALL 通过自连接筛选每个 `model_pair`+`evaluation_mode` 的最新 `evaluated_at` 记录
