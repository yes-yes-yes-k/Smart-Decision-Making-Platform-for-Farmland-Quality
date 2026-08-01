# Comet Design Handoff

- Change: replace-grade-eval-with-python-model
- Phase: design
- Mode: compact
- Context hash: 5aabfcd2b9d522b49c62b4f9bbbf97ba539f7f646374a54c765eec73c8a23732

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/replace-grade-eval-with-python-model/proposal.md

- Source: openspec/changes/replace-grade-eval-with-python-model/proposal.md
- Lines: 1-36
- SHA256: 68ccc228808cc824879f7bac8b0a0d54bffe218d2f09e4e985d9e84865151d6c

```md
## Why

model-7（耕地质量等级评价）当前依赖 Fortran exe + 二进制 `.dat` 文件，通过 `subprocess.Popen` 调用，存在部署复杂（需手动复制二进制文件且被 `.gitignore` 排除）、跨平台兼容性差（exe 仅限 Windows）、不可调试、无法版本管理等痛点。模型作者已提供完整 Python 实现（model2 源码，仅依赖标准库），可消除对 Fortran 二进制的依赖，并额外提供单地块潜力分析、县域统计与潜力情景分析等能力。

## What Changes

- 将 `farmland_grade_eval` 模块从 subprocess+exe 实现重写为纯 Python 实现（移植 model2 源码）
- 新增核心评价模块：`evaluation.py`（隶属函数 + 综合指数 + 等级评定）、`obstacle.py`（障碍度因子计算）、`config.py`（评价参数配置）、`data_loader.py`（CSV 加载器）、`models.py`（数据类）
- 新增潜力分析模块：`potential.py`（单地块潜力分析，模拟各指标改良后的潜在质量指数与等级提升）
- 新增县域统计模块：`statistics.py`（县域常规统计）+ `potential.py`（县域理想/最佳潜力情景批量计算）
- 新增调理剂计算模块：`conditioner.py`（作为库函数移植，**不接入 API**，调理剂 API 需求仍由 model-4 酸化模型处理，避免重叠）
- 数据源从二进制 `.dat` 改为 CSV（`Farmland_quality_Level_Database.csv`，含 20 字段、1193 地块）
- **BREAKING**：HTTP `/api/v1/data/import` 的 `data_type=dat` 改为接受 CSV 文件，部署为 `Farmland_quality_Level_Database.csv`
- 废弃 exe 和 .dat 依赖（`bin/farmland_quality_eval/` 下删除 `Farmland_quality_evaluation.exe` 和 `Farmlands_Quality_Level_Database.dat`，保留 CSV）
- `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 签名保持向后兼容，`dat_path` 语义改为 csv_path（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`），`exe_path` 忽略
- `check_deployment()` 改为校验 CSV 存在且可读
- 新增 `MODEL_VERSION = "python_v1_20260801"` 版本标识
- 新增独立函数暴露潜力分析与县域统计能力（`run_potential_analysis`、`run_county_statistics`，设计阶段细化签名）

## Capabilities

### New Capabilities
- `farmland-quality-grade-evaluation`: 耕地质量等级评价 Python 模型，覆盖核心评价（质量指数+等级+障碍度）、单地块潜力分析、县域统计与潜力情景分析、调理剂库函数

### Modified Capabilities
- `professional-model-agents`: `FarmlandGradeObstacleAgent` 智能体从 subprocess 调用 exe 改为 Python 直接调用，去除 Fortran 依赖
- `thematic-data-import`: `.dat` 部署触发 `FarmlandGradeRunner.check_deployment()` 改为 CSV 部署触发

## Impact

- **代码**：`src/ai_culti_demo/farmland_grade_eval/`（runner.py 重写 + 新增 8 个模块）、`framework/agents/specialized/grade_agent.py`（字段适配）、`src/ai_culti_demo/thematic_models.py`（字段适配）、`framework/core_engine/adapter.py`（部署校验改 CSV）、`framework/upload/data_trigger.py`（data/import 改 CSV）
- **数据**：`bin/farmland_quality_eval/` 新增 `Farmland_quality_Level_Database.csv`，删除 exe/.dat；`.gitignore` 调整（CSV 入库，exe/.dat 仍排除）
- **API**：`/api/v1/data/import` 的 `data_type=dat` → CSV；`openapi.json`、`api.md`、`README.md` 同步更新
- **依赖**：无新增第三方依赖（model2 仅用 Python 标准库 `csv`/`math`/`typing`/`dataclasses`）
- **测试**：`tests/test_farmland_grade_eval.py` 重写（`parse_output` 文本解析测试 → Python 评价逻辑测试 + 与 exe 历史输出的回归对比）
- **文档**：`bin/farmland_quality_eval/README.md` 更新部署说明

```

