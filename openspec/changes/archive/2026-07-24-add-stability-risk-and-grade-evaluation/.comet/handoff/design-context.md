# Comet Design Handoff

- Change: add-stability-risk-and-grade-evaluation
- Phase: design
- Mode: compact
- Context hash: 66588c218e3f173124cbd061d235b378f704541b3885ae057cbfd4cbe5fbfa95

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/add-stability-risk-and-grade-evaluation/proposal.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/proposal.md
- Lines: 1-40
- SHA256: 42011843416ff8f1290a85abacec4422daeef93285bab1b27eb63d14b5f1e795

```md
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

```

## openspec/changes/add-stability-risk-and-grade-evaluation/design.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/design.md
- Lines: 1-90
- SHA256: bc461d90977848186cab38a20fe51e6a916961ca4c260b27114b21621cfb0980

[TRUNCATED]

```md
## Context

项目现有耕地质量专题模型体系由 6 个占位 MODEL_SPECS 构成（定义于 `src/ai_culti_demo/thematic_models.py`），仅提供结构化描述而无真实算法实现。CoreEngine（`framework/core_engine/adapter.py`）通过 `run_thematic_model()` 统一调度，role-based-routing 按 question_type 1-4 将用户问题路由到不同 agent 组合。

本次整合三个已成熟的真实模型：
- **模型1（Python）**：耕地质量稳定性与退化风险识别模型，九模块分析，依赖 geopandas/scipy 处理多期 shapefile
- **耕地质量等级和障碍度（Fortran exe）**：基于 GB/T 33469-2016 的交互式评价工具，依赖加密数据库 .dat
- **模型3（Python）**：耕地质量主要问题精准识别与酸化改良模型（calculator.py + calculator2.py），基于 CSV 的批量评价和障碍诊断

生产环境为 Windows + waitress，Fortran exe 可直接运行。现有数据库为 SQLite（development.db / instance/production.db）。

## Goals / Non-Goals

**Goals:**
- 将模型1 整合为项目 thematic model，支持离线预计算（run_all_models）和在线地块查询（get_parcel_result）
- 将耕地质量等级和障碍度 exe 通过 subprocess 集成为请求-响应式模型服务
- 将模型3 整合为项目 thematic model，支持基于 CSV 的批量质量等级评价和障碍诊断
- 模型3 与模型1 整合：障碍诊断结果与退化风险识别结果互补，共同构成综合诊断能力
- 替换对应占位 MODEL_SPECS 为真实模型实现，扩展输出字段
- 扩展 question_type 路由，使三类新模型可通过 /api/v1/chat/ 接口访问
- 提供数据导入接口，支持 shapefile、CSV 和 .dat 数据库的部署与更新

**Non-Goals:**
- 不重新实现 Fortran exe 为 Python（生产环境是 Windows，可直接调用 exe）
- 不改变现有 role-based-routing 的三角色路由架构
- 不对接项目现有 SQLite 数据库作为模型数据源
- 不替换其他不相关占位模型（如 spatial-structure-analysis 等）
- 不在 design.md 阶段确定所有实现细节（具体替换映射、question_type 分配等留待 Design Doc 细化）

## Decisions

### 决策1：模型1 采用离线预计算 + 在线查询双模式

**选择**：`run_all_models()` 作为离线预计算入口，处理 3 期 shapefile 并将 9 模块结果持久化（GeoJSON/Parquet/SQLite）；`get_parcel_result()` 作为在线查询接口对接 `run_thematic_model()`，从持久化结果中按 parcel_id + module 查询。

**理由**：模型1 的 `run_all_models()` 需读取 3 期 shapefile（各约 20MB）并执行空间邻域分析（cKDTree）、历史趋势回归等计算密集操作，单次运行耗时较长，不适合每次 API 请求都执行。而 `get_parcel_result()` 仅从已计算的 GeoDataFrame 中筛选地块结果，响应快。

### 决策2：耕地质量等级和障碍度采用 subprocess 调用 exe

**选择**：通过 subprocess.Popen 启动 `Farmland_quality_evaluation.exe`，通过 stdin 写入地块代码，从 stdout 读取评价结果，解析后返回结构化 JSON。将交互式程序转为单次请求-响应模式。

**理由**：生产环境是 Windows，exe 可直接运行；subprocess 方式保留 Fortran 算法的准确性，无需重新实现隶属函数、等级划分等复杂逻辑。

### 决策3：模型3 与模型1 整合为综合诊断能力

**选择**：模型3 的 calculator.py（批量质量等级评价）和 calculator2.py（障碍诊断）独立集成，但障碍诊断结果与模型1 的退化风险识别结果在 agent 层进行整合。模型3 的障碍诊断侧重指标层面的障碍识别和组合判定，模型1 的退化风险侧重空间和时间维度的稳定性分析，两者互补。

**理由**：模型3 的障碍诊断基于单期数据的指标隶属度和障碍度计算，输出障碍类型（单一/多重）和因素排序；模型1 的退化风险基于多期数据的空间分析和趋势回归，输出稳定性和风险等级。两者结合可提供更全面的诊断结果。

### 决策4：模型3 采用批量 CSV 评价 + 在线诊断查询模式

**选择**：模型3 的 calculator.py 作为批量评价入口（处理 CSV 数据并输出隶属度、等级、障碍度），结果持久化后可通过在线查询接口按地块 ID 查询障碍诊断结果。

**理由**：模型3 的 calculator.py 设计为批量处理 CSV 文件，与模型1 的 shapefile 输入不同。将批量评价结果持久化后，可通过统一接口查询单地块诊断结果。

### 决策5：数据策略为模型自带数据 + 导入接口

**选择**：将模型1 的 3 期 shapefile（2018/2021/2024）、模型3 的 CSV 测试数据和 .dat 加密数据库部署到项目 data/ 目录作为初始数据源；同时设计数据导入接口支持后续数据更新。

**理由**：模型1 的算法依赖特定的 shapefile 字段结构，模型3 的算法依赖特定的 CSV 字段结构，项目现有 SQLite 数据库无此数据；.dat 数据库经过异或加密，直接使用原文件最可靠。

## Risks / Trade-offs

- **[geopandas Windows 依赖复杂] → Mitigation**：geopandas 依赖 GDAL/PROJ/GEOS，Windows 安装可能困难。使用 conda 或预编译 wheel 安装；在 requirements.txt 中明确版本；提供安装文档。
- **[Fortran exe 进程启动开销] → Mitigation**：每次请求启动 exe 约 1-2 秒（含数据库解密）。对于实时性要求高的场景，后续可考虑长驻进程池优化；当前先保证正确性。
- **[.dat 加密数据库密钥内嵌] → Mitigation**：密钥 "YouYCKEY" 内嵌在 exe 中，数据库文件不可单独解密。保持 exe 和 .dat 配套使用，不尝试单独解密。
- **[shapefile/CSV 数据量大] → Mitigation**：3 期 shapefile 各约 20MB，模型3 的 CSV 测试数据约 7MB，预计算结果可能更大。预计算结果持久化为压缩格式；离线预计算在非高峰时段执行。
- **[占位模型替换的兼容性] → Mitigation**：替换占位 MODEL_SPECS 后，对应 question_type 的响应字段结构会变化。在 design 阶段明确字段映射；保留 fallback 机制处理数据缺失情况。
- **[subprocess 异常处理] → Mitigation**：exe 崩溃、超时、数据库缺失等异常需妥善处理。设置 subprocess 超时；捕获异常返回明确错误信息；不阻塞主服务。

## Migration Plan

1. **依赖安装**：在开发环境安装 geopandas、scipy 及其 Windows 依赖；更新 requirements.txt
2. **数据部署**：将模型1 的 3 期 shapefile 复制到 `data/farmland_stability/`；将模型3 的 CSV 复制到 `data/farmland_diagnosis/`；将 exe 和 .dat 复制到项目指定目录
3. **模型1 集成**：将九模块代码整合为项目模块；实现离线预计算脚本；实现在线查询接口对接 run_thematic_model()
4. **exe 集成**：实现 subprocess 调用包装器；解析 exe 输出为结构化 JSON；对接 run_thematic_model()
5. **模型3 集成**：将 calculator.py 和 calculator2.py 整合为项目模块；实现批量评价入口；实现在线障碍诊断查询接口；对接 run_thematic_model()
6. **路由扩展**：在 nodes.py 中扩展 question_type 关键词路由；在 agent 层实现 answer_question 对接
7. **测试验证**：单元测试覆盖三个模型；集成测试覆盖 /api/v1/chat/ 端到端
8. **回滚策略**：保留占位 MODEL_SPECS 的 git 历史；若新模型集成失败，可通过 git revert 回退到占位模型

```

