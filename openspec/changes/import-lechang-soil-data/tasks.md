# Tasks: import-lechang-soil-data

## 1. 土壤数据模型定义

- [x] 1.1 分析 `data/lechang/` 各 Excel 文件的实际列名和数据类型
- [x] 1.2 创建 `framework/models/soil_data.py`，定义 8 个 SQLAlchemy 模型（ThirdSurveyTopsoil、ThirdSurveyProfile、ThirdSurveySiteCondition、ThirdSurveyBulkDensity、SecondSurveyPoint、FormulaFertilization、AgriChemicalization、GrainYield）
- [x] 1.3 为每个模型添加中文字段名到英文字段名的映射注释
- [x] 1.4 更新 `framework/models/__init__.py` 注册新模型
- [x] 1.5 更新 `init_db.py` 确保 `db.create_all()` 包含新表

## 2. 数据导入脚本

- [x] 2.1 创建 `scripts/import_lechang_data.py` 导入脚本骨架
- [x] 2.2 实现各数据源的 Excel 读取逻辑（含 .xls 格式兼容，需 xlrd 引擎）
- [x] 2.3 实现中文列名到英文字段名的硬编码映射表
- [x] 2.4 实现幂等导入逻辑（先 DELETE 后 INSERT，按数据源逐表处理）
- [x] 2.5 添加导入日志：记录各表导入行数、跳过的缺失文件 warning、脱敏数据标注
- [x] 2.6 添加命令行参数支持：`--area lechang`（默认）、`--dry-run` 预览模式

## 3. soil_data_loader 改造

- [ ] 3.1 修改 `framework/domain/data/soil_data_loader.py` 的 `load_soil_data()`，从 DB 查询土壤数据
- [ ] 3.2 保留 mock fallback：DB 表为空时降级到 `_generate_mock_data()`，并记录 warning
- [ ] 3.3 确保返回字典结构兼容（`third_survey`、`formula_fertilization` 键不变）

## 4. 测试

- [x] 4.1 创建 `tests/test_soil_data_models.py` 测试模型定义和建表
- [x] 4.2 创建 `tests/test_import_lechang_data.py` 测试导入脚本的幂等性和列名映射
- [ ] 4.3 创建 `tests/test_soil_data_loader_db.py` 测试从 DB 读取和 mock fallback 降级
- [ ] 4.4 运行全量测试确保不破坏现有功能

## 5. 集成验证

- [ ] 5.1 运行 `init_db.py` 创建新表
- [ ] 5.2 运行 `scripts/import_lechang_data.py` 导入乐昌数据
- [ ] 5.3 验证 `load_soil_data()` 返回真实数据（非 mock）
- [ ] 5.4 验证模型 4/5/6 能读到真实乐昌数据
- [ ] 5.5 验证重复执行导入脚本不产生重复数据
