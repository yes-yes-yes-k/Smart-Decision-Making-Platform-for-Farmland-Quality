## 1. 依赖准备

- [x] 1.1 在 `pyproject.toml` 的 `dependencies` 中新增 `geoalchemy2>=0.14.0`
- [x] 1.2 安装新增依赖（`pip install -e .` 或 `pip install geoalchemy2`）

## 2. DDL 脚本与视图脚本

- [x] 2.1 创建 `scripts/thematic_models_v3_ddl.sql`（V3.0 §8 完整 DDL：CREATE EXTENSION + 15 张表 + COMMENT + 索引按表前缀化 + FK + 3 个视图）
- [x] 2.2 创建 `scripts/v3_views.sql`（V3.0 §5 的 3 个视图 DDL，供 `init_db.py` 在 `db.create_all()` 之后执行）

## 3. ORM 模型实现（V3.0 字段命名）

- [x] 3.1 创建 `framework/models/thematic_model.py`，导入 `db`（来自 `framework.models.user`）和 `geoalchemy2.Geometry`，添加模块文档字符串说明 15 张 V3.0 设计表 + 命名规范
- [x] 3.2 定义 `ThematicModelRegistry` 模型（表 `thematic_model_registry`），含 `agent_id`、`model_id`、`name`、`description`、`domain`、`question_type`(SmallInteger)、`analysis_scale`、`data_type`、`input_format`、`output_format`、`minimum_inputs`(JSON)、`runtime_requirement`、`version`、`status`、`created_at`、`updated_at`，每列加 `comment=`，在 `__table_args__` 定义 `uk_thematic_model_registry_agent_id`/`uk_thematic_model_registry_model_id`/`idx_thematic_model_registry_question_type`
- [x] 3.3 定义 `ModelExecutionLog` 模型（表 `model_execution_log`），含 `trace_id`、`agent_id`（FK `fk_model_execution_log_agent_id` → `thematic_model_registry.agent_id`）、`question_type`、`user_id`、`conversation_id`、`parcel_id`、`layer_id`（FK `fk_model_execution_log_layer_id` → `spatial_data_layer.id`）、`input_params`(JSON)、`output_result`(JSON)、`answer_text`、`evidence`(JSON)、`status`、`routing_mode`、`routing_status`、`simulated`、`confidence`、`started_at`、`completed_at`、`duration_ms`、`error_message`、`created_at`，索引 `uk_model_execution_log_trace_id`/`idx_model_execution_log_agent_id`/`idx_model_execution_log_parcel_id`/`idx_model_execution_log_layer_id`/`idx_model_execution_log_started_at`
- [x] 3.4 定义 `SpatialDataLayer` 模型（表 `spatial_data_layer`），含 `layer_name`、`layer_type`、`file_path`、`file_hash`、`crs`、`feature_count`、`extent`(Geometry POLYGON 4326)、`geometry_type`、`attribute_fields`(JSON)、`model_scope`、`upload_by`、`status`、`uploaded_at`，索引 `uk_spatial_data_layer_file_hash`/`idx_spatial_data_layer_layer_type`/`idx_spatial_data_layer_model_scope`/`idx_spatial_data_layer_status`/`idx_spatial_data_layer_extent`(GIST)
- [x] 3.5 定义 `ParcelGeometry` 模型（表 `parcel_geometry`），含 `parcel_id`（V3.0 取代 tybh）、`geom`(Geometry POLYGON 4326, nullable=False)、`crs`、`area_mu`、`area_sqm`、`centroid_lon`、`centroid_lat`、`layer_id`（FK `fk_parcel_geometry_layer_id`）、`properties`(JSON)、`created_at`，索引 `uk_parcel_geometry_parcel_id`/`idx_parcel_geometry_layer_id`/`idx_parcel_geometry_geom`(GIST)
- [x] 3.6 定义 `StabilityRiskResult` 模型（表 `stability_risk_result`，Model-1），含 33 列（V3.0 §8.5 全部字段）：`execution_id`（FK `fk_stability_risk_result_execution_id`）、`parcel_id`、`geom`、`grade_boundary_safety`、`indicator_balance_abs`/`_rel`、`critical_indicator`、`critical_indicator_degree_abs`/`_rel`、`spatial_consistency_abs`/`_rel`、`neighbor_count`、`historical_slope`/`_trend_abs`/`_trend_rel`/`_trend_type`/`_grade_change`、`grade_drop_count`/`_risk_abs`/`_risk_rel`、`key_degradation_factor`、`key_factor_risk_abs`/`_rel`、`neighbor_degradation_risk`、`degradation_cluster_risk_abs`/`_rel`、`low_quality_year_count`/`_ratio`、`persistent_low_risk_abs`/`_rel`、`input_snapshot`(JSON)、`simulated`、`created_at`，索引 `uk_stability_risk_result_execution_id`/`idx_stability_risk_result_parcel_id`/`idx_stability_risk_result_geom`(GIST)
- [x] 3.7 定义 `QualityGradeResult` 模型（表 `quality_grade_result`，Model-2），含 `execution_id`（FK）、`parcel_id`、`geom`、`quality_grade`、`composite_index`、`composite_weight`、`indicators`(JSON)、`obstacle_degree`(JSON)、`input_snapshot`(JSON)、`simulated`、`created_at`，索引 `uk_quality_grade_result_execution_id`/`idx_quality_grade_result_parcel_id`/`idx_quality_grade_result_quality_grade`/`idx_quality_grade_result_geom`(GIST)
- [x] 3.8 定义 `ObstacleDiagnosisResult` 模型（表 `obstacle_diagnosis_result`，Model-3），含 43 列：`execution_id`（FK）、`parcel_id`、12 membership（`soil_ph_membership`/`organic_matter_membership`/`available_p_membership`/`available_k_membership`/`soil_bulk_density_membership`/`topsoil_texture_membership`/`irrigation_capacity_membership`/`drainage_capacity_membership`/`terrain_position_membership`/`texture_profile_membership`/`effective_soil_depth_membership`/`topsoil_thickness_membership`）、12 obstacle_degree（`ph_obstacle_degree`/`organic_matter_obstacle_degree`/...）、12 obstacle_grade（`ph_obstacle_grade`/...）、`obstacle_type`、`primary_obstacle_factor`、`secondary_obstacle_factor`、`quality_grade`、`composite_weight`、`input_snapshot`(JSON)、`simulated`、`created_at`，索引 `uk_obstacle_diagnosis_result_execution_id`/`idx_obstacle_diagnosis_result_parcel_id`/`idx_obstacle_diagnosis_result_obstacle_type`
- [x] 3.9 定义 `AcidificationRemediationResult` 模型（表 `acidification_remediation_result`，Model-4），含 36 列（V3.0 §8.8）：`execution_id`（FK）、`parcel_id`、`soil_ph`、`exchangeable_hydrogen`、`exchangeable_aluminum`、`rainfall_ph`、`annual_rainfall`、`grain_yield`、`straw_yield`、`grain_p_content`/`grain_k_content`/`grain_ca_content`/`grain_mg_content`、`straw_p_content`/`straw_k_content`/`straw_ca_content`/`straw_mg_content`、`fertilizer_n`、`nitrogen_deposition`、`target_ph`、`grain_n_content`、`straw_n_content`、`acid_deposition_input`、`crop_uptake_acid`、`nitrogen_cycle_acid`、`agricultural_acid`、`background_soil_acid`、`soil_conditioner_dosage`、`woody_peat_dosage`、`model_version`、`status`、`warning`、`reason`、`out_of_range_features`(JSON)、`simulated`、`created_at`，索引 `uk_acidification_remediation_result_execution_id`/`idx_acidification_remediation_result_parcel_id`/`idx_acidification_remediation_result_status`
- [x] 3.10 定义 `OrganicMatterResult` 模型（表 `organic_matter_result`，Model-5，**无 parcel_id**），含 15 列：`execution_id`（FK `fk_organic_matter_result_execution_id`）、`soil_ph`、`available_potassium`、`organic_matter`、`available_phosphorus`、`total_phosphorus`、`total_potassium`、`total_nitrogen`、`organic_fertilizer_type`、`om_improvement_target`、`organic_fertilizer_dosage`、`level`、`potential_increase`、`simulated`、`created_at`，索引 `uk_organic_matter_result_execution_id`/`idx_organic_matter_result_level`
- [x] 3.11 定义 `ComprehensiveFertilityResult` 模型（表 `comprehensive_fertility_result`，Model-6 占位），含 `execution_id`（FK）、`parcel_id`、`fertility_score`、`fertility_level`、`improvement_plan`(JSON)、`input_snapshot`(JSON)、`simulated`、`created_at`，索引 `uk_comprehensive_fertility_result_execution_id`/`idx_comprehensive_fertility_result_parcel_id`
- [x] 3.12 定义 `RoutingDecisionLog` 模型（表 `routing_decision_log`），含 `trace_id`、`question`、`question_type`、`relevance`、`routing_status`、`router_method`、`candidate_agents`(JSON)、`hit_exclusive_rules`(JSON)、`llm_reason`、`llm_duration_ms`、`total_duration_ms`、`degradation`、`five_dim_context`(JSON)、`data_version`、`agent_version`、`result_version`、`failure_reason`、`logged_at`，索引 `uk_routing_decision_log_trace_id`/`idx_routing_decision_log_question_type`/`idx_routing_decision_log_router_method`/`idx_routing_decision_log_routing_status`/`idx_routing_decision_log_logged_at`
- [x] 3.13 定义 `ModelEvaluationMetrics` 模型（表 `model_evaluation_metrics`），含 `model_pair`、`positive_label`、`tp`、`fp`、`fn`、`tn`、`total`、`accuracy`、`confusion_rate`、`evaluation_mode`、`sample_count`、`evaluated_at`，索引 `idx_model_evaluation_metrics_model_pair`/`idx_model_evaluation_metrics_evaluation_mode`
- [x] 3.14 定义 `ExclusiveRuleConfig` 模型（表 `exclusive_rule_config`），含 `rule_name`、`rule_pair`(JSON)、`discriminator`、`condition`、`target`、`dimension_conditions`(JSON)、`enabled`、`created_at`、`updated_at`，索引 `uk_exclusive_rule_config_rule_name`/`idx_exclusive_rule_config_target`/`idx_exclusive_rule_config_enabled`
- [x] 3.15 定义 `ParcelInfo` 模型（表 `parcel_info`），含 `parcel_id`、`geom`(Geometry)、`area_code`、`centroid_lon`、`centroid_lat`、`land_type`、`fertilizer_type`、`target_ph`、`soil_indicators`(JSON)、`created_at`、`updated_at`，索引 `uk_parcel_info_parcel_id`/`idx_parcel_info_area_code`/`idx_parcel_info_geom`(GIST)
- [x] 3.16 定义 `ModelVersionHistory` 模型（表 `model_version_history`），含 `agent_id`（FK `fk_model_version_history_agent_id`）、`version`、`change_description`、`parameters`(JSON)、`status`、`created_at`，索引 `idx_model_version_history_agent_id`/`idx_model_version_history_version`

