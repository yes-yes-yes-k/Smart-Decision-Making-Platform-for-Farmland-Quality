# Proposal: Import Thematic Model Data

## Why

V3.0 专题模型数据库（15 张表）已通过 `add-thematic-model-orm` change 创建完成，但所有业务表均为空。`D:\destkop\模型1-5` 路径提供了 5 个专题模型的真实测试数据和生产数据，需要导入到数据库对应的 5 张结果表中，以便系统可以基于真实数据提供耕地质量评价、障碍诊断、酸化改良和有机质培肥等智能问答服务。

## What Changes

- 新增数据导入脚本 `scripts/import_model_data.py`，支持从多种格式（Shapefile、CSV、Excel）导入 5 个模型的测试数据到 V3.0 数据库表
- 新增字段映射配置 `scripts/model_field_mappings.py`，处理拼音缩写字段名（TYBH/SJD/YJZ 等）到 V3.0 英文 snake_case 字段名（parcel_id/soil_ph/organic_matter 等）的映射
- 新增 execution log 记录，每批导入数据前在 `model_execution_log` 表中记录执行元数据
- 导入后验证数据完整性和字段一致性

## Data Source Mapping

| 模型 | 数据路径 | 数据格式 | 目标表 |
|------|---------|---------|--------|
| 模型1 | `D:\destkop\模型1-5\模型1_v2\模型1_v2\` | Shapefile + Excel | stability_risk_result |
| 模型2 | `D:\destkop\模型1-5\模型2\Farmland_quality_Level_Database.csv` | CSV | quality_grade_result |
| 模型3 | `D:\destkop\模型1-5\模型3_V2.0\test_result.csv` | CSV | obstacle_diagnosis_result |
| 模型4 | `D:\destkop\模型1-5\模型4-SG-旱地和水田-Dose预测模型\` | Excel | acidification_remediation_result |
| 模型5 | `D:\destkop\模型1-5\模型5_酸化模型_v2_20260801(1)\` | CSV | organic_matter_result |

## Field Mapping Challenge

数据文件使用拼音缩写字段名（V2.0 规范），数据库表使用 V3.0 英文 snake_case 字段名。需要建立字段映射字典：

| 拼音缩写 | V3.0 英文 snake_case | 含义 |
|---------|---------------------|------|
| TYBH/SiteID | parcel_id | 地块唯一编号 |
| SJD | soil_ph | 土壤酸碱度 |
| YJZ | organic_matter | 有机质 |
| YXL | available_phosphorus | 有效磷 |
| SXJ | available_potassium | 速效钾 |
| TRRZ | bulk_density | 土壤容重 |
| YXTCHD | effective_soil_depth | 有效土层厚度 |
| GCHD | topsoil_thickness | 耕层厚度 |
| JHXLLZ | exchangeable_aluminum | 交换性铝离子 |
| JHXQLZ | exchangeable_hydrogen | 交换性氢离子 |

## Impact

- Affected specs: `thematic-data-import` (new capability)
- Affected code: `scripts/import_model_data.py` (new), `scripts/model_field_mappings.py` (new)
- Database: 5 张结果表填充测试数据（stability_risk_result, quality_grade_result, obstacle_diagnosis_result, acidification_remediation_result, organic_matter_result）
