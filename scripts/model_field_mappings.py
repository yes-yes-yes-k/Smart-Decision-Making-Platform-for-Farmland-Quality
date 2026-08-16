"""专题模型数据导入字段映射配置（V3.0）。

定义 5 个模型的数据源路径、字段映射（V2.0 拼音缩写 → V3.0 英文 snake_case）、
execution log 元数据和 thematic_model_registry 注册元数据。

数据源路径基于 D:\\destkop\\模型1-5，字段映射依据 V3.0 设计文档 §1.1/§6.2 命名规范。
数据文件编号与 agent_id 编号交叉（模型4→model-5, 模型5→model-4），按业务逻辑映射。
"""
import os

# 数据源根目录
DATA_ROOT = r"D:\destkop\模型1-5"

# 各模型数据源路径（相对 DATA_ROOT）
DATA_SOURCES = {
    "model-1": {
        "target_table": "stability_risk_result",
        "agent_id": "model-1",
        "file": os.path.join(DATA_ROOT, "模型1_v2", "模型1_v2", "耕地质量稳定性与退化风险结果.xlsx"),
        "file_type": "xlsx",
        "sheet": "Sheet1",
    },
    "model-2": {
        "target_table": "quality_grade_result",
        "agent_id": "model-2",
        "file": os.path.join(DATA_ROOT, "模型2", "Farmland_quality_Level_Database.csv"),
        "file_type": "csv",
    },
    "model-3": {
        "target_table": "obstacle_diagnosis_result",
        "agent_id": "model-3",
        "file": os.path.join(DATA_ROOT, "模型3_V2.0", "test_result.csv"),
        "file_type": "csv",
    },
    # 注意：数据文件"模型4"是 Dose预测（有机质培肥），对应 agent_id=model-5
    "model-5": {
        "target_table": "organic_matter_result",
        "agent_id": "model-5",
        "file": os.path.join(
            DATA_ROOT,
            "模型4-SG-旱地和水田-Dose预测模型",
            "SG-旱地和水田-Dose预测模型",
            "SG旱地-Dose-RF_Manual_splits.xlsx",
        ),
        "file_type": "xlsx",
        "sheets": ["Xtrain", "Xtest"],
    },
    # 注意：数据文件"模型5"是酸化模型，对应 agent_id=model-4
    "model-4": {
        "target_table": "acidification_remediation_result",
        "agent_id": "model-4",
        "file": os.path.join(
            DATA_ROOT,
            "模型5_酸化模型_v2_20260801(1)",
            "模型5_酸化模型_v2_20260801",
            "04_旱地复合肥计算结果.csv",
        ),
        "file_type": "csv",
    },
}

# thematic_model_registry 注册元数据（导入数据前需先注册 agent_id）
MODEL_REGISTRY = [
    {
        "agent_id": "model-1",
        "model_id": "stability_risk_v1",
        "name": "耕地质量稳定性与退化风险评价模型",
        "description": "基于历史多期耕地质量数据，评价地块稳定性与退化风险",
        "domain": "stability",
        "question_type": 1,
        "analysis_scale": "地块",
        "data_type": "评价结果",
        "input_format": "shp",
        "output_format": "shp",
        "runtime_requirement": "需多期(2018/2021/2024)耕地质量评价结果及空间边界图层",
    },
    {
        "agent_id": "model-2",
        "model_id": "quality_grade_v1",
        "name": "耕地质量等级评价模型",
        "description": "基于12项耕地质量指标计算综合质量等级",
        "domain": "quality_grade",
        "question_type": 2,
        "analysis_scale": "地块",
        "data_type": "评价结果",
        "input_format": "csv",
        "output_format": "json",
        "runtime_requirement": "需耕地质量指标输入数据( SiteID/SJD/YJZ等)",
    },
    {
        "agent_id": "model-3",
        "model_id": "obstacle_diagnosis_v2",
        "name": "耕地障碍诊断模型",
        "description": "基于12项指标隶属度、障碍度和障碍等级诊断耕地障碍因子",
        "domain": "obstacle_diagnosis",
        "question_type": 3,
        "analysis_scale": "地块",
        "data_type": "评价结果",
        "input_format": "csv",
        "output_format": "json",
        "runtime_requirement": "需耕地质量指标隶属度计算结果",
    },
    {
        "agent_id": "model-4",
        "model_id": "acidification_remediation_v2",
        "name": "酸化改良模型",
        "description": "基于产酸过程计算，给出亿土康和木本泥炭施加量",
        "domain": "acidification",
        "question_type": 4,
        "analysis_scale": "地块",
        "data_type": "处方用量",
        "input_format": "csv",
        "output_format": "json",
        "runtime_requirement": "需土壤pH/交换性氢铝/产酸分量等输入数据",
    },
    {
        "agent_id": "model-5",
        "model_id": "organic_matter_dose_v1",
        "name": "有机质培肥模型",
        "description": "基于随机森林预测有机肥施用量，县级分析",
        "domain": "organic_matter",
        "question_type": 5,
        "analysis_scale": "县",
        "data_type": "处方用量",
        "input_format": "csv",
        "output_format": "json",
        "runtime_requirement": "需土壤pH/有机质/氮磷钾等指标，及有机肥料类型",
    },
    {
        "agent_id": "model-6",
        "model_id": "comprehensive_fertility_v1",
        "name": "耕地综合地力改良提升模型",
        "description": "整合酸化改良与有机质培肥建议的综合改良方案（占位，业务逻辑待实现）",
        "domain": "comprehensive",
        "question_type": 6,
        "analysis_scale": "地块",
        "data_type": "评价结果",
        "input_format": "json",
        "output_format": "json",
        "runtime_requirement": "[占位] 待实现：整合 model-4 酸化改良与 model-5 有机质培肥建议",
    },
]

