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


def test_main_uses_manifest_id_column():
    """模型1 v2 应将 TYBH 传入预计算和结果持久化流程。"""
    from ai_culti_demo.farmland_stability import precompute

    mock_gdf = _make_mock_gdf()
    mock_storage = MagicMock()

    with patch.object(precompute, 'run_all_models', return_value=mock_gdf) as m_run, \
         patch.object(precompute, 'StabilityStorage', return_value=mock_storage), \
         patch.object(precompute, 'g_to_records', return_value=[]) as m_records, \
         patch.object(precompute, 'save_final_results'):

        manifest = {
            'current_filename': '2024_测试数据.shp',
            'history_filenames': ['2018_测试数据.shp', '2021_测试数据.shp', '2024_测试数据.shp'],
            'years': [2018, 2021, 2024],
            'id_column': 'TYBH',
        }
        precompute.main('/fake/shapefile_dir', manifest)

    m_run.assert_called_once_with(
        os.path.join('/fake/shapefile_dir', '2024_测试数据.shp'),
        [
            os.path.join('/fake/shapefile_dir', '2018_测试数据.shp'),
            os.path.join('/fake/shapefile_dir', '2021_测试数据.shp'),
            os.path.join('/fake/shapefile_dir', '2024_测试数据.shp'),
        ],
        [2018, 2021, 2024],
        id_col='TYBH',
    )
    m_records.assert_called_once_with(mock_gdf, id_col='TYBH')


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
