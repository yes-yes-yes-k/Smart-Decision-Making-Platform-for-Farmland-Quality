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
