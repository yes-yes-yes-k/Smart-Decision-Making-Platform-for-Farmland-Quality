# Task 7 Brief: 数据触发器

> 本文件是 Task 7 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 4 节（4.1-4.6）

## 前置依赖

- ✅ Task 3 已完成：`framework/core_engine/adapter.py` 已暴露三个方法
  - `bulk_evaluate_csv(csv_path: str) -> Dict[str, Any]`
  - `precompute_stability(shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]`
  - `check_grade_eval_deployment() -> Dict[str, Any]`（**注意：无参数**）
- ✅ Task 1 已完成：`framework/config.py` 已定义 `DATA_IMPORT_TIMEOUT = 600`

## 底层返回结构（仅供参考，trigger 透传即可）

- `bulk_evaluate_csv` 成功：`{'status': 'ok', 'processed': <int>, 'errors': [...]}`；异常：`{'status': 'error', 'error': {'code': 'BULK_EVALUATE_ERROR', 'message': str}}`
- `precompute_stability` 成功：`{'status': 'ok', 'processed': <int>, 'saved_to_db': bool, 'output_files': [...]}`；异常：`{'status': 'error', 'error': {'code': 'PRECOMPUTE_ERROR', 'message': str}}`
- `check_grade_eval_deployment` 成功：`{'deployment_ok': True, 'detail': {...}}`；失败：`{'deployment_ok': False, 'detail': None}`；异常：`{'deployment_ok': False, 'error': {'code': 'DEPLOYMENT_CHECK_ERROR', 'message': str}}`

## Files

- Create: `framework/upload/data_trigger.py`
- Test: `tests/test_data_trigger.py`

## Interfaces

- Consumes: `framework.config.Config.DATA_IMPORT_TIMEOUT`、`framework.core_engine.adapter.core_engine`
- Produces:
  - `trigger_csv_evaluate(csv_path: str, timeout: Optional[float] = None) -> Dict[str, Any]`
  - `trigger_shapefile_precompute(target_dir: str, manifest: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]`
  - `trigger_dat_check(target_dir: str, timeout: Optional[float] = None) -> Dict[str, Any]`

## 设计要点

1. **统一超时封装**：抽取 `_run_with_timeout(func, *args, timeout=None)` 辅助函数，用 `concurrent.futures.ThreadPoolExecutor(max_workers=1)` + `future.result(timeout=...)`。
2. **timeout 参数可注入**：默认 `None` → 取 `Config.DATA_IMPORT_TIMEOUT`；测试可传入小数值（如 0.1）验证超时。这是为了可测试性，不偏离 spec（spec 要求用 `DATA_IMPORT_TIMEOUT`，默认行为与之完全一致）。
3. **超时异常类型**：`concurrent.futures.TimeoutError` 在 Python 3.11+ 等价于内置 `TimeoutError`；为兼容且语义清晰，捕获 `concurrent.futures.TimeoutError` 后重新抛出内置 `TimeoutError`，错误消息含超时秒数。
4. **透传 adapter 返回**：trigger 不解释返回字典内容（成功/错误字典均原样返回），仅负责"调用 + 超时"。
5. **adapter 异常向上冒泡**：adapter 方法内部已 try/except 并返回错误字典，因此正常情况下不会抛异常；但若 adapter 调用前的属性访问等出错，异常应向上冒泡到调用方（由 API 路由层捕获）。
6. **`trigger_dat_check` 的 target_dir 参数**：保留用于与其他两个触发器签名一致（API 路由层统一调用），但 **不传给 adapter**（`check_grade_eval_deployment()` 无参数，FarmlandGradeRunner 内部从配置解析路径）。在 docstring 中说明此点。

## Step 1: 编写 tests/test_data_trigger.py 的失败测试

创建 `tests/test_data_trigger.py`：

