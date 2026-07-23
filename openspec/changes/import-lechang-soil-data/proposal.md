## Why

当前系统的土壤数据（三普表层土、二普、测土配方等）以 Excel 文件形式存放在 `data/lechang/` 目录下，运行时由 `soil_data_loader.py` 直接读取文件；文件缺失时回退到 mock 随机数据。这导致数据无法被高效查询、过滤和关联，模型 4/5/6 在缺失文件时只能使用假数据。将乐昌市土壤数据导入数据库可建立可查询的土壤数据底座，让模型从 DB 读取真实数据而非 mock。

## What Changes

- 新增按数据源分表的土壤数据 SQLAlchemy 模型：三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量
- 新增导入脚本 `scripts/import_lechang_data.py`，从 `data/lechang/` 目录的 Excel/xls 文件批量导入到数据库，支持幂等执行（先清除后导入）
- 修改 `framework/domain/data/soil_data_loader.py`，从数据库读取真实乐昌数据替代文件读取和 mock 生成逻辑
- **BREAKING**: `soil_data_loader.py` 的 `load_soil_data` 返回的数据将来自 DB 而非文件/mock，字段结构可能因数据源不同而变化

## Capabilities

### New Capabilities
- `soil-data-ingestion`: 土壤数据导入与存储能力——按数据源分表存储乐昌市土壤三普、二普、测土配方、农业化学化、粮食产量数据，提供幂等导入脚本和 DB 查询接口

### Modified Capabilities
- `database-models`: 新增土壤数据表模型（三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量），扩展现有 SQLAlchemy 模型集合

## Impact

- **新增代码**: `framework/models/soil_data.py`（土壤数据模型）、`scripts/import_lechang_data.py`（导入脚本）
- **修改代码**: `framework/domain/data/soil_data_loader.py`（改为从 DB 读取）、`framework/models/__init__.py`（注册新模型）、`init_db.py`（创建新表）
- **依赖**: 需要现有的 pandas、openpyxl、SQLAlchemy 依赖，无新增第三方依赖
- **数据库**: 开发环境 SQLite (`development.db`) 新增 8 张表；生产环境 MySQL 同步建表
- **运行时影响**: 首次需运行导入脚本填充数据；导入后模型 4/5/6 读取真实乐昌数据