Full source: openspec/changes/add-stability-risk-and-grade-evaluation/design.md

## openspec/changes/add-stability-risk-and-grade-evaluation/tasks.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/tasks.md
- Lines: 1-96
- SHA256: 9efcb25295c914b9f49c81f029d3bb322c4fb4302f08356f8f60531321209c38

[TRUNCATED]

```md
## 1. 环境与依赖准备

- [ ] 1.1 在 requirements.txt 中新增 geopandas、scipy 依赖（明确兼容版本）
- [ ] 1.2 在开发环境安装 geopandas 及其 Windows 依赖（GDAL/PROJ/GEOS），验证 `import geopandas` 成功
- [ ] 1.3 编写 geopandas Windows 安装说明文档（记录 conda/wheel 安装方式）

## 2. 数据部署

- [ ] 2.1 创建数据目录 `data/farmland_stability/`，将模型1 的 3 期 shapefile（2018/2021/2024 测试数据）复制到该目录
- [ ] 2.2 创建数据目录 `data/farmland_diagnosis/`，将模型3 的 CSV 测试数据（test.csv、test_with_LD.csv、test_with_LD_diagnosis.csv）复制到该目录
- [ ] 2.3 创建 exe 部署目录（如 `bin/farmland_quality_eval/`），将 `Farmland_quality_evaluation.exe` 和 `Farmlands_Quality_Level_Database.dat` 复制到该目录
- [ ] 2.4 在 `.gitignore` 中排除 shapefile 数据、CSV 数据和 exe/.dat 二进制文件（避免大文件入库）
- [ ] 2.5 编写数据部署说明文档（记录文件位置和目录结构）

## 3. 模型1（耕地质量稳定性与退化风险）集成

- [ ] 3.1 将模型1 核心代码（`代码03_耕地质量稳定性与退化风险_九模块总流程.py`）整合为项目模块（如 `src/ai_culti_demo/farmland_stability/model.py`），移除硬编码路径，改为项目相对路径
- [ ] 3.2 实现离线预计算入口（CLI 命令或脚本），调用 `run_all_models()` 处理 `data/farmland_stability/` 下的 3 期 shapefile，将结果持久化（GeoJSON/Parquet/SQLite 格式）
- [ ] 3.3 实现在线查询接口，调用 `get_parcel_result()` 从持久化结果中按 parcel_id + module 查询，对接 `run_thematic_model()` 的统一调用契约
- [ ] 3.4 实现预计算结果未就绪时的 `status: "not_ready"` 响应逻辑
- [ ] 3.5 实现地块 ID 不存在时的 `status: "not_found"` 错误响应
- [ ] 3.6 实现 12 指标 LSD/QZ + ZHQZ + GDZLDJ 必需字段的校验逻辑
- [ ] 3.7 在 `thematic_models.py` 的 MODEL_SPECS 中注册模型1（替换对应占位模型或新增 model_id），包含九模块输出字段说明和中文名称映射

## 4. 耕地质量等级和障碍度（Fortran exe）集成

- [ ] 4.1 实现 exe 调用包装器（如 `src/ai_culti_demo/farmland_grade_eval/runner.py`），通过 subprocess.Popen 启动 exe，stdin 发送地块代码 + "quit"，从 stdout 捕获输出
- [ ] 4.2 实现 exe 输出解析器，将文本输出解析为结构化 JSON（地块信息、12 指标原始值/隶属度、综合指数、质量等级、障碍度排序）
- [ ] 4.3 处理 GBK/UTF-8 编码差异，确保中文字段不乱码
- [ ] 4.4 实现 subprocess 超时控制（终止进程并返回 `status: "timeout"`）
- [ ] 4.5 实现 exe 文件缺失和 .dat 数据库缺失的错误处理（返回明确错误信息）
- [ ] 4.6 实现地块代码无效（exe 返回"未找到"）的错误处理
- [ ] 4.7 实现系统启动时的 exe/.dat 部署校验逻辑
- [ ] 4.8 将 exe 评价能力对接 `run_thematic_model()` 统一调用契约，在 MODEL_SPECS 中注册（替换 obstacle-factor-identification 或新增 model_id）

## 5. 模型3（耕地质量主要问题精准识别与酸化改良）集成

- [ ] 5.1 将模型3 的 calculator.py 和 calculator2.py 整合为项目模块（如 `src/ai_culti_demo/farmland_diagnosis/`），移除硬编码路径，改为项目相对路径
- [ ] 5.2 将 mappings_config.py 配置整合为项目配置文件（如 `config/farmland_diagnosis_config.py`），支持区域映射、隶属度系数、权重的配置管理
- [ ] 5.3 实现批量评价入口（CLI 命令或脚本），调用 calculator.py 处理 `data/farmland_diagnosis/test.csv`，计算隶属度、综合权重和质量等级，输出 `test_with_LD.csv`
- [ ] 5.4 实现批量障碍诊断入口，调用 calculator2.py 处理 calculator.py 的输出，识别障碍类型、主要/次要因素，输出完整诊断结果
- [ ] 5.5 实现酸化因子提取和酸化程度分区逻辑（从 calculator.py 的 pH 隶属度和障碍度结果中提取）
- [ ] 5.6 实现改良方案生成逻辑（基于酸化程度分区结果生成调理剂施用量建议和改良措施）
- [ ] 5.7 实现在线障碍诊断查询接口，从批量评价和诊断结果中按地块 ID 查询，对接 `run_thematic_model()` 的统一调用契约
- [ ] 5.8 实现在线酸化改良查询接口，从批量评价和诊断结果中按地块 ID 查询酸化程度和改良方案，对接 `run_thematic_model()` 的统一调用契约
- [ ] 5.9 在 MODEL_SPECS 中注册模型3 的两个能力（障碍诊断和酸化改良），包含输出字段说明和中文名称映射

## 6. 模型3 与模型1 整合

- [ ] 6.1 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合逻辑
- [ ] 6.2 实现综合诊断接口，同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果
- [ ] 6.3 设计综合诊断结果的输出格式，包含稳定性评价、退化风险、障碍类型、障碍因素等综合信息

## 7. 占位模型替换与路由扩展

- [ ] 7.1 确定具体替换映射：模型1/模型3 替换哪个占位 MODEL_SPECS
- [ ] 7.2 确定新模型的 question_type 分配（新增 5-6-7 或复用现有），更新 `framework/domain/nodes.py` 的 QUESTION_TYPE 关键词映射
- [ ] 7.3 在 `nodes.py` 中新增稳定性风险关键词路由到模型1
- [ ] 7.4 在 `nodes.py` 中新增质量等级/障碍度关键词路由到耕地质量等级评价模型
- [ ] 7.5 在 `nodes.py` 中新增障碍诊断/障碍组合关键词路由到模型3 的障碍诊断能力
- [ ] 7.6 在 `nodes.py` 中新增酸化程度/改良方案关键词路由到模型3 的酸化改良能力
- [ ] 7.7 更新被替换占位模型的 MODEL_SPECS 定义，将 `reliability` 从 `demo_stub` 改为 `real_model`，扩展输出字段
- [ ] 7.8 实现缺少地块代码时的提示逻辑（质量等级/障碍度/酸化改良查询需要地块代码）

## 8. Agent 实现

- [ ] 8.1 修改 `StabilityRiskAgent`（对应模型1），将 answer_question 从模拟数据改为调用模型1 在线查询接口（get_parcel_result）
- [ ] 8.2 新增 `FarmlandGradeObstacleAgent`，实现 answer_question 通过 subprocess 调用 exe
- [ ] 8.3 新增 `ObstacleDiagnosisAgent`，实现 answer_question 调用模型3 的在线障碍诊断查询接口
- [ ] 8.4 新增 `AcidificationImprovementAgent`，实现 answer_question 调用模型3 的在线酸化改良查询接口
- [ ] 8.5 在 `framework/agents/manager.py` 中注册新 agent（FarmlandGradeObstacleAgent、ObstacleDiagnosisAgent、AcidificationImprovementAgent）和更新 StabilityRiskAgent 的路由

## 9. API 与端到端集成

- [ ] 9.1 验证 `/api/v1/chat/` 接口能正确路由稳定性风险问题到 StabilityRiskAgent 并返回模型1 真实结果
- [ ] 9.2 验证 `/api/v1/chat/` 接口能正确路由质量等级/障碍度问题到 FarmlandGradeObstacleAgent 并返回 exe 评价结果
- [ ] 9.3 验证 `/api/v1/chat/` 接口能正确路由障碍诊断问题到 ObstacleDiagnosisAgent 并返回模型3 诊断结果
- [ ] 9.4 验证 `/api/v1/chat/` 接口能正确路由酸化改良问题到 AcidificationImprovementAgent 并返回模型3 改良方案
- [ ] 9.5 验证综合诊断接口能同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，返回整合结果
- [ ] 9.6 实现数据导入接口（如需），支持上传新 shapefile/CSV 并触发重新预计算/评价

```