## openspec/changes/replace-grade-eval-with-python-model/design.md

- Source: openspec/changes/replace-grade-eval-with-python-model/design.md
- Lines: 1-123
- SHA256: e0d78afde035173e77348225d49260018cca14b4fbd174b0ed61995893e91a3b

[TRUNCATED]

```md
## Context

model-7（耕地质量等级评价）当前架构为 `FarmlandGradeRunner` 通过 `subprocess.Popen` 调用 `bin/farmland_quality_eval/Farmland_quality_evaluation.exe`（Fortran 编译，~911KB），读取同目录二进制 `Farmlands_Quality_Level_Database.dat`（~199KB，1193 地块），以 GBK 编码通信，解析文本输出为结构化 dict。

调用方有三处：
- `framework/agents/specialized/grade_agent.py`（`FarmlandGradeAgent`）
- `src/ai_culti_demo/thematic_models.py`（`_run_real_grade_model`）
- `framework/core_engine/adapter.py`（`check_grade_eval_deployment`）

模型作者提供完整 Python 实现（model2 源码），仅依赖标准库（`csv`/`math`/`typing`/`dataclasses`），含核心评价、潜力分析、县域统计、调理剂计算等模块。本次将 model2 移植为项目内 Python 模块，彻底去除 exe/.dat 依赖。

## Goals / Non-Goals

**Goals:**
- 用纯 Python 实现完全替换 Fortran exe + .dat 二进制依赖
- 移植 model2 完整系统（核心评价 + 潜力分析 + 县域统计 + 调理剂库函数）
- 保持 `run_grade_evaluation` 签名向后兼容，三处调用方零改动
- 核心评价输出与 exe 历史输出数值等价（浮点容差 < 0.01）
- HTTP `/api/v1/data/import` 从 .dat 改为 CSV

**Non-Goals:**
- 不修改 model-3/4/5/6（其他专题模型）
- 不改变 HTTP API 端点结构（仅 data/import 文件类型变更）
- 不将 conditioner 接入 API（调理剂 API 仍由 model-4 处理）
- 不移植 model2 的 `main.py`/`reports.py`（交互式 CLI 与文本报告不在 API 范围）
- 不修改前端

## Decisions

### D1: 模块结构 — 移植 model2 模块到 farmland_grade_eval 包

将 model2 的 8 个核心模块移植到 `src/ai_culti_demo/farmland_grade_eval/`，保持模块划分：
- `models.py`（数据类：Parcel, QualityResult, ObstacleItem, PotentialItem, CountyStats, CountyPotentialResult）
- `config.py`（EvaluationConfig：隶属函数参数、权重、等级阈值、名称字典）
- `data_loader.py`（load_parcels_from_csv：CSV → List[Parcel]）
- `evaluation.py`（membership_numeric + evaluate_land_quality）
- `obstacle.py`（calc_limiting_factors + compute_obstacle_factors）
- `potential.py`（compute_single_parcel_potential + county_potential_statistics_data）
- `statistics.py`（county_statistics_data）
- `conditioner.py`（calculate_soil_conditioner，库函数，不接 API）

`runner.py` 重写为 Python 调用层：加载数据 → 查找地块 → 调用 evaluate_land_quality + compute_obstacle_factors → 组装为与 exe 时代一致的输出 dict。

**备选方案**：将 model2 作为独立子目录（如 `farmland_grade_eval/model2/`）整体复制。**未采用**，因为 model2 模块间用绝对导入（`from config import ...`），需改为包内相对导入，分散在包根目录更自然。

### D2: API 向后兼容 — 保持签名，dat_path 语义改为 csv_path

`run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 签名不变：
- `dat_path` 重新解释为 CSV 路径（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`）
- `exe_path` 忽略（保留参数避免调用方报错）
- 三处调用方（grade_agent、thematic_models、adapter）零改动

`FarmlandGradeRunner.__init__(self, exe_path=None, dat_path=None, timeout=30)` 同理：`dat_path` → csv_path 语义，`timeout` 保留但不再用于 subprocess（Python 计算无需超时，保留字段向后兼容）。

**备选方案**：新增 `csv_path` 参数。**未采用**，因为会增加调用方迁移成本，且现有 `dat_path` 参数语义自然过渡。

### D3: 数据源 — CSV 替代 .dat

- 数据文件：`bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（97KB，1193 地块，20 字段，UTF-8-sig 编码）
- CSV 入库（不再被 `.gitignore` 排除），exe/.dat 仍排除
- `check_deployment()` 改为校验 CSV 存在且可读（非空、含标题行）
- 数据加载策略：首次调用时加载 CSV 到内存并缓存（`_parcels_cache`），避免每次查询重复读文件

