703233c feat: add data deployer with backup and rollback
 framework/upload/data_deployer.py | 144 ++++++++++++++++++++++++++++++++++++
 tests/test_data_deployer.py       | 152 ++++++++++++++++++++++++++++++++++++++
 2 files changed, 296 insertions(+)
diff --git a/framework/upload/data_deployer.py b/framework/upload/data_deployer.py
new file mode 100644
index 0000000..c3dd46c
--- /dev/null
+++ b/framework/upload/data_deployer.py
@@ -0,0 +1,144 @@
+"""数据部署器：备份、部署、清理、回滚。
+
+部署语义：覆盖目标目录下的现有数据文件，保留原文件名约定（test.csv / Farmlands_Quality_Level_Database.dat）。
+备份语义：将现有文件移动到 <target_dir>/backup/YYYYMMDD-HHMMSS/，保留最近 N 份。
+"""
+import os
+import shutil
+import zipfile
+from datetime import datetime
+from typing import Optional, List
+
+from framework.config import Config
+
+# 备份时排除的文件/目录名
+BACKUP_EXCLUDES = {'README.md', 'backup'}
+
+
+def backup_existing(target_dir: str) -> Optional[str]:
+    """将 target_dir 下的现有数据文件移动到 backup/ 时间戳子目录。
+
+    排除 README.md 和 backup/ 子目录。无文件时返回 None。
+
+    Returns:
+        备份目录的绝对路径，或 None（无文件可备份）
+    """
+    if not os.path.exists(target_dir):
+        return None
+
+    files_to_backup = [
+        f for f in os.listdir(target_dir)
+        if f not in BACKUP_EXCLUDES and os.path.isfile(os.path.join(target_dir, f))
+    ]
+    if not files_to_backup:
+        return None
+
+    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
+    backup_dir = os.path.join(target_dir, 'backup', timestamp)
+    os.makedirs(backup_dir, exist_ok=True)
+
+    for f in files_to_backup:
+        src = os.path.join(target_dir, f)
+        dst = os.path.join(backup_dir, f)
+        shutil.move(src, dst)
+
+    return backup_dir
+
+
+def deploy_csv(src_path: str, target_dir: str) -> str:
+    """将 CSV 部署到 target_dir/test.csv（固定文件名）。
+
+    Returns:
+        部署后的绝对路径
+    """
+    os.makedirs(target_dir, exist_ok=True)
+    dst = os.path.join(target_dir, 'test.csv')
+    shutil.copy2(src_path, dst)
+    return dst
+
+
+def deploy_dat(src_path: str, target_dir: str) -> str:
+    """将 .dat 部署到 target_dir/Farmlands_Quality_Level_Database.dat（固定文件名）。
+
+    Returns:
+        部署后的绝对路径
+    """
+    os.makedirs(target_dir, exist_ok=True)
+    dst = os.path.join(target_dir, 'Farmlands_Quality_Level_Database.dat')
+    shutil.copy2(src_path, dst)
+    return dst
+
+
+def deploy_shapefile(zip_path: str, target_dir: str, manifest: dict) -> List[str]:
+    """解压 shapefile zip 到 target_dir。
+
+    Returns:
+        部署的文件名列表
+    """
+    os.makedirs(target_dir, exist_ok=True)
+    deployed_files = []
+    with zipfile.ZipFile(zip_path, 'r') as zf:
+        for info in zf.infolist():
+            # 跳过目录条目
+            if info.is_dir():
+                continue
+            # 解压到 target_dir（扁平化，不保留 zip 内子目录结构）
+            filename = os.path.basename(info.filename)
+            if not filename:
+                continue
+            dst = os.path.join(target_dir, filename)
+            with zf.open(info) as src, open(dst, 'wb') as dst_f:
+                dst_f.write(src.read())
+            deployed_files.append(filename)
+    return deployed_files
+
+
+def cleanup_backups(target_dir: str, keep: int = None) -> None:
+    """扫描 target_dir/backup/ 下时间戳目录，按目录名倒序保留前 keep 份。
+
+    Args:
+        target_dir: 目标目录
+        keep: 保留份数，默认使用 Config.BACKUP_RETENTION_COUNT
+    """
+    if keep is None:
+        keep = Config.BACKUP_RETENTION_COUNT
+
+    backup_root = os.path.join(target_dir, 'backup')
+    if not os.path.exists(backup_root):
+        return
+
+    subdirs = sorted([d for d in os.listdir(backup_root)
+                      if os.path.isdir(os.path.join(backup_root, d))], reverse=True)
+
+    for old_dir in subdirs[keep:]:
+        old_path = os.path.join(backup_root, old_dir)
+        shutil.rmtree(old_path, ignore_errors=True)
+
+
+def restore_from_backup(target_dir: str) -> bool:
+    """从最近一次 backup/ 子目录恢复文件到 target_dir。
+
+    Returns:
+        True 表示恢复成功；False 表示无备份或恢复失败
+    """
+    backup_root = os.path.join(target_dir, 'backup')
+    if not os.path.exists(backup_root):
+        return False
+
+    subdirs = sorted([d for d in os.listdir(backup_root)
+                      if os.path.isdir(os.path.join(backup_root, d))], reverse=True)
+    if not subdirs:
+        return False
+
+    latest_backup = os.path.join(backup_root, subdirs[0])
+    try:
+        for f in os.listdir(latest_backup):
+            src = os.path.join(latest_backup, f)
+            dst = os.path.join(target_dir, f)
+            if os.path.isfile(src):
+                shutil.move(src, dst)
+        # 恢复后删除已空的备份目录
+        os.rmdir(latest_backup)
+        return True
+    except Exception:
+        return False
diff --git a/tests/test_data_deployer.py b/tests/test_data_deployer.py
new file mode 100644
index 0000000..5570fa7
--- /dev/null
+++ b/tests/test_data_deployer.py
@@ -0,0 +1,152 @@
+"""测试数据部署器：备份、部署、清理、回滚。"""
+import sys
+import os
+import zipfile
+import json
+import tempfile
+import shutil
+from datetime import datetime
+sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
+
+import pytest
+from framework.upload.data_deployer import (
+    backup_existing, deploy_csv, deploy_shapefile, deploy_dat,
+    cleanup_backups, restore_from_backup,
+)
+
+
+def _create_target_dir_with_files(tmpdir, filenames=('test.csv',)):
+    """在 tmpdir 下创建文件，返回 tmpdir 路径。"""
+    for name in filenames:
+        with open(os.path.join(tmpdir, name), 'w', encoding='utf-8') as f:
+            f.write('old_data')
+    return tmpdir
+
+
+def test_backup_existing_no_files():
+    """首次部署（无现有文件）返回 None。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        result = backup_existing(tmpdir)
+        assert result is None
+
+
+def test_backup_existing_with_files():
+    """有现有文件时移动到 backup/ 时间戳目录。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        _create_target_dir_with_files(tmpdir, ('test.csv', 'other.csv'))
+        result = backup_existing(tmpdir)
+        assert result is not None
+        assert os.path.basename(result)  # 时间戳目录名
+        assert os.path.exists(os.path.join(result, 'test.csv'))
+        assert os.path.exists(os.path.join(result, 'other.csv'))
+        # 原文件已移走
+        assert not os.path.exists(os.path.join(tmpdir, 'test.csv'))
+
+
+def test_backup_existing_excludes_readme_and_backup_dir():
+    """备份时排除 README.md 和 backup/ 子目录。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        with open(os.path.join(tmpdir, 'README.md'), 'w') as f:
+            f.write('readme')
+        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
+            f.write('data')
+        os.makedirs(os.path.join(tmpdir, 'backup', '20240101-000000'))
+
+        result = backup_existing(tmpdir)
+        assert result is not None
+        # README 不应被备份
+        assert not os.path.exists(os.path.join(result, 'README.md'))
+        # test.csv 应被备份
+        assert os.path.exists(os.path.join(result, 'test.csv'))
+        # 原 README 仍在
+        assert os.path.exists(os.path.join(tmpdir, 'README.md'))
+
+
+def test_deploy_csv_renames_to_test_csv():
+    """CSV 部署时重命名为 test.csv。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        src = os.path.join(tmpdir, 'upload', 'mydata.csv')
+        os.makedirs(os.path.dirname(src))
+        with open(src, 'w') as f:
+            f.write('csv_content')
+        target = os.path.join(tmpdir, 'target')
+
+        deployed = deploy_csv(src, target)
+        assert deployed.endswith('test.csv')
+        with open(deployed, 'r') as f:
+            assert f.read() == 'csv_content'
+
+
+def test_deploy_dat_renames_to_fixed_name():
+    """dat 部署时重命名为 Farmlands_Quality_Level_Database.dat。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        src = os.path.join(tmpdir, 'upload', 'custom.dat')
+        os.makedirs(os.path.dirname(src))
+        with open(src, 'wb') as f:
+            f.write(b'\x00\x01')
+        target = os.path.join(tmpdir, 'target')
+
+        deployed = deploy_dat(src, target)
+        assert deployed.endswith('Farmlands_Quality_Level_Database.dat')
+        assert os.path.exists(deployed)
+
+
+def test_deploy_shapefile_extracts_zip():
+    """shapefile zip 部署时解压到目标目录。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        zip_path = os.path.join(tmpdir, 'upload.zip')
+        with zipfile.ZipFile(zip_path, 'w') as zf:
+            zf.writestr('2024_data.shp', b'shp')
+            zf.writestr('2024_data.dbf', b'dbf')
+            zf.writestr('manifest.json', b'{}')
+        target = os.path.join(tmpdir, 'target')
+        manifest = {'current_filename': '2024_data.shp', 'history_filenames': []}
+
+        deployed = deploy_shapefile(zip_path, target, manifest)
+        assert '2024_data.shp' in deployed
+        assert os.path.exists(os.path.join(target, '2024_data.shp'))
+        assert os.path.exists(os.path.join(target, 'manifest.json'))
+
+
+def test_cleanup_backups_keeps_latest_3():
+    """连续 4 次备份后仅保留最近 3 份。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        backup_dir = os.path.join(tmpdir, 'backup')
+        os.makedirs(backup_dir)
+        # 创建 4 个时间戳目录（倒序命名使最新在前）
+        for ts in ['20240104-000000', '20240103-000000', '20240102-000000', '20240101-000000']:
+            d = os.path.join(backup_dir, ts)
+            os.makedirs(d)
+            with open(os.path.join(d, 'test.csv'), 'w') as f:
+                f.write(ts)
+
+        cleanup_backups(tmpdir, keep=3)
+        remaining = sorted(os.listdir(backup_dir))
+        assert len(remaining) == 3
+        assert '20240101-000000' not in remaining  # 最旧的被删除
+        assert '20240104-000000' in remaining       # 最新的保留
+
+
+def test_restore_from_backup_success():
+    """回滚：从最近备份恢复文件。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        # 先部署旧文件
+        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
+            f.write('old')
+        # 备份
+        backup_path = backup_existing(tmpdir)
+        # 部署新文件
+        with open(os.path.join(tmpdir, 'test.csv'), 'w') as f:
+            f.write('new')
+        # 回滚
+        ok = restore_from_backup(tmpdir)
+        assert ok is True
+        with open(os.path.join(tmpdir, 'test.csv'), 'r') as f:
+            assert f.read() == 'old'
+
+
+def test_restore_from_backup_no_backup():
+    """无备份时回滚返回 False。"""
+    with tempfile.TemporaryDirectory() as tmpdir:
+        ok = restore_from_backup(tmpdir)
+        assert ok is False
