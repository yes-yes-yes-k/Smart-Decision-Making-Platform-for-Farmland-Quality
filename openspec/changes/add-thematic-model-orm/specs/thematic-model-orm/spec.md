## Purpose

定义专题模型数据库 V2.0 的 15 张设计表的 SQLAlchemy ORM 契约，支持 `db.create_all()` 一次性创建全部新表，覆盖专题模型注册、执行日志、空间数据图层、地块几何与信息、稳定性/质量等级/障碍诊断/酸化改良/有机质/综合地力等评价结果持久化、路由决策日志、模型评估指标、排他规则配置和模型版本历史。字段命名遵循数据字段标准化表的拼音缩写。

## ADDED Requirements

### Requirement: 专题模型注册表

系统 SHALL 提供 `thematic_model_registry` 表的 ORM 模型，用于注册专题模型元数据。模型 SHALL 包含字段：`agent_id`（字符串）、`model_id`（字符串）、`name`（字符串）、`description`（字符串）、`domain`（字符串）、`question_type`（整数）、`analysis_scale`（字符串）、`data_type`（字符串）、`input_format`（字符串）、`output_format`（字符串）、`minimum_inputs`（JSON）、`runtime_requirement`（字符串）、`version`（字符串）、`status`（字符串）。

#### Scenario: 注册表字段完整性
- **WHEN** `thematic_model_registry` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `minimum_inputs` 字段 SHALL 使用 JSON 类型存储数组结构

### Requirement: 模型执行日志

系统 SHALL 提供 `model_execution_log` 表的 ORM 模型，记录每次专题模型执行的完整上下文。模型 SHALL 包含字段：`trace_id`（字符串）、`agent_id`（字符串）、`question_type`（整数）、`user_id`（字符串）、`conversation_id`（字符串）、`tybh`（字符串，地块统一编号）、`layer_id`（整数）、`input_params`（JSON）、`output_result`（JSON）、`answer_text`（文本）、`evidence`（JSON）、`status`（字符串）、`routing_mode`（字符串）、`routing_status`（字符串）、`simulated`（布尔）、`confidence`（浮点）、`started_at`（日期时间）、`completed_at`（日期时间）、`duration_ms`（整数）、`error_message`（文本）。

#### Scenario: 执行日志字段完整性
- **WHEN** `model_execution_log` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `input_params`、`output_result`、`evidence` 字段 SHALL 使用 JSON 类型

### Requirement: 空间数据图层管理

系统 SHALL 提供 `spatial_data_layer` 表的 ORM 模型，管理上传的空间数据图层。模型 SHALL 包含字段：`layer_name`（字符串）、`layer_type`（字符串）、`file_path`（字符串）、`file_hash`（字符串）、`crs`（字符串）、`feature_count`（整数）、`extent`（Geometry 几何）、`geometry_type`（字符串）、`attribute_fields`（JSON）、`model_scope`（字符串）、`upload_by`（字符串）、`status`（字符串）。

#### Scenario: 图层管理字段完整性
- **WHEN** `spatial_data_layer` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `extent` 字段 SHALL 使用 GeoAlchemy2 的 Geometry 类型
- **AND** `attribute_fields` 字段 SHALL 使用 JSON 类型

### Requirement: 地块空间几何

系统 SHALL 提供 `parcel_geometry` 表的 ORM 模型，存储地块空间几何数据。模型 SHALL 包含字段：`tybh`（字符串，地块统一编号）、`geom`（Geometry 几何）、`crs`（字符串）、`area_mu`（浮点，亩）、`area_sqm`（浮点，平方米）、`centroid_lon`（浮点）、`centroid_lat`（浮点）、`layer_id`（整数）、`properties`（JSON）。

#### Scenario: 地块几何字段完整性
- **WHEN** `parcel_geometry` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `geom` 字段 SHALL 使用 GeoAlchemy2 的 Geometry 类型

### Requirement: 稳定性风险评价结果持久化