### D4: conditioner 移植但不接 API

`conditioner.py` 移植为库函数 `calculate_soil_conditioner(config, tybh, mj, xqmc, ph_start, alex, hex_)`，去除交互式 `input()`（参数全部由函数签名传入）。**不接入 API**，调理剂 API 需求仍由 model-4 酸化模型（4 子模型，过程式）处理。移植目的：保留 model2 完整源码，供未来参考或离线工具使用。

### D5: 潜力分析与县域统计 — 新增独立函数

新增对外函数（具体签名设计阶段细化）：
- `run_potential_analysis(parcel_code, csv_path=None)` → 单地块潜力分析结果
- `run_county_statistics(xqmc_code, csv_path=None)` → 县域常规统计
- `run_county_potential(xqmc_code, scenario, csv_path=None)` → 县域潜力情景（1=理想，2=最佳）

这些函数返回结构化 dict，不改变现有 `run_grade_evaluation` 的输出契约。

### D6: HTTP data/import — .dat 改 CSV

`/api/v1/data/import` 的 `data_type=dat` 改为接受 CSV：
- 上传 CSV 部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）

```

Full source: openspec/changes/replace-grade-eval-with-python-model/design.md

## openspec/changes/replace-grade-eval-with-python-model/tasks.md

- Source: openspec/changes/replace-grade-eval-with-python-model/tasks.md
- Lines: 1-76
- SHA256: 5714da9e0499574dd23ca82c5a49c517d74e80a25a5ace40912b37e311490ae9

```md
## 1. model2 核心模块移植

- [ ] 1.1 移植 `models.py`（Parcel, QualityResult, ObstacleItem, PotentialItem, CountyStats, CountyPotentialResult 数据类）到 `src/ai_culti_demo/farmland_grade_eval/models.py`
- [ ] 1.2 移植 `config.py`（EvaluationConfig：隶属函数参数 a/c/ut1/ut2、概念型隶属度、权重、等级阈值、名称字典）到 `src/ai_culti_demo/farmland_grade_eval/config.py`
- [ ] 1.3 移植 `data_loader.py`（load_parcels_from_csv：UTF-8-sig CSV → List[Parcel]，20 字段解析）到 `src/ai_culti_demo/farmland_grade_eval/data_loader.py`
- [ ] 1.4 移植 `evaluation.py`（membership_numeric 峰型/戒上型隶属函数 + evaluate_land_quality 综合指数与等级评定）到 `src/ai_culti_demo/farmland_grade_eval/evaluation.py`
- [ ] 1.5 移植 `obstacle.py`（calc_limiting_factors + compute_obstacle_factors 障碍度因子计算与分级）到 `src/ai_culti_demo/farmland_grade_eval/obstacle.py`
- [ ] 1.6 修正所有模块导入为包内相对导入（`from .config import`、`from .models import` 等）

## 2. runner.py 重写为 Python 调用层