Full source: openspec/changes/add-stability-risk-and-grade-evaluation/tasks.md

## openspec/changes/add-stability-risk-and-grade-evaluation/specs/farmland-acidification-improvement-model/spec.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/specs/farmland-acidification-improvement-model/spec.md
- Lines: 1-48
- SHA256: c1c735ec7ae01987d921cbd91ce6772fcd8d3530e95765aca3372888f1feb223

```md
## ADDED Requirements

### Requirement: 模型3 酸化因子提取
系统 SHALL 从地块指标数据中提取酸化相关因子（pH 值、酸化方向），为后续酸化程度判定和改良方案生成提供基础数据。

#### Scenario: 提取酸化因子
- **WHEN** 系统处理地块数据（CSV 或在线查询），且包含 pH 字段
- **THEN** 系统 SHALL 提取 pH 值，并根据阈值（<6.5 为酸化，>7.5 为碱化）判定酸化方向

### Requirement: 模型3 酸化程度分区
系统 SHALL 根据酸化因子和障碍诊断结果，对地块进行酸化程度分区（无明显酸化、轻度酸化、中度酸化、重度酸化）。

#### Scenario: 酸化程度判定
- **WHEN** 系统完成酸化因子提取和障碍诊断，且 pH 隶属度和障碍度数据已就绪
- **THEN** 系统 SHALL 根据 pH 隶属度和障碍度阈值，将地块划分为无明显酸化、轻度酸化、中度酸化或重度酸化

#### Scenario: 酸化分区统计
- **WHEN** 调用方请求某区域的酸化分区统计
- **THEN** 系统 SHALL 返回该区域各酸化程度分区的地块数量或面积占比

### Requirement: 模型3 改良方案生成
系统 SHALL 基于酸化程度分区结果，生成针对性的改良方案，包括调理剂施用量建议和改良措施匹配。

#### Scenario: 生成改良方案
- **WHEN** 用户请求某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 系统 SHALL 根据酸化程度和土壤特性，生成调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户请求某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 系统 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 酸化改良在线查询
系统 SHALL 提供在线查询接口，按地块 ID 查询酸化程度分区和改良方案，对接 `run_thematic_model()` 的统一调用契约。

#### Scenario: 查询指定地块的酸化改良方案
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的酸化程度、酸化方向、调理剂施用量建议和改良措施

#### Scenario: 数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

### Requirement: 模型3 改良方案输出格式
系统 SHALL 以标准化格式输出改良方案，包含酸化程度、调理剂施用量、改良措施和预期效果。

#### Scenario: 标准化改良方案输出
- **WHEN** 系统生成改良方案
- **THEN** 输出 SHALL 包含：酸化程度（轻/中/重度）、调理剂类型、施用量（kg/亩）、改良措施描述、预期效果（pH 提升幅度、有机质提升预期）

```

