# Task 3 Report: Adapter 扩展（3 个新方法）

## Status

DONE

## 实现内容摘要

按 brief 原文在 `framework/core_engine/adapter.py` 的 `CoreEngine.verify_runtime` 方法之后、`core_engine = CoreEngine()` 单例之前插入：

- `_ensure_data_import_imports(self)`：延迟导入 `bulk_evaluate`、`precompute.main`、`FarmlandGradeRunner`，使用 `hasattr(self, '_data_import_ready')` 做一次性缓存
- `bulk_evaluate_csv(self, csv_path: str) -> Dict[str, Any]`：委托 `bulk_evaluate`，异常返回 `{"status": "error", "error": {"code": "BULK_EVALUATE_ERROR", "message": str(e)}}`
- `precompute_stability(self, shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]`：委托 `precompute.main`，异常返回 `{"status": "error", "error": {"code": "PRECOMPUTE_ERROR", "message": str(e)}}`
- `check_grade_eval_deployment(self) -> Dict[str, Any]`：实例化 `FarmlandGradeRunner` 并调用 `check_deployment()`，返回 `{"deployment_ok": bool, "detail": ...}`

3 个新方法均先调用 `self._ensure_import()` 再调用 `self._ensure_data_import_imports()`。未修改 adapter.py 中任何已有方法。

在 `tests/test_precompute.py` 末尾追加 4 个 adapter 测试，覆盖委托成功、异常路径、deployment 检查。

## RED/GREEN 证据

### RED 证据

命令：
```
d:\miniconda3\python.exe -m pytest tests/test_precompute.py::test_adapter_bulk_evaluate_csv_delegates -v
```

失败摘要（exit code 1）：
```
FAILED tests/test_precompute.py::test_adapter_bulk_evaluate_csv_delegates
E           AttributeError: 'CoreEngine' object has no attribute 'bulk_evaluate_csv'
1 failed in 3.52s
```

失败原因与 brief 预期完全一致：缺失 `bulk_evaluate_csv` 方法（非拼写错误、非其它异常）。

### GREEN 证据

命令：
```
d:\miniconda3\python.exe -m pytest tests/test_precompute.py -v
```

通过摘要（exit code 0）：
```
tests/test_precompute.py::test_g_to_records_basic_mapping PASSED         [ 14%]
tests/test_precompute.py::test_g_to_records_missing_field_skipped PASSED [ 28%]
tests/test_precompute.py::test_main_full_flow_with_mocks PASSED          [ 42%]
tests/test_precompute.py::test_adapter_bulk_evaluate_csv_delegates PASSED [ 57%]
tests/test_precompute.py::test_adapter_bulk_evaluate_csv_error_handling PASSED [ 71%]
tests/test_precompute.py::test_adapter_precompute_stability_delegates PASSED [ 85%]
tests/test_precompute.py::test_adapter_check_grade_eval_deployment_ok PASSED [100%]
7 passed in 2.65s
```

7 个测试全部 PASS（3 原有 + 4 新增），输出无 warning（仅 git LF→CRLF 提示与测试无关）。

## 变更文件列表

- `framework/core_engine/adapter.py`（+37 行：仅插入新方法，未改已有方法）
- `tests/test_precompute.py`（+51 行：末尾追加 4 个测试）

未修改任何其他文件（`subagent-progress.md` 在工作区有改动但未纳入本提交）。

## 提交哈希

`8c180d39a705390496d280ca9e4ad6d1e190fce3`（短：`8c180d3`）

提交信息：`feat: extend CoreEngine adapter with data import methods`

## 风险信号自报（逐条）

| 风险信号 | 命中 | 说明 |
|---|---|---|
| 跨模块/跨子系统协调改动 | **是** | adapter 桥接 `framework/core_engine/` 与 `src/ai_culti_demo/` 下三个子系统（farmland_diagnosis、farmland_stability、farmland_grade_eval）。这是 adapter 模式的预期职责，且本任务通过延迟导入 + patch 测试将耦合控制在调用时点，未触及三个子系统的源码本身。 |
| 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥） | 否 | 仅传递 `csv_path` 字符串与 `manifest` 字典给被委托函数，无认证、加解密、SQL 或凭证处理。 |
| 并发、锁、共享可变状态 | 否 | adapter 为单线程同步调用，无锁。`_data_import_ready` 缓存标志为实例属性，非跨实例共享可变状态。 |
| 数据或 schema 迁移 | 否 | 无数据库 schema 变更，无数据迁移。 |
| 公共 API 契约或对外接口变更 | **是** | `CoreEngine` 新增 3 个公共方法（`bulk_evaluate_csv`、`precompute_stability`、`check_grade_eval_deployment`），属于公共 API 扩展。本次为纯新增，不破坏既有契约。 |
| 单任务 diff 超过 200 行 | 否 | 本任务 diff 共 88 行新增（adapter +37、test +51），未超 200。 |

## 自检清单

- [x] 3 个新方法均先调用 `self._ensure_import()` 再 `self._ensure_data_import_imports()`
- [x] `_ensure_data_import_imports` 用 `hasattr(self, '_data_import_ready')` 做一次性缓存
- [x] 异常返回 `{"status": "error", "error": {"code": "...", "message": str(e)}}` 格式
- [x] `check_grade_eval_deployment` 返回 `{"deployment_ok": bool, "detail": ...}` 格式
- [x] 未修改 adapter.py 已有方法（diff 仅显示插入）
- [x] 7 个测试全部 PASS

## 顾虑

无。所有自检项通过，RED/GREEN 证据与 brief 预期完全一致，diff 行数远低于 200 行阈值。
