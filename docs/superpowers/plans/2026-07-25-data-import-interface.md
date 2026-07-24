---
change: add-data-import-interface
design-doc: docs/superpowers/specs/2026-07-25-data-import-interface-design.md
base-ref: ce3c7c2fe3d0e2d7c1c7169141b60cc37d477d3d
---

# 数据导入接口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `POST /api/v1/data/import` HTTP API，支持 admin 用户上传 CSV / shapefile / .dat 三类专题模型数据，自动完成校验、部署、触发离线计算，替代手工 SSH + Copy-Item 流程。

**Architecture:** 单一端点 + `data_type` 字段区分类型。路由层编排 校验 → 部署（带备份） → 触发（带超时） → 审计日志 的完整流程。新建 `precompute.py` 填补稳定性模型持久化空缺；扩展 `CoreEngine` adapter 3 个方法；触发器用 `ThreadPoolExecutor` 实现跨平台超时控制；部署 + 触发为单一事务，失败从时间戳备份回滚。

**Tech Stack:** Python 3.10+, Flask, Flask-JWT-Extended, pandas, geopandas, sqlite3, concurrent.futures, zipfile, tempfile

## Global Constraints

- 单一端点 `POST /api/v1/data/import`，通过 multipart form 的 `data_type` 字段（`csv` / `shapefile` / `dat`）区分类型
- 文件大小上限 200MB（`Config.MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024`）
- 触发超时 600 秒（`Config.DATA_IMPORT_TIMEOUT = 600`），用 `ThreadPoolExecutor` 跨平台实现
- 仅 `role == 'admin'` 用户可调用，复用 `User.is_admin()`，非 admin 返回 403
- 时间戳备份目录 `<target_dir>/backup/YYYYMMDD-HHMMSS/`，保留最近 3 份（`Config.BACKUP_RETENTION_COUNT = 3`）
- 部署 + 触发单一事务，触发失败/超时从备份回滚；回滚失败记录警告并返回 500
- CSV 部署时重命名为 `test.csv`；.dat 部署时重命名为 `Farmlands_Quality_Level_Database.dat`
- shapefile 用 zip + manifest.json 上传，解压前校验总大小 ≤ 200MB、文件数 ≤ 30、无路径穿越
- shapefile 字段校验延迟到触发阶段（由 `run_all_models` 内置 `require_columns` 执行）
- 审计日志写入 `logs/data_import.log`（JSON 行格式）
- 不加并发锁，文档提示"避免并发导入"
- 数据类型 → 目标目录映射：`{'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'}`

---

## 文件结构

```
framework/
├── config.py                          # 修改：新增 4 个配置项
├── api/
│   ├── app.py                         # 修改：注册 data_import_bp
│   └── routes/
│       └── data_import.py             # 新建：POST /import 路由
├── upload/
│   ├── __init__.py                    # 修改：导出数据导入模块
│   ├── data_validator.py              # 新建：CSV/shapefile/.dat 校验器
│   ├── data_deployer.py               # 新建：备份/部署/清理/回滚
│   ├── data_trigger.py                # 新建：触发器 + 超时控制
│   └── audit_logger.py                # 新建：审计日志（JSON 行）
└── core_engine/
    └── adapter.py                     # 修改：新增 3 方法 + _ensure_data_import_imports

src/ai_culti_demo/farmland_stability/
└── precompute.py                      # 新建：run_all_models → DB + 文件持久化

tests/
├── test_precompute.py                 # 新建
├── test_data_validator.py             # 新建
├── test_data_deployer.py              # 新建
├── test_data_trigger.py               # 新建
├── test_audit_logger.py               # 新建
├── test_data_import_route.py          # 新建
└── test_data_import_integration.py    # 新建

logs/
└── .gitkeep                           # 新建：确保 logs/ 目录存在

docs/api/
└── data_import.md                     # 新建：完整 API 契约文档

data/farmland_diagnosis/README.md      # 修改：增加 API 部署说明
data/farmland_stability/README.md      # 修改：增加 zip + manifest 打包说明
bin/farmland_quality_eval/README.md    # 修改：增加 .dat API 部署说明
```

---

### Task 1: 配置项与基础设施

**对应 tasks.md：** 第 1 节（1.1-1.4）+ 第 9 节（9.3 启动校验 logs/ 目录）

**Files:**
- Modify: `framework/config.py`
- Modify: `framework/upload/__init__.py`
- Create: `logs/.gitkeep`

**Interfaces:**
- Consumes: 无
- Produces: `Config.MAX_DATA_IMPORT_SIZE`、`Config.DATA_IMPORT_TIMEOUT`、`Config.DATA_IMPORT_TARGETS`、`Config.BACKUP_RETENTION_COUNT`

- [ ] **Step 1: 在 `framework/config.py` 的 `Config` 类中新增 4 个配置项**

在 `framework/config.py` 的 `Config` 类中，`MAX_CONCURRENT_MODELS` 行之后、`get_max_concurrent` 方法之前插入：

```python
    # 数据导入接口配置
    MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024  # 200MB
    DATA_IMPORT_TIMEOUT = 600  # 秒
    DATA_IMPORT_TARGETS = {
        'csv': 'data/farmland_diagnosis',
        'shapefile': 'data/farmland_stability',
        'dat': 'bin/farmland_quality_eval',
    }
    BACKUP_RETENTION_COUNT = 3
```

- [ ] **Step 2: 在 `framework/upload/__init__.py` 中导出数据导入模块**

`framework/upload/__init__.py` 当前为空文件，写入以下内容：

```python
"""framework.upload 包：文件上传与数据导入相关模块。"""
```

- [ ] **Step 3: 创建 `logs/` 目录占位文件**

创建 `logs/.gitkeep` 文件（空文件），确保 `logs/` 目录在仓库中存在，供审计日志写入。

- [ ] **Step 4: 验证配置项可导入**

运行：

```bash
python -c "from framework.config import Config; print(Config.MAX_DATA_IMPORT_SIZE, Config.DATA_IMPORT_TIMEOUT, Config.DATA_IMPORT_TARGETS, Config.BACKUP_RETENTION_COUNT)"
```

预期输出：`209715200 600 {'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'} 3`

- [ ] **Step 5: 提交**

```bash
git add framework/config.py framework/upload/__init__.py logs/.gitkeep
git commit -m "feat: add data import config items and logs directory"
```

---

### Task 2: precompute.py 模块（稳定性模型持久化）

**对应 tasks.md：** 第 10 节（10.1-10.4）

**前置依赖：** 无（仅依赖现有 `model.py` / `storage.py`）

**Files:**
- Create: `src/ai_culti_demo/farmland_stability/precompute.py`
- Test: `tests/test_precompute.py`

**Interfaces:**
- Consumes: `run_all_models`、`save_final_results`、`MODULE_FIELDS`、`RESULT_CN`（来自 `model.py`）；`StabilityStorage`（来自 `storage.py`）
- Produces: `g_to_records(G, ...) -> List[Dict]`、`main(shapefile_dir, manifest) -> Dict`

- [ ] **Step 1: 编写 `tests/test_precompute.py` 的失败测试**

创建 `tests/test_precompute.py`：

```python
"""测试 precompute.py：g_to_records 转换 + main 完整流程。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))

import pandas as pd
from unittest.mock import patch, MagicMock


def _make_mock_gdf():
    """构造一个 mock GeoDataFrame，含 1 行 2 个模块字段。"""
    data = {
        'ID': ['P001'],
        'PJFQ': ['HN'],
        'ZHQZ': [85.5],
        'GDZLDJ': ['2'],
        'SAFE_ABS': [0.95],          # module 1
        'BAL_ABS': [0.88],            # module 2
        'BAL_REL': [0.72],            # module 2
    }
    gdf = pd.DataFrame(data)
    gdf.attrs = {}
    return gdf


def test_g_to_records_basic_mapping():
    """验证 g_to_records 将 GeoDataFrame 转换为 records 列表。"""
    from ai_culti_demo.farmland_stability.precompute import g_to_records

    G = _make_mock_gdf()
    records = g_to_records(G)

    assert len(records) == 1
    r = records[0]
    assert r['parcel_id'] == 'P001'
    assert r['region'] == 'HN'
    assert r['score'] == 85.5
    assert r['grade'] == '2'
    # module_1 字段映射
    assert '等级边界安全度' in r['module_1']
    # all_results 汇总所有模块
    assert 'module_1' in r['all_results']
    assert 'module_2' in r['all_results']


def test_g_to_records_missing_field_skipped():
    """验证 g_to_records 对缺失字段跳过而非报错。"""
    from ai_culti_demo.farmland_stability.precompute import g_to_records

    G = _make_mock_gdf()
    # 不含 module 3-9 的字段，应正常返回，只是对应模块为空字典
    records = g_to_records(G)
    r = records[0]
    assert r['module_3'] == {}
    assert r['module_9'] == {}


def test_main_full_flow_with_mocks():
    """验证 main 完整流程：run_all_models → save_results → save_final_results。"""
    from ai_culti_demo.farmland_stability import precompute

    mock_gdf = _make_mock_gdf()
    mock_storage = MagicMock()
    mock_storage.save_results.return_value = 1

    with patch.object(precompute, 'run_all_models', return_value=mock_gdf) as m_run, \
         patch.object(precompute, 'StabilityStorage', return_value=mock_storage) as m_storage_cls, \
         patch.object(precompute, 'save_final_results') as m_save_final:

        manifest = {
            'current_filename': '2024_data.shp',
            'history_filenames': ['2018_data.shp', '2021_data.shp'],
            'years': [2018, 2021, 2024],
        }
        result = precompute.main('/fake/shapefile_dir', manifest)

        assert result['status'] == 'ok'
        assert result['processed'] == 1
        assert result['saved_to_db'] == 1
        assert len(result['output_files']) == 2
        m_run.assert_called_once()
        m_storage_cls.assert_called_once()
        mock_storage.create_tables.assert_called_once()
        mock_storage.save_results.assert_called_once()
        m_save_final.assert_called_once()
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_precompute.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_stability.precompute'`