## 4. 模型注册

- [x] 4.1 修改 `framework/models/__init__.py`，从 `.thematic_model` 导入全部 15 个模型类，使 `db.create_all()` 能发现新表

## 5. Model-6 元数据升级

- [x] 5.1 修改 `framework/agents/capabilities.py` 中 Model-6 的 `ProfessionalCapability`：将 `model_id` 从 `placeholder` 更新为 `comprehensive-fertility-improvement`，`name` 更新为"耕地综合地力改良提升模型"，`description` 更新为综合地力评价与改良提升描述，`domain` 从 `placeholder` 更新为 `fertility`，`runtime_requirement` 标注为占位状态（业务逻辑尚未实现），保持 `question_type=6` 不变

## 6. init_db.py 视图执行

- [x] 6.1 修改 `init_db.py`，在 `db.create_all()` 之后执行 `scripts/v3_views.sql`（通过 `db.session.execute(text(open('scripts/v3_views.sql').read()))` + `db.session.commit()`）

## 7. 验证

- [x] 7.1 在 PostgreSQL 16 + PostGIS 3.4 环境运行 `python init_db.py`，验证 `db.create_all()` 成功创建全部 15 张新表
- [x] 7.2 验证 15 张表名与 V3.0 §3 列表完全一致：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`
- [x] 7.3 验证字段命名使用 V3.0 英文 snake_case（`soil_ph`、`organic_matter`、`available_potassium`、`exchangeable_hydrogen`、`parcel_id` 等），与数据库设计文档 V3.0 §8 DDL 一致；**不出现** V2.0 拼音缩写（`sjd`/`yjz`/`ytk`/`tybh`/`hex`/`alex`）
- [x] 7.4 验证 V3.0 后缀规范：`_membership`/`_weight`/`_obstacle_degree`/`_obstacle_grade`/`_abs`/`_rel`/`_content`/`_dosage`
- [x] 7.5 验证空间几何列（`geom`、`extent`）使用 GeoAlchemy2 `Geometry` 类型且 GIST 索引存在
- [x] 7.6 验证 JSONB 列（`input_params`、`output_result`、`evidence`、`minimum_inputs`、`indicators`、`obstacle_degree`、`input_snapshot`、`improvement_plan`、`candidate_agents`、`hit_exclusive_rules`、`five_dim_context`、`rule_pair`、`dimension_conditions`、`soil_indicators`、`parameters`、`out_of_range_features`、`attribute_fields`、`properties`）使用 SQLAlchemy `JSON` 类型
- [x] 7.7 验证全部 10 个外键约束存在（`SELECT * FROM information_schema.referential_constraints ORDER BY table_name`）
- [x] 7.8 验证每列 `comment` 与 V3.0 §8 COMMENT ON COLUMN 一致（`SELECT column_name, col_description(...) FROM information_schema.columns`）
- [x] 7.9 验证索引名按表前缀化（`\di` 或 `SELECT indexname FROM pg_indexes WHERE schemaname='public'`），无跨表重名
- [x] 7.10 验证 GIST 索引在所有 `geom` 和 `extent` 列上（`SELECT indexname, tablename FROM pg_indexes WHERE indexdef LIKE '%USING gist%'`）
- [x] 7.11 验证 3 个视图创建成功（`SELECT viewname FROM pg_views WHERE schemaname='public'`）
- [x] 7.12 验证视图可查询（`SELECT * FROM v_model_execution_summary LIMIT 1; SELECT * FROM v_parcel_stability_spatial LIMIT 1; SELECT * FROM v_confusion_matrix_latest LIMIT 1;`）
- [x] 7.13 验证 Model-6 元数据升级：`model_id=comprehensive-fertility-improvement`、`name=耕地综合地力改良提升模型`、`domain=fertility`、`runtime_requirement` 标注占位状态、`question_type=6` 不变
- [x] 7.14 验证旧的 8 张土壤数据表未被修改，`db.create_all()` 同时创建旧表与新表
- [x] 7.15 验证 `scripts/thematic_models_v3_ddl.sql` 可独立 source 执行（`psql -d agent_culti_demo -f scripts/thematic_models_v3_ddl.sql`）创建完整 V3.0 schema（含表、COMMENT、索引、FK、视图）