- [ ] 2.1 重写 `FarmlandGradeRunner.__init__`：`dat_path` 语义改为 csv_path（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`），`exe_path` 忽略，新增 `MODEL_VERSION = "python_v1_20260801"`
- [ ] 2.2 实现 `check_deployment()`：校验 CSV 存在且可读（非空、含标题行），返回 `csv_exists`/`csv_path`/`ready` 字段
- [ ] 2.3 实现数据加载与缓存（`_load_parcels`：首次调用加载 CSV 到内存 `_parcels_cache`，避免重复读文件）
- [ ] 2.4 实现 `run(parcel_code)`：查找地块 → 调用 evaluate_land_quality + compute_obstacle_factors → 组装输出 dict（与 exe 时代契约一致：parcel_info/indicators/composite_index/quality_grade/obstacle_degree）
- [ ] 2.5 实现 indicators 字段组装：从 Parcel 字段 + config.indicator_names 构造 12 项 `{name, code, raw_value}`
- [ ] 2.6 实现 obstacle_degree 字段组装：从 compute_obstacle_factors 结果构造 12 项 `{rank, indicator, degree, level}`（按 degree 降序）
- [ ] 2.7 实现 parcel_info 字段组装：地块代码/经纬度/县区名称/二级农业区名称
- [ ] 2.8 保持 `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 便捷函数签名不变
- [ ] 2.9 错误处理：DEPLOYMENT_ERROR（CSV 缺失）、PARCEL_NOT_FOUND（地块不存在）、编码越界 ValueError

## 3. 数据文件部署

- [ ] 3.1 将 `D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv` 复制到 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`
- [ ] 3.2 更新 `.gitignore`：确保 CSV 不被排除（exe/.dat 仍排除）
- [ ] 3.3 更新 `bin/farmland_quality_eval/README.md`：部署说明从 exe/.dat 改为 CSV

## 4. 潜力分析与县域统计模块移植

- [ ] 4.1 移植 `potential.py`（compute_single_parcel_potential 单地块潜力分析 + county_potential_statistics_data 县域潜力情景）到 `src/ai_culti_demo/farmland_grade_eval/potential.py`
- [ ] 4.2 移植 `statistics.py`（county_statistics_data 县域常规统计）到 `src/ai_culti_demo/farmland_grade_eval/statistics.py`
- [ ] 4.3 实现 `run_potential_analysis(parcel_code, csv_path=None)` 对外函数，返回结构化 dict
- [ ] 4.4 实现 `run_county_statistics(xqmc_code, csv_path=None)` 对外函数，返回结构化 dict
- [ ] 4.5 实现 `run_county_potential(xqmc_code, scenario, csv_path=None)` 对外函数（scenario=1 理想/2 最佳），返回结构化 dict

## 5. 调理剂库函数移植

- [ ] 5.1 移植 `conditioner.py`（calculate_soil_conditioner）到 `src/ai_culti_demo/farmland_grade_eval/conditioner.py`，去除交互式 input()，参数全部由函数签名传入
- [ ] 5.2 添加文档注释标注"库函数，不接 API；API 调理剂需求走 model-4"

## 6. 调用方字段适配

- [ ] 6.1 检查 `framework/agents/specialized/grade_agent.py`：确认无需改动（签名兼容），更新 docstring 从"调用Fortran exe"改为"Python 实现"
- [ ] 6.2 检查 `src/ai_culti_demo/thematic_models.py`：确认 `_run_real_grade_model` 无需改动，更新 reliability.message 从"Fortran exe"改为"Python 模型"
- [ ] 6.3 检查 `framework/core_engine/adapter.py`：确认 `check_grade_eval_deployment` 调用 check_deployment 兼容新返回字段
- [ ] 6.4 更新 `src/ai_culti_demo/farmland_grade_eval/__init__.py`：导出新增对外函数（run_potential_analysis, run_county_statistics, run_county_potential）

## 7. HTTP data/import 改 CSV

- [ ] 7.1 更新 `framework/upload/data_trigger.py`：data_type=dat 分支改为接受 CSV，部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）
- [ ] 7.2 更新 CSV 校验逻辑：非空、≤200MB、UTF-8 编码、含 20 必需字段
- [ ] 7.3 部署后触发 `FarmlandGradeRunner.check_deployment()` 校验（沿用备份/回滚机制）
- [ ] 7.4 更新 HTTP 接口路由（如 data_type 枚举值变更）

## 8. 测试重写与回归

- [ ] 8.1 重写 `tests/test_farmland_grade_eval.py`：删除 parse_output 文本解析测试，新增 Python 评价逻辑单元测试
- [ ] 8.2 新增 A0001 回归测试：对比 Python 输出与 exe 历史输出（composite_index=0.6728、quality_grade="10等"、obstacle_degree 12 项，容差 < 0.01）
- [ ] 8.3 新增潜力分析单元测试（run_potential_analysis 对 A0001）
- [ ] 8.4 新增县域统计单元测试（run_county_statistics / run_county_potential 对武江区）
- [ ] 8.5 新增 conditioner 库函数单元测试
- [ ] 8.6 新增部署校验测试（check_deployment CSV 存在/缺失场景）
- [ ] 8.7 新增向后兼容测试（传 exe_path/dat_path 旧参数不报错）

## 9. 文档更新

- [ ] 9.1 更新 `README.md`：model-7 架构从 exe 改为 Python，专题模型数量/版本标识
- [ ] 9.2 更新 `docs/api.md`：data/import 接口 data_type=dat → CSV 说明
- [ ] 9.3 更新 `openapi.json`：data/import 请求/响应字段、版本号递增
- [ ] 9.4 更新 `bin/farmland_quality_eval/README.md`：部署说明改 CSV

## 10. exe/.dat 废弃与清理

- [ ] 10.1 确认 exe/.dat 不再被任何代码引用（全局搜索 subprocess/Farmland_quality_evaluation.exe/.dat）
- [ ] 10.2 删除 `bin/farmland_quality_eval/Farmland_quality_evaluation.exe` 和 `Farmlands_Quality_Level_Database.dat`（本地文件，已被 gitignore 排除）
- [ ] 10.3 更新 `.gitignore` 确认 exe/.dat 模式仍保留（防止误提交）

```

