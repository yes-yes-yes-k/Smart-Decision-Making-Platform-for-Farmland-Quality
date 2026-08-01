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