- [ ] **Step 3: 实现 `src/ai_culti_demo/farmland_stability/precompute.py`**

创建 `src/ai_culti_demo/farmland_stability/precompute.py`：

```python
"""稳定性模型离线预计算入口。

封装 run_all_models → StabilityStorage.save_results → save_final_results 完整流程。
支持 `python -m src.ai_culti_demo.farmland_stability.precompute` 命令行调用（见 data/farmland_stability/README.md）。
"""
import os
from typing import Any, Dict, List

from .model import run_all_models, save_final_results, MODULE_FIELDS, RESULT_CN
from .storage import StabilityStorage


def g_to_records(G, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ') -> List[Dict[str, Any]]:
    """将 GeoDataFrame G 转换为 StabilityStorage.save_results 期望的 records 列表。

    每条 record 包含：
    - parcel_id / region / score / grade：基础字段
    - module_1..9：各模块字段值的字典（中文 key，来自 RESULT_CN 映射）
    - all_results：汇总所有模块的字典
    """
    records = []
    for _, row in G.iterrows():
        record = {
            'parcel_id': str(row[id_col]),
            'region': row.get(region),
            'score': row.get(score),
            'grade': row.get(grade),
        }
        all_results = {}
        for module_num, fields in MODULE_FIELDS.items():
            module_data = {}
            for f in fields:
                if f in row.index:
                    module_data[RESULT_CN.get(f, f)] = row[f]
            record[f'module_{module_num}'] = module_data
            all_results[f'module_{module_num}'] = module_data
        record['all_results'] = all_results
        records.append(record)
    return records


def main(shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """完整预计算流程：run_all_models → DB 持久化 → 文件输出。

    Args:
        shapefile_dir: shapefile 所在目录
        manifest: 含 current_filename / history_filenames / years 的字典

    Returns:
        {status, processed, saved_to_db, output_files}
    """
    current_file = os.path.join(shapefile_dir, manifest['current_filename'])
    history_files = [os.path.join(shapefile_dir, f) for f in manifest['history_filenames']]
    years = manifest['years']

    G = run_all_models(current_file, history_files, years)

    # DB 持久化
    storage = StabilityStorage()
    storage.create_tables()
    records = g_to_records(G)
    saved_count = storage.save_results(records)

    # 文件持久化（shapefile + xlsx，供在线查询重载）
    shp_file = os.path.join(shapefile_dir, 'stability_results.shp')
    xlsx_file = os.path.join(shapefile_dir, 'stability_results.xlsx')
    save_final_results(G, shp_file, xlsx_file, years)

    return {
        'status': 'ok',
        'processed': len(records),
        'saved_to_db': saved_count,
        'output_files': [shp_file, xlsx_file]
    }


if __name__ == '__main__':
    # 命令行入口：从 data/farmland_stability/ 读取默认 manifest 并运行
    import json
    default_dir = 'data/farmland_stability'
    manifest_path = os.path.join(default_dir, 'manifest.json')
    if not os.path.exists(manifest_path):
        print(f"错误：未找到 {manifest_path}")
        raise SystemExit(1)
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    result = main(default_dir, manifest)
    print(result)
```

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_precompute.py -v
```

预期：3 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/ai_culti_demo/farmland_stability/precompute.py tests/test_precompute.py
git commit -m "feat: add precompute.py for stability model persistence"
```

---

### Task 3: Adapter 扩展（3 个新方法）

**对应 tasks.md：** 第 9 节（9.2）

**前置依赖：** Task 2（precompute.py 已存在，方可延迟导入）

**Files:**
- Modify: `framework/core_engine/adapter.py`
- Test: `tests/test_precompute.py` 已覆盖间接调用；本任务通过 adapter 单元测试验证

**Interfaces:**
- Consumes: `bulk_evaluate`（farmland_diagnosis.evaluation）、`precompute.main`（Task 2）、`FarmlandGradeRunner`（farmland_grade_eval.runner）
- Produces: `CoreEngine.bulk_evaluate_csv(csv_path) -> Dict`、`CoreEngine.precompute_stability(shapefile_dir, manifest) -> Dict`、`CoreEngine.check_grade_eval_deployment() -> Dict`

- [ ] **Step 1: 编写 adapter 新方法的失败测试**

在 `tests/test_precompute.py` 末尾追加（或新建 `tests/test_adapter_data_import.py`）：

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

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_precompute.py::test_adapter_bulk_evaluate_csv_delegates -v
```

预期：FAIL，报 `AttributeError: 'CoreEngine' object has no attribute 'bulk_evaluate_csv'`

- [ ] **Step 3: 在 `framework/core_engine/adapter.py` 的 `CoreEngine` 类中新增方法**

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

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_precompute.py -v
```

预期：全部 PASS（含原有 3 个 + 新增 4 个 adapter 测试）

- [ ] **Step 5: 提交**

```bash
git add framework/core_engine/adapter.py tests/test_precompute.py
git commit -m "feat: extend CoreEngine adapter with data import methods"
```

---

### Task 4: 数据校验器

**对应 tasks.md：** 第 2 节（2.1-2.5）

**前置依赖：** Task 1（Config 配置项）

**Files:**
- Create: `framework/upload/data_validator.py`
- Test: `tests/test_data_validator.py`

**Interfaces:**
- Consumes: `Config.MAX_DATA_IMPORT_SIZE`、`pandas`
- Produces: `validate_csv(file_path) -> Tuple[bool, str]`、`validate_shapefile_zip(zip_path) -> Tuple[bool, str, dict]`、`validate_dat(file_path) -> Tuple[bool, str]`

- [ ] **Step 1: 编写 `tests/test_data_validator.py` 的失败测试**

创建 `tests/test_data_validator.py`：

```python
"""测试数据校验器：CSV / shapefile zip / .dat。"""
import sys
import os
import zipfile
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload.data_validator import validate_csv, validate_shapefile_zip, validate_dat


def _write_csv(path, columns, encoding='utf-8'):
    """辅助：写入一行 CSV（仅表头 + 1 行数据）。"""
    import pandas as pd
    row = {c: '1' for c in columns}
    df = pd.DataFrame([row], columns=columns)
    df.to_csv(path, index=False, encoding=encoding)


# ---------- validate_csv ----------

REQUIRED_CSV_COLS = ['一级农业区', '二级农业区', 'pH', '有机质', '有效磷', '速效钾',
                     '容重', '耕层质地', '灌溉能力', '排水能力', '地形部位',
                     '质地构型', '有效土层', '耕层厚度']


def test_validate_csv_success_utf8():
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', encoding='utf-8') as f:
        _write_csv(f.name, REQUIRED_CSV_COLS)
        path = f.name
    ok, msg = validate_csv(path)
    assert ok is True
    assert msg == ''
    os.unlink(path)


def test_validate_csv_success_gbk():
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        path = f.name
    _write_csv(path, REQUIRED_CSV_COLS, encoding='gbk')
    ok, msg = validate_csv(path)
    assert ok is True
    os.unlink(path)


def test_validate_csv_missing_column():
    cols = REQUIRED_CSV_COLS.copy()
    cols.remove('有效磷')
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', encoding='utf-8') as f:
        _write_csv(f.name, cols)
        path = f.name
    ok, msg = validate_csv(path)
    assert ok is False
    assert '有效磷' in msg
    os.unlink(path)


def test_validate_csv_unparseable():
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        f.write(b'\xff\xfe\x00\x01\x02')  # 非 UTF-8/GBK 内容
        path = f.name
    ok, msg = validate_csv(path)
    assert ok is False
    os.unlink(path)


# ---------- validate_dat ----------

def test_validate_dat_success():
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        f.write(b'\x00\x01\x02\x03')
        path = f.name
    ok, msg = validate_dat(path)
    assert ok is True
    os.unlink(path)


def test_validate_dat_empty():
    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
        f.write(b'')
        path = f.name
    ok, msg = validate_dat(path)
    assert ok is False
    assert '空' in msg
    os.unlink(path)


# ---------- validate_shapefile_zip ----------

def _make_valid_manifest():
    return {
        'current_year': 2024,
        'history_years': [2018, 2021],
        'years': [2018, 2021, 2024],
        'current_filename': '2024_data.shp',
        'history_filenames': ['2018_data.shp', '2021_data.shp'],
    }


def _write_shapefile_zip(zip_path, manifest, components=('.shp', '.cpg', '.dbf', '.prj', '.shx')):
    """构造合法 shapefile zip。"""
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('manifest.json', json.dumps(manifest))
        # 为 current + history 每个 shapefile 写入 5 组件
        for shp_name in [manifest['current_filename']] + manifest['history_filenames']:
            base = os.path.splitext(shp_name)[0]
            for ext in components:
                zf.writestr(f'{base}{ext}', b'fake_content')


def test_validate_shapefile_zip_success():
    manifest = _make_valid_manifest()
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
        zip_path = f.name
    _write_shapefile_zip(zip_path, manifest)

    ok, msg, returned_manifest = validate_shapefile_zip(zip_path)
    assert ok is True
    assert returned_manifest['current_filename'] == '2024_data.shp'
    os.unlink(zip_path)


def test_validate_shapefile_zip_missing_manifest():
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
        zip_path = f.name
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('2024_data.shp', b'fake')

    ok, msg, manifest = validate_shapefile_zip(zip_path)
    assert ok is False
    assert 'manifest' in msg
    os.unlink(zip_path)


def test_validate_shapefile_zip_incomplete_components():
    manifest = _make_valid_manifest()
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
        zip_path = f.name
    # 只写 .shp 不写 .dbf
    _write_shapefile_zip(zip_path, manifest, components=('.shp',))

    ok, msg, _ = validate_shapefile_zip(zip_path)
    assert ok is False
    assert 'dbf' in msg or '组件' in msg
    os.unlink(zip_path)


def test_validate_shapefile_zip_path_traversal():
    manifest = _make_valid_manifest()
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
        zip_path = f.name
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('manifest.json', json.dumps(manifest))
        zf.writestr('../evil.shp', b'fake')  # 路径穿越

    ok, msg, _ = validate_shapefile_zip(zip_path)
    assert ok is False
    assert '路径' in msg or '非法' in msg
    os.unlink(zip_path)


def test_validate_shapefile_zip_manifest_missing_field():
    manifest = _make_valid_manifest()
    del manifest['years']  # 缺字段
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
        zip_path = f.name
    _write_shapefile_zip(zip_path, manifest)

    ok, msg, _ = validate_shapefile_zip(zip_path)
    assert ok is False
    assert 'years' in msg or '字段' in msg
    os.unlink(zip_path)
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_data_validator.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'framework.upload.data_validator'`