## openspec/changes/replace-grade-eval-with-python-model/specs/farmland-quality-grade-evaluation/spec.md

- Source: openspec/changes/replace-grade-eval-with-python-model/specs/farmland-quality-grade-evaluation/spec.md
- Lines: 1-75
- SHA256: 4eb584a1bd3777760b581d49fa65f62fc92f109ee5ed2505904b041e13428ea9

```md
## ADDED Requirements

### Requirement: 耕地质量等级评价 Python 模型
系统 SHALL 通过纯 Python 实现（不依赖 Fortran exe 或二进制 .dat 文件）完成耕地质量等级评价，移植 model2 源码，基于 GB/T 33469-2016 标准的隶属函数模型与权重加权指数和法计算质量综合指数与等级。`MODEL_VERSION` SHALL 为 `python_v1_20260801`。

#### Scenario: 核心评价查询
- **WHEN** 调用 `run_grade_evaluation(parcel_code)` 且 CSV 数据文件已部署、地块代码存在
- **THEN** 系统 SHALL 返回 `status: "ok"`，包含 `parcel_code`、`parcel_info`（地块代码/经纬度/县区名称/二级农业区名称）、`indicators`（12 项含 name/code/raw_value）、`composite_index`（浮点）、`quality_grade`（如"10等"字符串）、`obstacle_degree`（12 项含 rank/indicator/degree/level，按 degree 降序）

#### Scenario: 数据文件未部署
- **WHEN** 调用 `run_grade_evaluation` 时 CSV 数据文件不存在或不可读
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code: "DEPLOYMENT_ERROR"`，`error.message` 说明 CSV 文件缺失

#### Scenario: 地块代码未找到
- **WHEN** 调用 `run_grade_evaluation(parcel_code)` 且 parcel_code 在 CSV 数据中不存在
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code: "PARCEL_NOT_FOUND"`，`error.message` 包含未找到的地块代码

#### Scenario: 编码字段越界
- **WHEN** 地块的 ZDGC/PSNL/GGNL/DXBW/ZDGX/ejnyq 编码超出合法范围
- **THEN** 系统 SHALL 返回 `status: "error"`，`error.code` 标识越界字段，不返回部分结果

#### Scenario: 数值等价性
- **WHEN** 对 A0001 地块执行 Python 评价
- **THEN** `composite_index` SHALL 与 exe 历史输出（0.6728）一致（浮点容差 < 0.01），`quality_grade` SHALL 为"10等"，`obstacle_degree` 各项 degree SHALL 与 exe 历史输出一致（容差 < 0.01）

### Requirement: 向后兼容的 API 签名
系统 SHALL 保持 `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 函数签名不变，其中 `dat_path` 参数语义改为 CSV 文件路径（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`），`exe_path` 参数 SHALL 被忽略且不报错。`FarmlandGradeRunner.__init__` SHALL 同理保持签名兼容。

#### Scenario: 默认路径调用
- **WHEN** 调用 `run_grade_evaluation("A0001")` 不传 dat_path
- **THEN** 系统 SHALL 使用默认 CSV 路径 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv` 加载数据

