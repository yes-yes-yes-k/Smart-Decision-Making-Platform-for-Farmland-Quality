"""数据导入校验器：CSV / shapefile zip / 耕地质量评价 CSV。

校验仅检查文件结构和必需字段，不触发离线计算。
- CSV：校验 14 项必需列（UTF-8 失败回退 GBK）
- shapefile zip：校验 manifest + 5 组件完整性 + 防 zip bomb + 路径穿越
- 耕地质量评价 CSV：校验非空、≤200MB、UTF-8、含 20 个必需字段
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


# 耕地质量评价 CSV 必需的 20 个字段（以 CSV 首行表头为准）
GRADE_CSV_REQUIRED_COLUMNS = [
    'SiteID', 'JD', 'WD', 'MJ', 'SJD', 'YJZ', 'YXL', 'SXJ', 'TRRZ',
    'YXTCHD', 'GCHD', 'JHXLLZ', 'JHXQLZ', 'EJNYQcode', 'XQMCcode',
    'GCZDcode', 'PSNLcode', 'GGNLcode', 'DXBWcode', 'ZDGXcode',
]


def validate_grade_csv(file_path: str) -> Tuple[bool, str]:
    """校验耕地质量评价 CSV 文件：非空、≤200MB、UTF-8、含 20 个必需字段。

    Returns:
        (ok, error_msg): ok=True 时 error_msg 为空字符串
    """
    size = os.path.getsize(file_path)
    if size == 0:
        return False, "CSV 文件为空"
    if size > Config.MAX_DATA_IMPORT_SIZE:
        return False, f"CSV 文件大小超过 {Config.MAX_DATA_IMPORT_SIZE // (1024 * 1024)}MB 限制"

    try:
        try:
            df = pd.read_csv(file_path, encoding='utf-8', nrows=1)
        except UnicodeDecodeError:
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig', nrows=1)
            except UnicodeDecodeError:
                return False, "CSV 文件编码非 UTF-8"
    except Exception as e:
        return False, f"CSV 文件解析失败: {e}"

    missing = [c for c in GRADE_CSV_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"CSV 缺少必需字段: {missing}"
    return True, ''


# 向后兼容别名（data_import.py 仍使用 validate_dat 名称）
validate_dat = validate_grade_csv


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