## openspec/changes/add-stability-risk-and-grade-evaluation/specs/farmland-obstacle-diagnosis-model/spec.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/specs/farmland-obstacle-diagnosis-model/spec.md
- Lines: 1-64
- SHA256: 7b039e5d8b1a266b285057a86617a7e9fc78c48f7d14de3c7f6fae90405696a4

```md
## ADDED Requirements

### Requirement: 模型3 批量质量等级评价
系统 SHALL 提供基于 CSV 的批量质量等级评价入口，对包含 12 项指标（pH、有机质、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、耕层厚度）和区域信息（一级/二级农业区）的 CSV 数据执行隶属度计算、综合权重计算和质量等级划分(1-10等)。

#### Scenario: 执行批量评价
- **WHEN** 管理员触发批量评价，且 CSV 文件已部署到指定目录，包含必需字段（一级农业区、二级农业区、pH、有机质、有效磷、速效钾、容重、耕层质地、灌溉能力、排水能力、地形部位、质地构型、有效土层、耕层厚度）
- **THEN** 系统 SHALL 调用 calculator.py 处理 CSV，计算各指标隶属度、综合权重，并按区域配置的阈值划分质量等级，输出包含 `*_LD`（隶属度）、`composite_weight`（综合权重）、`grade`（质量等级）的结果

#### Scenario: CSV 字段缺失
- **WHEN** 批量评价被触发，但 CSV 文件缺少必需字段（如一级农业区、pH、有机质等）
- **THEN** 系统 SHALL 返回明确的错误信息，列出缺失的字段，不执行部分计算

#### Scenario: 区域名称无效
- **WHEN** CSV 中存在未在 REGION_MAP 或 SECONDARY_REGION_MAP 中定义的区域名称
- **THEN** 系统 SHALL 返回错误信息，列出无效区域名称所在的行号

### Requirement: 模型3 障碍诊断
系统 SHALL 基于 calculator.py 的输出（包含隶属度、综合权重、质量等级）执行障碍诊断，识别障碍类型（单一障碍/多障碍）、主要障碍因素和次要障碍因素。

#### Scenario: 执行障碍诊断
- **WHEN** calculator.py 的输出 CSV 已就绪，且包含所有指标隶属度和障碍度字段
- **THEN** 系统 SHALL 调用 calculator2.py，对每行数据进行障碍诊断，输出障碍类型、主要因素描述、次要因素描述

#### Scenario: 无明显障碍
- **WHEN** 某地块所有指标的障碍度均低于阈值（主要障碍度 < 20%，次要障碍度 < 10%）
- **THEN** 系统 SHALL 返回障碍类型为"无明显障碍"，主要/次要因素描述为空

#### Scenario: 单一障碍
- **WHEN** 某地块只有一个指标的障碍度达到主要障碍阈值（>= 20%），且没有其他中度以上障碍
- **THEN** 系统 SHALL 返回障碍类型为"单一障碍"，仅列出该指标为主要因素

#### Scenario: 多障碍
- **WHEN** 某地块有多个指标的障碍度达到主要或次要障碍阈值
- **THEN** 系统 SHALL 返回障碍类型为"多障碍"，按障碍度降序列出主要和次要因素

### Requirement: 模型3 障碍组合类型识别
系统 SHALL 识别障碍组合类型，支持单一障碍、双重障碍和多因素叠加障碍等组合类型的判定。

#### Scenario: 识别障碍组合类型
- **WHEN** 系统完成障碍诊断后，识别到多个中度以上障碍因素
- **THEN** 系统 SHALL 返回障碍组合类型描述（如"酸化+有机质不足"、"养分失衡+耕层条件偏弱"）

### Requirement: 模型3 在线障碍诊断查询
系统 SHALL 提供在线查询接口，按地块 ID 从批量评价和障碍诊断结果中查询障碍诊断信息，对接 `run_thematic_model()` 的统一调用契约。

#### Scenario: 查询指定地块的障碍诊断结果
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的障碍类型、主要障碍因素、次要障碍因素和障碍度排序

#### Scenario: 诊断数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成或结果文件缺失
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

### Requirement: 模型3 数据导入接口
系统 SHALL 提供数据导入接口，支持上传新的 CSV 数据并触发重新评价和诊断。

#### Scenario: 导入新 CSV 数据
- **WHEN** 用户通过导入接口上传 CSV 文件
- **THEN** 系统 SHALL 将文件部署到数据目录，并提示用户触发批量评价以更新诊断结果

#### Scenario: 导入数据格式校验
- **WHEN** 用户上传的 CSV 缺少必需字段（如一级农业区、二级农业区、12 项指标）
- **THEN** 系统 SHALL 拒绝导入并返回缺失字段列表

```

