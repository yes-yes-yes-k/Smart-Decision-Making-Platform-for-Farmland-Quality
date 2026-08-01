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
- 部署后触发 `FarmlandGradeRunner.check_deployment()` 校验
- 备份/回滚机制沿用现有逻辑（backup/ 目录，保留 3 份）
- `data_trigger.py` 更新 data_type 分支

### D7: MODEL_VERSION 标识

新增 `MODEL_VERSION = "python_v1_20260801"`，在 `runner.py` 顶部定义，输出 dict 中可选携带 `model_version` 字段（与 model-4 acidification 风格一致）。

### D8: 回归测试策略

- 用 exe 历史输出样本（A0001 地块，已捕获于 `test_farmland_grade_eval.py` 的 `REAL_OUTPUT_A0001`）作为基准
- Python 实现对 A0001 计算后，对比 composite_index（0.6728）、quality_grade（"10等"）、obstacle_degree（12 项 degree 值），浮点容差 < 0.01
- 新增潜力分析、县域统计的独立单元测试
- `parse_output` 相关测试删除（不再有文本解析）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| Python 实现与 exe 数值不完全等价（隶属函数/权重差异） | 用 A0001 历史输出做回归对比；model2 与 exe 基于同一标准（GB/T 33469-2016），数学一致 |
| CSV 数据文件入库增大仓库体积（97KB） | 97KB 可接受；远小于 exe（911KB）且为文本可 diff |
| 数据加载缓存内存占用（1193 地块） | 单次加载约几 MB，可接受；进程级缓存 |
| conditioner 与 model-4 并存造成混淆 | conditioner 不接 API、文档标注"仅库函数，API 调理剂需求走 model-4" |
| HTTP data/import 改 CSV 是 BREAKING 变更 | 文档明确标注；旧 .dat 上传方需改传 CSV；无在线迁移需求（demo 项目） |
| `ejnyq`/编码字段越界导致评价异常 | 保留 model2 的 ValueError 校验（ZDGC/PSNL/GGNL/DXBW/ZDGX 范围检查） |

## Migration Plan

1. 移植 model2 模块到 `farmland_grade_eval/` 包，修正导入为相对导入
2. 重写 `runner.py` 为 Python 调用层，保持输出 dict 契约
3. 部署 CSV 数据文件到 `bin/farmland_quality_eval/`
4. 更新 grade_agent.py、thematic_models.py、adapter.py 字段适配（如有必要）
5. 更新 data_trigger.py 和 HTTP 接口（.dat → CSV）
6. 重写测试 + 新增回归测试
7. 更新文档（README、api.md、openapi.json）
8. 删除 exe/.dat（.gitignore 保持排除）

**回滚策略**：如 Python 实现验证失败，恢复 runner.py 旧版（subprocess+exe），exe/.dat 部署不受代码改动影响（仍被 gitignore 排除，本地保留）。

## Open Questions

- 潜力分析与县域统计函数的精确签名与返回结构（设计阶段 Design Doc 细化）
- CSV 数据文件是否需要支持热更新（当前 data/import 已支持重新部署）