- [ ] **Step 3: 实现 `framework/upload/data_validator.py`**

创建 `framework/upload/data_validator.py`：

```python
"""数据导入校验器：CSV / shapefile zip / .dat。

校验仅检查文件结构和必需字段，不触发离线计算。
- CSV：校验 14 项必需列（UTF-8 失败回退 GBK）
- shapefile zip：校验 manifest + 5 组件完整性 + 防 zip bomb + 路径穿越
- .dat：校验非空且 ≤ 200MB
"""
import os
import zipfile
import json
from typing import Tuple, Dict, Any

import pandas as pd

from framework.config import Config

# CSV 必需的 14 列（中文表头，与 farmland_diagnosis/config.py 的 COLUMN_RENAME key 一致）
CSV_REQUIRED_COLUMNS = [
    '一级农业区', '二级农业区', 'pH', '有机质', '有效磷', '速效钾',
    '容重', '耕层质地', '灌溉能力', '排水能力', '地形部位',
    '质地构型', '有效土层', '耕层厚度',
]

# manifest.json 必需字段
MANIFEST_REQUIRED_FIELDS = ['current_year', 'history_years', 'years', 'current_filename', 'history_filenames']

# shapefile 5 组件
SHP_COMPONENTS = ['.shp', '.cpg', '.dbf', '.prj', '.shx']

# zip 安全限制
ZIP_MAX_TOTAL_SIZE = Config.MAX_DATA_IMPORT_SIZE  # 200MB
ZIP_MAX_FILE_COUNT = 30


def validate_csv(file_path: str) -> Tuple[bool, str]:
    """校验 CSV 文件包含全部 14 项必需列。

    Returns:
        (ok, error_msg): ok=True 时 error_msg 为空字符串
    """
    try:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', nrows=1)
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding='gbk', nrows=1)
    except Exception as e:
        return False, f"CSV 文件解析失败: {e}"

    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"CSV 缺少必需列: {missing}"
    return True, ''


def validate_dat(file_path: str) -> Tuple[bool, str]:
    """校验 .dat 文件非空且大小 ≤ 200MB。

    Returns:
        (ok, error_msg)
    """
    size = os.path.getsize(file_path)
    if size == 0:
        return False, ".dat 文件为空"
    if size > Config.MAX_DATA_IMPORT_SIZE:
        return False, f".dat 文件大小超过 {Config.MAX_DATA_IMPORT_SIZE // (1024 * 1024)}MB 限制"
    return True, ''


def validate_shapefile_zip(zip_path: str) -> Tuple[bool, str, Dict[str, Any]]:
    """校验 shapefile zip 包完整性。

    校验项：
    1. 解压前：总大小 ≤ 200MB、文件数 ≤ 30、无路径穿越
    2. 解压后：manifest.json 存在且字段完整
    3. 每期 shapefile 5 组件齐全

    Returns:
        (ok, error_msg, manifest): ok=True 时 manifest 为解析后的字典；ok=False 时 manifest 为 {}
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infos = zf.infolist()

            # 1. 文件数校验
            if len(infos) > ZIP_MAX_FILE_COUNT:
                return False, f"zip 包文件数超过 {ZIP_MAX_FILE_COUNT} 限制", {}

            # 2. 总大小校验（解压后）
            total_size = sum(i.file_size for i in infos)
            if total_size > ZIP_MAX_TOTAL_SIZE:
                return False, f"zip 包解压后总大小超过 {ZIP_MAX_TOTAL_SIZE // (1024 * 1024)}MB 限制", {}

            # 3. 路径穿越校验
            for info in infos:
                name = info.filename
                if '..' in name or name.startswith('/') or name.startswith('\\'):
                    return False, f"zip 包含非法路径: {name}", {}

            # 4. manifest.json 校验
            manifest_names = [n for n in zf.namelist() if n.endswith('manifest.json')]
            if not manifest_names:
                return False, "zip 包缺少 manifest.json", {}

            with zf.open(manifest_names[0]) as mf:
                try:
                    manifest = json.loads(mf.read().decode('utf-8'))
                except json.JSONDecodeError as e:
                    return False, f"manifest.json 解析失败: {e}", {}

            missing_fields = [f for f in MANIFEST_REQUIRED_FIELDS if f not in manifest]
            if missing_fields:
                return False, f"manifest.json 缺少字段: {missing_fields}", {}

            # 5. shapefile 5 组件校验
            all_names = zf.namelist()
            all_basenames = set()
            for n in all_names:
                base, ext = os.path.splitext(n)
                if ext.lower() in SHP_COMPONENTS:
                    all_basenames.add(base)

            declared_shps = [manifest['current_filename']] + list(manifest['history_filenames'])
            for shp_name in declared_shps:
                base = os.path.splitext(shp_name)[0]
                for ext in SHP_COMPONENTS:
                    expected = f'{base}{ext}'
                    # 支持同名文件在不同子目录，只要存在即可
                    found = any(n.endswith(expected) for n in all_names)
                    if not found:
                        return False, f"shapefile 组件不完整，缺少: {expected}", {}

            return True, '', manifest

    except zipfile.BadZipFile as e:
        return False, f"zip 文件损坏: {e}", {}
    except Exception as e:
        return False, f"zip 校验失败: {e}", {}
```

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_data_validator.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add framework/upload/data_validator.py tests/test_data_validator.py
git commit -m "feat: add data validators for CSV/shapefile/dat"
```

---

### Task 5: 数据部署器

**对应 tasks.md：** 第 3 节（3.1-3.8）

**前置依赖：** Task 1（Config.BACKUP_RETENTION_COUNT）

**Files:**
- Create: `framework/upload/data_deployer.py`
- Test: `tests/test_data_deployer.py`

**Interfaces:**
- Consumes: `Config.BACKUP_RETENTION_COUNT`
- Produces:
  - `backup_existing(target_dir) -> Optional[str]`：返回备份目录路径或 None
  - `deploy_csv(src_path, target_dir) -> str`：返回部署路径（`test.csv`）
  - `deploy_shapefile(zip_path, target_dir, manifest) -> List[str]`：返回部署文件名列表
  - `deploy_dat(src_path, target_dir) -> str`：返回部署路径（`Farmlands_Quality_Level_Database.dat`）
  - `cleanup_backups(target_dir, keep=3)`
  - `restore_from_backup(target_dir) -> bool`

- [ ] **Step 1: 编写 `tests/test_data_deployer.py` 的失败测试**

创建 `tests/test_data_deployer.py`：

```python
"""测试数据部署器：备份、部署、清理、回滚。"""
import sys
import os
import zipfile
import json
import tempfile
import shutil
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload.data_deployer import (
    backup_existing, deploy_csv, deploy_shapefile, deploy_dat,
    cleanup_backups, restore_from_backup,
)


def _create_target_dir_with_files(tmpdir, filenames=('test.csv',)):
    """在 tmpdir 下创建文件，返回 tmpdir 路径。"""
    for name in filenames:
        with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
            f.write('old_data')
    return tmpdir


def test_backup_existing_no_files():
    """首次部署（无现有文件）返回 None。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = backup_existing(tmpdir)
        assert result is None


def test_backup_existing_with_files():
    """有现有文件时移动到 backup/ 时间戳目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        _create_target_dir_with_files(tmpdir, ('test.csv', 'other.csv'))
        result = backup_existing(tmpdir)
        assert result is not None
        assert os.path.basename(result)  # 时间戳目录名
        assert os.path.exists(os.path.join(result, 'test.csv'))
        assert os.path.exists(os.path.join(result, 'other.csv'))
        # 原文件已移走
        assert not os.path.exists(os.path.join(tmpdir, 'test.csv'))