## openspec/changes/add-stability-risk-and-grade-evaluation/specs/professional-model-agents/spec.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/specs/professional-model-agents/spec.md
- Lines: 1-74
- SHA256: 066818dd9e5c175217ebb202d35b24ae792235ae50d743d21812750228465f03

```md
## MODIFIED Requirements

### Requirement: StabilityRiskAgent 智能体
系统 SHALL 实现 `StabilityRiskAgent` 智能体，对应模型1「耕地质量等级稳定性与退化风险识别模型」，通过调用模型1 的在线查询接口（`get_parcel_result`）获取预计算结果，返回基于真实九模块分析的稳定性评价和退化风险识别，不再使用模拟数据。

#### Scenario: 等级稳定性评价
- **WHEN** 用户询问"全省耕地质量整体稳定吗？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取历史变化趋势模块（module=5）结果，返回基于真实数据的稳定性评价，包括持续改善/基本稳定/波动退化/持续退化的分类统计

#### Scenario: 退化风险识别
- **WHEN** 用户询问"哪些县区高等级耕地存在退化风险？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取掉级风险（module=6）和关键因子退化风险（module=7）模块结果，返回真实的退化风险分布和关键退化因子

#### Scenario: 重点关注清单
- **WHEN** 用户询问"哪些对象需要纳入重点关注清单？"，且模型1 预计算结果已就绪
- **THEN** 智能体 SHALL 调用模型1 在线查询接口获取持续低质风险（module=9）模块结果，输出需要关注的地块清单、低质年份数和风险类型

#### Scenario: 预计算数据未就绪
- **WHEN** 用户询问稳定性或退化风险相关问题，但模型1 离线预计算结果未就绪
- **THEN** 智能体 SHALL 返回"模型1 数据未就绪，请先执行离线预计算"的提示，`confidence` 字段降低，不返回模拟数据冒充真实结果

## ADDED Requirements

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应耕地质量等级和障碍度评价模型（Fortran exe），通过 subprocess 调用 `Farmland_quality_evaluation.exe` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回质量等级（1-10等）、综合指数和 12 项指标的隶属度

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 通过 subprocess 调用 exe，返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: exe 调用失败
- **WHEN** exe 调用失败（超时、数据库缺失、exe 未部署、地块代码无效）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"评价服务超时"、"数据库文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

### Requirement: ObstacleDiagnosisAgent 智能体
系统 SHALL 实现 `ObstacleDiagnosisAgent` 智能体，对应模型3「耕地质量主要问题精准识别模型」，通过调用模型3 的在线查询接口获取障碍诊断结果，返回真实的障碍类型、主要/次要障碍因素和障碍组合类型。

#### Scenario: 障碍诊断查询
- **WHEN** 用户询问某地块的障碍诊断结果，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 调用模型3 在线查询接口，返回障碍类型（单一障碍/多障碍）、主要障碍因素、次要障碍因素和障碍度排序

#### Scenario: 障碍组合类型识别
- **WHEN** 用户询问某地块的障碍组合类型，且该地块存在多个中度以上障碍因素
- **THEN** 智能体 SHALL 返回障碍组合类型描述（如"酸化+有机质不足"、"养分失衡+耕层条件偏弱"）

#### Scenario: 诊断数据未就绪
- **WHEN** 用户询问障碍诊断相关问题，但模型3 批量评价和诊断结果未就绪
- **THEN** 智能体 SHALL 返回"模型3 数据未就绪，请先执行批量评价"的提示，不返回模拟数据

### Requirement: AcidificationImprovementAgent 智能体
系统 SHALL 实现 `AcidificationImprovementAgent` 智能体，对应模型3「耕地土壤酸化改良模型」，通过调用模型3 的在线查询接口获取酸化程度分区和改良方案，返回真实的酸化程度、调理剂施用量建议和改良措施。

#### Scenario: 酸化程度查询
- **WHEN** 用户询问某地块的酸化程度，且模型3 批量评价和诊断结果已就绪
- **THEN** 智能体 SHALL 返回酸化程度（无明显酸化/轻度/中度/重度）、酸化方向（酸化/碱化）和 pH 值

#### Scenario: 改良方案查询
- **WHEN** 用户询问某地块的酸化改良方案，且该地块被判定为中度或重度酸化
- **THEN** 智能体 SHALL 返回调理剂施用量建议（如石灰施用量 kg/亩）和改良措施（如施肥方式、轮作制度调整）

#### Scenario: 轻度或无酸化
- **WHEN** 用户询问某地块的酸化改良方案，但该地块为轻度酸化或无明显酸化
- **THEN** 智能体 SHALL 返回"无需特殊改良"的提示，建议常规监测和维护

### Requirement: 模型3 与模型1 整合诊断
系统 SHALL 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合，当用户请求综合诊断时，同时调用两个模型并整合结果。

#### Scenario: 综合诊断查询
- **WHEN** 用户询问某地块的综合诊断结果（同时涉及稳定性和障碍诊断），且两个模型的数据均已就绪
- **THEN** 系统 SHALL 同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果，返回综合诊断报告

```

