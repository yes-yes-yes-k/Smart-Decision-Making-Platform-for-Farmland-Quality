-- =============================================================================
-- 专题模型数据库 V3.0 DDL 脚本（最终版）
-- 项目：耕地土壤酸化治理智能问答系统
-- 数据库：PostgreSQL 16 + PostGIS 3.4
-- 版本：V3.0    日期：2026-08-16
-- 来源：专题模型数据库设计文档_V3.docx（§8）+ Design Doc 2026-08-16
-- 命名规范：英文 snake_case；parcel_id 取代 tybh；索引名按表前缀化（PostgreSQL 全局唯一）
-- 执行顺序：按 FK 依赖拓扑排序（非 V3.0 §8 章节顺序）；章节号保留用于交叉引用
-- 独立执行：psql -d <dbname> -f scripts/thematic_models_v3_ddl.sql
-- ORM 等价：framework/models/thematic_model.py 的 db.create_all() 生成等价结构
-- =============================================================================

-- 前置：创建扩展
CREATE EXTENSION IF NOT EXISTS postgis;

-- =============================================================================
-- §8.1  thematic_model_registry（无 FK，最先创建）
-- =============================================================================
CREATE TABLE thematic_model_registry (
  id SERIAL,
  agent_id VARCHAR(32) NOT NULL,
  model_id VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT,
  domain VARCHAR(32) NOT NULL,
  question_type SMALLINT NOT NULL,
  analysis_scale VARCHAR(16) NOT NULL,
  data_type VARCHAR(16) NOT NULL,
  input_format VARCHAR(16) NOT NULL DEFAULT 'shp',
  output_format VARCHAR(16) NOT NULL DEFAULT 'shp',
  minimum_inputs JSONB,
  runtime_requirement TEXT,
  version VARCHAR(16) NOT NULL DEFAULT '1.0',
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE thematic_model_registry IS '专题模型注册表';
COMMENT ON COLUMN thematic_model_registry.id IS '主键';
COMMENT ON COLUMN thematic_model_registry.agent_id IS '智能体标识（model-1 ~ model-6）';
COMMENT ON COLUMN thematic_model_registry.model_id IS '规范模型标识';
COMMENT ON COLUMN thematic_model_registry.name IS '模型中文名称';
COMMENT ON COLUMN thematic_model_registry.description IS '模型描述';
COMMENT ON COLUMN thematic_model_registry.domain IS '领域标识';
COMMENT ON COLUMN thematic_model_registry.question_type IS '问题类型（1~6）';
COMMENT ON COLUMN thematic_model_registry.analysis_scale IS '分析尺度（省/县/片区/地块）';
COMMENT ON COLUMN thematic_model_registry.data_type IS '数据类型（指标数据/评价结果/处方用量）';
COMMENT ON COLUMN thematic_model_registry.input_format IS '输入格式（shp/csv/json）';
COMMENT ON COLUMN thematic_model_registry.output_format IS '输出格式（shp/csv/json）';
COMMENT ON COLUMN thematic_model_registry.minimum_inputs IS '最小输入字段列表';
COMMENT ON COLUMN thematic_model_registry.runtime_requirement IS '运行时前置条件';
COMMENT ON COLUMN thematic_model_registry.version IS '当前模型版本';
COMMENT ON COLUMN thematic_model_registry.status IS '状态';
COMMENT ON COLUMN thematic_model_registry.created_at IS '创建时间';
COMMENT ON COLUMN thematic_model_registry.updated_at IS '更新时间';

CREATE UNIQUE INDEX uk_thematic_model_registry_agent_id ON thematic_model_registry (agent_id);
CREATE UNIQUE INDEX uk_thematic_model_registry_model_id ON thematic_model_registry (model_id);
CREATE INDEX idx_thematic_model_registry_question_type ON thematic_model_registry (question_type);

-- =============================================================================
-- §8.3  spatial_data_layer（无 FK，在 §8.2 之前创建以满足 FK 依赖）
-- =============================================================================
CREATE TABLE spatial_data_layer (
  id BIGSERIAL,
  layer_name VARCHAR(128) NOT NULL,
  layer_type VARCHAR(32) NOT NULL,
  file_path TEXT NOT NULL,
  file_hash VARCHAR(64),
  crs VARCHAR(32) NOT NULL DEFAULT 'EPSG:4326',
  feature_count INTEGER,
  extent geometry(Polygon,4326),
  geometry_type VARCHAR(16),
  attribute_fields JSONB,
  model_scope VARCHAR(32),
  upload_by INTEGER,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE spatial_data_layer IS '空间数据图层管理表';
COMMENT ON COLUMN spatial_data_layer.id IS '主键';
COMMENT ON COLUMN spatial_data_layer.layer_name IS '图层名称';
COMMENT ON COLUMN spatial_data_layer.layer_type IS '图层类型（farmland_boundary/stability_result/diagnosis_result 等）';
COMMENT ON COLUMN spatial_data_layer.file_path IS 'Shapefile 文件路径';
COMMENT ON COLUMN spatial_data_layer.file_hash IS '文件哈希（SHA-256）';
COMMENT ON COLUMN spatial_data_layer.crs IS '坐标参考系（如 EPSG:4326）';
COMMENT ON COLUMN spatial_data_layer.feature_count IS '要素数量';
COMMENT ON COLUMN spatial_data_layer.extent IS '图层空间范围（PostGIS 几何）';
COMMENT ON COLUMN spatial_data_layer.geometry_type IS '几何类型（Point/Polygon/MultiPolygon）';
COMMENT ON COLUMN spatial_data_layer.attribute_fields IS '属性字段列表 [{name, type}]';
COMMENT ON COLUMN spatial_data_layer.model_scope IS '适用模型（model-1/model-2/model-3/all）';
COMMENT ON COLUMN spatial_data_layer.upload_by IS '上传用户ID';
COMMENT ON COLUMN spatial_data_layer.status IS '状态（active/archived）';
COMMENT ON COLUMN spatial_data_layer.uploaded_at IS '上传时间';

CREATE UNIQUE INDEX uk_spatial_data_layer_file_hash ON spatial_data_layer (file_hash);
CREATE INDEX idx_spatial_data_layer_layer_type ON spatial_data_layer (layer_type);
CREATE INDEX idx_spatial_data_layer_model_scope ON spatial_data_layer (model_scope);
CREATE INDEX idx_spatial_data_layer_status ON spatial_data_layer (status);
CREATE INDEX idx_spatial_data_layer_extent ON spatial_data_layer USING GIST (extent);

-- =============================================================================
-- §8.2  model_execution_log（FK → thematic_model_registry + spatial_data_layer）
-- =============================================================================
CREATE TABLE model_execution_log (
  id BIGSERIAL,
  trace_id VARCHAR(64) NOT NULL,
  agent_id VARCHAR(32) NOT NULL,
  question_type SMALLINT NOT NULL,
  user_id INTEGER,
  conversation_id INTEGER,
  parcel_id VARCHAR(64),
  analysis_object_type VARCHAR(16),
  analysis_object_id VARCHAR(64),
  area_code VARCHAR(32),
  context_version INTEGER,
  analysis_context_snapshot JSONB,
  model_version VARCHAR(32),
  data_as_of VARCHAR(32),
  data_version VARCHAR(32),
  layer_id BIGINT,
  input_params JSONB,
  output_result JSONB,
  answer_text TEXT,
  evidence JSONB,
  status VARCHAR(16) NOT NULL,
  routing_mode VARCHAR(16),
  routing_status VARCHAR(16),
  simulated BOOLEAN NOT NULL DEFAULT FALSE,
  confidence REAL,
  started_at TIMESTAMP WITH TIME ZONE NOT NULL,
  completed_at TIMESTAMP WITH TIME ZONE,
  duration_ms REAL,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_model_execution_log_agent_id FOREIGN KEY (agent_id) REFERENCES thematic_model_registry(agent_id),
  CONSTRAINT fk_model_execution_log_layer_id FOREIGN KEY (layer_id) REFERENCES spatial_data_layer(id)
);
COMMENT ON TABLE model_execution_log IS '模型执行日志表';
COMMENT ON COLUMN model_execution_log.id IS '主键';
COMMENT ON COLUMN model_execution_log.trace_id IS '追溯ID（UUID）';
COMMENT ON COLUMN model_execution_log.agent_id IS '关联 thematic_model_registry.agent_id';
COMMENT ON COLUMN model_execution_log.question_type IS '问题类型（1~6）';
COMMENT ON COLUMN model_execution_log.user_id IS '用户ID';
COMMENT ON COLUMN model_execution_log.conversation_id IS '会话ID';
COMMENT ON COLUMN model_execution_log.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN model_execution_log.layer_id IS '关联 spatial_data_layer.id';
COMMENT ON COLUMN model_execution_log.input_params IS '输入参数快照';
COMMENT ON COLUMN model_execution_log.output_result IS '输出结果快照';
COMMENT ON COLUMN model_execution_log.answer_text IS '自然语言答复';
COMMENT ON COLUMN model_execution_log.evidence IS '证据列表';
COMMENT ON COLUMN model_execution_log.status IS '执行状态（ok/error/fallback/rejected）';
COMMENT ON COLUMN model_execution_log.routing_mode IS '路由模式（llm/keyword）';
COMMENT ON COLUMN model_execution_log.routing_status IS '路由状态';
COMMENT ON COLUMN model_execution_log.simulated IS '是否模拟数据';
COMMENT ON COLUMN model_execution_log.confidence IS '置信度（0~1）';
COMMENT ON COLUMN model_execution_log.started_at IS '执行开始时间';
COMMENT ON COLUMN model_execution_log.completed_at IS '执行完成时间';
COMMENT ON COLUMN model_execution_log.duration_ms IS '执行耗时（毫秒）';
COMMENT ON COLUMN model_execution_log.error_message IS '错误信息';
COMMENT ON COLUMN model_execution_log.created_at IS '记录创建时间';

CREATE INDEX idx_model_execution_log_trace_id ON model_execution_log (trace_id);
CREATE INDEX idx_model_execution_log_agent_id ON model_execution_log (agent_id);
CREATE INDEX idx_model_execution_log_parcel_id ON model_execution_log (parcel_id);
CREATE INDEX idx_model_execution_log_object ON model_execution_log (analysis_object_type, analysis_object_id);
CREATE INDEX idx_model_execution_log_area_agent_status ON model_execution_log (area_code, agent_id, status);
CREATE INDEX idx_model_execution_log_layer_id ON model_execution_log (layer_id);
CREATE INDEX idx_model_execution_log_started_at ON model_execution_log (started_at);

-- =============================================================================
-- §8.4  parcel_geometry（FK → spatial_data_layer）
-- =============================================================================
CREATE TABLE parcel_geometry (
  id BIGSERIAL,
  parcel_id VARCHAR(64) NOT NULL,
  geom geometry(Polygon,4326) NOT NULL,
  crs VARCHAR(32) NOT NULL DEFAULT 'EPSG:4326',
  area_mu DOUBLE PRECISION,
  area_sqm DOUBLE PRECISION,
  centroid_lon DOUBLE PRECISION,
  centroid_lat DOUBLE PRECISION,
  layer_id BIGINT,
  properties JSONB,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_parcel_geometry_layer_id FOREIGN KEY (layer_id) REFERENCES spatial_data_layer(id)
);
COMMENT ON TABLE parcel_geometry IS '地块空间几何表';
COMMENT ON COLUMN parcel_geometry.id IS '主键';
COMMENT ON COLUMN parcel_geometry.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN parcel_geometry.geom IS '地块几何（PostGIS Polygon）';
COMMENT ON COLUMN parcel_geometry.crs IS '坐标参考系';
COMMENT ON COLUMN parcel_geometry.area_mu IS '面积（亩）';
COMMENT ON COLUMN parcel_geometry.area_sqm IS '面积（平方米）';
COMMENT ON COLUMN parcel_geometry.centroid_lon IS '质心经度';
COMMENT ON COLUMN parcel_geometry.centroid_lat IS '质心纬度';
COMMENT ON COLUMN parcel_geometry.layer_id IS '关联 spatial_data_layer.id';
COMMENT ON COLUMN parcel_geometry.properties IS '其他土壤指标属性快照';
COMMENT ON COLUMN parcel_geometry.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_parcel_geometry_parcel_id ON parcel_geometry (parcel_id);
CREATE INDEX idx_parcel_geometry_layer_id ON parcel_geometry (layer_id);
CREATE INDEX idx_parcel_geometry_geom ON parcel_geometry USING GIST (geom);

-- =============================================================================
-- §8.5  stability_risk_result (Model-1, FK → model_execution_log)
-- =============================================================================
CREATE TABLE stability_risk_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  parcel_id VARCHAR(64) NOT NULL,
  geom geometry(Polygon,4326),
  grade_boundary_safety DOUBLE PRECISION,
  indicator_balance_abs DOUBLE PRECISION,
  indicator_balance_rel DOUBLE PRECISION,
  critical_indicator DOUBLE PRECISION,
  critical_indicator_degree_abs DOUBLE PRECISION,
  critical_indicator_degree_rel DOUBLE PRECISION,
  spatial_consistency_abs DOUBLE PRECISION,
  spatial_consistency_rel DOUBLE PRECISION,
  neighbor_count INTEGER,
  historical_slope DOUBLE PRECISION,
  historical_trend_abs DOUBLE PRECISION,
  historical_trend_rel DOUBLE PRECISION,
  historical_trend_type VARCHAR(64),
  historical_grade_change DOUBLE PRECISION,
  grade_drop_count INTEGER,
  grade_drop_risk_abs DOUBLE PRECISION,
  grade_drop_risk_rel DOUBLE PRECISION,
  key_degradation_factor VARCHAR(64),
  key_factor_risk_abs DOUBLE PRECISION,
  key_factor_risk_rel DOUBLE PRECISION,
  neighbor_degradation_risk DOUBLE PRECISION,
  degradation_cluster_risk_abs DOUBLE PRECISION,
  degradation_cluster_risk_rel DOUBLE PRECISION,
  low_quality_year_count INTEGER,
  low_quality_ratio DOUBLE PRECISION,
  persistent_low_risk_abs DOUBLE PRECISION,
  persistent_low_risk_rel DOUBLE PRECISION,
  input_snapshot JSONB,
  simulated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_stability_risk_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE stability_risk_result IS '稳定性风险评价结果表（Model-1）';
COMMENT ON COLUMN stability_risk_result.id IS '主键';
COMMENT ON COLUMN stability_risk_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN stability_risk_result.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN stability_risk_result.geom IS '地块几何（PostGIS，用于空间邻域分析）';
COMMENT ON COLUMN stability_risk_result.grade_boundary_safety IS '等级边界安全度';
COMMENT ON COLUMN stability_risk_result.indicator_balance_abs IS '指标支撑均衡度_绝对';
COMMENT ON COLUMN stability_risk_result.indicator_balance_rel IS '指标支撑均衡度_相对';
COMMENT ON COLUMN stability_risk_result.critical_indicator IS '关键临界指标';
COMMENT ON COLUMN stability_risk_result.critical_indicator_degree_abs IS '关键指标临界度_绝对';
COMMENT ON COLUMN stability_risk_result.critical_indicator_degree_rel IS '关键指标临界度_相对';
COMMENT ON COLUMN stability_risk_result.spatial_consistency_abs IS '空间邻域一致性_绝对';
COMMENT ON COLUMN stability_risk_result.spatial_consistency_rel IS '空间邻域一致性_相对';
COMMENT ON COLUMN stability_risk_result.neighbor_count IS '邻域地块数';
COMMENT ON COLUMN stability_risk_result.historical_slope IS '历史年均变化斜率';
COMMENT ON COLUMN stability_risk_result.historical_trend_abs IS '历史变化趋势_绝对';
COMMENT ON COLUMN stability_risk_result.historical_trend_rel IS '历史变化趋势_相对';
COMMENT ON COLUMN stability_risk_result.historical_trend_type IS '历史变化类型';
COMMENT ON COLUMN stability_risk_result.historical_grade_change IS '历史等级变化';
COMMENT ON COLUMN stability_risk_result.grade_drop_count IS '历史掉级次数';
COMMENT ON COLUMN stability_risk_result.grade_drop_risk_abs IS '掉级风险_绝对';
COMMENT ON COLUMN stability_risk_result.grade_drop_risk_rel IS '掉级风险_相对';
COMMENT ON COLUMN stability_risk_result.key_degradation_factor IS '关键退化因子';
COMMENT ON COLUMN stability_risk_result.key_factor_risk_abs IS '关键因子退化风险_绝对';
COMMENT ON COLUMN stability_risk_result.key_factor_risk_rel IS '关键因子退化风险_相对';
COMMENT ON COLUMN stability_risk_result.neighbor_degradation_risk IS '邻域平均退化风险';
COMMENT ON COLUMN stability_risk_result.degradation_cluster_risk_abs IS '退化空间集聚风险_绝对';
COMMENT ON COLUMN stability_risk_result.degradation_cluster_risk_rel IS '退化空间集聚风险_相对';
COMMENT ON COLUMN stability_risk_result.low_quality_year_count IS '低质年份数';
COMMENT ON COLUMN stability_risk_result.low_quality_ratio IS '持续低质比例';
COMMENT ON COLUMN stability_risk_result.persistent_low_risk_abs IS '持续低质风险_绝对';
COMMENT ON COLUMN stability_risk_result.persistent_low_risk_rel IS '持续低质风险_相对';
COMMENT ON COLUMN stability_risk_result.input_snapshot IS '输入参数快照（含 terrain_position/topsoil_thickness/soil_ph 等41个标准输入字段）';
COMMENT ON COLUMN stability_risk_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN stability_risk_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_stability_risk_result_execution_id ON stability_risk_result (execution_id);
CREATE INDEX idx_stability_risk_result_parcel_id ON stability_risk_result (parcel_id);
CREATE INDEX idx_stability_risk_result_geom ON stability_risk_result USING GIST (geom);

-- =============================================================================
-- §8.6  quality_grade_result (Model-2, FK → model_execution_log)
-- =============================================================================
CREATE TABLE quality_grade_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  parcel_id VARCHAR(64),
  geom geometry(Polygon,4326),
  quality_grade VARCHAR(4) NOT NULL,
  composite_index DOUBLE PRECISION NOT NULL,
  composite_weight DOUBLE PRECISION,
  indicators JSONB,
  obstacle_degree JSONB,
  input_snapshot JSONB,
  simulated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_quality_grade_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE quality_grade_result IS '质量等级评价结果表（Model-2）';
COMMENT ON COLUMN quality_grade_result.id IS '主键';
COMMENT ON COLUMN quality_grade_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN quality_grade_result.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN quality_grade_result.geom IS '地块几何（PostGIS）';
COMMENT ON COLUMN quality_grade_result.quality_grade IS '耕地质量等级（1~10）';
COMMENT ON COLUMN quality_grade_result.composite_index IS '综合指数（0~1）';
COMMENT ON COLUMN quality_grade_result.composite_weight IS '综合权重';
COMMENT ON COLUMN quality_grade_result.indicators IS '指标列表 [{name, raw_value, membership, weight}]';
COMMENT ON COLUMN quality_grade_result.obstacle_degree IS '障碍度排序 [{rank, indicator, degree}]';
COMMENT ON COLUMN quality_grade_result.input_snapshot IS '输入参数快照（含 terrain_position/soil_ph/organic_matter 等标准输入字段）';
COMMENT ON COLUMN quality_grade_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN quality_grade_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_quality_grade_result_execution_id ON quality_grade_result (execution_id);
CREATE INDEX idx_quality_grade_result_parcel_id ON quality_grade_result (parcel_id);
CREATE INDEX idx_quality_grade_result_quality_grade ON quality_grade_result (quality_grade);
CREATE INDEX idx_quality_grade_result_geom ON quality_grade_result USING GIST (geom);

-- =============================================================================
-- §8.7  obstacle_diagnosis_result (Model-3, FK → model_execution_log)
-- =============================================================================
CREATE TABLE obstacle_diagnosis_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  parcel_id VARCHAR(64),
  soil_ph_membership DOUBLE PRECISION,
  organic_matter_membership DOUBLE PRECISION,
  available_p_membership DOUBLE PRECISION,
  available_k_membership DOUBLE PRECISION,
  soil_bulk_density_membership DOUBLE PRECISION,
  topsoil_texture_membership DOUBLE PRECISION,
  irrigation_capacity_membership DOUBLE PRECISION,
  drainage_capacity_membership DOUBLE PRECISION,
  terrain_position_membership DOUBLE PRECISION,
  texture_profile_membership DOUBLE PRECISION,
  effective_soil_depth_membership DOUBLE PRECISION,
  topsoil_thickness_membership DOUBLE PRECISION,
  ph_obstacle_degree DOUBLE PRECISION,
  organic_matter_obstacle_degree DOUBLE PRECISION,
  available_p_obstacle_degree DOUBLE PRECISION,
  available_k_obstacle_degree DOUBLE PRECISION,
  bulk_density_obstacle_degree DOUBLE PRECISION,
  texture_obstacle_degree DOUBLE PRECISION,
  irrigation_obstacle_degree DOUBLE PRECISION,
  drainage_obstacle_degree DOUBLE PRECISION,
  terrain_obstacle_degree DOUBLE PRECISION,
  texture_profile_obstacle_degree DOUBLE PRECISION,
  soil_depth_obstacle_degree DOUBLE PRECISION,
  topsoil_thickness_obstacle_degree DOUBLE PRECISION,
  ph_obstacle_grade DOUBLE PRECISION,
  organic_matter_obstacle_grade DOUBLE PRECISION,
  available_p_obstacle_grade DOUBLE PRECISION,
  available_k_obstacle_grade DOUBLE PRECISION,
  bulk_density_obstacle_grade DOUBLE PRECISION,
  texture_obstacle_grade DOUBLE PRECISION,
  irrigation_obstacle_grade DOUBLE PRECISION,
  drainage_obstacle_grade DOUBLE PRECISION,
  terrain_obstacle_grade DOUBLE PRECISION,
  texture_profile_obstacle_grade DOUBLE PRECISION,
  soil_depth_obstacle_grade DOUBLE PRECISION,
  topsoil_thickness_obstacle_grade DOUBLE PRECISION,
  obstacle_type VARCHAR(64),
  primary_obstacle_factor VARCHAR(64),
  secondary_obstacle_factor VARCHAR(64),
  quality_grade VARCHAR(64),
  composite_weight DOUBLE PRECISION,
  input_snapshot JSONB,
  simulated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_obstacle_diagnosis_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE obstacle_diagnosis_result IS '障碍诊断结果表（Model-3）';
COMMENT ON COLUMN obstacle_diagnosis_result.id IS '主键';
COMMENT ON COLUMN obstacle_diagnosis_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN obstacle_diagnosis_result.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN obstacle_diagnosis_result.soil_ph_membership IS '酸碱度隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.organic_matter_membership IS '有机质隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.available_p_membership IS '有效磷隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.available_k_membership IS '速效钾隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.soil_bulk_density_membership IS '土壤容重隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.topsoil_texture_membership IS '耕层质地隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.irrigation_capacity_membership IS '灌溉能力隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.drainage_capacity_membership IS '排水能力隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.terrain_position_membership IS '地形部位隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.texture_profile_membership IS '质地构型隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.effective_soil_depth_membership IS '有效土层厚度隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.topsoil_thickness_membership IS '耕层厚度隶属度';
COMMENT ON COLUMN obstacle_diagnosis_result.ph_obstacle_degree IS 'pH障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.organic_matter_obstacle_degree IS '有机质障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.available_p_obstacle_degree IS '有效磷障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.available_k_obstacle_degree IS '速效钾障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.bulk_density_obstacle_degree IS '容重障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.texture_obstacle_degree IS '耕层质地障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.irrigation_obstacle_degree IS '灌溉能力障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.drainage_obstacle_degree IS '排水能力障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.terrain_obstacle_degree IS '地形部位障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.texture_profile_obstacle_degree IS '质地构型障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.soil_depth_obstacle_degree IS '有效土层障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.topsoil_thickness_obstacle_degree IS '耕层厚度障碍度';
COMMENT ON COLUMN obstacle_diagnosis_result.ph_obstacle_grade IS 'pH障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.organic_matter_obstacle_grade IS '有机质障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.available_p_obstacle_grade IS '有效磷障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.available_k_obstacle_grade IS '速效钾障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.bulk_density_obstacle_grade IS '容重障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.texture_obstacle_grade IS '耕层质地障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.irrigation_obstacle_grade IS '灌溉能力障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.drainage_obstacle_grade IS '排水能力障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.terrain_obstacle_grade IS '地形部位障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.texture_profile_obstacle_grade IS '质地构型障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.soil_depth_obstacle_grade IS '有效土层障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.topsoil_thickness_obstacle_grade IS '耕层厚度障碍等级';
COMMENT ON COLUMN obstacle_diagnosis_result.obstacle_type IS '障碍类型';
COMMENT ON COLUMN obstacle_diagnosis_result.primary_obstacle_factor IS '主要障碍因素';
COMMENT ON COLUMN obstacle_diagnosis_result.secondary_obstacle_factor IS '次要障碍因素';
COMMENT ON COLUMN obstacle_diagnosis_result.quality_grade IS '耕地质量等级';
COMMENT ON COLUMN obstacle_diagnosis_result.composite_weight IS '综合权重';
COMMENT ON COLUMN obstacle_diagnosis_result.input_snapshot IS '输入参数快照';
COMMENT ON COLUMN obstacle_diagnosis_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN obstacle_diagnosis_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_obstacle_diagnosis_result_execution_id ON obstacle_diagnosis_result (execution_id);
CREATE INDEX idx_obstacle_diagnosis_result_parcel_id ON obstacle_diagnosis_result (parcel_id);
CREATE INDEX idx_obstacle_diagnosis_result_obstacle_type ON obstacle_diagnosis_result (obstacle_type);

-- =============================================================================
-- §8.8  acidification_remediation_result (Model-4, FK → model_execution_log)
-- =============================================================================
CREATE TABLE acidification_remediation_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  parcel_id VARCHAR(64),
  soil_ph DOUBLE PRECISION,
  exchangeable_hydrogen DOUBLE PRECISION,
  exchangeable_aluminum DOUBLE PRECISION,
  rainfall_ph DOUBLE PRECISION,
  annual_rainfall DOUBLE PRECISION,
  grain_yield DOUBLE PRECISION,
  straw_yield DOUBLE PRECISION,
  grain_p_content DOUBLE PRECISION,
  grain_k_content DOUBLE PRECISION,
  grain_ca_content DOUBLE PRECISION,
  grain_mg_content DOUBLE PRECISION,
  straw_p_content DOUBLE PRECISION,
  straw_k_content DOUBLE PRECISION,
  straw_ca_content DOUBLE PRECISION,
  straw_mg_content DOUBLE PRECISION,
  fertilizer_n DOUBLE PRECISION,
  nitrogen_deposition DOUBLE PRECISION,
  target_ph DOUBLE PRECISION,
  grain_n_content DOUBLE PRECISION,
  straw_n_content DOUBLE PRECISION,
  acid_deposition_input DOUBLE PRECISION,
  crop_uptake_acid DOUBLE PRECISION,
  nitrogen_cycle_acid DOUBLE PRECISION,
  agricultural_acid DOUBLE PRECISION,
  background_soil_acid DOUBLE PRECISION,
  soil_conditioner_dosage DOUBLE PRECISION,
  woody_peat_dosage DOUBLE PRECISION,
  model_version VARCHAR(32),
  status VARCHAR(16) NOT NULL DEFAULT 'ok',
  warning TEXT,
  reason TEXT,
  out_of_range_features JSONB,
  simulated BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_acidification_remediation_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE acidification_remediation_result IS '酸化改良结果表（Model-4）';
COMMENT ON COLUMN acidification_remediation_result.id IS '主键';
COMMENT ON COLUMN acidification_remediation_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN acidification_remediation_result.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN acidification_remediation_result.soil_ph IS '酸碱度（土壤pH）';
COMMENT ON COLUMN acidification_remediation_result.exchangeable_hydrogen IS '土壤交换性氢离子';
COMMENT ON COLUMN acidification_remediation_result.exchangeable_aluminum IS '土壤交换性铝离子';
COMMENT ON COLUMN acidification_remediation_result.rainfall_ph IS '降水pH年均值';
COMMENT ON COLUMN acidification_remediation_result.annual_rainfall IS '年降水量';
COMMENT ON COLUMN acidification_remediation_result.grain_yield IS '籽粒产量';
COMMENT ON COLUMN acidification_remediation_result.straw_yield IS '秸秆产量';
COMMENT ON COLUMN acidification_remediation_result.grain_p_content IS '籽粒P含量';
COMMENT ON COLUMN acidification_remediation_result.grain_k_content IS '籽粒K含量';
COMMENT ON COLUMN acidification_remediation_result.grain_ca_content IS '籽粒Ca含量';
COMMENT ON COLUMN acidification_remediation_result.grain_mg_content IS '籽粒Mg含量';
COMMENT ON COLUMN acidification_remediation_result.straw_p_content IS '秸秆P含量';
COMMENT ON COLUMN acidification_remediation_result.straw_k_content IS '秸秆K含量';
COMMENT ON COLUMN acidification_remediation_result.straw_ca_content IS '秸秆Ca含量';
COMMENT ON COLUMN acidification_remediation_result.straw_mg_content IS '秸秆Mg含量';
COMMENT ON COLUMN acidification_remediation_result.fertilizer_n IS '施肥量以N元素计算';
COMMENT ON COLUMN acidification_remediation_result.nitrogen_deposition IS 'N沉降';
COMMENT ON COLUMN acidification_remediation_result.target_ph IS '目标pH值';
COMMENT ON COLUMN acidification_remediation_result.grain_n_content IS '籽粒N含量';
COMMENT ON COLUMN acidification_remediation_result.straw_n_content IS '秸秆N含量';
COMMENT ON COLUMN acidification_remediation_result.acid_deposition_input IS '酸沉降产酸量';
COMMENT ON COLUMN acidification_remediation_result.crop_uptake_acid IS '植株吸收利用产H+量';
COMMENT ON COLUMN acidification_remediation_result.nitrogen_cycle_acid IS '氮循环净产酸量';
COMMENT ON COLUMN acidification_remediation_result.agricultural_acid IS '农业活动产酸量';
COMMENT ON COLUMN acidification_remediation_result.background_soil_acid IS '土壤本底酸量';
COMMENT ON COLUMN acidification_remediation_result.soil_conditioner_dosage IS '亿土康施加量';
COMMENT ON COLUMN acidification_remediation_result.woody_peat_dosage IS '木本泥炭施加量';
COMMENT ON COLUMN acidification_remediation_result.model_version IS '模型版本（如 process_v2_20260801）';
COMMENT ON COLUMN acidification_remediation_result.status IS '执行状态（ok/rejected/fallback）';
COMMENT ON COLUMN acidification_remediation_result.warning IS '警告信息';
COMMENT ON COLUMN acidification_remediation_result.reason IS '拒绝原因';
COMMENT ON COLUMN acidification_remediation_result.out_of_range_features IS '越界特征列表';
COMMENT ON COLUMN acidification_remediation_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN acidification_remediation_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_acidification_remediation_result_execution_id ON acidification_remediation_result (execution_id);
CREATE INDEX idx_acidification_remediation_result_parcel_id ON acidification_remediation_result (parcel_id);
CREATE INDEX idx_acidification_remediation_result_status ON acidification_remediation_result (status);

-- =============================================================================
-- §8.9  organic_matter_result (Model-5, 无 parcel_id, 县级分析, FK → model_execution_log)
-- =============================================================================
CREATE TABLE organic_matter_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  soil_ph DOUBLE PRECISION,
  available_potassium DOUBLE PRECISION,
  organic_matter DOUBLE PRECISION,
  available_phosphorus DOUBLE PRECISION,
  total_phosphorus DOUBLE PRECISION,
  total_potassium DOUBLE PRECISION,
  total_nitrogen DOUBLE PRECISION,
  organic_fertilizer_type VARCHAR(64),
  om_improvement_target DOUBLE PRECISION,
  organic_fertilizer_dosage DOUBLE PRECISION,
  level VARCHAR(8),
  potential_increase DOUBLE PRECISION,
  simulated BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_organic_matter_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE organic_matter_result IS '有机质培肥结果表（Model-5）';
COMMENT ON COLUMN organic_matter_result.id IS '主键';
COMMENT ON COLUMN organic_matter_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN organic_matter_result.soil_ph IS '酸碱度（土壤pH）';
COMMENT ON COLUMN organic_matter_result.available_potassium IS '土壤速效钾含量';
COMMENT ON COLUMN organic_matter_result.organic_matter IS '土壤有机质含量';
COMMENT ON COLUMN organic_matter_result.available_phosphorus IS '土壤有效磷含量';
COMMENT ON COLUMN organic_matter_result.total_phosphorus IS '土壤总磷含量';
COMMENT ON COLUMN organic_matter_result.total_potassium IS '土壤总钾含量';
COMMENT ON COLUMN organic_matter_result.total_nitrogen IS '土壤总氮含量';
COMMENT ON COLUMN organic_matter_result.organic_fertilizer_type IS '土壤有机肥料类型';
COMMENT ON COLUMN organic_matter_result.om_improvement_target IS '土壤有机质提升值';
COMMENT ON COLUMN organic_matter_result.organic_fertilizer_dosage IS '有机肥施用量';
COMMENT ON COLUMN organic_matter_result.level IS '有机质等级（极低/低/中/高/极高）';
COMMENT ON COLUMN organic_matter_result.potential_increase IS '预期有机质提升量（g/kg）';
COMMENT ON COLUMN organic_matter_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN organic_matter_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_organic_matter_result_execution_id ON organic_matter_result (execution_id);
CREATE INDEX idx_organic_matter_result_level ON organic_matter_result (level);

-- =============================================================================
-- §8.10  comprehensive_fertility_result (Model-6, 占位, FK → model_execution_log)
-- =============================================================================
CREATE TABLE comprehensive_fertility_result (
  id BIGSERIAL,
  execution_id BIGINT NOT NULL,
  parcel_id VARCHAR(64),
  fertility_score DOUBLE PRECISION,
  fertility_level VARCHAR(8),
  improvement_plan JSONB,
  input_snapshot JSONB,
  simulated BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_comprehensive_fertility_result_execution_id FOREIGN KEY (execution_id) REFERENCES model_execution_log(id)
);
COMMENT ON TABLE comprehensive_fertility_result IS '综合地力改良提升结果表（Model-6）';
COMMENT ON COLUMN comprehensive_fertility_result.id IS '主键';
COMMENT ON COLUMN comprehensive_fertility_result.execution_id IS '关联 model_execution_log.id';
COMMENT ON COLUMN comprehensive_fertility_result.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN comprehensive_fertility_result.fertility_score IS '综合地力得分';
COMMENT ON COLUMN comprehensive_fertility_result.fertility_level IS '综合地力等级';
COMMENT ON COLUMN comprehensive_fertility_result.improvement_plan IS '综合改良方案（整合酸化改良+有机质培肥建议）';
COMMENT ON COLUMN comprehensive_fertility_result.input_snapshot IS '输入参数快照';
COMMENT ON COLUMN comprehensive_fertility_result.simulated IS '是否模拟数据';
COMMENT ON COLUMN comprehensive_fertility_result.created_at IS '创建时间';

CREATE UNIQUE INDEX uk_comprehensive_fertility_result_execution_id ON comprehensive_fertility_result (execution_id);
CREATE INDEX idx_comprehensive_fertility_result_parcel_id ON comprehensive_fertility_result (parcel_id);

-- =============================================================================
-- §8.11  routing_decision_log（无 FK）
-- =============================================================================
CREATE TABLE routing_decision_log (
  id BIGSERIAL,
  trace_id VARCHAR(64) NOT NULL,
  question TEXT NOT NULL,
  question_type SMALLINT NOT NULL,
  relevance REAL,
  routing_status VARCHAR(16) NOT NULL DEFAULT 'normal',
  router_method VARCHAR(16) NOT NULL,
  candidate_agents JSONB,
  hit_exclusive_rules JSONB,
  llm_reason TEXT,
  llm_duration_ms REAL,
  total_duration_ms REAL,
  degradation TEXT,
  five_dim_context JSONB,
  data_version VARCHAR(32),
  agent_version VARCHAR(32),
  result_version VARCHAR(16) DEFAULT 'v1.2',
  failure_reason TEXT,
  logged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE routing_decision_log IS '路由决策日志表';
COMMENT ON COLUMN routing_decision_log.id IS '主键';
COMMENT ON COLUMN routing_decision_log.trace_id IS '追溯ID（UUID）';
COMMENT ON COLUMN routing_decision_log.question IS '用户原始问题';
COMMENT ON COLUMN routing_decision_log.question_type IS '问题类型（0~6）';
COMMENT ON COLUMN routing_decision_log.relevance IS '相关性得分（0~1）';
COMMENT ON COLUMN routing_decision_log.routing_status IS '路由状态';
COMMENT ON COLUMN routing_decision_log.router_method IS '路由方法（keyword/llm/knowledge/vector）';
COMMENT ON COLUMN routing_decision_log.candidate_agents IS '候选智能体列表';
COMMENT ON COLUMN routing_decision_log.hit_exclusive_rules IS '命中的排他规则';
COMMENT ON COLUMN routing_decision_log.llm_reason IS 'LLM 路由理由';
COMMENT ON COLUMN routing_decision_log.llm_duration_ms IS 'LLM 路由耗时（毫秒）';
COMMENT ON COLUMN routing_decision_log.total_duration_ms IS '路由总耗时（毫秒）';
COMMENT ON COLUMN routing_decision_log.degradation IS '降级说明';
COMMENT ON COLUMN routing_decision_log.five_dim_context IS '五维上下文 {scale, data_type, business_task, expected_output}';
COMMENT ON COLUMN routing_decision_log.data_version IS '数据版本';
COMMENT ON COLUMN routing_decision_log.agent_version IS '智能体版本';
COMMENT ON COLUMN routing_decision_log.result_version IS '路由算法版本';
COMMENT ON COLUMN routing_decision_log.failure_reason IS '失败原因';
COMMENT ON COLUMN routing_decision_log.logged_at IS '日志记录时间';

CREATE UNIQUE INDEX uk_routing_decision_log_trace_id ON routing_decision_log (trace_id);
CREATE INDEX idx_routing_decision_log_question_type ON routing_decision_log (question_type);
CREATE INDEX idx_routing_decision_log_router_method ON routing_decision_log (router_method);
CREATE INDEX idx_routing_decision_log_routing_status ON routing_decision_log (routing_status);
CREATE INDEX idx_routing_decision_log_logged_at ON routing_decision_log (logged_at);

-- =============================================================================
-- §8.12  model_evaluation_metrics（无 FK）
-- =============================================================================
CREATE TABLE model_evaluation_metrics (
  id BIGSERIAL,
  model_pair VARCHAR(32) NOT NULL,
  positive_label VARCHAR(32) NOT NULL,
  tp INTEGER NOT NULL DEFAULT 0,
  fp INTEGER NOT NULL DEFAULT 0,
  fn INTEGER NOT NULL DEFAULT 0,
  tn INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  accuracy REAL NOT NULL DEFAULT 0,
  confusion_rate REAL NOT NULL DEFAULT 0,
  evaluation_mode VARCHAR(16) NOT NULL,
  sample_count INTEGER,
  evaluated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE model_evaluation_metrics IS '模型评估指标表';
COMMENT ON COLUMN model_evaluation_metrics.id IS '主键';
COMMENT ON COLUMN model_evaluation_metrics.model_pair IS '易混淆模型对标识';
COMMENT ON COLUMN model_evaluation_metrics.positive_label IS '正类标签';
COMMENT ON COLUMN model_evaluation_metrics.tp IS '真阳性';
COMMENT ON COLUMN model_evaluation_metrics.fp IS '假阳性';
COMMENT ON COLUMN model_evaluation_metrics.fn IS '假阴性';
COMMENT ON COLUMN model_evaluation_metrics.tn IS '真阴性';
COMMENT ON COLUMN model_evaluation_metrics.total IS '样本总数';
COMMENT ON COLUMN model_evaluation_metrics.accuracy IS '正确率';
COMMENT ON COLUMN model_evaluation_metrics.confusion_rate IS '混淆率';
COMMENT ON COLUMN model_evaluation_metrics.evaluation_mode IS '评估模式（keyword/llm）';
COMMENT ON COLUMN model_evaluation_metrics.sample_count IS '评估样本数';
COMMENT ON COLUMN model_evaluation_metrics.evaluated_at IS '评估时间';

CREATE INDEX idx_model_evaluation_metrics_model_pair ON model_evaluation_metrics (model_pair);
CREATE INDEX idx_model_evaluation_metrics_evaluation_mode ON model_evaluation_metrics (evaluation_mode);

-- =============================================================================
-- §8.13  exclusive_rule_config（无 FK）
-- =============================================================================
CREATE TABLE exclusive_rule_config (
  id SERIAL,
  rule_name VARCHAR(64) NOT NULL,
  rule_pair JSONB NOT NULL,
  discriminator VARCHAR(128) NOT NULL,
  condition VARCHAR(64),
  target VARCHAR(32) NOT NULL,
  dimension_conditions JSONB,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE exclusive_rule_config IS '排他规则配置表';
COMMENT ON COLUMN exclusive_rule_config.id IS '主键';
COMMENT ON COLUMN exclusive_rule_config.rule_name IS '规则名称';
COMMENT ON COLUMN exclusive_rule_config.rule_pair IS '易混淆模型对';
COMMENT ON COLUMN exclusive_rule_config.discriminator IS '判别维度描述';
COMMENT ON COLUMN exclusive_rule_config.condition IS '关键词条件名';
COMMENT ON COLUMN exclusive_rule_config.target IS '目标模型ID';
COMMENT ON COLUMN exclusive_rule_config.dimension_conditions IS '维度条件';
COMMENT ON COLUMN exclusive_rule_config.enabled IS '是否启用';
COMMENT ON COLUMN exclusive_rule_config.created_at IS '创建时间';
COMMENT ON COLUMN exclusive_rule_config.updated_at IS '更新时间';

CREATE UNIQUE INDEX uk_exclusive_rule_config_rule_name ON exclusive_rule_config (rule_name);
CREATE INDEX idx_exclusive_rule_config_target ON exclusive_rule_config (target);
CREATE INDEX idx_exclusive_rule_config_enabled ON exclusive_rule_config (enabled);

-- =============================================================================
-- §8.14  parcel_info（无 FK）
-- =============================================================================
CREATE TABLE parcel_info (
  id BIGSERIAL,
  parcel_id VARCHAR(64) NOT NULL,
  legacy_parcel_code VARCHAR(64),
  geom geometry(Polygon,4326),
  area_code VARCHAR(32),
  centroid_lon DOUBLE PRECISION,
  centroid_lat DOUBLE PRECISION,
  land_type VARCHAR(16),
  fertilizer_type VARCHAR(32),
  target_ph DOUBLE PRECISION,
  soil_indicators JSONB,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
COMMENT ON TABLE parcel_info IS '地块信息表';
COMMENT ON COLUMN parcel_info.id IS '主键';
COMMENT ON COLUMN parcel_info.parcel_id IS '地块唯一编号';
COMMENT ON COLUMN parcel_info.geom IS '地块几何（PostGIS）';
COMMENT ON COLUMN parcel_info.area_code IS '区域编码';
COMMENT ON COLUMN parcel_info.centroid_lon IS '质心经度';
COMMENT ON COLUMN parcel_info.centroid_lat IS '质心纬度';
COMMENT ON COLUMN parcel_info.land_type IS '土地利用类型（upland/paddy）';
COMMENT ON COLUMN parcel_info.fertilizer_type IS '肥料类型';
COMMENT ON COLUMN parcel_info.target_ph IS '目标pH值';
COMMENT ON COLUMN parcel_info.soil_indicators IS '结构化土壤指标快照（terrain_position/topsoil_thickness/soil_ph 等）';
COMMENT ON COLUMN parcel_info.created_at IS '创建时间';
COMMENT ON COLUMN parcel_info.updated_at IS '更新时间';

CREATE UNIQUE INDEX uk_parcel_info_parcel_id ON parcel_info (parcel_id);
CREATE UNIQUE INDEX uk_parcel_info_legacy_parcel_code ON parcel_info (legacy_parcel_code);
CREATE INDEX idx_parcel_info_legacy_parcel_code ON parcel_info (legacy_parcel_code);
CREATE INDEX idx_parcel_info_area_code ON parcel_info (area_code);
CREATE INDEX idx_parcel_info_geom ON parcel_info USING GIST (geom);

-- =============================================================================
-- §8.15  model_version_history（FK → thematic_model_registry）
-- =============================================================================
CREATE TABLE model_version_history (
  id BIGSERIAL,
  agent_id VARCHAR(32) NOT NULL,
  version VARCHAR(16) NOT NULL,
  change_description TEXT,
  parameters JSONB,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_model_version_history_agent_id FOREIGN KEY (agent_id) REFERENCES thematic_model_registry(agent_id)
);
COMMENT ON TABLE model_version_history IS '模型版本历史表';
COMMENT ON COLUMN model_version_history.id IS '主键';
COMMENT ON COLUMN model_version_history.agent_id IS '关联 thematic_model_registry.agent_id';
COMMENT ON COLUMN model_version_history.version IS '版本号';
COMMENT ON COLUMN model_version_history.change_description IS '变更描述';
COMMENT ON COLUMN model_version_history.parameters IS '版本参数快照';
COMMENT ON COLUMN model_version_history.status IS '状态';
COMMENT ON COLUMN model_version_history.created_at IS '创建时间';

CREATE INDEX idx_model_version_history_agent_id ON model_version_history (agent_id);
CREATE INDEX idx_model_version_history_version ON model_version_history (version);

-- =============================================================================
-- §5 视图（V3.0 §5）
-- 依赖全部 15 张表已就绪；由 init_db.py 在 db.create_all() 之后执行
-- 也可直接 source 本文件（DDL 已按依赖排序，视图在最后）
-- =============================================================================

-- §5.1  v_model_execution_summary（模型执行汇总视图）
CREATE OR REPLACE VIEW v_model_execution_summary AS
SELECT r.agent_id, r.name AS model_name, r.question_type,
    COUNT(l.id) AS total_executions,
    SUM(CASE WHEN l.status = 'ok' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN l.status = 'error' THEN 1 ELSE 0 END) AS error_count,
    SUM(CASE WHEN l.simulated THEN 1 ELSE 0 END) AS simulated_count,
    ROUND(AVG(l.duration_ms)::numeric, 2) AS avg_duration_ms,
    ROUND(AVG(l.confidence)::numeric, 4) AS avg_confidence,
    MAX(l.started_at) AS last_execution_time
FROM thematic_model_registry r
LEFT JOIN model_execution_log l ON r.agent_id = l.agent_id
GROUP BY r.agent_id, r.name, r.question_type;

-- §5.2  v_parcel_stability_spatial（地块稳定性空间视图）
CREATE OR REPLACE VIEW v_parcel_stability_spatial AS
SELECT g.parcel_id, g.geom, g.area_mu, g.centroid_lon, g.centroid_lat,
    s.grade_boundary_safety, s.grade_drop_risk_abs, s.grade_drop_risk_rel,
    s.key_degradation_factor, s.degradation_cluster_risk_abs,
    s.persistent_low_risk_abs, s.created_at
FROM parcel_geometry g
JOIN stability_risk_result s ON g.parcel_id = s.parcel_id;

-- §5.3  v_confusion_matrix_latest（最新混淆矩阵视图）
CREATE OR REPLACE VIEW v_confusion_matrix_latest AS
SELECT m.* FROM model_evaluation_metrics m
INNER JOIN (
    SELECT model_pair, evaluation_mode, MAX(evaluated_at) AS max_time
    FROM model_evaluation_metrics GROUP BY model_pair, evaluation_mode
) latest ON m.model_pair = latest.model_pair
    AND m.evaluation_mode = latest.evaluation_mode
    AND m.evaluated_at = latest.max_time;

-- =============================================================================
-- 结束 — 15 表 + 10 FK 约束 + 3 视图 + 全部索引（按表前缀化命名）
-- =============================================================================
