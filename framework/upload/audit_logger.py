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