## openspec/changes/add-stability-risk-and-grade-evaluation/specs/role-based-routing/spec.md

- Source: openspec/changes/add-stability-risk-and-grade-evaluation/specs/role-based-routing/spec.md
- Lines: 1-52
- SHA256: 5fe566d273829d620bec065870ad31328d80e0c4cf8bd7bc99e7a9754e4453f7

```md
## ADDED Requirements

### Requirement: 耕地质量稳定性风险模型路由
系统 SHALL 为耕地质量稳定性与退化风险识别模型分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问稳定性与退化风险相关问题并路由到对应智能体。

#### Scenario: 稳定性问题路由
- **WHEN** 用户问题包含"稳定性"、"稳定吗"、"质量稳定"等关键词
- **THEN** 系统 SHALL 识别为稳定性问题，路由到 StabilityRiskAgent，调用模型1 的历史变化趋势模块查询

#### Scenario: 退化风险问题路由
- **WHEN** 用户问题包含"退化风险"、"持续退化"、"掉级风险"、"退化趋势"等关键词
- **THEN** 系统 SHALL 识别为退化风险问题，路由到 StabilityRiskAgent，调用模型1 的掉级风险或关键因子退化风险模块查询

### Requirement: 耕地质量等级与障碍度评价路由
系统 SHALL 为耕地质量等级与障碍度评价模型分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问质量等级和障碍度相关问题并路由到对应智能体。

#### Scenario: 质量等级问题路由
- **WHEN** 用户问题包含"质量等级"、"几等"、"等级评价"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为质量等级问题，路由到 FarmlandGradeObstacleAgent，通过 subprocess 调用 exe 获取等级结果

#### Scenario: 障碍度诊断问题路由
- **WHEN** 用户问题包含"障碍度"、"障碍因子"、"主要障碍"、"限制因素"等关键词，且包含地块代码
- **THEN** 系统 SHALL 识别为障碍度诊断问题，路由到 FarmlandGradeObstacleAgent，通过 subprocess 调用 exe 获取障碍度排序

### Requirement: 模型3 障碍诊断路由
系统 SHALL 为模型3「耕地质量主要问题精准识别模型」分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问障碍诊断相关问题并路由到对应智能体。

#### Scenario: 障碍诊断问题路由
- **WHEN** 用户问题包含"障碍诊断"、"障碍因素"、"障碍类型"、"精准识别"等关键词
- **THEN** 系统 SHALL 识别为障碍诊断问题，路由到 ObstacleDiagnosisAgent，调用模型3 的在线查询接口获取诊断结果

#### Scenario: 障碍组合问题路由
- **WHEN** 用户问题包含"障碍组合"、"多重障碍"、"障碍叠加"等关键词
- **THEN** 系统 SHALL 识别为障碍组合问题，路由到 ObstacleDiagnosisAgent，调用模型3 的在线查询接口获取障碍组合类型

### Requirement: 模型3 酸化改良路由
系统 SHALL 为模型3「耕地土壤酸化改良模型」分配 question_type，并扩展关键词路由规则，使用户可通过 `/api/v1/chat/` 接口提问酸化改良相关问题并路由到对应智能体。

#### Scenario: 酸化程度问题路由
- **WHEN** 用户问题包含"酸化程度"、"酸化分区"、"酸化评价"等关键词
- **THEN** 系统 SHALL 识别为酸化程度问题，路由到 AcidificationImprovementAgent，调用模型3 的在线查询接口获取酸化程度结果

#### Scenario: 改良方案问题路由
- **WHEN** 用户问题包含"改良方案"、"调理剂"、"酸化治理"、"改良措施"等关键词
- **THEN** 系统 SHALL 识别为改良方案问题，路由到 AcidificationImprovementAgent，调用模型3 的在线查询接口获取改良方案

### Requirement: 缺少地块代码时的提示
系统 SHALL 在用户问题包含质量等级、障碍度或酸化改良关键词但未提供地块代码时，返回提示信息要求用户提供地块统一代码。

#### Scenario: 缺少地块代码提示
- **WHEN** 用户问题包含质量等级、障碍度或酸化改良关键词，但未提供地块代码
- **THEN** 系统 SHALL 返回提示信息，要求用户提供地块统一代码以进行评价查询

```