#### Scenario: 旧参数兼容
- **WHEN** 调用方传入 `exe_path` 和 `dat_path`（旧调用方式）
- **THEN** 系统 SHALL 忽略 `exe_path`，将 `dat_path` 解释为 CSV 路径，不抛出参数错误

### Requirement: 部署校验改为 CSV
`FarmlandGradeRunner.check_deployment()` SHALL 校验 CSV 数据文件存在且可读（非空、含标题行），不再校验 exe 或 .dat 文件。返回 dict SHALL 包含 `csv_exists`、`csv_path`、`ready` 字段。

#### Scenario: CSV 已部署
- **WHEN** CSV 文件存在于默认路径且非空
- **THEN** `check_deployment` SHALL 返回 `csv_exists: true`、`ready: true`

#### Scenario: CSV 未部署
- **WHEN** CSV 文件不存在
- **THEN** `check_deployment` SHALL 返回 `csv_exists: false`、`ready: false`

### Requirement: 单地块潜力分析
系统 SHALL 提供 `run_potential_analysis(parcel_code, csv_path=None)` 函数，基于 model2 的 `compute_single_parcel_potential` 实现单地块潜力分析，按固定顺序（灌溉→排水→有机质→速效钾→有效磷→有效土层厚度→容重→pH→耕层厚度）模拟各指标改良后的潜在质量指数与等级提升，并计算全改良后的潜在质量指数与等级。

#### Scenario: 潜力分析查询
- **WHEN** 调用 `run_potential_analysis("A0001")` 且地块存在
- **THEN** 系统 SHALL 返回各指标的原始值、潜力值、原始质量指数、潜在质量指数、原等级、潜在等级，以及全改良后的综合质量指数与等级

### Requirement: 县域统计与潜力情景分析
系统 SHALL 提供 `run_county_statistics(xqmc_code, csv_path=None)` 和 `run_county_potential(xqmc_code, scenario, csv_path=None)` 函数，实现县域常规统计与潜力情景分析（scenario=1 理想潜力、scenario=2 最佳潜力），返回等级分布、障碍度统计、首要障碍指标等结构化结果。

#### Scenario: 县域常规统计
- **WHEN** 调用 `run_county_statistics(8)`（武江区）且该县区有地块数据
- **THEN** 系统 SHALL 返回地块数量、总面积、平均等级、各指标统计、障碍度排序、等级分布、首要障碍指标统计

#### Scenario: 县域潜力情景
- **WHEN** 调用 `run_county_potential(8, 1)`（理想潜力）
- **THEN** 系统 SHALL 返回潜力情景下的等级分布、障碍度变化及原始对比数据

#### Scenario: 县区无数据
- **WHEN** 调用县域统计且该县区无地块数据
- **THEN** 系统 SHALL 返回 `status: "error"` 或空结果，标识无数据

### Requirement: 调理剂库函数（不接 API）
系统 SHALL 移植 model2 的 `calculate_soil_conditioner` 作为库函数（去除交互式 input，参数由函数签名传入），计算亿土康（YTK）和木本泥炭（MBNT）施用量。该函数 SHALL NOT 通过 HTTP API 暴露；调理剂 API 需求 SHALL 由 model-4 酸化模型处理。

#### Scenario: 库函数调用
- **WHEN** 在代码中直接调用 `calculate_soil_conditioner(config, tybh, mj, xqmc, ph_start, alex, hex_)`
- **THEN** 函数 SHALL 返回 YTK/MBNT 的单位施用量（kg/ha）和地块总施用量（tons）

```

## openspec/changes/replace-grade-eval-with-python-model/specs/professional-model-agents/spec.md

- Source: openspec/changes/replace-grade-eval-with-python-model/specs/professional-model-agents/spec.md
- Lines: 1-16
- SHA256: 694e2de0c140039fca38bdb09b0daffddbe389b1d989191ce49e3b9a0365d369

```md
## MODIFIED Requirements

