# Task 3 Brief: Adapter 扩展（3 个新方法）

> 本文件是 Task 3 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 9 节（9.2）

## 前置依赖

Task 2（precompute.py 已存在，方可延迟导入）。已确认 precompute.py 在 `src/ai_culti_demo/farmland_stability/precompute.py`。

## Files

- Modify: `framework/core_engine/adapter.py`
- Test: `tests/test_precompute.py`（在末尾追加 4 个 adapter 测试）

## Interfaces

- Consumes: `bulk_evaluate`（farmland_diagnosis.evaluation）、`precompute.main`（Task 2）、`FarmlandGradeRunner`（farmland_grade_eval.runner）
- Produces: `CoreEngine.bulk_evaluate_csv(csv_path) -> Dict`、`CoreEngine.precompute_stability(shapefile_dir, manifest) -> Dict`、`CoreEngine.check_grade_eval_deployment() -> Dict`

## adapter.py 当前结构（已确认）

- `class CoreEngine:` 在第 4 行
- `def verify_runtime(self) -> Dict[str, Any]:` 在第 105 行
- `core_engine = CoreEngine()` 在第 115 行（模块级单例）
- 插入位置：在 `verify_runtime` 方法之后、`core_engine = CoreEngine()` 之前

## Step 1: 编写 adapter 新方法的失败测试

在 `tests/test_precompute.py` 末尾追加以下 4 个测试：

```python
def test_adapter_bulk_evaluate_csv_delegates():
    """验证 adapter.bulk_evaluate_csv 委托给 bulk_evaluate 并捕获异常。"""
    from framework.core_engine.adapter import CoreEngine

    engine = CoreEngine()

    with patch('src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate', return_value={"status": "ok", "processed": 5}) as m:
        result = engine.bulk_evaluate_csv("/fake/test.csv")
        assert result["status"] == "ok"
        assert result["processed"] == 5
        m.assert_called_once_with("/fake/test.csv")


def test_adapter_bulk_evaluate_csv_error_handling():
    """验证 adapter.bulk_evaluate_csv 捕获异常返回错误字典。"""
    from framework.core_engine.adapter import CoreEngine

    engine = CoreEngine()

    with patch('src.ai_culti_demo.farmland_diagnosis.evaluation.bulk_evaluate', side_effect=RuntimeError("boom")):
        result = engine.bulk_evaluate_csv("/fake/test.csv")
        assert result["status"] == "error"
        assert result["error"]["code"] == "BULK_EVALUATE_ERROR"
        assert "boom" in result["error"]["message"]


def test_adapter_precompute_stability_delegates():
    """验证 adapter.precompute_stability 委托给 precompute.main。"""
    from framework.core_engine.adapter import CoreEngine

    engine = CoreEngine()
    manifest = {"current_filename": "2024.shp", "history_filenames": ["2018.shp"], "years": [2018, 2024]}

    with patch('src.ai_culti_demo.farmland_stability.precompute.main', return_value={"status": "ok", "processed": 10}) as m:
        result = engine.precompute_stability("/fake/dir", manifest)
        assert result["status"] == "ok"
        m.assert_called_once_with("/fake/dir", manifest)


def test_adapter_check_grade_eval_deployment_ok():
    """验证 adapter.check_grade_eval_deployment 返回 deployment_ok。"""
    from framework.core_engine.adapter import CoreEngine

    engine = CoreEngine()

    with patch('src.ai_culti_demo.farmland_grade_eval.runner.FarmlandGradeRunner') as MockRunner:
        MockRunner.return_value.check_deployment.return_value = {"exe_exists": True, "dat_exists": True, "ready": True}
        result = engine.check_grade_eval_deployment()
        assert result["deployment_ok"] is True
```

## Step 2: 运行测试验证失败

```bash
d:\miniconda3\python.exe -m pytest tests/test_precompute.py::test_adapter_bulk_evaluate_csv_delegates -v
```

预期：FAIL，报 `AttributeError: 'CoreEngine' object has no attribute 'bulk_evaluate_csv'`

## Step 3: 在 framework/core_engine/adapter.py 的 CoreEngine 类中新增方法

在 `verify_runtime` 方法之后、`core_engine = CoreEngine()` 之前插入：

```python
    def _ensure_data_import_imports(self):
        """延迟导入数据导入相关模块，避免在 _ensure_import 中引入 geopandas 等重依赖。"""
        if not hasattr(self, '_data_import_ready'):
            from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate
            from src.ai_culti_demo.farmland_stability.precompute import main as precompute_main
            from src.ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
            self._bulk_evaluate = bulk_evaluate
            self._precompute_main = precompute_main
            self._FarmlandGradeRunner = FarmlandGradeRunner
            self._data_import_ready = True

    def bulk_evaluate_csv(self, csv_path: str) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            return self._bulk_evaluate(csv_path)
        except Exception as e:
            return {"status": "error", "error": {"code": "BULK_EVALUATE_ERROR", "message": str(e)}}

    def precompute_stability(self, shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            return self._precompute_main(shapefile_dir, manifest)
        except Exception as e:
            return {"status": "error", "error": {"code": "PRECOMPUTE_ERROR", "message": str(e)}}

    def check_grade_eval_deployment(self) -> Dict[str, Any]:
        self._ensure_import()
        self._ensure_data_import_imports()
        try:
            runner = self._FarmlandGradeRunner()
            result = runner.check_deployment()
            return {"deployment_ok": True, "detail": result} if result else {"deployment_ok": False, "detail": None}
        except Exception as e:
            return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}
```

## Step 4: 运行测试验证通过

```bash
d:\miniconda3\python.exe -m pytest tests/test_precompute.py -v
```

预期：全部 PASS（含原有 3 个 + 新增 4 个 adapter 测试 = 7 个）

## Step 5: 提交

```bash
git add framework/core_engine/adapter.py tests/test_precompute.py
git commit -m "feat: extend CoreEngine adapter with data import methods"
```

## 全局约束（binds this task）

- 3 个新方法均先调用 `self._ensure_import()` 再调用 `self._ensure_data_import_imports()`
- `_ensure_data_import_imports` 使用 `hasattr(self, '_data_import_ready')` 做一次性延迟导入缓存
- 异常捕获返回 `{"status": "error", "error": {"code": "...", "message": str(e)}}` 格式
- `check_grade_eval_deployment` 返回 `{"deployment_ok": bool, "detail": ...}` 格式

## 环境提示（重要）

- **运行测试必须用 `d:\miniconda3\python.exe -m pytest`**，不要用默认 `python`
- 原因：farmland_stability/__init__.py 顶部 import geopandas，默认 python 无 geopandas 会报错
- 测试文件已包含 `sys.path.insert(0, .../src)` 处理导入路径
- 测试用 `patch` 模拟源模块函数，adapter 内部 `from ... import` 会拿到 patched 版本（因延迟导入在方法调用时执行）

## 注意事项

- 不要修改 adapter.py 中已有的方法（如 verify_runtime、_ensure_import 等）
- 只在 verify_runtime 之后、core_engine = CoreEngine() 之前插入新代码
- 确认 `Dict` 和 `Any` 已在 adapter.py 顶部导入（通常是 `from typing import Dict, Any`）；若未导入，在顶部添加
