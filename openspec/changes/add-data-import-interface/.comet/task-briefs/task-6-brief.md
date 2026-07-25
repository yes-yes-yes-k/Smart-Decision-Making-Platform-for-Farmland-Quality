# Task 6 Brief: 审计日志

> 本文件是 Task 6 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 5 节（5.1-5.4）

## 前置依赖

无（仅依赖标准库 json / os / datetime）

## Files

- Create: `framework/upload/audit_logger.py`
- Test: `tests/test_audit_logger.py`

## Interfaces

- Consumes: 无
- Produces: `log_data_import(username, data_type, filename, deployed_path, trigger_result, success, message='', restored_from_backup=False)`

## Step 1: 编写 tests/test_audit_logger.py 的失败测试

创建 `tests/test_audit_logger.py`：

```python
"""测试审计日志写入。"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.upload.audit_logger import log_data_import, set_log_path


def test_log_data_import_success():
    """成功导入审计条目字段完整性。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='csv',
            filename='mydata.csv',
            deployed_path='/data/farmland_diagnosis/test.csv',
            trigger_result={'status': 'ok', 'processed': 100},
            success=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry['username'] == 'admin'
        assert entry['data_type'] == 'csv'
        assert entry['filename'] == 'mydata.csv'
        assert entry['deployed_path'] == '/data/farmland_diagnosis/test.csv'
        assert entry['success'] is True
        assert entry['restored_from_backup'] is False
        assert 'timestamp' in entry
        assert 'trigger_result' in entry


def test_log_data_import_failure_with_rollback():
    """失败 + 回滚条目包含 restored_from_backup。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        log_data_import(
            username='admin',
            data_type='shapefile',
            filename='data.zip',
            deployed_path='/data/farmland_stability/',
            trigger_result={'status': 'error', 'error': {'message': '字段缺失'}},
            success=False,
            message='触发失败已回滚',
            restored_from_backup=True,
        )

        with open(log_path, 'r', encoding='utf-8') as f:
            entry = json.loads(f.readline())
        assert entry['success'] is False
        assert entry['restored_from_backup'] is True
        assert '回滚' in entry['message']


def test_log_data_import_appends_multiple():
    """多次调用追加写入（不覆盖）。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = os.path.join(tmpdir, 'data_import.log')
        set_log_path(log_path)

        for i in range(3):
            log_data_import(
                username='admin', data_type='csv', filename=f'f{i}.csv',
                deployed_path='/p', trigger_result={}, success=True,
            )

        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        assert len(lines) == 3
```

## Step 2: 运行测试验证失败

```bash
d:\miniconda3\python.exe -m pytest tests/test_audit_logger.py -v
```

预期：FAIL，报 `ModuleNotFoundError`

## Step 3: 实现 framework/upload/audit_logger.py

创建 `framework/upload/audit_logger.py`：

```python
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
```

## Step 4: 运行测试验证通过

```bash
d:\miniconda3\python.exe -m pytest tests/test_audit_logger.py -v
```

预期：全部 PASS（3 个测试）

## Step 5: 提交

```bash
git add framework/upload/audit_logger.py tests/test_audit_logger.py
git commit -m "feat: add audit logger for data import operations"
```

## 全局约束（binds this task）

- 日志格式：JSON 行（每行一条 JSON 记录）
- 日志路径：`logs/data_import.log`（可通过 set_log_path 覆盖用于测试）
- 日志字段：timestamp、username、data_type、filename、deployed_path、trigger_result、success、message、restored_from_backup
- 追加写入（'a' 模式），不覆盖
- ensure_ascii=False（中文不转义）

## 环境提示

- 用 `d:\miniconda3\python.exe -m pytest` 运行测试
- audit_logger 仅依赖标准库（os/json/datetime），不依赖 geopandas