### Requirement: FarmlandGradeObstacleAgent 智能体
系统 SHALL 实现 `FarmlandGradeObstacleAgent` 智能体，对应耕地质量等级和障碍度评价模型（纯 Python 实现），通过调用 `run_grade_evaluation` 获取地块评价结果，返回基于 GB/T 33469-2016 标准的真实质量等级和障碍度诊断，不再依赖 Fortran exe 或 subprocess。

#### Scenario: 质量等级查询
- **WHEN** 用户询问某地块的耕地质量等级，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回质量等级（1-10等）、综合指数和 12 项指标的原始值

#### Scenario: 障碍度诊断
- **WHEN** 用户询问某地块的主要障碍因素，且提供了合法的地块统一代码
- **THEN** 智能体 SHALL 调用 `run_grade_evaluation`（Python 实现），返回障碍度因子排序表（从大到小），识别主要限制因子

#### Scenario: 评价调用失败
- **WHEN** Python 评价调用失败（CSV 数据缺失、地块代码无效、编码字段越界）
- **THEN** 智能体 SHALL 返回明确的错误信息（如"CSV 数据文件缺失"、"未找到地块代码"），`confidence` 字段降低，不返回模拟数据

```

## openspec/changes/replace-grade-eval-with-python-model/specs/thematic-data-import/spec.md

- Source: openspec/changes/replace-grade-eval-with-python-model/specs/thematic-data-import/spec.md
- Lines: 1-74
- SHA256: 64ab6d4bc3de83cc7e9967fa0469dde6ce1d959c32f0fc880a725aeab99366d9

```md
## REMOVED Requirements

### Requirement: DAT Data Validation
**Reason**: 耕地质量等级评价已从 Fortran exe + 二进制 .dat 替换为纯 Python 实现 + CSV 数据文件，不再接受 .dat 文件上传。
**Migration**: 通过 `POST /api/v1/data/import` 上传 CSV 文件（data_type 标识为耕地质量评价数据），部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`。

## ADDED Requirements

### Requirement: 耕地质量评价 CSV 数据校验
系统 SHALL 校验上传的耕地质量评价 CSV 文件为非空可读文本文件，文件大小 > 0 且 ≤ 200MB，编码为 UTF-8（带或不带 BOM），且 SHALL 包含 20 个必需字段（SiteID、JD、WD、MJ、SJD、YJZ、YXL、SXJ、TRRZ、YXTCHD、GCHD、JHXLLZ、JHXQLZ、EJNYQcode、XQMCcode、GCZDcode、PSNLcode、GGNLcode、DXBWcode、ZDGXcode），字段名以 CSV 首行表头为准。

#### Scenario: CSV 文件为空
- **WHEN** 上传的耕地质量评价 CSV 文件大小为 0 字节
- **THEN** 系统 SHALL 返回 HTTP 400，响应体 `status: "error"`、`message: "CSV 文件为空"`

#### Scenario: CSV 文件可读且字段完整
- **WHEN** 上传的 CSV 文件大小 > 0 且 ≤ 200MB，含 20 个必需字段
- **THEN** 系统 SHALL 接受该文件并继续部署和触发流程

#### Scenario: CSV 字段缺失
- **WHEN** 上传的 CSV 文件缺少必需字段（如缺少 ejnyq 或 zdgx 列）
- **THEN** 系统 SHALL 返回 HTTP 400，`status: "error"`、`message` 包含缺失的字段名列表

## MODIFIED Requirements

### Requirement: Data Deployment with Backup
系统 SHALL 在部署新数据前，将目标目录下的现有文件移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/` 子目录；部署完成后 SHALL 扫描 `backup/` 下所有时间戳目录，按目录名倒序保留前 3 份，删除其余。诊断 CSV 部署到 `data/farmland_diagnosis/`、shapefile 部署到 `data/farmland_stability/`、耕地质量评价 CSV 部署到 `bin/farmland_quality_eval/`。

