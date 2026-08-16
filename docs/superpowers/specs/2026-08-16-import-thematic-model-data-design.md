---
comet_change: import-thematic-model-data
role: technical-design
canonical_spec: openspec
date: 2026-08-16
archived-with: 2026-08-16-import-thematic-model-data
status: final
---

# Design Doc: Import Thematic Model Data

**Change**: import-thematic-model-data
**Date**: 2026-08-16
**Status**: design

## 目标

将 `D:\destkop\模型1-5` 路径中的 5 个专题模型数据导入到 V3.0 数据库对应的 5 张结果表，填充业务数据以便系统提供智能问答服务。

## 非目标

- 不修改数据库表结构（表已通过 `add-thematic-model-orm` change 创建）
- 不实现模型计算逻辑（只导入已有结果数据）
- 不处理生产环境大数据量（当前只导入测试数据）

## 数据源到目标表映射

**重要发现**：数据文件编号与 agent_id 编号交叉。按业务逻辑映射：

| 数据文件 | 业务含义 | 目标表 | agent_id |
|---------|---------|--------|---------|
| 模型1_v2 | 稳定性风险 | stability_risk_result | model-1 |
| 模型2 | 质量等级 | quality_grade_result | model-2 |
| 模型3_V2.0 | 障碍诊断 | obstacle_diagnosis_result | model-3 |
| 模型4 (Dose预测) | 有机质培肥 | organic_matter_result | model-5 |
| 模型5 (酸化模型) | 酸化改良 | acidification_remediation_result | model-4 |

## 字段映射

### 模型1（stability_risk_result）
- 数据格式：Shapefile + Excel
- 结果文件：`耕地质量稳定性与退化风险结果.xlsx`
- 需运行时读取列名，按位置或名称映射到 34 列

### 模型2（quality_grade_result）
- 数据文件：`Farmland_quality_Level_Database.csv`
- 字段映射：
  - SiteID → parcel_id
  - SJD → soil_ph（input_snapshot JSON）
  - YJZ → organic_matter（input_snapshot JSON）
  - YXL → available_phosphorus（input_snapshot JSON）
  - SXJ → available_potassium（input_snapshot JSON）
  - 其他指标存入 input_snapshot JSONB 列

### 模型3（obstacle_diagnosis_result）
- 数据文件：`test_result.csv`
- 字段映射：
  - SJDLSD → soil_ph_membership
  - YJZLSD → organic_matter_membership
  - SJDZAD → ph_obstacle_degree
  - SJDZADJ → ph_obstacle_grade
  - ZHQZ → composite_weight
  - GDZLDJ → quality_grade
  - ZALX → obstacle_type
  - ZYZAYS → primary_obstacle_factor
  - CYZAYS → secondary_obstacle_factor

### 模型4（organic_matter_result，agent_id=model-5）
- 数据文件：`SG旱地-Dose-RF_Manual_splits.xlsx`
- 字段映射：
  - pH → soil_ph
  - SOMbe → organic_matter
  - TN → total_nitrogen
  - TP → total_phosphorus
  - TK → total_potassium
  - AP → available_phosphorus
  - AK → available_potassium
  - Gap → om_improvement_target
  - Fertilizer type → organic_fertilizer_type

### 模型5（acidification_remediation_result，agent_id=model-4）
- 数据文件：`04_旱地复合肥计算结果.csv`
- 字段映射：
  - TYBH → parcel_id
  - SJD → soil_ph
  - Hex → acid_deposition_input（或 exchangeable_hydrogen）
  - Alex → exchangeable_aluminum
  - Adep → acid_deposition_input
  - Acrop → crop_uptake_acid
  - ANcy → nitrogen_cycle_acid
  - Aagri → agricultural_acid
  - Aback → background_soil_acid
  - YTK → soil_conditioner_dosage
  - MBNT → woody_peat_dosage

## 技术方法

### 数据导入脚本架构

```
scripts/import_model_data.py     # 主入口
scripts/model_field_mappings.py  # 字段映射配置
```

### 执行流程

1. 解析命令行参数（`--model <1-5>` 或 `--all`）
2. 加载字段映射配置
3. 对每个模型：
   a. 在 model_execution_log 表插入记录（status='running'）
   b. 读取数据文件（CSV/Excel/Shapefile）
   c. 执行字段映射
   d. 导入数据到目标表
   e. 更新 model_execution_log 记录（status='ok', duration_ms）
4. 验证数据完整性

### 依赖

- pandas（CSV/Excel 读取）
- geopandas（Shapefile 读取，可选）
- psycopg2（PostgreSQL 连接）
- sqlalchemy（ORM 操作）

## 风险

1. **字段映射不完整**：模型1 的 Shapefile 属性表列名未知，需运行时发现
2. **数据编码**：CSV 文件可能使用 GBK 编码，需自动检测
3. **空间数据**：Shapefile 的 geom 列需要 WKT/WKB 转换
4. **execution_id 外键**：导入结果数据前需要先在 model_execution_log 表创建记录
5. **数据量小**：模型5 只有 3-4 行测试数据

## 验证方法

1. 运行 `python scripts/import_model_data.py --all`
2. 检查 5 张表的数据行数
3. 检查 model_execution_log 表的 5 条记录
4. 查询视图 v_model_execution_summary 验证执行记录
