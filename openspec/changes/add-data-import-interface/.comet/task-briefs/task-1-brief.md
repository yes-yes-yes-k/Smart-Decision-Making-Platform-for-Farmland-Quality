# Task 1 Brief: 配置项与基础设施

> 本文件是 Task 1 的唯一需求来源，包含精确待写代码。请先完整阅读本文件。

## 对应 tasks.md

第 1 节（1.1-1.4）+ 第 9 节（9.3 启动校验 logs/ 目录）

## Files

- Modify: `framework/config.py`
- Modify: `framework/upload/__init__.py`
- Create: `logs/.gitkeep`

## Interfaces

- Consumes: 无
- Produces: `Config.MAX_DATA_IMPORT_SIZE`、`Config.DATA_IMPORT_TIMEOUT`、`Config.DATA_IMPORT_TARGETS`、`Config.BACKUP_RETENTION_COUNT`

## Step 1: 在 framework/config.py 的 Config 类中新增 4 个配置项

在 `framework/config.py` 的 `Config` 类中，`MAX_CONCURRENT_MODELS` 行（第 49 行附近）之后、`get_max_concurrent` 方法（第 52 行附近）之前插入：

```python
    # 数据导入接口配置
    MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024  # 200MB
    DATA_IMPORT_TIMEOUT = 600  # 秒
    DATA_IMPORT_TARGETS = {
        'csv': 'data/farmland_diagnosis',
        'shapefile': 'data/farmland_stability',
        'dat': 'bin/farmland_quality_eval',
    }
    BACKUP_RETENTION_COUNT = 3
```

## Step 2: 在 framework/upload/__init__.py 中写入包说明

`framework/upload/__init__.py` 当前为空文件，写入以下内容：

```python
"""framework.upload 包：文件上传与数据导入相关模块。"""
```

## Step 3: 创建 logs/ 目录占位文件

创建 `logs/.gitkeep` 文件（空文件），确保 `logs/` 目录在仓库中存在，供审计日志写入。

## Step 4: 验证配置项可导入

运行：

```bash
python -c "from framework.config import Config; print(Config.MAX_DATA_IMPORT_SIZE, Config.DATA_IMPORT_TIMEOUT, Config.DATA_IMPORT_TARGETS, Config.BACKUP_RETENTION_COUNT)"
```

预期输出：`209715200 600 {'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'} 3`

## Step 5: 提交

```bash
git add framework/config.py framework/upload/__init__.py logs/.gitkeep
git commit -m "feat: add data import config items and logs directory"
```

## 全局约束（binds this task）

- 文件大小上限 200MB（`Config.MAX_DATA_IMPORT_SIZE = 200 * 1024 * 1024`）
- 触发超时 600 秒（`Config.DATA_IMPORT_TIMEOUT = 600`）
- 时间戳备份目录保留最近 3 份（`Config.BACKUP_RETENTION_COUNT = 3`）
- 数据类型 → 目标目录映射：`{'csv': 'data/farmland_diagnosis', 'shapefile': 'data/farmland_stability', 'dat': 'bin/farmland_quality_eval'}`

## TDD 说明

本任务为纯配置项与基础设施（目录占位），不涉及业务逻辑。验证方式为 import 检查（Step 4），无需编写 pytest 测试文件。加载 test-driven-development 技能后，理解其对"配置值"的适用边界——配置项的"失败测试"即 import 失败，"通过测试"即 Step 4 的 import 成功输出预期值。