#### Scenario: 首次部署（目标目录无现有文件）
- **WHEN** 目标目录下不存在任何现有数据文件（仅有 README.md 或为空）
- **THEN** 系统 SHALL 跳过备份步骤，直接写入新文件，响应中 `backup_path` 为 `null`

#### Scenario: 覆盖部署（目标目录有现有文件）
- **WHEN** 目标目录下存在现有数据文件
- **THEN** 系统 SHALL 将现有数据文件（排除 README.md 和 `backup/` 子目录）移动到 `<target_dir>/backup/<YYYYMMDD-HHMMSS>/`，再写入新文件，响应中 `backup_path` 为该备份目录路径

#### Scenario: 诊断 CSV 部署时重命名为 test.csv
- **WHEN** 上传的诊断 CSV 文件原名为任意名称（如 `mydata.csv`），校验通过后部署到 `data/farmland_diagnosis/`
- **THEN** 系统 SHALL 将文件重命名为 `test.csv` 写入目标目录（与 README 约定和下游 `bulk_evaluate` 默认读取路径一致），原文件名记录在审计日志中

#### Scenario: 耕地质量评价 CSV 部署时重命名为固定文件名
- **WHEN** 上传的耕地质量评价 CSV 文件原名为任意名称，校验通过后部署到 `bin/farmland_quality_eval/`
- **THEN** 系统 SHALL 将文件重命名为 `Farmland_quality_Level_Database.csv` 写入目标目录（与 runner 默认读取路径一致），原文件名记录在审计日志中

#### Scenario: 备份目录超过 3 份
- **WHEN** 部署完成后 `backup/` 下存在超过 3 个时间戳子目录
- **THEN** 系统 SHALL 按目录名倒序保留最新 3 份，删除其余旧备份目录及其内容

### Requirement: Offline Computation Trigger
系统 SHALL 在部署成功后同步触发对应数据类型的离线计算：诊断 CSV 触发 `bulk_evaluate(input_csv, output_db_path)`、shapefile 触发 `precompute.main(shapefile_dir, manifest)`（封装 `run_all_models` → `StabilityStorage.save_results` → `save_final_results` 完整流程）、耕地质量评价 CSV 触发 `FarmlandGradeRunner.check_deployment()`。触发超时为 600 秒（配置项 `DATA_IMPORT_TIMEOUT`）。

#### Scenario: 诊断 CSV 触发 bulk_evaluate 成功
- **WHEN** 诊断 CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "ok"`
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `processed` 行数和 `errors` 列表（可能为空）

#### Scenario: 诊断 CSV 触发 bulk_evaluate 返回错误
- **WHEN** 诊断 CSV 部署成功后调用 `bulk_evaluate` 返回 `status: "error"`（例如未知区域名称）
- **THEN** 系统 SHALL 从最近一次 `backup/` 恢复文件，返回 HTTP 500，`status: "error"`、`message: "触发失败已回滚"`、`trigger_error` 包含 bulk_evaluate 返回的错误信息

#### Scenario: shapefile 触发 precompute 成功
- **WHEN** shapefile 部署成功后调用 `precompute.main(shapefile_dir, manifest)` 完整执行 `run_all_models` → `StabilityStorage.save_results` → `save_final_results` 流程并返回 `status: "ok"`
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `processed`（处理的地块数）、`saved_to_db`（写入 DB 的记录数）、`output_files`（输出的 shapefile 和 xlsx 文件路径列表）

#### Scenario: 触发抛出未捕获异常
- **WHEN** 触发函数抛出未捕获异常（非返回错误字典）
- **THEN** 系统 SHALL 从最近一次 `backup/` 恢复文件，返回 HTTP 500，`status: "error"`、`message: "触发异常已回滚"`、`detail` 包含异常信息

#### Scenario: 触发超时
- **WHEN** 触发函数执行时间超过 600 秒
- **THEN** 系统 SHALL 终止触发操作，从最近一次 `backup/` 恢复文件，返回 HTTP 504，`status: "error"`、`message: "触发超时已回滚"`

#### Scenario: 耕地质量评价 CSV 部署后自动生效
- **WHEN** 耕地质量评价 CSV 部署成功后调用 `check_deployment` 返回通过
- **THEN** 系统 SHALL 返回 HTTP 200，`trigger_result` 包含 `deployment_ok: true`，后续查询时按需从 CSV 加载数据

```
