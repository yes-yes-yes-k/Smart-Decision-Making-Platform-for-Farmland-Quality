-- =============================================================================
-- 专题模型数据库 V3.0 视图 DDL
-- 项目：耕地土壤酸化治理智能问答系统
-- 数据库：PostgreSQL 16 + PostGIS 3.4
-- 版本：V3.0    日期：2026-08-16
-- 来源：专题模型数据库设计文档_V3.docx（§5）+ Design Doc 2026-08-16
-- 用途：由 init_db.py 在 db.create_all() 之后执行，创建 3 个查询辅助视图
-- 注意：执行前依赖的全部 15 张表已通过 ORM db.create_all() 创建
-- =============================================================================

-- 5.1  v_model_execution_summary（模型执行汇总视图）
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

-- 5.2  v_parcel_stability_spatial（地块稳定性空间视图）
CREATE OR REPLACE VIEW v_parcel_stability_spatial AS
SELECT g.parcel_id, g.geom, g.area_mu, g.centroid_lon, g.centroid_lat,
    s.grade_boundary_safety, s.grade_drop_risk_abs, s.grade_drop_risk_rel,
    s.key_degradation_factor, s.degradation_cluster_risk_abs,
    s.persistent_low_risk_abs, s.created_at
FROM parcel_geometry g
JOIN stability_risk_result s ON g.parcel_id = s.parcel_id;

-- 5.3  v_confusion_matrix_latest（最新混淆矩阵视图）
CREATE OR REPLACE VIEW v_confusion_matrix_latest AS
SELECT m.* FROM model_evaluation_metrics m
INNER JOIN (
    SELECT model_pair, evaluation_mode, MAX(evaluated_at) AS max_time
    FROM model_evaluation_metrics GROUP BY model_pair, evaluation_mode
) latest ON m.model_pair = latest.model_pair
    AND m.evaluation_mode = latest.evaluation_mode
    AND m.evaluated_at = latest.max_time;
