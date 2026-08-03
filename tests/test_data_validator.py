"""测试数据校验器：CSV / shapefile zip / 耕地质量评价 CSV。"""
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


# ---------- validate_dat（耕地质量评价 CSV，别名 validate_grade_csv）----------

GRADE_CSV_COLS = ['SiteID', 'JD', 'WD', 'MJ', 'SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ',
                  'YXTCHD', 'GCHD', 'JHXLLZ', 'JHXQLZ', 'EJNYQcode', 'XQMCcode',
                  'GCZDcode', 'PSNLcode', 'GGNLcode', 'DXBWcode', 'ZDGXcode']


def test_validate_dat_success():
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        path = f.name
    _write_csv(path, GRADE_CSV_COLS)
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


def test_validate_dat_missing_column():
    """耕地质量评价 CSV 缺少必需字段时校验失败。"""
    cols = GRADE_CSV_COLS.copy()
    cols.remove('ZDGXcode')
    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
        path = f.name
    _write_csv(path, cols)
    ok, msg = validate_dat(path)
    assert ok is False
    assert 'ZDGXcode' in msg
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
