## Why

Model-4（酸化防治）和 Model-5（肥力评价）计算时查询 `parcel_info` 的 `soil_indicators` JSON 字段，发现关键字段缺失（交换性氢离子、交换性铝离子、全氮、目标pH、肥料类型），导致这两个模型无法正常运行。同时，区域代码 `440233`（新丰县）未在 `AREA_TO_REGION` 映射表中配置，Model-1/2/3 使用默认值而非该区域的正确农业区系数，评价结果不准确。

## What Changes

- **新增数据库字段**：在 `ThirdSurveyTopsoil` 模型添加 `exchangeable_hydrogen`（交换性氢离子）、`exchangeable_aluminum`（交换性铝离子）、`exchangeable_acid_total`（交换性酸总量）、`hydrolytic_total_acidity`（水解性总酸度）等 Model-4 必需字段
- **新增数据库字段**：在 `ThirdSurveyProfile` 模型添加 Model-4/5 依赖的缺失字段
- **创建区域代码映射表**：新建 `area_code_region_map` 表，存储行政区划代码到农业区参数的映射（440281乐昌、440233新丰 → HN/NL/ejnyq_idx=3），取代硬编码 `AREA_TO_REGION` 字典
- **实现映射服务层**：创建 `get_region_mapping(area_code)` 函数，采用 DB 缓存 → 硬编码回退 → 默认值的三层降级策略
- **重新导入土壤数据**：使用 `F:\BaiduNetdiskDownload\耕地质量大模型` 的数据源，重新导入以填充新增字段
- **修复 parcel_info 导入脚本**：在 `soil_indicators` JSON 中包含 `exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 等字段，使 Model-4/5 能从 `parcel_info` 表直接查询到所需指标
- **补充 Model-4/5 的 indicator 映射**：确保 `soil_ph`、`exchangeable_hydrogen`、`exchangeable_aluminum`、`organic_matter`、`available_potassium`、`available_phosphorus`、`total_n` 等字段在数据库中有值
- **更新消费者代码**：将 `grade_calculation.py`、`obstacle_calculation.py`、`stability_calculation.py` 中的 `AREA_TO_REGION.get()` 替换为 `get_region_mapping()`

## Capabilities

### New Capabilities
- `area-code-mapping`: 区域代码（440281乐昌、440233新丰）到农业区一级/二级系数的映射配置，采用独立数据库表 `area_code_region_map` + 服务层 `get_region_mapping()` 实现
- `parcel-indicators-data`: `parcel_info.soil_indicators` JSON 新增 `exchangeable_hydrogen`、`exchangeable_aluminum`、`total_n` 等字段，使 Model-4/5 计算接口能获取完整指标

### Modified Capabilities
- `soil-data-ingestion`: 扩展土壤数据导入脚本，支持从 `05_` 剖面理化数据解析交换性氢离子、交换性铝离子、全氮等 Model-4/5 必需字段，并将其写入 `third_survey_profiles` 和 `third_survey_topsoils` 表
- `farmland-quality-grade-evaluation`: 改为通过 `get_region_mapping()` 服务函数从 `area_code_region_map` 表查询映射，使 Model-1/2 对新丰县地块使用正确系数
- `farmland-obstacle-diagnosis-model`: 改为通过 `get_region_mapping()` 服务函数从 `area_code_region_map` 表查询映射，使 Model-3 对新丰县地块使用正确隶属度系数和权重
- `database-models`: 新增 `AreaCodeRegionMap` 模型（`area_code_region_map` 表），在 `third_survey_topsoils` 和 `third_survey_profiles` 表新增交换性氢离子、交换性铝离子、全氮等 Model-4/5 必需字段

## Impact

- **Database Schema**: `third_survey_topsoils` 表需新增至少 4 列（交换性氢离子、交换性铝离子、交换性酸总量、水解性总酸度）；`third_survey_profiles` 表需同步新增；新增 `area_code_region_map` 表
- **Import Scripts**: `scripts/import_real_parcels.py` 需修改 `FIELD_MAP` 和 `build_soil_indicators` 函数，在 JSON 中包含 Model-4/5 所需全部字段
- **Calculation Logic**: `framework/domain/calculations/coefficients.py` 保留 `AREA_TO_REGION` 作为回退；新增 `region_mapping_service.py` 提供 `get_region_mapping()`；消费者代码需从 `AREA_TO_REGION.get()` 改为 `get_region_mapping()`
- **Model Agents**: Model-4 和 Model-5 的 `parcel_data_accessor` 查询逻辑验证修复后字段是否能正确加载
- **Data Source**: 需从 `F:\BaiduNetdiskDownload\耕地质量大模型\05_乐昌市土壤三普剖面理化和基本数据2022\` 和 `04_乐昌市土壤三普表层土点数据2022\` 重新读取 xlsx 数据
