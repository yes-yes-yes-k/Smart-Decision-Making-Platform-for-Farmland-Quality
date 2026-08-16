# Design: Import Thematic Model Data

## Overview

将 `D:\destkop\模型1-5` 路径中的 5 个专题模型数据导入到 V3.0 数据库对应的 5 张结果表。

## Architecture

### 数据导入流程

```
数据源文件 → 字段映射 → execution_log 记录 → 数据库导入 → 验证
```

### 核心组件

1. **字段映射配置**（`scripts/model_field_mappings.py`）
   - 定义 5 个模型的字段映射字典
   - 处理拼音缩写 → V3.0 英文 snake_case 的转换
   - 定义数据源路径常量

2. **数据导入脚本**（`scripts/import_model_data.py`）
   - 支持单模型导入（`--model <1-5>`）和全量导入（`--all`）
   - 支持多种数据格式：Shapefile（geopandas）、CSV（pandas）、Excel（openpyxl）
   - 导入前在 model_execution_log 表记录执行元数据
   - 导入后更新 execution_log 的 status 和 duration_ms

3. **execution_log 记录**
   - 每批导入前插入 model_execution_log 记录
   - 记录 agent_id, model_id, layer_id, started_at, status
   - 导入完成后更新 status='ok', duration_ms, completed_at

## Data Source Details

### 模型1（stability_risk_result）
- 数据路径：`D:\destkop\模型1-5\模型1_v2\模型1_v2\`
- 结果文件：`耕地质量稳定性与退化风险结果.xlsx` 或 `.shp`
- 字段映射：需要读取 Excel/Shapefile 属性表，映射到 stability_risk_result 的 34 列

### 模型2（quality_grade_result）
- 数据文件：`Farmland_quality_Level_Database.csv`
- 字段：SiteID, JD, WD, MJ, SJD, YJZ, YXL, SXJ, TRRZ, YXTCHD, GCHD, JHXLLZ, JHXQLZ, EJNYQcode, XQMCcode, GCZDcode, PSNLcode, GGNLcode, DXBWcode, ZDGXcode
- 映射：SiteID→parcel_id, SJD→soil_ph, YJZ→organic_matter 等
- input_snapshot：存储原始指标 JSON

### 模型3（obstacle_diagnosis_result）
- 数据文件：`test_result.csv`
- 输入字段：YJNYQ, EJNYQ, SJD, YJZ, YXL, SXJ, TRRZ, GCZD, GGNL, PSNL, DXBW, ZDGX, YXTCHD, GCHD
- 输出字段：隶属度列（SJDLSD 等）、综合权重（ZHQZ）、综合等级（GDZLDJ）、障碍度列（SJDZAD 等）、障碍等级列（SJDZADJ 等）、障碍类型（ZALX）、主要/次要障碍因素
- 映射：SJDLSD→soil_ph_membership, SJDZAD→ph_obstacle_degree, SJDZADJ→ph_obstacle_grade 等

### 模型4（acidification_remediation_result）
- 数据文件：`SG旱地-Dose-RF_Manual_splits.xlsx`
- 需要读取 Excel 列名，识别与 acidification_remediation_result 表字段的对应关系

### 模型5（organic_matter_result）
- 输入文件：`03_Data.csv`（TYBH, SJD, Hex, Alex）
- 输出文件：`04_旱地复合肥计算结果.csv`
- 映射：TYBH→parcel_id, SJD→soil_ph

## Risks

- **字段映射不完整**：数据文件字段名可能与预期不一致，需要运行时验证
- **数据编码问题**：CSV 文件可能使用 GBK 编码，需要自动检测
- **空间数据导入**：Shapefile 需要处理 geom 列，可能需要 GDAL/OGR
- **数据量**：测试数据量较小（模型5 只有 3 行），但生产数据可能更大
