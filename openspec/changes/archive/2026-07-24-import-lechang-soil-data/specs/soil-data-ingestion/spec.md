## ADDED Requirements

### Requirement: Soil Data Import
系统 SHALL 提供导入脚本，从 `data/lechang/` 目录的 Excel/xls 文件批量导入乐昌市土壤数据到数据库，按数据源分表存储。导入的数据源包括：三普表层土、三普剖面理化、三普立地条件、三普容重、二普点、测土配方、农业化学化、粮食产量。

#### Scenario: 成功导入所有数据源
- **WHEN** 运行 `scripts/import_lechang_data.py` 且 `data/lechang/` 目录文件齐全
- **THEN** 系统 SHALL 将 8 个数据源的数据分别导入到对应的数据库表，每张表行数大于 0

#### Scenario: 部分数据文件缺失
- **WHEN** 运行导入脚本且部分 Excel 文件缺失
- **THEN** 系统 SHALL 跳过缺失文件的数据源，记录 warning 日志，继续导入其他可用数据源

#### Scenario: 列名映射处理
- **WHEN** Excel 文件的中文列名与数据库字段名不一致
- **THEN** 导入脚本 SHALL 使用硬编码列名映射表将中文列名转换为英文字段名，缺失列允许 NULL 值

### Requirement: Idempotent Import
导入脚本 SHALL 支持幂等执行，重复运行不产生重复数据。

#### Scenario: 重复执行导入
- **WHEN** 导入脚本被重复执行
- **THEN** 系统 SHALL 在导入前先清除目标表的所有行，再批量插入新数据，保证结果一致

#### Scenario: 导入中断恢复
- **WHEN** 导入脚本中途失败后重新运行
- **THEN** 系统 SHALL 从头重新导入所有数据源（先清除后导入），不残留部分写入的数据

### Requirement: Soil Data Database Query
系统 SHALL 通过 `soil_data_loader.py` 从数据库读取土壤数据，替代运行时文件读取和 mock 生成逻辑。

#### Scenario: 从 DB 读取真实数据
- **WHEN** `load_soil_data()` 被调用且数据库中有土壤数据
- **THEN** 系统 SHALL 从数据库表查询返回真实乐昌市土壤数据，不读取 Excel 文件

#### Scenario: DB 表为空时降级
- **WHEN** `load_soil_data()` 被调用但数据库表为空（未导入数据）
- **THEN** 系统 SHALL 降级到 mock 数据生成，并在日志中记录 warning 提示数据未导入

#### Scenario: 返回数据字段一致
- **WHEN** `load_soil_data()` 从 DB 读取数据
- **THEN** 返回的字典 SHALL 包含 `third_survey` 和 `formula_fertilization` 键；顶层键与原有 mock 返回值兼容，但列名不兼容——DB 路径返回模型英文属性名（如 `ph`/`som`/`as_`），mock 降级返回中文列名（如 `pH`/`有机质`/`容重`）。下游接线应以 DB schema（模型英文属性名）为准，不应假设与 mock 列名一致