# execution log 元数据（每个模型导入时创建一条记录）
EXECUTION_META = {
    "model-1": {"question_type": 1, "routing_mode": "keyword", "routing_status": "normal"},
    "model-2": {"question_type": 2, "routing_mode": "keyword", "routing_status": "normal"},
    "model-3": {"question_type": 3, "routing_mode": "keyword", "routing_status": "normal"},
    "model-4": {"question_type": 4, "routing_mode": "keyword", "routing_status": "normal"},
    "model-5": {"question_type": 5, "routing_mode": "keyword", "routing_status": "normal"},
}

# ============================================================================
# 字段映射：数据源列名 → V3.0 目标表列名
# ============================================================================

# 模型1：耕地质量稳定性与退化风险结果.xlsx → stability_risk_result
# 78列：TYBH + 输入指标(拼音) + 隶属度/权重 + 结果列(中文命名)
MODEL1_MAPPING = {
    # 标识列
    "TYBH": "parcel_id",
    # 稳定性风险结果列（中文命名，直接映射）
    "等级边界安全度": "grade_boundary_safety",
    "指标支撑均衡度_绝对": "indicator_balance_abs",
    "指标支撑均衡度_相对": "indicator_balance_rel",
    "关键临界指标": "critical_indicator",
    "关键指标临界度_绝对": "critical_indicator_degree_abs",
    "关键指标临界度_相对": "critical_indicator_degree_rel",
    "空间邻域一致性_绝对": "spatial_consistency_abs",
    "空间邻域一致性_相对": "spatial_consistency_rel",
    "邻域地块数": "neighbor_count",
    "历史年均变化斜率": "historical_slope",
    "历史变化趋势_绝对": "historical_trend_abs",
    "历史变化趋势_相对": "historical_trend_rel",
    "历史变化类型": "historical_trend_type",
    "历史等级变化": "historical_grade_change",
    "历史掉级次数": "grade_drop_count",
    "掉级风险_绝对": "grade_drop_risk_abs",
    "掉级风险_相对": "grade_drop_risk_rel",
    "关键退化因子": "key_degradation_factor",
    "关键因子退化风险_绝对": "key_factor_risk_abs",
    "关键因子退化风险_相对": "key_factor_risk_rel",
    "邻域平均退化风险": "neighbor_degradation_risk",
    "退化空间集聚风险_绝对": "degradation_cluster_risk_abs",
    "退化空间集聚风险_相对": "degradation_cluster_risk_rel",
    "低质年份数": "low_quality_year_count",
    "持续低质比例": "low_quality_ratio",
    "持续低质风险_绝对": "persistent_low_risk_abs",
    "持续低质风险_相对": "persistent_low_risk_rel",
}
# 模型1输入指标列（存入 input_snapshot JSONB）
MODEL1_INPUT_FIELDS = [
    "DSMC", "FXZQ", "XQMC", "TKMJ", "PJFQ", "DLMC",
    "SJD", "YJZ", "YXL", "SXJ", "TRRZ", "GCZD", "GGNL", "PSNL",
    "DXBW", "ZDGX", "YXTCHD", "GCHD",
    "SJDLSD", "YJZLSD", "YXLLSD", "SXJLSD", "TRRZLSD", "GCZDLSD",
    "GGNLLSD", "PSNLLSD", "DXBWLSD", "ZDGXLSD", "YXTCHDLSD", "GCHDLSD",
    "SJDQZ", "YJZQZ", "YXLQZ", "SXJQZ", "TRRZQZ", "GCZDQZ",
    "GGNLQZ", "PSNLQZ", "DXBWQZ", "ZDGXQZ", "YXTCHDQZ", "GCHDQZ",
    "ZHQZ", "GDZLDJ",
    "综合权重_2018", "质量等级_2018", "综合权重_2021", "质量等级_2021",
    "综合权重_2024", "质量等级_2024",
]