系统 SHALL 提供 `stability_risk_result` 表的 ORM 模型，持久化 Model-1 稳定性风险评价结果。模型 SHALL 包含字段：`execution_id`（整数）、`tybh`（字符串）、`geom`（Geometry 几何）、`safe_abs`（等级边界安全度绝对值）、`bal_abs`（指标支撑均衡度绝对值）、`bal_rel`（均衡度相对值）、`key_fac`（关键因子）、`key_abs`（关键因子绝对值）、`key_rel`（关键因子相对值）、`nbr_abs`（邻域绝对值）、`nbr_rel`（邻域相对值）、`nbr_n`（邻域数量）、`h_slope`（坡度）、`h_abs`（高度绝对值）、`h_rel`（高度相对值）、`h_type`（高度类型）、`g_change`（变化）、`drop_n`（掉级数量）、`drop_abs`（掉级绝对值）、`drop_re`（掉级相对值）、`kfd_factor`（退化因子）、`kfd_abs`（退化绝对值）、`kfd_rel`（退化相对值）、`dgr_nbr`（度等级邻域）、`dgr_abs`（度等级绝对值）、`dgr_rel`（度等级相对值）、`low_n`（低值数量）、`low_rate`（低值比例）、`low_abs`（低值绝对值）、`low_rel`（低值相对值）、`input_snapshot`（JSON）、`simulated`（布尔）。

#### Scenario: 稳定性结果字段完整性
- **WHEN** `stability_risk_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `geom` 字段 SHALL 使用 Geometry 类型，`input_snapshot` 字段 SHALL 使用 JSON 类型

### Requirement: 质量等级评价结果持久化

系统 SHALL 提供 `quality_grade_result` 表的 ORM 模型，持久化 Model-2 质量等级评价结果。模型 SHALL 包含字段：`execution_id`（整数）、`tybh`（字符串）、`geom`（Geometry 几何）、`gdzldj`（耕地质量等级）、`composite_index`（综合指数）、`zhqz`（综合权重）、`indicators`（JSON）、`obstacle_degree`（JSON）、`input_snapshot`（JSON）、`simulated`（布尔）。

#### Scenario: 质量等级结果字段完整性
- **WHEN** `quality_grade_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `indicators`、`obstacle_degree`、`input_snapshot` 字段 SHALL 使用 JSON 类型

### Requirement: 障碍诊断结果持久化

系统 SHALL 提供 `obstacle_diagnosis_result` 表的 ORM 模型，持久化 Model-3 障碍诊断结果。模型 SHALL 包含字段：`execution_id`（整数）、`tybh`（字符串）、12 项障碍度原始值字段（`sjdlsd`、`yjzlsd`、`yxllsd`、`sxjlsd`、`trrzlsd`、`gczdlsd`、`ggnllsd`、`psnllsd`、`dxbwlsd`、`zdgxlsd`、`yxtchdlsd`、`gchdlsd`）、12 项障碍度字段、12 项障碍等级字段、`zalx`（障碍类型）、`zyzays`（主要障碍因素）、`cyzays`（次要障碍因素）、`gdzldj`（耕地质量等级）、`zhqz`（综合权重）、`input_snapshot`（JSON）、`simulated`（布尔）。

