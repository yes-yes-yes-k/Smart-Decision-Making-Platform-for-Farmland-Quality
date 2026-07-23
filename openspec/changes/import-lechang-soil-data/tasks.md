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

- [x] 3.1 修改 `framework/domain/data/soil_data_loader.py` 的 `load_soil_data()`，从 DB 查询土壤数据
- [x] 3.2 保留 mock fallback：DB 表为空时降级到 `_generate_mock_data()`，并记录 warning
- [x] 3.3 确保返回字典结构兼容（`third_survey`、`formula_fertilization` 键不变）

## 4. 测试

- [x] 4.1 创建 `tests/test_soil_data_models.py` 测试模型定义和建表
- [x] 4.2 创建 `tests/test_import_lechang_data.py` 测试导入脚本的幂等性和列名映射
- [x] 4.3 创建 `tests/test_soil_data_loader_db.py` 测试从 DB 读取和 mock fallback 降级
- [x] 4.4 运行全量测试确保不破坏现有功能（12 passed；现有 93 passed / 5 pre-existing failures 与本任务无关）

## 5. 集成验证

- [x] 5.1 运行 `init_db.py` 创建新表（8 表全部创建，`as`/`yield` 保留字列名正确建表）
- [x] 5.2 运行 `scripts/import_lechang_data.py` 导入乐昌数据（6 表成功：topsoil649/profile216/site848/bd1003/second82/formula1233；2 表因 .xls 加密跳过）
- [x] 5.3 验证 `load_soil_data()` 返回真实数据（非 mock）（649≠mock623，1233≠mock1256）
- [x] 5.4 验证导入数据经 ORM 可查（**重定范围**：模型 4/5/6 收用户输入不读 DB，故改为验证导入数据经 ORM 可查 + 保留字 as_/yield_ 读写路径；均 PASS）
- [x] 5.5 验证重复执行导入脚本不产生重复数据（二次导入各表行数不变，幂等 PASS）

### 集成验证说明（spec 偏差记录）

- **5.4 范围调整**：原范围「验证模型 4/5/6 能读到真实乐昌数据」前提错误——经核实模型 4/5/6（model_4/5/6.py 及其 agent 包装）接收用户输入特征字典，不通过 `load_soil_data()` 读 DB（该函数当前无生产消费者）。乐昌土壤数据定位为**参考数据**入库供未来接线/RAG 使用。重定为「验证导入数据经 ORM 可查 + 保留字字段读写」。属小范围 spec 偏差。
- **DB 路径**：开发库实际位于 `instance/development.db`（Flask-SQLAlchemy 将相对 SQLite 路径解析到 instance_path），非项目根 `development.db`；`instance/` 已 gitignore，不影响功能。
- **导入脚本修复**（commit `f883a42`）：验证中发现并修复 3 个导入侧缺陷——sys.path 缺 PROJECT_ROOT、数值列未强转致 to_float 崩溃、保留字列名未转属性名致 As 数据静默丢失 632/649 行。

## 代码审查结论（review_mode: standard，最终 whole-branch 审查）

- 审查范围 `d480d68..9951d21`，无 Critical 问题。
- Important 问题 #1/#2/#3/#4 已修复（commit `9951d21`）：保留字 round-trip 回归测试、run_import 单源失败隔离、area_code 废弃标注、spec 列名兼容性描述修正。13 passed / 0 failed。

### 延后处理的 Minor 项（接受，记录原因与影响）

以下 5 项 Minor 经评估接受延后，不影响本次合并：
- #5 `scripts/import_lechang_data.py` 的 `FAKE_SOURCES` 死代码——无功能影响，清理属代码整洁，follow-up。
- #6 `soil_data_loader.py` 的 `load_soil_data` `except Exception` 过宽（吞所有异常降级 mock）——当前无生产消费者，未来接线时再收紧日志级别/异常分类。
- #7 `_resolve_files` 的 `{year}` 硬编码 2020-2024 且无单测——2025 年后新增数据需改常量，影响小；follow-up 补测试。
- #8 `ThirdSurveyProfile` 模型字段与 `specs/database-models/spec.md` 描述（"质地/容重/孔隙度"）不匹配——模型以实际 Excel 列为准，spec 描述为举例，follow-up 对齐 spec 文案。
- #9 `--dry-run` 模式无单测覆盖——逻辑简单（仅日志不写库），follow-up 补测试。

接受理由：均为代码整洁/文档/测试覆盖类 Minor，无功能或数据完整性风险；本次 change 核心目标（数据导入 + 保留字数据完整性 + 幂等性）已由 13 个测试 + 端到端集成验证覆盖。
