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
