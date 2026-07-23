## Context

当前系统通过 `framework/domain/data/soil_data_loader.py` 在运行时直接读取 `data/lechang/` 目录下的 Excel 文件。文件缺失时回退到 `_generate_mock_data()` 生成随机 mock 数据。模型 4/5/6 调用 `load_soil_data()` 获取土壤理化指标。

`data/lechang/` 目录包含以下数据文件：
- 乐昌市土壤三普表层土点位数据（xlsx）
- 乐昌市三普土壤容重（xlsx）
- 乐昌市土壤三普剖面理化和基本数据（xlsx）
- 乐昌市土壤三普立地条件（xlsx）
- 乐昌市二普点数据（xlsx）
- 乐昌市测土配方表层土数据2008（xlsx）
- 各县(区)农村电气化和农业化学化情况 2020-2024（5个 xls）
- 各县(区)粮食作物播种面积和产量 2020-2024（5个 xls）

现有数据库仅含 User/Conversation/Message/Document 四张应用表，无土壤数据表。

## Goals / Non-Goals

**Goals:**
- 按数据源分表存储乐昌市土壤数据到数据库
- 提供幂等导入脚本（先清除后导入，可重复执行）
- 改造 `soil_data_loader.py` 从 DB 读取真实数据，淘汰 mock 生成逻辑

**Non-Goals:**
- 不修改六种专业模型的定义和代码逻辑（属于拆分项 B）
- 不做空间分析和 GIS 可视化
- 不训练新的 ML 模型
- 不处理韶关市级别数据（仅乐昌市）

## Decisions

### D1: 按数据源分表 vs 统一宽表
**选择**: 按数据源分表
**理由**: 各数据源字段结构差异大（三普表层土有 pH/有机质等理化指标，农业化学化有化肥施用量等社会经济指标），统一宽表会导致大量空值。分表结构清晰，各表字段独立，查询效率高。
**备选**: 统一宽表——字段稀疏，维护困难，已排除。

### D2: 导入幂等策略 — 先清除后导入
**选择**: 每次导入前先 DELETE 该表所有行，再批量 INSERT
**理由**: 实现简单，保证数据一致性，避免主键冲突。乐昌市数据量小（千级行），清除重导耗时可忽略。
**备选**: 增量导入（UPSERT）——需要唯一标识判断重复，各数据源主键定义不统一，复杂度高，排除。

### D3: soil_data_loader.py 改造 — 从 DB 读取
**选择**: 修改 `load_soil_data()` 查询 DB 表，保留 fallback 到 mock（DB 表为空时）
**理由**: 保证向后兼容——如果 DB 未导入数据，仍能降级到 mock。模型 4/5/6 调用接口不变。
**备选**: 完全移除 mock——若 DB 未初始化会导致模型报错，风险较高，排除。

### D4: 模型字段映射 — 动态列名处理
**选择**: 导入脚本中硬编码列名映射表（中文列名 → 英文字段名），缺失列允许 NULL
**理由**: Excel 文件列名含中文且不统一，需映射到 SQLAlchemy 模型的英文字段名。硬编码映射表清晰可控。
**备选**: 自动推断列名——不可靠，排除。

### D5: 数据库引擎 — 开发用 SQLite，生产用 MySQL
**选择**: 复用现有 Config 的 SQLAlchemy 配置，模型定义兼容两者
**理由**: 现有架构已支持双数据库，SQLAlchemy ORM 天然兼容。新表通过 `db.create_all()` 自动建表。

## Risks / Trade-offs

- [Excel 列名变化] → 导入脚本硬编码列名映射表，若源文件列名变化需更新映射表
- [xls 格式（非 xlsx）兼容] → 农业化学化和粮食产量文件为 .xls 格式，需确认 pandas `read_excel` 能读取（需 xlrd 引擎）
- [数据脱敏标记] → 三普/测土配方数据已脱敏（文件名含 _fake），导入后不作为生产级空间真值，在导入日志中标注
- [DB 表为空时降级] → soil_data_loader 保留 mock fallback，DB 表为空时降级到 mock，并在日志中 warning

## Migration Plan

1. 新增 `framework/models/soil_data.py` 定义 8 张表的 SQLAlchemy 模型
2. 更新 `framework/models/__init__.py` 注册新模型
3. 更新 `init_db.py` 确保 `db.create_all()` 包含新表
4. 新增 `scripts/import_lechang_data.py` 导入脚本
5. 运行 `init_db.py` 创建新表
6. 运行 `scripts/import_lechang_data.py` 导入数据
7. 修改 `soil_data_loader.py` 从 DB 读取
8. 验证模型 4/5/6 能读到真实数据
9. 回滚策略：删除新表、还原 soil_data_loader.py