#### Scenario: 障碍诊断结果字段完整性
- **WHEN** `obstacle_diagnosis_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段，含 12 项障碍度原始值、12 项障碍度、12 项障碍等级
- **AND** `input_snapshot` 字段 SHALL 使用 JSON 类型

### Requirement: 酸化改良结果持久化

系统 SHALL 提供 `acidification_remediation_result` 表的 ORM 模型，持久化 Model-4 酸化改良结果。模型 SHALL 包含字段：`execution_id`（整数）、`tybh`（字符串）、`sjd`（酸碱度）、`hex`（交换性氢）、`alex`（交换性铝）、`rph`（降雨 pH）、`r`（降雨量）、`y`（产量）、`s`（土壤）、`yp`（产量磷）、`yk`（产量钾）、`yca`（产量钙）、`ymg`（产量镁）、`sp`（土壤磷）、`sk`（土壤钾）、`sca`（土壤钙）、`smg`（土壤镁）、`fertn`（施肥氮）、`ndep`（氮沉降）、`phtarget`（目标 pH）、`yn`（氮）、`sn`（硫氮）、`adep`（酸沉降）、`acrop`（作物酸）、`ancy`（氮沉降产酸）、`aagri`（农业产酸）、`aback`（本底酸）、`ytk`（碳钾）、`mbnt`（木本泥炭）、`model_version`（字符串）、`status`（字符串）、`warning`（字符串）、`reason`（文本）、`out_of_range_features`（JSON）、`simulated`（布尔）。

#### Scenario: 酸化改良结果字段完整性
- **WHEN** `acidification_remediation_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `out_of_range_features` 字段 SHALL 使用 JSON 类型

### Requirement: 有机质培肥结果持久化

系统 SHALL 提供 `organic_matter_result` 表的 ORM 模型，持久化 Model-5 有机质培肥结果。模型 SHALL 包含字段：`execution_id`（整数）、`sjd`（酸碱度）、`sxj`（速效钾）、`yjz`（有机质）、`yxl`（有效磷）、`tl`（土壤）、`tj`（铁）、`td`（土壤氮）、`yjflx`（有机肥类型）、`yjztsz`（有机质提升值）、`yjfsyl`（有机肥施用量）、`level`（等级）、`potential_increase`（浮点，潜在提升）、`simulated`（布尔）。