def test_backup_existing_excludes_readme_and_backup_dir():
    """备份时排除 README.md 和 backup/ 子目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        with open(os.path.join(tmpdir, 'README.md'), 'w') as f:
            f.write('readme')
        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
            f.write('data')
        os.makedirs(os.path.join(tmpdir, 'backup', '20240101-000000'))

        result = backup_existing(tmpdir)
        assert result is not None
        # README 不应被备份
        assert not os.path.exists(os.path.join(result, 'README.md'))
        # test.csv 应被备份
        assert os.path.exists(os.path.join(result, 'test.csv'))
        # 原 README 仍在
        assert os.path.exists(os.path.join(tmpdir, 'README.md'))


def test_deploy_csv_renames_to_test_csv():
    """CSV 部署时重命名为 test.csv。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'upload', 'mydata.csv')
        os.makedirs(os.path.dirname(src))
        with open(src, 'w') as f:
            f.write('csv_content')
        target = os.path.join(tmpdir, 'target')

        deployed = deploy_csv(src, target)
        assert deployed.endswith('test.csv')
        with open(deployed, 'r') as f:
            assert f.read() == 'csv_content'


def test_deploy_dat_renames_to_fixed_name():
    """dat 部署时重命名为 Farmlands_Quality_Level_Database.dat。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'upload', 'custom.dat')
        os.makedirs(os.path.dirname(src))
        with open(src, 'wb') as f:
            f.write(b'\x00\x01')
        target = os.path.join(tmpdir, 'target')

        deployed = deploy_dat(src, target)
        assert deployed.endswith('Farmlands_Quality_Level_Database.dat')
        assert os.path.exists(deployed)


def test_deploy_shapefile_extracts_zip():
    """shapefile zip 部署时解压到目标目录。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, 'upload.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr('2024_data.shp', b'shp')
            zf.writestr('2024_data.dbf', b'dbf')
            zf.writestr('manifest.json', b'{}')
        target = os.path.join(tmpdir, 'target')
        manifest = {'current_filename': '2024_data.shp', 'history_filenames': []}

        deployed = deploy_shapefile(zip_path, target, manifest)
        assert '2024_data.shp' in deployed
        assert os.path.exists(os.path.join(target, '2024_data.shp'))
        assert os.path.exists(os.path.join(target, 'manifest.json'))


def test_cleanup_backups_keeps_latest_3():
    """连续 4 次备份后仅保留最近 3 份。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        backup_dir = os.path.join(tmpdir, 'backup')
        os.makedirs(backup_dir)
        # 创建 4 个时间戳目录（倒序命名使最新在前）
        for ts in ['20240104-000000', '20240103-000000', '20240102-000000', '20240101-000000']:
            d = os.path.join(backup_dir, ts)
            os.makedirs(d)
            with open(os.path.join(d, 'test.csv'), 'w') as f:
                f.write(ts)

        cleanup_backups(tmpdir, keep=3)
        remaining = sorted(os.listdir(backup_dir))
        assert len(remaining) == 3
        assert '20240101-000000' not in remaining  # 最旧的被删除
        assert '20240104-000000' in remaining       # 最新的保留


def test_restore_from_backup_success():
    """回滚：从最近备份恢复文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 先部署旧文件
        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
            f.write('old')
        # 备份
        backup_path = backup_existing(tmpdir)
        # 部署新文件
        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
            f.write('new')
        # 回滚
        ok = restore_from_backup(tmpdir)
        assert ok is True
        with open(os.path.join(tmpdir, 'test.csv'), 'r') as f:
            assert f.read() == 'old'


def test_restore_from_backup_no_backup():
    """无备份时回滚返回 False。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        ok = restore_from_backup(tmpdir)
        assert ok is False
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_data_deployer.py -v
```

预期：FAIL，报 `ModuleNotFoundError`

- [ ] **Step 3: 实现 `framework/upload/data_deployer.py`**

创建 `framework/upload/data_deployer.py`：

```python
"""数据部署器：备份、部署、清理、回滚。

部署语义：覆盖目标目录下的现有数据文件，保留原文件名约定（test.csv / Farmlands_Quality_Level_Database.dat）。
备份语义：将现有文件移动到 <target_dir>/backup/YYYYMMDD-HHMMSS/，保留最近 N 份。
"""
import os
import shutil
import zipfile
from datetime import datetime
from typing import Optional, List

from framework.config import Config

# 备份时排除的文件/目录名
BACKUP_EXCLUDES = {'README.md', 'backup'}


def backup_existing(target_dir: str) -> Optional[str]:
    """将 target_dir 下的现有数据文件移动到 backup/ 时间戳子目录。

    排除 README.md 和 backup/ 子目录。无文件时返回 None。

    Returns:
        备份目录的绝对路径，或 None（无文件可备份）
    """
    if not os.path.exists(target_dir):
        return None

    files_to_backup = [
        f for f in os.listdir(target_dir)
        if f not in BACKUP_EXCLUDES and os.path.isfile(os.path.join(target_dir, f))
    ]
    if not files_to_backup:
        return None

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir = os.path.join(target_dir, 'backup', timestamp)
    os.makedirs(backup_dir, exist_ok=True)

    for f in files_to_backup:
        src = os.path.join(target_dir, f)
        dst = os.path.join(backup_dir, f)
        shutil.move(src, dst)

    return backup_dir


def deploy_csv(src_path: str, target_dir: str) -> str:
    """将 CSV 部署到 target_dir/test.csv（固定文件名）。

    Returns:
        部署后的绝对路径
    """
    os.makedirs(target_dir, exist_ok=True)
    dst = os.path.join(target_dir, 'test.csv')
    shutil.copy2(src_path, dst)
    return dst


def deploy_dat(src_path: str, target_dir: str) -> str:
    """将 .dat 部署到 target_dir/Farmlands_Quality_Level_Database.dat（固定文件名）。

    Returns:
        部署后的绝对路径
    """
    os.makedirs(target_dir, exist_ok=True)
    dst = os.path.join(target_dir, 'Farmlands_Quality_Level_Database.dat')
    shutil.copy2(src_path, dst)
    return dst


def deploy_shapefile(zip_path: str, target_dir: str, manifest: dict) -> List[str]:
    """解压 shapefile zip 到 target_dir。

    Returns:
        部署的文件名列表
    """
    os.makedirs(target_dir, exist_ok=True)
    deployed_files = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for info in zf.infolist():
            # 跳过目录条目
            if info.is_dir():
                continue
            # 解压到 target_dir（扁平化，不保留 zip 内子目录结构）
            filename = os.path.basename(info.filename)
            if not filename:
                continue
            dst = os.path.join(target_dir, filename)
            with zf.open(info) as src, open(dst, 'wb') as dst_f:
                dst_f.write(src.read())
            deployed_files.append(filename)
    return deployed_files


def cleanup_backups(target_dir: str, keep: int = None) -> None:
    """扫描 target_dir/backup/ 下时间戳目录，按目录名倒序保留前 keep 份。

    Args:
        target_dir: 目标目录
        keep: 保留份数，默认使用 Config.BACKUP_RETENTION_COUNT
    """
    if keep is None:
        keep = Config.BACKUP_RETENTION_COUNT

    backup_root = os.path.join(target_dir, 'backup')
    if not os.path.exists(backup_root):
        return

    subdirs = sorted([d for d in os.listdir(backup_root)
                      if os.path.isdir(os.path.join(backup_root, d))], reverse=True)

    for old_dir in subdirs[keep:]:
        old_path = os.path.join(backup_root, old_dir)
        shutil.rmtree(old_path, ignore_errors=True)


def restore_from_backup(target_dir: str) -> bool:
    """从最近一次 backup/ 子目录恢复文件到 target_dir。

    Returns:
        True 表示恢复成功；False 表示无备份或恢复失败
    """
    backup_root = os.path.join(target_dir, 'backup')
    if not os.path.exists(backup_root):
        return False

    subdirs = sorted([d for d in os.listdir(backup_root)
                      if os.path.isdir(os.path.join(backup_root, d))], reverse=True)
    if not subdirs:
        return False

    latest_backup = os.path.join(backup_root, subdirs[0])
    try:
        for f in os.listdir(latest_backup):
            src = os.path.join(latest_backup, f)
            dst = os.path.join(target_dir, f)
            if os.path.isfile(src):
                shutil.move(src, dst)
        # 恢复后删除已空的备份目录
        os.rmdir(latest_backup)
        return True
    except Exception:
        return False
```

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_data_deployer.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add framework/upload/data_deployer.py tests/test_data_deployer.py
git commit -m "feat: add data deployer with backup and rollback"
```

---

### Task 6: 审计日志

**对应 tasks.md：** 第 5 节（5.1-5.4）

**前置依赖：** 无（仅依赖标准库 `json` / `os`）

**Files:**
- Create: `framework/upload/audit_logger.py`
- Test: `tests/test_audit_logger.py`

**Interfaces:**
- Consumes: 无
- Produces: `log_data_import(username, data_type, filename, deployed_path, trigger_result, success, message='', restored_from_backup=False)`

- [ ] **Step 1: 编写 `tests/test_audit_logger.py` 的失败测试**

创建 `tests/test_audit_logger.py`：

```python
"""测试审计日志写入。"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload.audit_logger import log_data_import, set_log_path