# 模型2：Farmland_quality_Level_Database.csv → quality_grade_result
# 输入数据库，无直接结果列；指标存入 input_snapshot，结果用占位值
MODEL2_MAPPING = {
    "SiteID": "parcel_id",
    "JD": "_centroid_lon",  # 存入 input_snapshot
    "WD": "_centroid_lat",
    "MJ": "_area",
}
# 模型2输入指标列（存入 input_snapshot JSONB）
MODEL2_INPUT_FIELDS = [
    "SJD", "YJZ", "YXL", "SXJ", "TRRZ", "YXTCHD", "GCHD",
    "JHXLLZ", "JHXQLZ",
    "EJNYQcode", "XQMCcode", "GCZDcode", "PSNLcode", "GGNLcode", "DXBWcode", "ZDGXcode",
    "JD", "WD", "MJ",
]

# 模型3：test_result.csv → obstacle_diagnosis_result
# 41列：12隶属度(LSD) + 12障碍度(ZAD) + 12障碍等级(ZADJ) + 5汇总列
MODEL3_MAPPING = {
    # 12 隶属度 → _membership
    "SJDLSD": "soil_ph_membership",
    "YJZLSD": "organic_matter_membership",
    "YXLLSD": "available_p_membership",
    "SXJLSD": "available_k_membership",
    "TRRZLSD": "soil_bulk_density_membership",
    "GCZDLSD": "topsoil_texture_membership",
    "GGNLLSD": "irrigation_capacity_membership",
    "PSNLLSD": "drainage_capacity_membership",
    "DXBWLSD": "terrain_position_membership",
    "ZDGXLSD": "texture_profile_membership",
    "YXTCHDLSD": "effective_soil_depth_membership",
    "GCHDLSD": "topsoil_thickness_membership",
    # 12 障碍度 → _obstacle_degree
    "SJDZAD": "ph_obstacle_degree",
    "YJZZAD": "organic_matter_obstacle_degree",
    "YXLZAD": "available_p_obstacle_degree",
    "SXJZAD": "available_k_obstacle_degree",
    "TRRZZAD": "bulk_density_obstacle_degree",
    "GCZDZAD": "texture_obstacle_degree",
    "GGNLZAD": "irrigation_obstacle_degree",
    "PSNLZAD": "drainage_obstacle_degree",
    "DXBWZAD": "terrain_obstacle_degree",
    "ZDGXZAD": "texture_profile_obstacle_degree",
    "YXTCHDZAD": "soil_depth_obstacle_degree",
    "GCHDZAD": "topsoil_thickness_obstacle_degree",
    # 12 障碍等级 → _obstacle_grade
    "SJDZADJ": "ph_obstacle_grade",
    "YJZZADJ": "organic_matter_obstacle_grade",
    "YXLZADJ": "available_p_obstacle_grade",
    "SXJZADJ": "available_k_obstacle_grade",
    "TRRZZADJ": "bulk_density_obstacle_grade",
    "GCZDZADJ": "texture_obstacle_grade",
    "GGNLZADJ": "irrigation_obstacle_grade",
    "PSNLZADJ": "drainage_obstacle_grade",
    "DXBWZADJ": "terrain_obstacle_grade",
    "ZDGXZADJ": "texture_profile_obstacle_grade",
    "YXTCHDZADJ": "soil_depth_obstacle_grade",
    "GCHDZADJ": "topsoil_thickness_obstacle_grade",
    # 汇总列
    "ZHQZ": "composite_weight",
    "GDZLDJ": "quality_grade",
    "ZALX": "obstacle_type",
    "ZYZAYS": "primary_obstacle_factor",
    "CYZAYS": "secondary_obstacle_factor",
}

# 模型4（agent_id=model-5）：SG旱地-Dose-RF_Manual_splits.xlsx → organic_matter_result
# 注意：列名有尾随空格（'TN '等），映射时需 strip
MODEL4_MAPPING = {
    "pH": "soil_ph",
    "SOMbe": "organic_matter",
    "TN": "total_nitrogen",
    "TP": "total_phosphorus",
    "TK": "total_potassium",
    "AP": "available_phosphorus",
    "AK": "available_potassium",
    "Gap": "om_improvement_target",
    "Fertilizer type": "organic_fertilizer_type",
}

# 模型5（agent_id=model-4）：04_旱地复合肥计算结果.csv → acidification_remediation_result
MODEL5_MAPPING = {
    "TYBH": "parcel_id",
    "SJD": "soil_ph",
    "Hex": "exchangeable_hydrogen",
    "Alex": "exchangeable_aluminum",
    "Adep": "acid_deposition_input",
    "Acrop": "crop_uptake_acid",
    "ANcy": "nitrogen_cycle_acid",
    "Aagri": "agricultural_acid",
    "Aback": "background_soil_acid",
    "YTK": "soil_conditioner_dosage",
    "MBNT": "woody_peat_dosage",
}
