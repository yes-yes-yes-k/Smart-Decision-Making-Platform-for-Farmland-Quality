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
    """耕地质量评价 CSV 部署时重命名为 Farmland_quality_Level_Database.csv。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, 'upload', 'custom.csv')
        os.makedirs(os.path.dirname(src))
        with open(src, 'wb') as f:
            f.write(b'SiteID,JD\nA0001,112.97\n')
        target = os.path.join(tmpdir, 'target')

        deployed = deploy_dat(src, target)
        assert deployed.endswith('Farmland_quality_Level_Database.csv')
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
