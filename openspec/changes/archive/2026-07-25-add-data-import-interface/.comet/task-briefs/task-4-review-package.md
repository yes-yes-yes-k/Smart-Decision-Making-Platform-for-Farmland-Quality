dd784ad feat: add data validators for CSV/shapefile/dat
 framework/upload/data_validator.py | 137 +++++++++++++++++++++++++++++
 tests/test_data_validator.py       | 173 +++++++++++++++++++++++++++++++++++++
 2 files changed, 310 insertions(+)
diff --git a/framework/upload/data_validator.py b/framework/upload/data_validator.py
new file mode 100644
index 0000000..0efefa7
--- /dev/null
+++ b/framework/upload/data_validator.py
@@ -0,0 +1,137 @@
+"""数据导入校验器：CSV / shapefile zip / .dat。
+
+校验仅检查文件结构和必需字段，不触发离线计算。
+- CSV：校验 14 项必需列（UTF-8 失败回退 GBK）
+- shapefile zip：校验 manifest + 5 组件完整性 + 防 zip bomb + 路径穿越
+- .dat：校验非空且 ≤ 200MB
+"""
+import os
+import zipfile
+import json
+from typing import Tuple, Dict, Any
+
+import pandas as pd
+
+from framework.config import Config
+
+# CSV 必需的 14 列（中文表头，与 farmland_diagnosis/config.py 的 COLUMN_RENAME key 一致）
+CSV_REQUIRED_COLUMNS = [
+    '一级农业区', '二级农业区', 'pH', '有机质', '有效磷', '速效钾',
+    '容重', '耕层质地', '灌溉能力', '排水能力', '地形部位',
+    '质地构型', '有效土层', '耕层厚度',
+]
+
+# manifest.json 必需字段
+MANIFEST_REQUIRED_FIELDS = ['current_year', 'history_years', 'years', 'current_filename', 'history_filenames']
+
+# shapefile 5 组件
+SHP_COMPONENTS = ['.shp', '.cpg', '.dbf', '.prj', '.shx']
+
+# zip 安全限制
+ZIP_MAX_TOTAL_SIZE = Config.MAX_DATA_IMPORT_SIZE  # 200MB
+ZIP_MAX_FILE_COUNT = 30
+
+
+def validate_csv(file_path: str) -> Tuple[bool, str]:
+    """校验 CSV 文件包含全部 14 项必需列。
+
+    Returns:
+        (ok, error_msg): ok=True 时 error_msg 为空字符串
+    """
+    try:
+        try:
+            df = pd.read_csv(file_path, encoding='utf-8', nrows=1)
+        except UnicodeDecodeError:
+            df = pd.read_csv(file_path, encoding='gbk', nrows=1)
+    except Exception as e:
+        return False, f"CSV 文件解析失败: {e}"
+
+    missing = [c for c in CSV_REQUIRED_COLUMNS if c not in df.columns]
+    if missing:
+        return False, f"CSV 缺少必需列: {missing}"
+    return True, ''
+
+
+def validate_dat(file_path: str) -> Tuple[bool, str]:
+    """校验 .dat 文件非空且大小 ≤ 200MB。
+
+    Returns:
+        (ok, error_msg)
+    """
+    size = os.path.getsize(file_path)
+    if size == 0:
+        return False, ".dat 文件为空"
+    if size > Config.MAX_DATA_IMPORT_SIZE:
+        return False, f".dat 文件大小超过 {Config.MAX_DATA_IMPORT_SIZE // (1024 * 1024)}MB 限制"
+    return True, ''
+
+
+def validate_shapefile_zip(zip_path: str) -> Tuple[bool, str, Dict[str, Any]]:
+    """校验 shapefile zip 包完整性。
+
+    校验项：
+    1. 解压前：总大小 ≤ 200MB、文件数 ≤ 30、无路径穿越
+    2. 解压后：manifest.json 存在且字段完整
+    3. 每期 shapefile 5 组件齐全
+
+    Returns:
+        (ok, error_msg, manifest): ok=True 时 manifest 为解析后的字典；ok=False 时 manifest 为 {}
+    """
+    try:
+        with zipfile.ZipFile(zip_path, 'r') as zf:
+            infos = zf.infolist()
+
+            # 1. 文件数校验
+            if len(infos) > ZIP_MAX_FILE_COUNT:
+                return False, f"zip 包文件数超过 {ZIP_MAX_FILE_COUNT} 限制", {}
+
+            # 2. 总大小校验（解压后）
+            total_size = sum(i.file_size for i in infos)
+            if total_size > ZIP_MAX_TOTAL_SIZE:
+                return False, f"zip 包解压后总大小超过 {ZIP_MAX_TOTAL_SIZE // (1024 * 1024)}MB 限制", {}
+
+            # 3. 路径穿越校验
+            for info in infos:
+                name = info.filename
+                if '..' in name or name.startswith('/') or name.startswith('\\'):
+                    return False, f"zip 包含非法路径: {name}", {}
+
+            # 4. manifest.json 校验
+            manifest_names = [n for n in zf.namelist() if n.endswith('manifest.json')]
+            if not manifest_names:
+                return False, "zip 包缺少 manifest.json", {}
+
+            with zf.open(manifest_names[0]) as mf:
+                try:
+                    manifest = json.loads(mf.read().decode('utf-8'))
+                except json.JSONDecodeError as e:
+                    return False, f"manifest.json 解析失败: {e}", {}
+
+            missing_fields = [f for f in MANIFEST_REQUIRED_FIELDS if f not in manifest]
+            if missing_fields:
+                return False, f"manifest.json 缺少字段: {missing_fields}", {}
+
+            # 5. shapefile 5 组件校验
+            all_names = zf.namelist()
+            all_basenames = set()
+            for n in all_names:
+                base, ext = os.path.splitext(n)
+                if ext.lower() in SHP_COMPONENTS:
+                    all_basenames.add(base)
+
+            declared_shps = [manifest['current_filename']] + list(manifest['history_filenames'])
+            for shp_name in declared_shps:
+                base = os.path.splitext(shp_name)[0]
+                for ext in SHP_COMPONENTS:
+                    expected = f'{base}{ext}'
+                    # 支持同名文件在不同子目录，只要存在即可
+                    found = any(n.endswith(expected) for n in all_names)
+                    if not found:
+                        return False, f"shapefile 组件不完整，缺少: {expected}", {}
+
+            return True, '', manifest
+
+    except zipfile.BadZipFile as e:
+        return False, f"zip 文件损坏: {e}", {}
+    except Exception as e:
+        return False, f"zip 校验失败: {e}", {}
diff --git a/tests/test_data_validator.py b/tests/test_data_validator.py
new file mode 100644
index 0000000..ca24837
--- /dev/null
+++ b/tests/test_data_validator.py
@@ -0,0 +1,173 @@
+"""测试数据校验器：CSV / shapefile zip / .dat。"""
+import sys
+import os
+import zipfile
+import json
+import tempfile
+sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
+
+import pytest
+from framework.upload.data_validator import validate_csv, validate_shapefile_zip, validate_dat
+
+
+def _write_csv(path, columns, encoding='utf-8'):
+    """辅助：写入一行 CSV（仅表头 + 1 行数据）。"""
+    import pandas as pd
+    row = {c: '1' for c in columns}
+    df = pd.DataFrame([row], columns=columns)
+    df.to_csv(path, index=False, encoding=encoding)
+
+
+# ---------- validate_csv ----------
+
+REQUIRED_CSV_COLS = ['一级农业区', '二级农业区', 'pH', '有机质', '有效磷', '速效钾',
+                     '容重', '耕层质地', '灌溉能力', '排水能力', '地形部位',
+                     '质地构型', '有效土层', '耕层厚度']
+
+
+def test_validate_csv_success_utf8():
+    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', encoding='utf-8') as f:
+        _write_csv(f.name, REQUIRED_CSV_COLS)
+        path = f.name
+    ok, msg = validate_csv(path)
+    assert ok is True
+    assert msg == ''
+    os.unlink(path)
+
+
+def test_validate_csv_success_gbk():
+    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
+        path = f.name
+    _write_csv(path, REQUIRED_CSV_COLS, encoding='gbk')
+    ok, msg = validate_csv(path)
+    assert ok is True
+    os.unlink(path)
+
+
+def test_validate_csv_missing_column():
+    cols = REQUIRED_CSV_COLS.copy()
+    cols.remove('有效磷')
+    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='w', encoding='utf-8') as f:
+        _write_csv(f.name, cols)
+        path = f.name
+    ok, msg = validate_csv(path)
+    assert ok is False
+    assert '有效磷' in msg
+    os.unlink(path)
+
+
+def test_validate_csv_unparseable():
+    with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as f:
+        f.write(b'\xff\xfe\x00\x01\x02')  # 非 UTF-8/GBK 内容
+        path = f.name
+    ok, msg = validate_csv(path)
+    assert ok is False
+    os.unlink(path)
+
+
+# ---------- validate_dat ----------
+
+def test_validate_dat_success():
+    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
+        f.write(b'\x00\x01\x02\x03')
+        path = f.name
+    ok, msg = validate_dat(path)
+    assert ok is True
+    os.unlink(path)
+
+
+def test_validate_dat_empty():
+    with tempfile.NamedTemporaryFile(suffix='.dat', delete=False) as f:
+        f.write(b'')
+        path = f.name
+    ok, msg = validate_dat(path)
+    assert ok is False
+    assert '空' in msg
+    os.unlink(path)
+
+
+# ---------- validate_shapefile_zip ----------
+
+def _make_valid_manifest():
+    return {
+        'current_year': 2024,
+        'history_years': [2018, 2021],
+        'years': [2018, 2021, 2024],
+        'current_filename': '2024_data.shp',
+        'history_filenames': ['2018_data.shp', '2021_data.shp'],
+    }
+
+
+def _write_shapefile_zip(zip_path, manifest, components=('.shp', '.cpg', '.dbf', '.prj', '.shx')):
+    """构造合法 shapefile zip。"""
+    with zipfile.ZipFile(zip_path, 'w') as zf:
+        zf.writestr('manifest.json', json.dumps(manifest))
+        # 为 current + history 每个 shapefile 写入 5 组件
+        for shp_name in [manifest['current_filename']] + manifest['history_filenames']:
+            base = os.path.splitext(shp_name)[0]
+            for ext in components:
+                zf.writestr(f'{base}{ext}', b'fake_content')
+
+
+def test_validate_shapefile_zip_success():
+    manifest = _make_valid_manifest()
+    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
+        zip_path = f.name
+    _write_shapefile_zip(zip_path, manifest)
+
+    ok, msg, returned_manifest = validate_shapefile_zip(zip_path)
+    assert ok is True
+    assert returned_manifest['current_filename'] == '2024_data.shp'
+    os.unlink(zip_path)
+
+
+def test_validate_shapefile_zip_missing_manifest():
+    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
+        zip_path = f.name
+    with zipfile.ZipFile(zip_path, 'w') as zf:
+        zf.writestr('2024_data.shp', b'fake')
+
+    ok, msg, manifest = validate_shapefile_zip(zip_path)
+    assert ok is False
+    assert 'manifest' in msg
+    os.unlink(zip_path)
+
+
+def test_validate_shapefile_zip_incomplete_components():
+    manifest = _make_valid_manifest()
+    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
+        zip_path = f.name
+    # 只写 .shp 不写 .dbf
+    _write_shapefile_zip(zip_path, manifest, components=('.shp',))
+
+    ok, msg, _ = validate_shapefile_zip(zip_path)
+    assert ok is False
+    assert 'dbf' in msg or '组件' in msg
+    os.unlink(zip_path)
+
+
+def test_validate_shapefile_zip_path_traversal():
+    manifest = _make_valid_manifest()
+    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
+        zip_path = f.name
+    with zipfile.ZipFile(zip_path, 'w') as zf:
+        zf.writestr('manifest.json', json.dumps(manifest))
+        zf.writestr('../evil.shp', b'fake')  # 路径穿越
+
+    ok, msg, _ = validate_shapefile_zip(zip_path)
+    assert ok is False
+    assert '路径' in msg or '非法' in msg
+    os.unlink(zip_path)
+
+
+def test_validate_shapefile_zip_manifest_missing_field():
+    manifest = _make_valid_manifest()
+    del manifest['years']  # 缺字段
+    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as f:
+        zip_path = f.name
+    _write_shapefile_zip(zip_path, manifest)
+
+    ok, msg, _ = validate_shapefile_zip(zip_path)
+    assert ok is False
+    assert 'years' in msg or '字段' in msg
+    os.unlink(zip_path)