def test_log_data_import_success():
    """成功导入审计条目字段完整性。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='csv',
            filename='mydata.csv',
            deployed_path='/data/farmland_diagnosis/test.csv',
            trigger_result={'status': 'ok', 'processed': 100},
            success=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry['username'] == 'admin'
        assert entry['data_type'] == 'csv'
        assert entry['filename'] == 'mydata.csv'
        assert entry['deployed_path'] == '/data/farmland_diagnosis/test.csv'
        assert entry['success'] is True
        assert entry['restored_from_backup'] is False
        assert 'timestamp' in entry
        assert 'trigger_result' in entry


def test_log_data_import_failure_with_rollback():
    """失败 + 回滚条目包含 restored_from_backup。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='shapefile',
            filename='data.zip',
            deployed_path='/data/farmland_stability/',
            trigger_result={'status': 'error', 'error': {'message': '字段缺失'}},
            success=False,
            message='触发失败已回滚',
            restored_from_backup=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            entry = json.loads(f.readline())
        assert entry['success'] is False
        assert entry['restored_from_backup'] is True
        assert '回滚' in entry['message']


def test_log_data_import_appends_multiple():
    """多次调用追加写入（不覆盖）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        for i in range(3):
            log_data_import(
                username='admin', data_type='csv', filename=f'f{i}.csv',
                deployed_path='/p', trigger_result={}, success=True,
            )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 3
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_audit_logger.py -v
```

预期：FAIL，报 `ModuleNotFoundError`

- [ ] **Step 3: 实现 `framework/upload/audit_logger.py`**

创建 `framework/upload/audit_logger.py`：

```python
"""审计日志：数据导入操作的结构化日志（JSON 行格式）。

日志写入 logs/data_import.log，每行一条 JSON 记录。
"""
import os
import json
from datetime import datetime
from typing import Any, Dict, Optional

# 默认日志路径（可被 set_log_path 覆盖，便于测试）
_DEFAULT_LOG_PATH = os.path.join('logs', 'data_import.log')
_log_path = _DEFAULT_LOG_PATH


def set_log_path(path: str) -> None:
    """覆盖日志文件路径（主要用于测试）。"""
    global _log_path
    _log_path = path


def log_data_import(
    username: str,
    data_type: str,
    filename: str,
    deployed_path: str,
    trigger_result: Dict[str, Any],
    success: bool,
    message: str = '',
    restored_from_backup: bool = False,
) -> None:
    """写入一条数据导入审计日志。

    Args:
        username: 操作人用户名
        data_type: 数据类型（csv/shapefile/dat）
        filename: 上传的原文件名
        deployed_path: 部署后的路径
        trigger_result: 触发器返回的结果字典
        success: 是否成功
        message: 附加消息（失败原因等）
        restored_from_backup: 是否已从备份回滚
    """
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'username': username,
        'data_type': data_type,
        'filename': filename,
        'deployed_path': deployed_path,
        'trigger_result': trigger_result,
        'success': success,
        'message': message,
        'restored_from_backup': restored_from_backup,
    }

    os.makedirs(os.path.dirname(os.path.abspath(_log_path)), exist_ok=True)
    with open(_log_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
```

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_audit_logger.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add framework/upload/audit_logger.py tests/test_audit_logger.py
git commit -m "feat: add audit logger for data import operations"
```

---

### Task 7: 触发器封装

**对应 tasks.md：** 第 4 节（4.1-4.6）

**前置依赖：** Task 3（adapter 3 方法）、Task 1（Config.DATA_IMPORT_TIMEOUT）

**Files:**
- Create: `framework/upload/data_trigger.py`
- Test: `tests/test_data_trigger.py`

**Interfaces:**
- Consumes: `core_engine.bulk_evaluate_csv`、`core_engine.precompute_stability`、`core_engine.check_grade_eval_deployment`、`Config.DATA_IMPORT_TIMEOUT`
- Produces:
  - `trigger_csv_evaluate(csv_path) -> Dict`
  - `trigger_shapefile_precompute(target_dir, manifest) -> Dict`
  - `trigger_dat_check() -> Dict`
  - 超时抛 `TimeoutError`

- [ ] **Step 1: 编写 `tests/test_data_trigger.py` 的失败测试**

创建 `tests/test_data_trigger.py`：

```python
"""测试触发器：成功、错误字典、异常、超时。"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from framework.upload.data_trigger import (
    trigger_csv_evaluate, trigger_shapefile_precompute, trigger_dat_check,
)


def test_trigger_csv_evaluate_success():
    """CSV 触发成功返回结果字典。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        mock_engine.bulk_evaluate_csv.return_value = {'status': 'ok', 'processed': 50, 'errors': []}
        result = trigger_csv_evaluate('/fake/test.csv')
        assert result['status'] == 'ok'
        assert result['processed'] == 50
        mock_engine.bulk_evaluate_csv.assert_called_once_with('/fake/test.csv')


def test_trigger_csv_evaluate_error_dict():
    """CSV 触发返回错误字典（不抛异常）。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        mock_engine.bulk_evaluate_csv.return_value = {'status': 'error', 'error': {'code': 'X', 'message': 'boom'}}
        result = trigger_csv_evaluate('/fake/test.csv')
        assert result['status'] == 'error'


def test_trigger_csv_evaluate_exception():
    """CSV 触发抛异常时向上传播。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        mock_engine.bulk_evaluate_csv.side_effect = RuntimeError('unexpected')
        with pytest.raises(RuntimeError, match='unexpected'):
            trigger_csv_evaluate('/fake/test.csv')


def test_trigger_shapefile_precompute_success():
    """shapefile 触发成功。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        mock_engine.precompute_stability.return_value = {'status': 'ok', 'processed': 100, 'saved_to_db': 100}
        manifest = {'current_filename': '2024.shp', 'history_filenames': ['2018.shp'], 'years': [2018, 2024]}
        result = trigger_shapefile_precompute('/fake/dir', manifest)
        assert result['status'] == 'ok'
        mock_engine.precompute_stability.assert_called_once_with('/fake/dir', manifest)


def test_trigger_dat_check_success():
    """dat 触发返回 deployment_ok。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        mock_engine.check_grade_eval_deployment.return_value = {'deployment_ok': True, 'detail': {'ready': True}}
        result = trigger_dat_check()
        assert result['deployment_ok'] is True


def test_trigger_csv_evaluate_timeout():
    """触发超时抛 TimeoutError。"""
    with patch('framework.upload.data_trigger.core_engine') as mock_engine:
        # 模拟长时间执行
        def slow_func(*args, **kwargs):
            time.sleep(10)
            return {'status': 'ok'}

        mock_engine.bulk_evaluate_csv.side_effect = slow_func
        with patch('framework.upload.data_trigger.Config') as mock_config:
            mock_config.DATA_IMPORT_TIMEOUT = 0.1  # 100ms 超时
            with pytest.raises(TimeoutError):
                trigger_csv_evaluate('/fake/test.csv')
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_data_trigger.py -v
```

预期：FAIL，报 `ModuleNotFoundError`

- [ ] **Step 3: 实现 `framework/upload/data_trigger.py`**

创建 `framework/upload/data_trigger.py`：

```python
"""触发器：封装离线计算调用 + 超时控制。

通过 CoreEngine adapter 调用三类离线计算：
- CSV → bulk_evaluate_csv
- shapefile → precompute_stability
- .dat → check_grade_eval_deployment

超时用 ThreadPoolExecutor 实现（跨平台，Windows 不支持 signal.alarm）。
"""
import concurrent.futures

from framework.config import Config
from framework.core_engine.adapter import core_engine


def _run_with_timeout(func, *args, timeout=None) -> dict:
    """用 ThreadPoolExecutor 包裹 func，超时抛 TimeoutError。

    注意：超时后后台线程仍在运行（Python 无法强制终止线程），
    但结果会被丢弃（DB 写入幂等，无副作用）。
    """
    if timeout is None:
        timeout = Config.DATA_IMPORT_TIMEOUT

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"触发超时（{timeout}s）")


def trigger_csv_evaluate(csv_path: str) -> dict:
    """触发 CSV 批量评价。

    Args:
        csv_path: 部署后的 CSV 路径（test.csv）

    Returns:
        bulk_evaluate 返回的结果字典
    """
    return _run_with_timeout(core_engine.bulk_evaluate_csv, csv_path)


def trigger_shapefile_precompute(target_dir: str, manifest: dict) -> dict:
    """触发 shapefile 稳定性预计算。

    Args:
        target_dir: shapefile 部署目录
        manifest: manifest 字典

    Returns:
        precompute.main 返回的结果摘要
    """
    return _run_with_timeout(core_engine.precompute_stability, target_dir, manifest)


def trigger_dat_check() -> dict:
    """触发 .dat 部署校验（不调用 exe，仅检查文件存在性）。

    Returns:
        {'deployment_ok': bool, 'detail': ...}
    """
    return _run_with_timeout(core_engine.check_grade_eval_deployment)
```

- [ ] **Step 4: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_data_trigger.py -v
```

预期：全部 PASS

- [ ] **Step 5: 提交**

```bash
git add framework/upload/data_trigger.py tests/test_data_trigger.py
git commit -m "feat: add data triggers with timeout control"
```

---

### Task 8: API 路由

**对应 tasks.md：** 第 6 节（6.1-6.12）

**前置依赖：** Task 4（validator）、Task 5（deployer）、Task 6（audit_logger）、Task 7（trigger）

**Files:**
- Create: `framework/api/routes/data_import.py`
- Modify: `framework/api/app.py`
- Test: `tests/test_data_import_route.py`

**Interfaces:**
- Consumes: `validate_csv` / `validate_shapefile_zip` / `validate_dat`、`backup_existing` / `deploy_csv` / `deploy_shapefile` / `deploy_dat` / `cleanup_backups` / `restore_from_backup`、`trigger_csv_evaluate` / `trigger_shapefile_precompute` / `trigger_dat_check`、`log_data_import`、`Config`、`User.is_admin()`
- Produces: `data_import_bp` Blueprint，挂载到 `/api/v1/data`，提供 `POST /import`

- [ ] **Step 1: 编写 `tests/test_data_import_route.py` 的失败测试**

创建 `tests/test_data_import_route.py`：

```python
"""测试数据导入路由：鉴权、校验、部署、触发、回滚、审计。"""
import sys
import os
import io
import tempfile
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from framework.api.routes.data_import import data_import_bp
from framework.models.user import db


@pytest.fixture
def app():
    """构造测试 Flask app，内存数据库。"""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
    db.init_app(app)
    app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')
    with app.app_context():
        db.create_all()
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_token():
    """mock jwt_required 直接放行。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f):
        yield