#### Scenario: 有机质结果字段完整性
- **WHEN** `organic_matter_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段

### Requirement: 综合地力改良提升结果持久化

系统 SHALL 提供 `comprehensive_fertility_result` 表的 ORM 模型，持久化 Model-6 综合地力改良提升结果。模型 SHALL 包含字段：`execution_id`（整数）、`tybh`（字符串，地块统一编号）、`fertility_score`（浮点，地力得分）、`fertility_level`（字符串，地力等级）、`improvement_plan`（JSON，改良方案）、`input_snapshot`（JSON，输入快照）、`simulated`（布尔）。

#### Scenario: 综合地力结果字段完整性
- **WHEN** `comprehensive_fertility_result` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `improvement_plan`、`input_snapshot` 字段 SHALL 使用 JSON 类型

### Requirement: 路由决策日志

系统 SHALL 提供 `routing_decision_log` 表的 ORM 模型，记录路由决策全过程。模型 SHALL 包含字段：`trace_id`（字符串）、`question`（文本）、`question_type`（整数）、`relevance`（字符串）、`routing_status`（字符串）、`router_method`（字符串）、`candidate_agents`（JSON）、`hit_exclusive_rules`（JSON）、`llm_reason`（文本）、`llm_duration_ms`（整数）、`total_duration_ms`（整数）、`degradation`（字符串）、`five_dim_context`（JSON）、`data_version`（字符串）、`agent_version`（字符串）、`result_version`（字符串）、`failure_reason`（文本）。

#### Scenario: 路由日志字段完整性
- **WHEN** `routing_decision_log` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `candidate_agents`、`hit_exclusive_rules`、`five_dim_context` 字段 SHALL 使用 JSON 类型

### Requirement: 模型评估指标

系统 SHALL 提供 `model_evaluation_metrics` 表的 ORM 模型，存储模型评估指标。模型 SHALL 包含字段：`model_pair`（字符串）、`positive_label`（字符串）、`tp`（整数）、`fp`（整数）、`fn`（整数）、`tn`（整数）、`total`（整数）、`accuracy`（浮点）、`confusion_rate`（浮点）、`evaluation_mode`（字符串）、`sample_count`（整数）。

#### Scenario: 评估指标字段完整性
- **WHEN** `model_evaluation_metrics` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段

### Requirement: 排他规则配置

系统 SHALL 提供 `exclusive_rule_config` 表的 ORM 模型，存储排他规则配置。模型 SHALL 包含字段：`rule_name`（字符串）、`rule_pair`（JSON）、`discriminator`（字符串）、`condition`（字符串）、`target`（字符串）、`dimension_conditions`（JSON）、`enabled`（布尔）。

#### Scenario: 排他规则字段完整性
- **WHEN** `exclusive_rule_config` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `rule_pair`、`dimension_conditions` 字段 SHALL 使用 JSON 类型

### Requirement: 地块信息

系统 SHALL 提供 `parcel_info` 表的 ORM 模型，存储地块基础信息。模型 SHALL 包含字段：`tybh`（字符串，地块统一编号）、`geom`（Geometry 几何）、`area_code`（字符串，区域代码）、`centroid_lon`（浮点）、`centroid_lat`（浮点）、`land_type`（字符串，土地利用类型）、`fertilizer_type`（字符串，施肥类型）、`target_ph`（浮点，目标 pH）、`soil_indicators`（JSON，土壤指标）。

#### Scenario: 地块信息字段完整性
- **WHEN** `parcel_info` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `geom` 字段 SHALL 使用 Geometry 类型，`soil_indicators` 字段 SHALL 使用 JSON 类型

### Requirement: 模型版本历史

系统 SHALL 提供 `model_version_history` 表的 ORM 模型，记录模型版本变更历史。模型 SHALL 包含字段：`agent_id`（字符串）、`version`（字符串）、`change_description`（文本）、`parameters`（JSON）、`status`（字符串）。

#### Scenario: 版本历史字段完整性
- **WHEN** `model_version_history` 表被创建
- **THEN** 模型 SHALL 包含上述全部字段
- **AND** `parameters` 字段 SHALL 使用 JSON 类型

### Requirement: 专题模型表一次性建表

系统 SHALL 在 `framework/models/thematic_model.py` 中定义全部 15 张表的 ORM 模型，并通过 `framework/models/__init__.py` 导入触发模型注册，使 `db.create_all()` 能一次性创建全部新表。

#### Scenario: db.create_all 创建全部 15 张表
- **WHEN** `init_db.py` 运行 `db.create_all()`
- **THEN** 系统 SHALL 创建全部 15 张新表：`thematic_model_registry`、`model_execution_log`、`spatial_data_layer`、`parcel_geometry`、`stability_risk_result`、`quality_grade_result`、`obstacle_diagnosis_result`、`acidification_remediation_result`、`organic_matter_result`、`comprehensive_fertility_result`、`routing_decision_log`、`model_evaluation_metrics`、`exclusive_rule_config`、`parcel_info`、`model_version_history`

#### Scenario: 模型导入触发注册
- **WHEN** `framework/models/__init__.py` 被导入
- **THEN** `thematic_model.py` 中定义的全部 15 个模型类 SHALL 被 SQLAlchemy 注册
- **AND** `db.create_all()` SHALL 能发现并创建全部 15 张表

#### Scenario: 拼音缩写字段命名
- **WHEN** ORM 模型字段被定义
- **THEN** 字段名 SHALL 使用数据字段标准化表的拼音缩写（如 `sjd`、`yjz`、`ytk`、`gdzldj`、`safe_abs` 等）
- **AND** 字段命名 SHALL 与数据库设计文档 V2.0 保持一致

#### Scenario: 空间几何列使用 Geometry 类型
- **WHEN** ORM 模型定义空间几何列（`geom`、`extent`）
- **THEN** 该列 SHALL 使用 GeoAlchemy2 的 `Geometry` 类型

#### Scenario: JSONB 列使用 JSON 类型
- **WHEN** ORM 模型定义 JSONB 列（如 `input_params`、`output_result`、`minimum_inputs` 等）
- **THEN** 该列 SHALL 使用 SQLAlchemy 的 `JSON` 类型
