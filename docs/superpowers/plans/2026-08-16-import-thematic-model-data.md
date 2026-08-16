---
change: import-thematic-model-data
design-doc: docs/superpowers/specs/2026-08-16-import-thematic-model-data-design.md
base-ref: 8ac69bfe1c0daa8c27bd4c436e74446eb7e76677
archived-with: 2026-08-16-import-thematic-model-data
---

# Plan: Import Thematic Model Data

## 任务清单

### Step 1：字段映射配置（model_field_mappings.py）

- [x] 1.1 创建 `scripts/model_field_mappings.py`，定义 5 个模型的字段映射字典
- [x] 1.2 定义数据源路径常量（DATA_SOURCES 字典）
- [x] 1.3 定义 execution log 元数据常量（agent_id, model_id 等）

### Step 2：数据导入脚本（import_model_data.py）

- [x] 2.1 创建 `scripts/import_model_data.py` 主入口，支持 `--model <1-5>` 和 `--all` 参数
- [x] 2.2 实现 create_execution_log() 函数：插入 model_execution_log 记录
- [x] 2.3 实现 update_execution_log() 函数：更新 status 和 duration_ms
- [x] 2.4 实现数据源验证函数：检查文件存在性

### Step 3：模型1导入（Excel → stability_risk_result）

- [x] 3.1 读取 `耕地质量稳定性与退化风险结果.xlsx`
- [x] 3.2 字段映射并导入到 stability_risk_result 表（5488 行）
- [x] 3.3 验证导入行数

### Step 4：模型2导入（CSV → quality_grade_result）

- [x] 4.1 读取 `Farmland_quality_Level_Database.csv`（自动检测编码）
- [x] 4.2 字段映射（SiteID→parcel_id 等），input_snapshot 存储原始指标 JSON
- [x] 4.3 导入到 quality_grade_result 表（1107 行）
- [x] 4.4 验证导入行数

### Step 5：模型3导入（CSV → obstacle_diagnosis_result）

- [x] 5.1 读取 `test_result.csv`
- [x] 5.2 字段映射（SJDLSD→soil_ph_membership 等），VARCHAR(64) 字段截断
- [x] 5.3 导入到 obstacle_diagnosis_result 表（14585 行）
- [x] 5.4 验证导入行数

### Step 6：模型4导入（Excel → organic_matter_result, agent_id=model-5）

- [x] 6.1 读取 `SG旱地-Dose-RF_Manual_splits.xlsx`（合并 Xtrain+Xtest）
- [x] 6.2 字段映射（pH→soil_ph, SOMbe→organic_matter 等）
- [x] 6.3 导入到 organic_matter_result 表（232 行）
- [x] 6.4 验证导入行数

### Step 7：模型5导入（CSV → acidification_remediation_result, agent_id=model-4）

- [x] 7.1 读取 `04_旱地复合肥计算结果.csv`
- [x] 7.2 字段映射（TYBH→parcel_id, SJD→soil_ph, YTK→soil_conditioner_dosage 等）
- [x] 7.3 导入到 acidification_remediation_result 表（393 行）
- [x] 7.4 验证导入行数

### Step 8：集成验证

- [x] 8.1 运行 `python scripts/import_model_data.py --all` 一键导入
- [x] 8.2 验证 5 张表数据行数（5488+1107+14585+232+393=21805）
- [x] 8.3 验证 model_execution_log 表 21805 条记录
- [x] 8.4 验证视图 v_model_execution_summary 可查询（6 行，每 agent 一行）
