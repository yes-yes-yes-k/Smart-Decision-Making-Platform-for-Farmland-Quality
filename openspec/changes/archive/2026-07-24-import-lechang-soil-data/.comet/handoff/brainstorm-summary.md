# Brainstorm Summary

- Change: import-lechang-soil-data
- Date: 2026-07-23

## 确认的技术方案

按数据源分表存储乐昌市土壤数据到数据库（SQLite 开发 / MySQL 生产），共 8 张表：
- ThirdSurveyTopsoil（三普表层土，649 行 × 52 列）
- ThirdSurveyProfile（三普剖面理化，216 行 × 97 列）
- ThirdSurveySiteCondition（三普立地条件，848 行 × 111 列）
- ThirdSurveyBulkDensity（三普容重，1003 行 × 11 列）
- SecondSurveyPoint（二普点，82 行 × 39 列）
- FormulaFertilization（测土配方，1233 行 × 57 列）
- AgriChemicalization（农业化学化，.xls 加密，待处理）
- GrainYield（粮食产量，.xls 加密，待处理）

导入脚本 `scripts/import_lechang_data.py`：pandas read_excel → 硬编码列名映射表（中文→英文）→ 先 DELETE 后 INSERT 幂等导入。

soil_data_loader.py 改造：`load_soil_data()` 查询 DB 表返回 DataFrame，DB 为空时降级到 mock fallback。返回字典结构兼容（`third_survey`、`formula_fertilization` 键不变）。

## 关键取舍与风险

- **加密 .xls 文件无法读取**：农业化学化和粮食产量的 .xls 文件被加密（Workbook is encrypted），xlrd 无法读取。方案：导入脚本检测加密后跳过并 warning，对应的 AgriChemicalization/GrainYield 表将为空表（保留建表）。需用户提供密码或解密后的文件才能填充。
- **load_soil_data 当前无消费者**：经全量搜索，`load_soil_data` 仅在 soil_data_loader.py 中定义，没有任何 agent 或模块调用它。当前所有 specialized agents 使用硬编码 mock 数据。本次变更只建立数据底座和 DB 读取能力，不修改 agent 代码（符合 Non-Goal）。
- **列名含尾随空格**：三普表层土的 ` Ni` 列、`TK ` 列含尾随空格，导入时需 strip()。
- **datetime 字段处理**：三普容重的 接样时间/报告时间 为 datetime64，导入时转为 ISO 字符串存储。
- **列名映射硬编码**：若源 Excel 列名变化需更新映射表。

## 测试策略

- 单元测试：模型建表、列名映射、导入幂等性（重复执行无重复数据）、DB 读取与 mock fallback 降级
- 集成测试：运行 init_db.py 建表 → 运行导入脚本 → 验证 load_soil_data() 返回真实数据
- 边界测试：加密文件跳过、缺失文件跳过、空表降级 mock

## Spec Patch

无。OpenSpec delta spec 的验收场景已覆盖加密文件跳过和空表降级，无需补充。