```python
"""测试数据导入触发器：用 monkeypatch 模拟 adapter 调用。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload import data_trigger


@pytest.fixture
def fake_adapter(monkeypatch):
    """用 monkeypatch 替换 core_engine 的三个方法，并记录调用参数。"""
    calls = {
        'bulk_evaluate_csv': [],
        'precompute_stability': [],
        'check_grade_eval_deployment': [],
    }

    def fake_bulk(csv_path):
        calls['bulk_evaluate_csv'].append(csv_path)
        return {'status': 'ok', 'processed': 100, 'errors': []}

    def fake_precompute(shapefile_dir, manifest):
        calls['precompute_stability'].append((shapefile_dir, manifest))
        return {'status': 'ok', 'processed': 50, 'saved_to_db': True, 'output_files': ['/o/s.shp']}

    def fake_check():
        calls['check_grade_eval_deployment'].append(None)
        return {'deployment_ok': True, 'detail': {'ready': True}}

    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', fake_bulk)
    monkeypatch.setattr(data_trigger.core_engine, 'precompute_stability', fake_precompute)
    monkeypatch.setattr(data_trigger.core_engine, 'check_grade_eval_deployment', fake_check)
    return calls


def test_trigger_csv_evaluate_success(fake_adapter):
    """CSV 触发成功：透传 adapter 返回，参数正确传递。"""
    result = data_trigger.trigger_csv_evaluate('/tmp/test.csv')
    assert result['status'] == 'ok'
    assert result['processed'] == 100
    assert fake_adapter['bulk_evaluate_csv'] == ['/tmp/test.csv']


def test_trigger_csv_evaluate_returns_error_dict(monkeypatch):
    """adapter 返回错误字典时，trigger 原样透传。"""
    monkeypatch.setattr(
        data_trigger.core_engine, 'bulk_evaluate_csv',
        lambda p: {'status': 'error', 'error': {'code': 'BULK_EVALUATE_ERROR', 'message': '字段缺失'}},
    )
    result = data_trigger.trigger_csv_evaluate('/tmp/bad.csv')
    assert result['status'] == 'error'
    assert result['error']['code'] == 'BULK_EVALUATE_ERROR'
    assert '字段缺失' in result['error']['message']


def test_trigger_csv_evaluate_propagates_exception(monkeypatch):
    """adapter 抛异常时，异常向上冒泡（由 API 路由层捕获）。"""
    def raise_error(csv_path):
        raise RuntimeError('connection lost')
    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', raise_error)
    with pytest.raises(RuntimeError, match='connection lost'):
        data_trigger.trigger_csv_evaluate('/tmp/x.csv')


def test_trigger_shapefile_precompute_success(fake_adapter):
    """shapefile 触发成功：参数（target_dir, manifest）正确传递。"""
    manifest = {'current_year': 2024, 'history_years': [2020, 2021]}
    result = data_trigger.trigger_shapefile_precompute('/tmp/shp', manifest)
    assert result['status'] == 'ok'
    assert result['saved_to_db'] is True
    assert fake_adapter['precompute_stability'] == [('/tmp/shp', manifest)]


def test_trigger_dat_check_success(fake_adapter):
    """dat 触发成功：调用无参 adapter 方法，target_dir 不传入。"""
    result = data_trigger.trigger_dat_check('/bin/farmland_quality_eval')
    assert result['deployment_ok'] is True
    # 验证 adapter 被调用一次（无参数）
    assert len(fake_adapter['check_grade_eval_deployment']) == 1


def test_trigger_timeout_raises_timeout_error(monkeypatch):
    """超时抛内置 TimeoutError。"""
    import time

    def slow_call(csv_path):
        time.sleep(10)
        return {'status': 'ok'}

    monkeypatch.setattr(data_trigger.core_engine, 'bulk_evaluate_csv', slow_call)
    with pytest.raises(TimeoutError):
        data_trigger.trigger_csv_evaluate('/tmp/slow.csv', timeout=0.1)


def test_trigger_default_timeout_uses_config(monkeypatch):
    """timeout=None 时使用 Config.DATA_IMPORT_TIMEOUT。"""
    captured = {}

    def fake_bulk(csv_path):
        # 由于无法真正等待 600s，这里通过捕获 future.result 的 timeout 间接验证
        return {'status': 'ok'}

    # 用 monkeypatch 替换 ThreadPoolExecutor 以捕获 timeout 参数
    import concurrent.futures

    class FakeFuture:
        def __init__(self, result_value):
            self._result = result_value

        def result(self, timeout=None):
            captured['timeout'] = timeout
            return self._result

    class FakeExecutor:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, func, *args):
            return FakeFuture(func(*args))

    monkeypatch.setattr(data_trigger, 'core_engine', type('FakeCE', (), {
        'bulk_evaluate_csv': staticmethod(fake_bulk),
    })())
    monkeypatch.setattr(data_trigger.concurrent_futures, 'ThreadPoolExecutor', FakeExecutor)

    from framework.config import Config
    data_trigger.trigger_csv_evaluate('/tmp/x.csv')
    assert captured['timeout'] == Config.DATA_IMPORT_TIMEOUT
```

## Step 2: 运行测试验证失败

```bash
d:\miniconda3\python.exe -m pytest tests/test_data_trigger.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'framework.upload.data_trigger'`（或 `ImportError`）

