# Task 2 Brief: precompute.py 模块（稳定性模型持久化）

> 本文件是 Task 2 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 10 节（10.1-10.4）

## 前置依赖

无（仅依赖现有 `model.py` / `storage.py`，已确认存在）：
- `src/ai_culti_demo/farmland_stability/model.py`: `run_all_models` (line 290), `save_final_results` (line 341), `MODULE_FIELDS` (line 357), `RESULT_CN` (line 310)
- `src/ai_culti_demo/farmland_stability/storage.py`: `StabilityStorage` (line 10), `create_tables` (line 24), `save_results` (line 53)

## Files

- Create: `src/ai_culti_demo/farmland_stability/precompute.py`
- Test: `tests/test_precompute.py`

## Interfaces

- Consumes: `run_all_models`、`save_final_results`、`MODULE_FIELDS`、`RESULT_CN`（来自 `model.py`）；`StabilityStorage`（来自 `storage.py`）
- Produces: `g_to_records(G, ...) -> List[Dict]`、`main(shapefile_dir, manifest) -> Dict`

## Step 1: 编写 tests/test_precompute.py 的失败测试

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

## Step 2: 运行测试验证失败

```bash
python -m pytest tests/test_precompute.py -v
```

预期：FAIL，报 `ModuleNotFoundError: No module named 'ai_culti_demo.farmland_stability.precompute'`

## Step 3: 实现 src/ai_culti_demo/farmland_stability/precompute.py

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

## Step 4: 运行测试验证通过

```bash
python -m pytest tests/test_precompute.py -v
```

预期：3 个测试全部 PASS

## Step 5: 提交

```bash
git add src/ai_culti_demo/farmland_stability/precompute.py tests/test_precompute.py
git commit -m "feat: add precompute.py for stability model persistence"
```

## 全局约束（binds this task）

- `precompute.main` 返回 `{status, processed, saved_to_db, output_files}`
- `g_to_records` 用 `MODULE_FIELDS` 映射 module_1..9，`RESULT_CN` 做中文 key
- `main` 流程：run_all_models → StabilityStorage.create_tables + save_results → save_final_results
- 命令行入口从 `data/farmland_stability/manifest.json` 读取默认 manifest

## 环境提示

- 测试需设置 `PYTHONPATH=src` 或 `pip install -e .` 才能导入 `ai_culti_demo` 包
- 测试文件已包含 `sys.path.insert(0, .../src)` 处理路径
