## 1. 依赖准备

- [ ] 1.1 在 `pyproject.toml` 的 `dependencies` 中新增 `geoalchemy2>=0.14.0`
- [ ] 1.2 安装新增依赖（`pip install -e .` 或 `pip install geoalchemy2`）

## 2. ORM 模型实现

- [ ] 2.1 创建 `framework/models/thematic_model.py`，导入 `db`（来自 `framework.models.user`）和 `geoalchemy2.Geometry`，添加模块文档字符串说明 15 张 V2.0 设计表
- [ ] 2.2 定义 `ThematicModelRegistry` 模型（表 `thematic_model_registry`），含 `agent_id`、`model_id`、`name`、`description`、`domain`、`question_type`、`analysis_scale`、`data_type`、`input_format`、`output_format`、`minimum_inputs`(JSON)、`runtime_requirement`、`version`、`status` 字段
- [ ] 2.3 定义 `ModelExecutionLog` 模型（表 `model_execution_log`），含 `trace_id`、`agent_id`、`question_type`、`user_id`、`conversation_id`、`tybh`、`layer_id`、`input_params`(JSON)、`output_result`(JSON)、`answer_text`、`evidence`(JSON)、`status`、`routing_mode`、`routing_status`、`simulated`、`confidence`、`started_at`、`completed_at`、`duration_ms`、`error_message` 字段
- [ ] 2.4 定义 `SpatialDataLayer` 模型（表 `spatial_data_layer`），含 `layer_name`、`layer_type`、`file_path`、`file_hash`、`crs`、`feature_count`、`extent`(Geometry)、`geometry_type`、`attribute_fields`(JSON)、`model_scope`、`upload_by`、`status` 字段
- [ ] 2.5 定义 `ParcelGeometry` 模型（表 `parcel_geometry`），含 `tybh`、`geom`(Geometry)、`crs`、`area_mu`、`area_sqm`、`centroid_lon`、`centroid_lat`、`layer_id`、`properties`(JSON) 字段
- [ ] 2.6 定义 `StabilityRiskResult` 模型（表 `stability_risk_result`），含 `execution_id`、`tybh`、`geom`(Geometry)、`safe_abs`、`bal_abs`、`bal_rel`、`key_fac`、`key_abs`、`key_rel`、`nbr_abs`、`nbr_rel`、`nbr_n`、`h_slope`、`h_abs`、`h_rel`、`h_type`、`g_change`、`drop_n`、`drop_abs`、`drop_re`、`kfd_factor`、`kfd_abs`、`kfd_rel`、`dgr_nbr`、`dgr_abs`、`dgr_rel`、`low_n`、`low_rate`、`low_abs`、`low_rel`、`input_snapshot`(JSON)、`simulated` 字段
- [ ] 2.7 定义 `QualityGradeResult` 模型（表 `quality_grade_result`），含 `execution_id`、`tybh`、`geom`(Geometry)、`gdzldj`、`composite_index`、`zhqz`、`indicators`(JSON)、`obstacle_degree`(JSON)、`input_snapshot`(JSON)、`simulated` 字段
- [ ] 2.8 定义 `ObstacleDiagnosisResult` 模型（表 `obstacle_diagnosis_result`），含 `execution_id`、`tybh`、12 项障碍度原始值（`sjdlsd`/`yjzlsd`/`yxllsd`/`sxjlsd`/`trrzlsd`/`gczdlsd`/`ggnllsd`/`psnllsd`/`dxbwlsd`/`zdgxlsd`/`yxtchdlsd`/`gchdlsd`）、12 项障碍度、12 项障碍等级、`zalx`、`zyzays`、`cyzays`、`gdzldj`、`zhqz`、`input_snapshot`(JSON)、`simulated` 字段
- [ ] 2.9 定义 `AcidificationRemediationResult` 模型（表 `acidification_remediation_result`），含 `execution_id`、`tybh`、`sjd`、`hex`、`alex`、`rph`、`r`、`y`、`s`、`yp`、`yk`、`yca`、`ymg`、`sp`、`sk`、`sca`、`smg`、`fertn`、`ndep`、`phtarget`、`yn`、`sn`、`adep`、`acrop`、`ancy`、`aagri`、`aback`、`ytk`、`mbnt`、`model_version`、`status`、`warning`、`reason`、`out_of_range_features`(JSON)、`simulated` 字段
- [ ] 2.10 定义 `OrganicMatterResult` 模型（表 `organic_matter_result`），含 `execution_id`、`sjd`、`sxj`、`yjz`、`yxl`、`tl`、`tj`、`td`、`yjflx`、`yjztsz`、`yjfsyl`、`level`、`potential_increase`、`simulated` 字段
- [ ] 2.11 定义 `ComprehensiveFertilityResult` 模型（表 `comprehensive_fertility_result`），含 `execution_id`、`tybh`、`fertility_score`、`fertility_level`、`improvement_plan`(JSON)、`input_snapshot`(JSON)、`simulated` 字段
- [ ] 2.12 定义 `RoutingDecisionLog` 模型（表 `routing_decision_log`），含 `trace_id`、`question`、`question_type`、`relevance`、`routing_status`、`router_method`、`candidate_agents`(JSON)、`hit_exclusive_rules`(JSON)、`llm_reason`、`llm_duration_ms`、`total_duration_ms`、`degradation`、`five_dim_context`(JSON)、`data_version`、`agent_version`、`result_version`、`failure_reason` 字段
- [ ] 2.13 定义 `ModelEvaluationMetrics` 模型（表 `model_evaluation_metrics`），含 `model_pair`、`positive_label`、`tp`、`fp`、`fn`、`tn`、`total`、`accuracy`、`confusion_rate`、`evaluation_mode`、`sample_count` 字段
- [ ] 2.14 定义 `ExclusiveRuleConfig` 模型（表 `exclusive_rule_config`），含 `rule_name`、`rule_pair`(JSON)、`discriminator`、`condition`、`target`、`dimension_conditions`(JSON)、`enabled` 字段
- [ ] 2.15 定义 `ParcelInfo` 模型（表 `parcel_info`），含 `tybh`、`geom`(Geometry)、`area_code`、`centroid_lon`、`centroid_lat`、`land_type`、`fertilizer_type`、`target_ph`、`soil_indicators`(JSON) 字段
- [ ] 2.16 定义 `ModelVersionHistory` 模型（表 `model_version_history`），含 `agent_id`、`version`、`change_description`、`parameters`(JSON)、`status` 字段

