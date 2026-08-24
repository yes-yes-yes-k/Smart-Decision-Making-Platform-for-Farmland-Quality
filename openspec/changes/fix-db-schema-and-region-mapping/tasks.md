## 1. 区域代码映射数据库表与服务层

- [x] 1.1 在 `framework/models/thematic_model.py` 中新增 `AreaCodeRegionMap` 模型（表 `area_code_region_map`），字段：area_code(String(10),UK)、region_name(String(64))、primary(String(10))、secondary(String(10))、ejnyq_idx(Integer)、enabled(Boolean,default true)、created_at、updated_at
- [x] 1.2 更新 `framework/models/__init__.py` 导出 `AreaCodeRegionMap`
- [x] 1.3 创建 `framework/domain/calculations/region_mapping_service.py`，实现 `get_region_mapping(area_code)`（DB 缓存 → 硬编码回退 → 默认值）、`refresh_region_cache()`、`validate_region_mappings()` 三个函数
- [x] 1.4 创建 `scripts/init_region_mappings.py`，初始化插入 440281（乐昌）和 440233（新丰）映射记录
- [x] 1.5 验证 `init_db.py` 能正确创建 `area_code_region_map` 表且不报错

## 2. 更新区域映射消费者

- [x] 2.1 修改 `framework/domain/calculations/grade_calculation.py`：将 `AREA_TO_REGION.get(area_code, ...)` 替换为 `get_region_mapping(area_code)`
- [x] 2.2 修改 `framework/domain/calculations/obstacle_calculation.py`：将 `AREA_TO_REGION.get(area_code, ...)` 替换为 `get_region_mapping(area_code)`
- [x] 2.3 修改 `framework/domain/calculations/stability_calculation.py`：将 `AREA_TO_REGION.get(area_code, ...)` 替换为 `get_region_mapping(area_code)`
- [x] 2.4 在 `tests/calculations/test_coefficients.py` 中添加 `get_region_mapping` 单元测试（DB 回退、硬编码回退、默认降级三种场景）

## 3. 数据库模型扩展

- [x] 3.1 在 `framework/models/soil_data.py` 的 `ThirdSurveyTopsoil` 模型中新增字段：`exchangeable_hydrogen`（Float，可 NULL）、`exchangeable_aluminum`（Float，可 NULL）、`exchangeable_acid_total`（Float，可 NULL）、`hydrolytic_total_acidity`（Float，可 NULL）、`total_n`（Float，可 NULL）
- [x] 3.2 在 `ThirdSurveyProfile` 模型中同步新增上述 Model-4/5 字段
- [x] 3.3 验证 SQLAlchemy 模型能正确建表（运行 `migrate_add_model45_fields.py` 检查 `ALTER TABLE` 不报错）

## 4. 土壤数据导入脚本

- [x] 4.1 创建 `scripts/import_soil_data.py`，支持从 `F:\BaiduNetdiskDownload\耕地质量大模型` 目录读取 Excel 数据
- [x] 4.2 实现 `05_` 剖面理化数据导入：解析中文列名（交换性氢离子→exchangeable_hydrogen、交换性铝离子→exchangeable_aluminum、全氮→total_n 等），导入到 `third_survey_profiles` 表
- [x] 4.3 实现 `04_` 表层土数据导入：解析 SOM→organic_matter、TN→total_n、AP→available_phosphorus、AK→available_potassium 等，导入到 `third_survey_topsoils` 表
- [x] 4.4 验证导入后 `third_survey_profiles` 的 exchangeable_hydrogen/exchangeable_aluminum/total_n 字段非空率 > 60%（源数据部分缺失，平均值填充后 parcels 覆盖 100%）

## 5. Parcel 指标补充

- [x] 5.1 更新 `scripts/import_lechang_data.py` 的 `COLUMN_MAPS`，添加 Model-4/5 所需字段映射（交换性氢离子、交换性铝离子、水解性总酸度、全氮）
- [x] 5.2 更新 `build_soil_indicators()` 函数，在 JSON 中包含 `target_ph`（默认 6.5）、`fertilizer_type`（默认 "compound"）
- [x] 5.3 创建 `scripts/link_soil_indicators.py`，按行政区域"乐昌市"批量将 `05_` 剖面数据的 Model-4 指标（exchangeable_hydrogen、exchangeable_aluminum）填充到 `parcel_info.soil_indicators`
- [x] 5.4 同一脚本按行政区域将 `04_` 表层土的 Model-5 指标（organic_matter、total_n、available_phosphorus、available_potassium）补充到 `parcel_info.soil_indicators`
- [x] 5.5 验证关联后 `parcel_info` 中至少 90% 的 parcels 的 `soil_indicators` 包含 total_n 字段（实测 100%）

## 6. 数据库重建与导入

- [x] 6.1 采用增量迁移（ALTER TABLE + create_all）而非完全重建，保留现有数据
- [x] 6.2 运行 `migrate_add_model45_fields.py` 创建 `area_code_region_map` 表 + 为 `third_survey_topsoils` 添加 5 列 + 为 `third_survey_profiles` 添加 3 列
- [x] 6.3 运行 `scripts/init_region_mappings.py` 初始化区域映射（2 条记录：440281、440233）
- [x] 6.4 执行 `scripts/import_soil_data.py` 导入土壤数据（649 行表层土 + 216 行剖面）
- [x] 6.5 修复 `third_survey_topsoils.total_n`（从 tn 列复制，649 行 100% 非空）
- [x] 6.6 执行 `scripts/link_soil_indicators.py` 关联 Model-4/5 指标到 `parcel_info.soil_indicators`（5491 parcels 全部更新）

## 7. 验证与测试

- [x] 7.1 编写 `AreaCodeRegionMap` 模型测试，验证建表和初始数据插入
- [x] 7.2 编写 `get_region_mapping()` 单元测试（DB 优先、硬编码回退、默认降级、缓存刷新）+ DB 集成测试
- [x] 7.3 编写数据库字段完整性测试，验证新增字段在 `third_survey_profiles` 和 `third_survey_topsoils` 表中存在
- [x] 7.4 编写 Model-4 数据查询测试，验证 parcel_info 中包含 exchangeable_hydrogen、exchangeable_aluminum 等字段
- [x] 7.5 编写 Model-5 数据查询测试，验证 parcel_info 中包含 total_n、organic_matter 等字段
- [x] 7.6 运行完整测试套件，确保所有现有测试通过（86 passed: 74 existing + 12 new）
- [x] 7.7 端到端验证：soil_indicators 中 target_ph 和 fertilizer_type 100% 非空
- [x] 7.8 端到端验证：soil_indicators 中 exchangeable_hydrogen、exchangeable_aluminum、total_n 均 100% 非空