## Step 3: 实现 framework/upload/data_trigger.py

创建 `framework/upload/data_trigger.py`：

```python
"""数据导入触发器：数据部署完成后调用对应专题模型的预计算/评价/校验入口。

每个触发函数通过 CoreEngine adapter 调用底层模型，使用线程池 + future.result(timeout=)
实现超时控制，超时抛 TimeoutError。trigger 不解释返回字典内容（成功/错误字典均原样透传）。
"""
import concurrent.futures
from typing import Any, Dict, Optional

from framework.config import Config
from framework.core_engine.adapter import core_engine

# 暴露 concurrent_futures 便于测试 monkeypatch
concurrent_futures = concurrent.futures


def _run_with_timeout(
    func,
    *args,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """在线程池中执行 func，超时抛内置 TimeoutError。

    Args:
        func: 要调用的函数
        *args: 传给 func 的位置参数
        timeout: 超时秒数；None 时取 Config.DATA_IMPORT_TIMEOUT
    """
    actual_timeout = timeout if timeout is not None else Config.DATA_IMPORT_TIMEOUT
    with concurrent_futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=actual_timeout)
        except concurrent_futures.TimeoutError as e:
            # 取消 future（仅当未开始时生效；已运行中的线程无法真正中断）
            future.cancel()
            raise TimeoutError(f"触发器执行超时（{actual_timeout}s）") from e


def trigger_csv_evaluate(csv_path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发 CSV 批量评价：调用 adapter.bulk_evaluate_csv。

    Args:
        csv_path: 部署后的 CSV 文件路径
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.bulk_evaluate_csv, csv_path, timeout=timeout)


def trigger_shapefile_precompute(
    target_dir: str,
    manifest: Dict[str, Any],
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """触发 shapefile 预计算：调用 adapter.precompute_stability。

    Args:
        target_dir: shapefile 解压部署目录
        manifest: 包含 current_year/history_years/years/current_filename/history_filenames 的字典
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.precompute_stability, target_dir, manifest, timeout=timeout)


def trigger_dat_check(target_dir: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """触发 .dat 部署校验：调用 adapter.check_grade_eval_deployment。

    注意：target_dir 参数保留用于与其他触发器签名一致（API 路由层统一调用），
    但不传给 adapter —— check_grade_eval_deployment() 无参数，
    FarmlandGradeRunner 内部从配置解析 .dat 路径。

    Args:
        target_dir: .dat 部署目录（仅用于日志/上下文一致性）
        timeout: 超时秒数（None 时用 Config.DATA_IMPORT_TIMEOUT）
    """
    return _run_with_timeout(core_engine.check_grade_eval_deployment, timeout=timeout)
```

## Step 4: 运行测试验证通过

```bash
d:\miniconda3\python.exe -m pytest tests/test_data_trigger.py -v
```

预期：全部 PASS（7 个测试）

## Step 5: 提交

```bash
git add framework/upload/data_trigger.py tests/test_data_trigger.py
git commit -m "feat: add data import trigger with timeout control"
```

## 全局约束（binds this task）

- 超时机制：`concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=DATA_IMPORT_TIMEOUT)`
- 超时异常类型：内置 `TimeoutError`（捕获 `concurrent.futures.TimeoutError` 后转换）
- 透传原则：trigger 不解释 adapter 返回字典（成功/错误字典均原样返回）
- 异常冒泡：adapter 调用前后的非 adapter 异常向上冒泡到 API 路由层
- `trigger_dat_check` 的 target_dir 保留但不传给 adapter
- 不修改 adapter / config / 其他已存在模块
- 仅依赖标准库（concurrent.futures, typing）+ 项目内 framework.config / framework.core_engine.adapter

## 环境提示

- 用 `d:\miniconda3\python.exe -m pytest` 运行测试
- 测试用 monkeypatch 替换 `data_trigger.core_engine` 的方法，不依赖真实模型/数据库
- 超时测试用 `timeout=0.1` + `time.sleep(10)` 模拟，避免真正等待 600s

## 风险信号自报项（回报时逐条回答）

1. 是否偏离 brief 代码？（任何"改进"或重构都需说明）
2. 是否跳过 RED？
3. 测试是否全部 PASS？数量？
4. 是否只修改允许文件（data_trigger.py + test_data_trigger.py）？
5. 是否提交了不该提交的文件？
6. 是否引入非预期依赖？
7. 是否满足全局约束（7 条）？
8. 自检项：3 个触发函数 + 1 个辅助函数 + 7 个测试？
