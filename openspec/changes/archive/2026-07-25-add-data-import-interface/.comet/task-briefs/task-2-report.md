# Task 2 报告：precompute.py 模块（稳定性模型持久化）

## Status

DONE

## 实现内容摘要

按 TDD Red-Green-Refactor 流程实现 Task 2，严格依据 `task-2-brief.md` 原文，未改动函数签名、返回结构或字段名。

新增两个文件：

1. `src/ai_culti_demo/farmland_stability/precompute.py`（88 行）
   - `g_to_records(G, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ') -> List[Dict[str, Any]]`：遍历 `MODULE_FIELDS`，用 `RESULT_CN` 做中文 key 映射，将 GeoDataFrame 转换为 `StabilityStorage.save_results` 期望的 records 列表；每条 record 含 `parcel_id/region/score/grade`、`module_1..9`（缺失字段跳过为空字典）、`all_results` 汇总。
   - `main(shapefile_dir, manifest) -> Dict[str, Any]`：封装 `run_all_models → StabilityStorage.create_tables + save_results → save_final_results` 完整流程，返回 `{status, processed, saved_to_db, output_files}` 四个 key。
   - 命令行入口：从 `data/farmland_stability/manifest.json` 读取默认 manifest 并运行。

2. `tests/test_precompute.py`（86 行）：3 个测试
   - `test_g_to_records_basic_mapping`：验证基础字段与模块映射、`all_results` 汇总。
   - `test_g_to_records_missing_field_skipped`：验证缺失字段对应模块为空字典 `{}`。
   - `test_main_full_flow_with_mocks`：用 mock 验证 main 完整流程及返回结构。

## TDD 证据

### RED 证据

命令：
```bash
d:\miniconda3\python.exe -m pytest tests/test_precompute.py -v
```

结果：3 failed in 5.97s

失败摘要（precompute 模块尚未创建）：
- `test_g_to_records_basic_mapping` → `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_stability.precompute'`
- `test_g_to_records_missing_field_skipped` → `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_stability.precompute'`
- `test_main_full_flow_with_mocks` → `ImportError: cannot import name 'precompute' from 'ai_culti_demo.farmland_stability'`

根因与 brief 预期一致：precompute 模块不存在。

### GREEN 证据

命令：
```bash
d:\miniconda3\python.exe -m pytest tests/test_precompute.py -v
```

结果：3 passed in 2.46s

通过摘要：
- `tests/test_precompute.py::test_g_to_records_basic_mapping PASSED [ 33%]`
- `tests/test_precompute.py::test_g_to_records_missing_field_skipped PASSED [ 66%]`
- `tests/test_precompute.py::test_main_full_flow_with_mocks PASSED [100%]`

无需 Refactor（实现已最小化并贴合 brief）。

## 变更文件列表

| 文件 | 类型 | 行数 |
| --- | --- | --- |
| `src/ai_culti_demo/farmland_stability/precompute.py` | 新建 | +88 |
| `tests/test_precompute.py` | 新建 | +86 |

合计 174 行，仅修改允许范围内的两个文件，未触碰 `model.py` / `storage.py` / `__init__.py` 或其他任何文件。

## 提交哈希

`b57ec2931ac65f2baf5c20a4d8788564fa987d3a`

分支：`feature/20260725/add-data-import-interface`

提交信息：
```
feat: 新增 precompute.py 实现稳定性模型离线预计算持久化
```

## 风险信号自报（逐条）

| 风险信号 | 是否命中 | 说明 |
| --- | --- | --- |
| 跨模块/跨子系统协调改动 | 否 | 仅新建 precompute.py 通过现有公共接口（run_all_models / StabilityStorage / save_final_results）消费 model.py 与 storage.py，未对其他模块做任何协调性改动。 |
| 安全敏感面（认证、授权、加解密、SQL、外部输入处理、密钥/凭证） | 否 | 不涉及认证/授权/加解密/密钥；DB 操作经 `StabilityStorage` 抽象，未直接写 SQL；`main` 接收 manifest 字段拼接文件路径，但 manifest 为受信任的本地配置，非外部不可信输入。 |
| 并发、锁、共享可变状态 | 否 | 单线程同步流程，无并发、无锁、无共享可变状态。 |
| 数据或 schema 迁移 | 否 | 调用既有 `storage.create_tables()`，未引入 schema 变更或数据迁移。 |
| 公共 API 契约或对外接口变更 | 否（增量） | 新增 `g_to_records` 与 `main` 两个公共函数，属纯增量添加，未变更既有契约；`__init__.py` 未修改，未导出新符号。 |
| 单任务 diff 超过 200 行 | 否 | 总 diff 174 行（precompute.py 88 + test_precompute.py 86），未超过 200 行。 |

结论：本任务未命中任何风险信号。

## 顾虑

1. **运行环境**：仓库存在两个 Python 安装。默认 `python`（`C:\Users\17417\AppData\Local\Programs\Python\Python312\python.exe`）未安装 `geopandas`，而 `src/ai_culti_demo/farmland_stability/__init__.py` 在导入包时会触发 `model.py` 顶部的 `import geopandas`。因此测试必须用 `d:\miniconda3\python.exe`（已安装 geopandas 1.0.1、pytest 9.1.1）运行，否则会以 `ModuleNotFoundError: No module named 'geopandas'` 失败，掩盖 precompute 模块本身的状态。后续 Task 若依赖此环境，建议统一使用 miniconda 解释器或在 Python312 中补装 `geopandas`。
2. 测试中 `test_main_full_flow_with_mocks` 对 `run_all_models` / `StabilityStorage` / `save_final_results` 全部 mock，未覆盖真实文件 I/O 与 DB 落库；真实端到端验证需在后续任务（或集成测试）中补足。
