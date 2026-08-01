## 1. model2 核心模块移植

- [x] 1.1 移植 `models.py`（Parcel, QualityResult, ObstacleItem, PotentialItem, CountyStats, CountyPotentialResult 数据类）到 `src/ai_culti_demo/farmland_grade_eval/models.py`
- [x] 1.2 移植 `config.py`（EvaluationConfig：隶属函数参数 a/c/ut1/ut2、概念型隶属度、权重、等级阈值、名称字典）到 `src/ai_culti_demo/farmland_grade_eval/config.py`
- [x] 1.3 移植 `data_loader.py`（load_parcels_from_csv：UTF-8-sig CSV → List[Parcel]，20 字段解析）到 `src/ai_culti_demo/farmland_grade_eval/data_loader.py`
- [x] 1.4 移植 `evaluation.py`（membership_numeric 峰型/戒上型隶属函数 + evaluate_land_quality 综合指数与等级评定）到 `src/ai_culti_demo/farmland_grade_eval/evaluation.py`
- [x] 1.5 移植 `obstacle.py`（calc_limiting_factors + compute_obstacle_factors 障碍度因子计算与分级）到 `src/ai_culti_demo/farmland_grade_eval/obstacle.py`
- [x] 1.6 修正所有模块导入为包内相对导入（`from .config import`、`from .models import` 等）

## 2. runner.py 重写为 Python 调用层

- [x] 2.1 重写 `FarmlandGradeRunner.__init__`：`dat_path` 语义改为 csv_path（默认 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`），`exe_path` 忽略，新增 `MODEL_VERSION = "python_v1_20260801"`
- [x] 2.2 实现 `check_deployment()`：校验 CSV 存在且可读（非空、含标题行），返回 `csv_exists`/`csv_path`/`ready` 字段
- [x] 2.3 实现数据加载与缓存（`_load_parcels`：首次调用加载 CSV 到内存 `_parcels_cache`，避免重复读文件）
- [x] 2.4 实现 `run(parcel_code)`：查找地块 → 调用 evaluate_land_quality + compute_obstacle_factors → 组装输出 dict（与 exe 时代契约一致：parcel_info/indicators/composite_index/quality_grade/obstacle_degree）
- [x] 2.5 实现 indicators 字段组装：从 Parcel 字段 + config.indicator_names 构造 12 项 `{name, code, raw_value}`
- [x] 2.6 实现 obstacle_degree 字段组装：从 compute_obstacle_factors 结果构造 12 项 `{rank, indicator, degree, level}`（按 degree 降序）
- [x] 2.7 实现 parcel_info 字段组装：地块代码/经纬度/县区名称/二级农业区名称
- [x] 2.8 保持 `run_grade_evaluation(parcel_code, exe_path=None, dat_path=None)` 便捷函数签名不变
- [x] 2.9 错误处理：DEPLOYMENT_ERROR（CSV 缺失）、PARCEL_NOT_FOUND（地块不存在）、编码越界 ValueError

## 3. 数据文件部署

- [x] 3.1 将 `D:\destkop\模型\模型2\Farmland_quality_Level_Database.csv` 复制到 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`
- [x] 3.2 更新 `.gitignore`：确保 CSV 不被排除（exe/.dat 仍排除）
- [x] 3.3 更新 `bin/farmland_quality_eval/README.md`：部署说明从 exe/.dat 改为 CSV

## 4. 潜力分析与县域统计模块移植

- [x] 4.1 移植 `potential.py`（compute_single_parcel_potential 单地块潜力分析 + county_potential_statistics_data 县域潜力情景）到 `src/ai_culti_demo/farmland_grade_eval/potential.py`
- [x] 4.2 移植 `statistics.py`（county_statistics_data 县域常规统计）到 `src/ai_culti_demo/farmland_grade_eval/statistics.py`
- [x] 4.3 实现 `run_potential_analysis(parcel_code, csv_path=None)` 对外函数，返回结构化 dict
- [x] 4.4 实现 `run_county_statistics(xqmc_code, csv_path=None)` 对外函数，返回结构化 dict
- [x] 4.5 实现 `run_county_potential(xqmc_code, scenario, csv_path=None)` 对外函数（scenario=1 理想/2 最佳），返回结构化 dict

