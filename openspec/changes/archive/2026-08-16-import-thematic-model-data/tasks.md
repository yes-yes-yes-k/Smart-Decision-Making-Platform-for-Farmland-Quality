# Tasks: Import Thematic Model Data

## 1. 字段映射配置

- [x] 1.1 创建 `scripts/model_field_mappings.py`，定义 5 个模型的字段映射字典（拼音缩写 → V3.0 英文 snake_case）
- [x] 1.2 定义数据源路径常量（模型1-5 的数据文件路径）
- [x] 1.3 定义 execution log 元数据常量（agent_id, model_id, layer_id 等）

## 2. 数据导入脚本

- [x] 2.1 创建 `scripts/import_model_data.py` 主入口，支持 `--model <1-5>` 或 `--all` 参数
- [x] 2.2 实现 execution_log 记录函数：导入前在 model_execution_log 表插入记录，导入后更新 status 和 duration_ms
- [x] 2.3 实现数据源验证函数：检查文件存在性、可读性

## 3. 模型1数据导入（Excel → stability_risk_result, agent_id=model-1）

- [x] 3.1 读取模型1结果文件 `耕地质量稳定性与退化风险结果.xlsx`（Sheet1）
- [x] 3.2 字段映射：TYBH→parcel_id + 28个中文结果列直接映射，其余存入 input_snapshot
- [x] 3.3 导入数据到 stability_risk_result 表（5488 行）
- [x] 3.4 验证导入行数和数据完整性

## 4. 模型2数据导入（CSV → quality_grade_result, agent_id=model-2）

- [x] 4.1 读取 `Farmland_quality_Level_Database.csv`（UTF-8 编码）
- [x] 4.2 字段映射：SiteID→parcel_id，指标存入 input_snapshot，结果用占位值
- [x] 4.3 导入数据到 quality_grade_result 表（1107 行）
- [x] 4.4 验证导入行数和数据完整性

## 5. 模型3数据导入（CSV → obstacle_diagnosis_result, agent_id=model-3）

- [x] 5.1 读取 `test_result.csv`（41列：12隶属度+12障碍度+12障碍等级+5汇总）
- [x] 5.2 字段映射：SJDLSD→soil_ph_membership, SJDZAD→ph_obstacle_degree, SJDZADJ→ph_obstacle_grade 等
- [x] 5.3 导入数据到 obstacle_diagnosis_result 表（14585 行）
- [x] 5.4 验证导入行数和数据完整性

## 6. 模型4数据导入（Excel → organic_matter_result, agent_id=model-5）

- [x] 6.1 读取 `SG旱地-Dose-RF_Manual_splits.xlsx`（Xtrain+Xtest sheets 合并）
- [x] 6.2 字段映射：pH→soil_ph, SOMbe→organic_matter, Gap→om_improvement_target 等
- [x] 6.3 导入数据到 organic_matter_result 表（232 行）
- [x] 6.4 验证导入行数和数据完整性

## 7. 模型5数据导入（CSV → acidification_remediation_result, agent_id=model-4）

- [x] 7.1 读取 `04_旱地复合肥计算结果.csv`（11列）
- [x] 7.2 字段映射：TYBH→parcel_id, SJD→soil_ph, YTK→soil_conditioner_dosage, MBNT→woody_peat_dosage 等
- [x] 7.3 导入数据到 acidification_remediation_result 表（393 行）
- [x] 7.4 验证导入行数和数据完整性

## 8. 集成验证

- [x] 8.1 运行 `python scripts/import_model_data.py --all` 一键导入全部 5 个模型数据
- [x] 8.2 验证 5 张表的数据行数符合预期（5488+1107+14585+232+393=21805）
- [x] 8.3 验证 model_execution_log 表记录了 21805 次执行记录
- [x] 8.4 验证视图 v_model_execution_summary 可查询到导入的执行记录（6 行，每 agent 一行）