def _make_admin_user():
    """mock User 查询返回 admin 用户。"""
    user = MagicMock()
    user.id = 1
    user.username = 'admin'
    user.is_admin.return_value = True
    return user


CSV_HEADER = '一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度\n'


def test_import_csv_success(client):
    """admin 成功上传 CSV。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_validator.validate_csv', return_value=(True, '')), \
         patch('framework.upload.data_deployer.backup_existing', return_value='/backup/20240101-000000'), \
         patch('framework.upload.data_deployer.deploy_csv', return_value='/data/farmland_diagnosis/test.csv'), \
         patch('framework.upload.data_deployer.cleanup_backups'), \
         patch('framework.upload.data_trigger.trigger_csv_evaluate', return_value={'status': 'ok', 'processed': 10}), \
         patch('framework.upload.audit_logger.log_data_import'):

        MockUser.query.get.return_value = _make_admin_user()

        data = {
            'data_type': 'csv',
            'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv'),
        }
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')

        assert resp.status_code == 200
        body = resp.get_json()
        assert body['status'] == 'ok'
        assert body['data_type'] == 'csv'
        assert body['trigger_result']['processed'] == 10


def test_import_missing_data_type(client):
    """缺 data_type 返回 400。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser:

        MockUser.query.get.return_value = _make_admin_user()
        data = {'file': (io.BytesIO(b'x'), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        assert 'data_type' in resp.get_json()['message']


def test_import_missing_file(client):
    """缺 file 返回 400。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser:

        MockUser.query.get.return_value = _make_admin_user()
        data = {'data_type': 'csv'}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        assert '文件' in resp.get_json()['message']


def test_import_non_admin_403(client):
    """非 admin 用户返回 403。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='2'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser:

        user = MagicMock()
        user.is_admin.return_value = False
        MockUser.query.get.return_value = user

        data = {'data_type': 'csv', 'file': (io.BytesIO(b'x'), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 403


def test_import_validation_failure_400(client):
    """校验失败返回 400。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_validator.validate_csv', return_value=(False, '缺少必需列: [有效磷]')):

        MockUser.query.get.return_value = _make_admin_user()
        data = {'data_type': 'csv', 'file': (io.BytesIO(b'bad'), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'


def test_import_trigger_failure_rollback_500(client):
    """触发失败回滚返回 500。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_validator.validate_csv', return_value=(True, '')), \
         patch('framework.upload.data_deployer.backup_existing', return_value='/backup/20240101'), \
         patch('framework.upload.data_deployer.deploy_csv', return_value='/data/test.csv'), \
         patch('framework.upload.data_deployer.cleanup_backups'), \
         patch('framework.upload.data_trigger.trigger_csv_evaluate', side_effect=RuntimeError('boom')), \
         patch('framework.upload.data_deployer.restore_from_backup', return_value=True), \
         patch('framework.upload.audit_logger.log_data_import'):

        MockUser.query.get.return_value = _make_admin_user()
        data = {'data_type': 'csv', 'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 500
        assert resp.get_json()['status'] == 'error'


def test_import_trigger_timeout_504(client):
    """触发超时返回 504。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_validator.validate_csv', return_value=(True, '')), \
         patch('framework.upload.data_deployer.backup_existing', return_value='/backup/20240101'), \
         patch('framework.upload.data_deployer.deploy_csv', return_value='/data/test.csv'), \
         patch('framework.upload.data_deployer.cleanup_backups'), \
         patch('framework.upload.data_trigger.trigger_csv_evaluate', side_effect=TimeoutError('600s')), \
         patch('framework.upload.data_deployer.restore_from_backup', return_value=True), \
         patch('framework.upload.audit_logger.log_data_import'):

        MockUser.query.get.return_value = _make_admin_user()
        data = {'data_type': 'csv', 'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 504
        assert '超时' in resp.get_json()['message']


def test_import_invalid_data_type(client):
    """无效 data_type 返回 400。"""
    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser:

        MockUser.query.get.return_value = _make_admin_user()
        data = {'data_type': 'invalid', 'file': (io.BytesIO(b'x'), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
```

- [ ] **Step 2: 运行测试验证失败**

运行：

```bash
python -m pytest tests/test_data_import_route.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'framework.api.routes.data_import'`

- [ ] **Step 3: 实现 `framework/api/routes/data_import.py`**

创建 `framework/api/routes/data_import.py`：

```python
"""数据导入路由：POST /api/v1/data/import

编排流程：鉴权 → 校验 → 部署（带备份） → 触发（带超时） → 审计日志
"""
import os
import tempfile

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from framework.config import Config
from framework.models.user import User
from framework.upload.data_validator import validate_csv, validate_shapefile_zip, validate_dat
from framework.upload.data_deployer import (
    backup_existing, deploy_csv, deploy_shapefile, deploy_dat,
    cleanup_backups, restore_from_backup,
)
from framework.upload.data_trigger import (
    trigger_csv_evaluate, trigger_shapefile_precompute, trigger_dat_check,
)
from framework.upload.audit_logger import log_data_import

data_import_bp = Blueprint('data_import', __name__)

VALID_DATA_TYPES = {'csv', 'shapefile', 'dat'}


@data_import_bp.route('/import', methods=['POST'])
@jwt_required()
def import_data():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user or not user.is_admin():
        return jsonify({"status": "error", "message": "需要 admin 权限"}), 403

    # 1. 解析 multipart form
    data_type = request.form.get('data_type', '').strip().lower()
    if data_type not in VALID_DATA_TYPES:
        return jsonify({"status": "error", "message": "无效的 data_type，必须为 csv/shapefile/dat"}), 400

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "未选择文件"}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"status": "error", "message": "未选择文件"}), 400

    # 2. 文件大小校验（Content-Length + 实际读取后校验）
    content_length = request.content_length or 0
    if content_length > Config.MAX_DATA_IMPORT_SIZE:
        return jsonify({"status": "error", "message": "文件大小超过 200MB 限制"}), 413

    # 3. 临时保存上传文件
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=_get_suffix(data_type, file.filename))
    os.close(tmp_fd)
    try:
        file.save(tmp_path)
        actual_size = os.path.getsize(tmp_path)
        if actual_size > Config.MAX_DATA_IMPORT_SIZE:
            return jsonify({"status": "error", "message": "文件大小超过 200MB 限制"}), 413

        # 4. 校验
        manifest = None
        if data_type == 'csv':
            ok, msg = validate_csv(tmp_path)
        elif data_type == 'shapefile':
            ok, msg, manifest = validate_shapefile_zip(tmp_path)
        else:  # dat
            ok, msg = validate_dat(tmp_path)

        if not ok:
            return jsonify({"status": "error", "message": msg}), 400

        # 5. 部署（带备份）
        target_dir = Config.DATA_IMPORT_TARGETS[data_type]
        backup_path = backup_existing(target_dir)

        try:
            if data_type == 'csv':
                deployed_path = deploy_csv(tmp_path, target_dir)
                deployed_files = None
            elif data_type == 'shapefile':
                deployed_files = deploy_shapefile(tmp_path, target_dir, manifest)
                deployed_path = target_dir
            else:  # dat
                deployed_path = deploy_dat(tmp_path, target_dir)
                deployed_files = None

            cleanup_backups(target_dir, keep=Config.BACKUP_RETENTION_COUNT)

        except Exception as e:
            # 部署失败：从备份恢复
            if backup_path:
                restore_from_backup(target_dir)
            log_data_import(
                username=user.username, data_type=data_type, filename=file.filename,
                deployed_path=target_dir, trigger_result={}, success=False,
                message=f"部署失败: {e}", restored_from_backup=bool(backup_path),
            )
            return jsonify({"status": "error", "message": f"部署失败: {e}"}), 500

        # 6. 触发（带超时）
        trigger_result = None
        try:
            if data_type == 'csv':
                trigger_result = trigger_csv_evaluate(deployed_path)
            elif data_type == 'shapefile':
                trigger_result = trigger_shapefile_precompute(target_dir, manifest)
            else:  # dat
                trigger_result = trigger_dat_check()

            # 触发返回错误字典（非异常）
            if isinstance(trigger_result, dict) and trigger_result.get('status') == 'error':
                raise _TriggerError(trigger_result)

        except TimeoutError as e:
            # 超时回滚
            restored = restore_from_backup(target_dir) if backup_path else False
            log_data_import(
                username=user.username, data_type=data_type, filename=file.filename,
                deployed_path=deployed_path, trigger_result={}, success=False,
                message="触发超时已回滚", restored_from_backup=restored,
            )
            return jsonify({"status": "error", "message": "触发超时已回滚"}), 504

        except _TriggerError as e:
            # 触发返回错误字典 → 回滚
            restored = restore_from_backup(target_dir) if backup_path else False
            log_data_import(
                username=user.username, data_type=data_type, filename=file.filename,
                deployed_path=deployed_path, trigger_result=e.result, success=False,
                message="触发失败已回滚", restored_from_backup=restored,
            )
            return jsonify({
                "status": "error",
                "message": "触发失败已回滚",
                "trigger_error": e.result,
            }), 500

        except Exception as e:
            # 触发抛异常 → 回滚
            restored = restore_from_backup(target_dir) if backup_path else False
            log_data_import(
                username=user.username, data_type=data_type, filename=file.filename,
                deployed_path=deployed_path, trigger_result={}, success=False,
                message=f"触发异常已回滚: {e}", restored_from_backup=restored,
            )
            return jsonify({
                "status": "error",
                "message": "触发异常已回滚",
                "detail": str(e),
            }), 500

        # 7. 成功：审计 + 返回
        log_data_import(
            username=user.username, data_type=data_type, filename=file.filename,
            deployed_path=deployed_path, trigger_result=trigger_result, success=True,
        )

        response_body = {
            "status": "ok",
            "data_type": data_type,
            "backup_path": backup_path,
            "trigger_result": trigger_result,
        }
        if data_type == 'shapefile':
            response_body["deployed_files"] = deployed_files
        else:
            response_body["deployed_path"] = deployed_path

        return jsonify(response_body), 200

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


class _TriggerError(Exception):
    """触发器返回错误字典时抛出的内部异常。"""
    def __init__(self, result: dict):
        self.result = result
        super().__init__(str(result))


def _get_suffix(data_type: str, filename: str) -> str:
    """根据 data_type 和文件名确定临时文件后缀。"""
    if '.' in filename:
        return '.' + filename.rsplit('.', 1)[-1]
    if data_type == 'csv':
        return '.csv'
    if data_type == 'shapefile':
        return '.zip'
    if data_type == 'dat':
        return '.dat'
    return ''
```

- [ ] **Step 4: 在 `framework/api/app.py` 注册 Blueprint**

修改 `framework/api/app.py`，在 `report_bp` 导入行之后新增导入，在 `register_blueprint(report_bp, ...)` 行之后新增注册：

```python
from framework.api.routes.report import report_bp
from framework.api.routes.data_import import data_import_bp  # 新增
```

```python
    app.register_blueprint(report_bp, url_prefix='/api/v1/report')
    app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')  # 新增
```

- [ ] **Step 5: 运行测试验证通过**

运行：

```bash
python -m pytest tests/test_data_import_route.py -v
```

预期：全部 PASS

- [ ] **Step 6: 提交**

```bash
git add framework/api/routes/data_import.py framework/api/app.py tests/test_data_import_route.py
git commit -m "feat: add POST /api/v1/data/import route with full orchestration"
```

---

### Task 9: 集成测试

**对应 tasks.md：** 第 7 节（7.1-7.5）

**前置依赖：** Task 8（路由已实现）

**Files:**
- Create: `tests/test_data_import_integration.py`

**Interfaces:**
- Consumes: 所有 Task 1-8 的产物
- Produces: 端到端测试覆盖 CSV / shapefile / .dat 三类导入 + 回滚 + 备份保留

- [ ] **Step 1: 编写 `tests/test_data_import_integration.py`**

创建 `tests/test_data_import_integration.py`：

```python
"""端到端集成测试：使用真实临时目录 + mock adapter。

覆盖：
- CSV 上传 → 部署 → 触发 → 审计日志
- shapefile zip 上传 → 解压 → 部署 → 触发 → 审计日志
- .dat 上传 → 部署 → check_deployment → 审计日志
- 触发失败 → 回滚 → 审计日志记录回滚
- 备份保留策略：连续导入 4 次仅保留 3 份
"""
import sys
import os
import io
import json
import zipfile
import tempfile
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask

from framework.api.routes.data_import import data_import_bp
from framework.models.user import db
from framework.config import Config


@pytest.fixture
def integration_env():
    """构造完整测试环境：临时目标目录 + 临时日志路径 + Flask app。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 覆盖目标目录到临时目录
        csv_dir = os.path.join(tmpdir, 'farmland_diagnosis')
        shp_dir = os.path.join(tmpdir, 'farmland_stability')
        dat_dir = os.path.join(tmpdir, 'farmland_quality_eval')
        os.makedirs(csv_dir)
        os.makedirs(shp_dir)
        os.makedirs(dat_dir)

        original_targets = Config.DATA_IMPORT_TARGETS.copy()
        Config.DATA_IMPORT_TARGETS = {
            'csv': csv_dir,
            'shapefile': shp_dir,
            'dat': dat_dir,
        }

        log_path = os.path.join(tmpdir, 'data_import.log')
        from framework.upload import audit_logger
        audit_logger.set_log_path(log_path)

        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['TESTING'] = True
        app.config['MAX_CONTENT_LENGTH'] = 250 * 1024 * 1024
        db.init_app(app)
        app.register_blueprint(data_import_bp, url_prefix='/api/v1/data')
        with app.app_context():
            db.create_all()

        yield {
            'app': app,
            'client': app.test_client(),
            'csv_dir': csv_dir,
            'shp_dir': shp_dir,
            'dat_dir': dat_dir,
            'log_path': log_path,
        }

        Config.DATA_IMPORT_TARGETS = original_targets


def _make_admin_mock():
    """构造 mock admin 用户（is_admin() 返回 True）。"""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.username = 'admin'
    mock_user.is_admin.return_value = True
    return mock_user


CSV_HEADER = '一级农业区,二级农业区,pH,有机质,有效磷,速效钾,容重,耕层质地,灌溉能力,排水能力,地形部位,质地构型,有效土层,耕层厚度\n1,2,5,30,20,100,1.1,壤土,1,1,平原,均质,100,20\n'


def test_csv_full_flow(integration_env):
    """CSV 上传 → 部署 → 触发 → 审计日志写入。"""
    client = integration_env['client']
    csv_dir = integration_env['csv_dir']

    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_trigger.trigger_csv_evaluate',
               return_value={'status': 'ok', 'processed': 1}):

        MockUser.query.get.return_value = _make_admin_mock()

        data = {'data_type': 'csv', 'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')

    assert resp.status_code == 200
    # 验证部署到 test.csv
    assert os.path.exists(os.path.join(csv_dir, 'test.csv'))
    # 验证审计日志
    with open(integration_env['log_path'], 'r', encoding='utf-8') as f:
        entry = json.loads(f.readline())
    assert entry['success'] is True
    assert entry['data_type'] == 'csv'


def test_shapefile_full_flow(integration_env):
    """shapefile zip 上传 → 解压 → 部署 → 触发 → 审计日志。"""
    client = integration_env['client']
    shp_dir = integration_env['shp_dir']

    # 构造合法 zip
    manifest = {
        'current_year': 2024,
        'history_years': [2018, 2021],
        'years': [2018, 2021, 2024],
        'current_filename': '2024_data.shp',
        'history_filenames': ['2018_data.shp', '2021_data.shp'],
    }
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zf:
        zf.writestr('manifest.json', json.dumps(manifest))
        for shp_name in [manifest['current_filename']] + manifest['history_filenames']:
            base = os.path.splitext(shp_name)[0]
            for ext in ['.shp', '.cpg', '.dbf', '.prj', '.shx']:
                zf.writestr(f'{base}{ext}', b'fake')

    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_trigger.trigger_shapefile_precompute',
               return_value={'status': 'ok', 'processed': 50, 'saved_to_db': 50}):

        MockUser.query.get.return_value = _make_admin_mock()

        zip_buffer.seek(0)
        data = {'data_type': 'shapefile', 'file': (zip_buffer, 'data.zip')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')

    assert resp.status_code == 200
    # 验证部署
    assert os.path.exists(os.path.join(shp_dir, '2024_data.shp'))
    assert os.path.exists(os.path.join(shp_dir, 'manifest.json'))


def test_dat_full_flow(integration_env):
    """dat 上传 → 部署 → check_deployment → 审计日志。"""
    client = integration_env['client']
    dat_dir = integration_env['dat_dir']

    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_trigger.trigger_dat_check',
               return_value={'deployment_ok': True, 'detail': {'ready': True}}):

        MockUser.query.get.return_value = _make_admin_mock()

        data = {'data_type': 'dat', 'file': (io.BytesIO(b'\x00\x01\x02\x03'), 'db.dat')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')

    assert resp.status_code == 200
    assert os.path.exists(os.path.join(dat_dir, 'Farmlands_Quality_Level_Database.dat'))


def test_trigger_failure_rollback(integration_env):
    """触发失败 → 回滚 → 审计日志记录回滚。"""
    client = integration_env['client']
    csv_dir = integration_env['csv_dir']

    # 先部署一份旧文件
    with open(os.path.join(csv_dir, 'test.csv'), 'w') as f:
        f.write('old_data')

    with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
         patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
         patch('framework.api.routes.data_import.User') as MockUser, \
         patch('framework.upload.data_trigger.trigger_csv_evaluate',
               side_effect=RuntimeError('trigger boom')):

        MockUser.query.get.return_value = _make_admin_mock()

        data = {'data_type': 'csv', 'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv')}
        resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')

    assert resp.status_code == 500
    # 验证回滚后旧文件恢复
    with open(os.path.join(csv_dir, 'test.csv'), 'r') as f:
        assert f.read() == 'old_data'
    # 验证审计日志记录回滚
    with open(integration_env['log_path'], 'r', encoding='utf-8') as f:
        entry = json.loads(f.readline())
    assert entry['success'] is False
    assert entry['restored_from_backup'] is True


def test_backup_retention_keeps_3(integration_env):
    """连续导入 4 次，backup/ 下仅保留最近 3 份。"""
    client = integration_env['client']
    csv_dir = integration_env['csv_dir']

    for i in range(4):
        # 每次部署前先写入一份旧文件（供下次备份）
        with open(os.path.join(csv_dir, 'test.csv'), 'w') as f:
            f.write(f'gen_{i}')

        with patch('framework.api.routes.data_import.get_jwt_identity', return_value='1'), \
             patch('framework.api.routes.data_import.jwt_required', lambda f: f), \
             patch('framework.api.routes.data_import.User') as MockUser, \
             patch('framework.upload.data_trigger.trigger_csv_evaluate',
                   return_value={'status': 'ok', 'processed': 1}):

            MockUser.query.get.return_value = _make_admin_mock()

            data = {'data_type': 'csv', 'file': (io.BytesIO(CSV_HEADER.encode('utf-8')), 'test.csv')}
            resp = client.post('/api/v1/data/import', data=data, content_type='multipart/form-data')
            assert resp.status_code == 200

    # 验证 backup 目录下不超过 3 份
    backup_dir = os.path.join(csv_dir, 'backup')
    if os.path.exists(backup_dir):
        subdirs = [d for d in os.listdir(backup_dir) if os.path.isdir(os.path.join(backup_dir, d))]
        assert len(subdirs) <= 3
```

- [ ] **Step 2: 运行集成测试验证通过**

运行：

```bash
python -m pytest tests/test_data_import_integration.py -v
```

预期：5 个测试全部 PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_data_import_integration.py
git commit -m "test: add end-to-end integration tests for data import"
```

---

### Task 10: 文档更新与依赖校验

**对应 tasks.md：** 第 8 节（8.1-8.5）+ 第 9 节（9.1 依赖确认）

**前置依赖：** Task 8（API 契约已定稿）

**Files:**
- Create: `docs/api/data_import.md`
- Modify: `data/farmland_diagnosis/README.md`
- Modify: `data/farmland_stability/README.md`
- Modify: `bin/farmland_quality_eval/README.md`

- [ ] **Step 1: 确认依赖已就绪**

运行：

```bash
python -c "import geopandas; import pandas; print('deps ok')"
```

预期输出：`deps ok`（geopandas 和 pandas 已在 pyproject.toml 中，上一轮已添加）

- [ ] **Step 2: 创建 `docs/api/data_import.md` API 契约文档**

创建 `docs/api/data_import.md`：

````markdown
# 数据导入 API

## 端点

`POST /api/v1/data/import`

## 鉴权

需要 admin 角色 JWT：

```
Authorization: Bearer <token>
```

非 admin 用户返回 403；未携带 JWT 返回 401。

## 请求

`multipart/form-data`：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `data_type` | string | 是 | 数据类型：`csv` / `shapefile` / `dat` |
| `file` | file | 是 | 上传的文件 |

### 文件大小限制

单次上传 ≤ 200MB（`Config.MAX_DATA_IMPORT_SIZE`），超限返回 413。

## 数据类型说明

### CSV（`data_type=csv`）

CSV 文件首行必须包含 14 项必需列：

`一级农业区`、`二级农业区`、`pH`、`有机质`、`有效磷`、`速效钾`、`容重`、`耕层质地`、`灌溉能力`、`排水能力`、`地形部位`、`质地构型`、`有效土层`、`耕层厚度`

编码支持 UTF-8 和 GBK（UTF-8 失败自动回退 GBK）。

部署时重命名为 `test.csv` 写入 `data/farmland_diagnosis/`。

### shapefile（`data_type=shapefile`）

上传一个 zip 包，内含：
- `manifest.json`：声明 3 期 shapefile 的元数据
- 3 期 shapefile 的 5 组件（.shp / .cpg / .dbf / .prj / .shx）

manifest.json 格式：

```json
{
  "current_year": 2024,
  "history_years": [2018, 2021],
  "years": [2018, 2021, 2024],
  "current_filename": "2024_data.shp",
  "history_filenames": ["2018_data.shp", "2021_data.shp"]
}
```

zip 包限制：
- 解压后总大小 ≤ 200MB
- 文件数 ≤ 30
- 无路径穿越（文件名不含 `..` 或绝对路径）

部署到 `data/farmland_stability/`。字段校验（LSD1-LSD12 等）延迟到触发阶段由 `run_all_models` 执行。

### .dat（`data_type=dat`）

二进制指标数据库文件，大小 > 0 且 ≤ 200MB。

部署时重命名为 `Farmlands_Quality_Level_Database.dat` 写入 `bin/farmland_quality_eval/`。

## 响应

### 成功（200）

```json
{
  "status": "ok",
  "data_type": "csv",
  "deployed_path": "/abs/path/to/test.csv",
  "backup_path": "/abs/path/to/backup/20260725-100000",
  "trigger_result": {
    "status": "ok",
    "processed": 100,
    "errors": []
  }
}
```

shapefile 类型响应中用 `deployed_files`（文件名列表）替代 `deployed_path`。

### 错误码

| HTTP | 说明 |
|------|------|
| 400 | 缺 data_type / 缺文件 / 无效 data_type / 校验失败 |
| 401 | 未携带 JWT |
| 403 | 非 admin 用户 |
| 413 | 文件大小超限 |
| 500 | 部署失败 / 触发失败（已回滚） / 触发异常（已回滚） |
| 504 | 触发超时（已回滚） |

## 备份策略

部署前将目标目录现有文件移动到 `<target_dir>/backup/YYYYMMDD-HHMMSS/`，保留最近 3 份。

## 触发超时

触发离线计算的超时为 600 秒（`Config.DATA_IMPORT_TIMEOUT`）。超时后自动从备份回滚并返回 504。

## 并发提示

本接口 v1 不加并发锁。请避免同时发起多个导入请求，否则可能导致文件冲突。
````

- [ ] **Step 3: 更新 `data/farmland_diagnosis/README.md`**

在 `## 部署方式` 小节末尾追加：

```markdown

### 通过 HTTP API 部署（推荐）

admin 用户可通过 HTTP API 远程部署 CSV，无需 SSH：

```bash
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <admin_token>" \
  -F "data_type=csv" \
  -F "file=@test.csv"
```

API 会自动完成校验（14 项必需列）、备份现有文件、部署（重命名为 `test.csv`）、触发 `bulk_evaluate` 批量评价。详见 `docs/api/data_import.md`。
```

- [ ] **Step 4: 更新 `data/farmland_stability/README.md`**

在 `## 部署方式` 小节末尾追加：

```markdown

### 通过 HTTP API 部署（推荐）

admin 用户可通过 HTTP API 远程部署 shapefile，无需 SSH。

**打包要求**：将 3 期 shapefile 的 5 组件（.shp / .cpg / .dbf / .prj / .shx）和 `manifest.json` 打包为一个 zip：

```json
// manifest.json
{
  "current_year": 2024,
  "history_years": [2018, 2021],
  "years": [2018, 2021, 2024],
  "current_filename": "2024_测试数据.shp",
  "history_filenames": ["2018_测试数据.shp", "2021_测试数据.shp"]
}
```

```bash
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <admin_token>" \
  -F "data_type=shapefile" \
  -F "file=@stability_data.zip"
```

API 会自动完成校验、备份、解压部署、触发 `precompute.main`（run_all_models → DB 持久化 → 文件输出）。详见 `docs/api/data_import.md`。
```

- [ ] **Step 5: 更新 `bin/farmland_quality_eval/README.md`**

在 `## 部署方式` 小节末尾追加：

```markdown

### 通过 HTTP API 部署 .dat（推荐）

admin 用户可通过 HTTP API 远程部署 .dat 文件，无需 SSH：

```bash
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <admin_token>" \
  -F "data_type=dat" \
  -F "file=@Farmlands_Quality_Level_Database.dat"
```

API 会自动完成校验、备份、部署（重命名为 `Farmlands_Quality_Level_Database.dat`）、触发 `check_deployment` 校验。详见 `docs/api/data_import.md`。

注意：exe 不通过 API 部署，仍由运维手动部署。
```

- [ ] **Step 6: 提交**

```bash
git add docs/api/data_import.md data/farmland_diagnosis/README.md data/farmland_stability/README.md bin/farmland_quality_eval/README.md
git commit -m "docs: add data import API documentation and update READMEs"
```

---

## 完整测试运行

完成所有任务后，运行全部新增测试：

```bash
python -m pytest tests/test_precompute.py tests/test_data_validator.py tests/test_data_deployer.py tests/test_data_trigger.py tests/test_audit_logger.py tests/test_data_import_route.py tests/test_data_import_integration.py -v
```

预期：全部 PASS。

## 关键里程碑

| 里程碑 | 完成任务 | 标志 |
|--------|---------|------|
| 基础配置就绪 | Task 1 | Config 4 项可导入 |
| 稳定性模型可持久化 | Task 2 | `precompute.py` 可独立运行 |
| Adapter 可调度三类触发 | Task 3 | adapter 3 方法单测通过 |
| 校验/部署/审计独立可用 | Task 4-6 | 三个模块单测通过 |
| 触发器带超时可用 | Task 7 | 触发器单测通过（含超时） |
| API 端点上线 | Task 8 | `POST /api/v1/data/import` 路由单测通过 |
| 端到端验证 | Task 9 | 集成测试 5 场景通过 |
| 文档齐备 | Task 10 | API 文档 + 3 个 README 更新 |