## 5. 调理剂库函数移植

- [x] 5.1 移植 `conditioner.py`（calculate_soil_conditioner）到 `src/ai_culti_demo/farmland_grade_eval/conditioner.py`，去除交互式 input()，参数全部由函数签名传入
- [x] 5.2 添加文档注释标注"库函数，不接 API；API 调理剂需求走 model-4"

## 6. 调用方字段适配

- [x] 6.1 检查 `framework/agents/specialized/grade_agent.py`：确认无需改动（签名兼容），更新 docstring 从"调用Fortran exe"改为"Python 实现"
- [x] 6.2 检查 `src/ai_culti_demo/thematic_models.py`：确认 `_run_real_grade_model` 无需改动，更新 reliability.message 从"Fortran exe"改为"Python 模型"
- [x] 6.3 检查 `framework/core_engine/adapter.py`：确认 `check_grade_eval_deployment` 调用 check_deployment 兼容新返回字段
- [x] 6.4 更新 `src/ai_culti_demo/farmland_grade_eval/__init__.py`：导出新增对外函数（run_potential_analysis, run_county_statistics, run_county_potential）

## 7. HTTP data/import 改 CSV

- [x] 7.1 更新 `framework/upload/data_trigger.py`：data_type=dat 分支改为接受 CSV，部署为 `bin/farmland_quality_eval/Farmland_quality_Level_Database.csv`（固定文件名）
- [x] 7.2 更新 CSV 校验逻辑：非空、≤200MB、UTF-8 编码、含 20 必需字段
- [x] 7.3 部署后触发 `FarmlandGradeRunner.check_deployment()` 校验（沿用备份/回滚机制）
- [x] 7.4 更新 HTTP 接口路由（如 data_type 枚举值变更）

## 8. 测试重写与回归

- [x] 8.1 重写 `tests/test_farmland_grade_eval.py`：删除 parse_output 文本解析测试，新增 Python 评价逻辑单元测试
- [x] 8.2 新增 A0001 回归测试：对比 Python 输出与 exe 历史输出（composite_index=0.6728、quality_grade="10等"、obstacle_degree 12 项，容差 < 0.01）
- [x] 8.3 新增潜力分析单元测试（run_potential_analysis 对 A0001）
- [x] 8.4 新增县域统计单元测试（run_county_statistics / run_county_potential 对武江区）
- [x] 8.5 新增 conditioner 库函数单元测试
- [x] 8.6 新增部署校验测试（check_deployment CSV 存在/缺失场景）
- [x] 8.7 新增向后兼容测试（传 exe_path/dat_path 旧参数不报错）

## 9. 文档更新

- [x] 9.1 更新 `README.md`：model-7 架构从 exe 改为 Python，专题模型数量/版本标识
- [x] 9.2 更新 `docs/api.md`：data/import 接口 data_type=dat → CSV 说明
- [x] 9.3 更新 `openapi.json`：data/import 请求/响应字段、版本号递增
- [x] 9.4 更新 `bin/farmland_quality_eval/README.md`：部署说明改 CSV

## 10. exe/.dat 废弃与清理

- [x] 10.1 确认 exe/.dat 不再被任何代码引用（全局搜索 subprocess/Farmland_quality_evaluation.exe/.dat）
- [x] 10.2 删除 `bin/farmland_quality_eval/Farmland_quality_evaluation.exe` 和 `Farmlands_Quality_Level_Database.dat`（本地文件，已被 gitignore 排除）
- [x] 10.3 更新 `.gitignore` 确认 exe/.dat 模式仍保留（防止误提交）