## 3. 模型注册

- [ ] 3.1 修改 `framework/models/__init__.py`，从 `.thematic_model` 导入全部 15 个模型类，使 `db.create_all()` 能发现新表

## 4. Model-6 元数据升级

- [ ] 4.1 修改 `framework/agents/capabilities.py` 中 Model-6 的 `ProfessionalCapability`：将 `model_id` 从 `placeholder` 更新为 `comprehensive-fertility-improvement`，`name` 更新为"耕地综合地力改良提升模型"，`description` 更新为综合地力评价与改良提升描述，`domain` 从 `placeholder` 更新为 `fertility`，`runtime_requirement` 标注为占位状态（业务逻辑尚未实现），保持 `question_type=6` 不变

## 5. 验证

- [ ] 5.1 在 PostgreSQL/PostGIS 环境运行 `python init_db.py`，验证 `db.create_all()` 成功创建全部 15 张新表
- [ ] 5.2 验证 15 张表名与 spec 列表完全一致：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`
- [ ] 5.3 验证空间几何列（`geom`、`extent`）使用 GeoAlchemy2 `Geometry` 类型
- [ ] 5.4 验证 JSONB 列（`input_params`、`output_result`、`evidence`、`minimum_inputs` 等）使用 SQLAlchemy `JSON` 类型
- [ ] 5.5 验证字段命名使用拼音缩写（`sjd`、`yjz`、`ytk`、`gdzldj`、`safe_abs`、`tybh` 等），与数据库设计文档 V2.0 一致
- [ ] 5.6 验证 Model-6 元数据升级：`model_id=comprehensive-fertility-improvement`、`name=耕地综合地力改良提升模型`、`runtime_requirement` 标注占位状态
- [ ] 5.7 验证旧的 8 张土壤数据表未被修改，`db.create_all()` 同时创建旧表与新表
