## Why

项目现有 6 个耕地质量专题模型均为占位实现（MODEL_SPECS 仅含结构化描述，无真实算法），无法产出真实的耕地质量评价结果。本次整合三个已成熟的真实模型——耕地质量稳定性与退化风险识别模型（Python，九模块分析）、耕地质量等级与障碍度评价工具（Fortran，基于 GB/T 33469-2016）、耕地质量主要问题精准识别与酸化改良模型（Python，障碍诊断+酸化改良）——替换对应占位模型并扩展能力，使系统具备真实的耕地质量稳定性诊断、退化风险识别、质量等级评定、障碍因子诊断和酸化改良方案生成能力。

## What Changes

- **新增模型1 集成**：将耕地质量稳定性与退化风险识别模型（Python，依赖 geopandas/scipy/pandas/numpy）整合为项目 thematic model，支持 9 个分析模块（等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险、持续低质风险）
- **新增离线预计算 + 在线查询模式**：`run_all_models()` 作为离线预计算入口（处理 3 期 shapefile 数据并持久化 9 模块结果），`get_parcel_result()` 作为在线查询接口对接 `run_thematic_model()`
- **新增耕地质量等级与障碍度评价集成**：通过 subprocess 调用 `Farmland_quality_evaluation.exe`（生产环境为 Windows），将交互式命令行程序转为请求-响应模式，输入地块代码返回 12 指标隶属度、综合指数、质量等级(1-10)和障碍度因子排序
- **新增模型3 集成**：将耕地质量主要问题精准识别与酸化改良模型（Python，calculator.py + calculator2.py）整合为项目 thematic model，支持：
  - calculator.py：基于 CSV 的批量质量等级评价（隶属度计算、综合权重、质量等级划分）
  - calculator2.py：基于 calculator 输出的障碍诊断（障碍类型判定、主要/次要因素识别、障碍组合类型）
  - 酸化改良因子提取和改良方案生成
- **模型3 与模型1 整合**：模型3 的障碍诊断结果与模型1 的退化风险识别结果互补，共同构成综合诊断能力
- **替换占位 MODEL_SPECS**：用三个真实模型替换对应的占位模型定义，保留其他不相关占位模型不变
- **扩展 question_type 路由**：为三个新模型分配 question_type 并扩展 role-based-routing 的关键词路由
- **新增数据导入接口**：支持导入 shapefile（模型1 的 3 期历史数据）、CSV（模型3 的批量评价数据）和部署 .dat 加密数据库（耕地质量等级评价）
- **新增依赖**：geopandas、scipy（模型1 的空间统计与邻域分析依赖）

## Capabilities

### New Capabilities
- `farmland-stability-risk-model`: 耕地质量稳定性与退化风险识别模型能力——基于多期 shapefile 数据的九模块分析（等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险、持续低质风险），支持离线预计算和在线地块查询
- `farmland-grade-obstacle-evaluation`: 耕地质量等级与障碍度评价能力——通过 subprocess 调用 Fortran exe，基于 GB/T 33469-2016 标准对地块进行 12 指标隶属度计算、综合指数评定、质量等级划分(1-10等)和障碍度因子诊断
- `farmland-obstacle-diagnosis-model`: 耕地质量主要问题精准识别模型能力——基于 CSV 的批量障碍诊断（障碍因子识别、障碍程度分级、障碍组合判定），支持单一障碍/双重障碍/多重障碍类型识别和主要/次要障碍因素排序
- `farmland-acidification-improvement-model`: 耕地土壤酸化改良模型能力——酸化因子提取、酸化程度分区、改良方案生成（包括调理剂施用量、改良措施匹配）

### Modified Capabilities
- `callable-thematic-model-stubs`: 替换耕地质量稳定性风险、障碍因素识别和酸化治理相关的占位 MODEL_SPECS 为真实模型实现，扩展模型输出字段以支持 9 模块结果、等级障碍度输出和酸化改良方案
- `role-based-routing`: 新增 question_type 路由到三个新模型，扩展关键词匹配规则以覆盖稳定性风险、退化风险、质量等级、障碍度诊断、酸化改良等用户问题
- `professional-model-agents`: 新增三个模型对应的 specialized agent，实现 answer_question 接口对接模型1 的在线查询、Fortran exe 的 subprocess 调用和模型3 的批量诊断

## Impact

- **代码**：`src/ai_culti_demo/thematic_models.py`（替换占位 MODEL_SPECS）、`framework/core_engine/adapter.py`（扩展 run_thematic_model 调度）、`framework/agents/specialized/`（新增 3 个 agent）、`framework/domain/nodes.py`（扩展 question_type 关键词路由）
- **API**：现有 `/api/v1/chat/` 接口扩展，支持新模型的路由和响应；可能新增离线预计算触发接口和数据导入接口
- **依赖**：新增 geopandas、scipy（需更新 requirements.txt）；Fortran exe 及 .dat 数据库需部署到项目目录
- **数据**：导入模型1 的 3 期 shapefile 测试数据（2018/2021/2024）、模型3 的 CSV 测试数据和加密数据库 .dat 作为初始数据源
- **部署**：生产环境为 Windows，Fortran exe 可直接运行；需确保 geopandas 的 GDAL/PROJ 依赖在 Windows 环境可用
- **现有行为**：替换占位模型后，对应 question_type 的响应将从占位结构变为真实模型输出，响应字段结构将扩展
