# Verification Report: import-lechang-soil-data

**Change**: import-lechang-soil-data
**Branch**: feature/20260723/import-lechang-soil-data
**Base ref**: d480d687 → HEAD: 7616bff (区间内含 7 个提交)
**Verify mode**: full
**Verify date**: 2026-07-24
**Language**: zh-CN

## Summary

| Dimension | Status |
|---|---|
| Completeness | 23/23 tasks [x]；2 capabilities（database-models / soil-data-ingestion）全部实现 |
| Correctness | 13/13 测试通过（fresh run，本会话亲自执行）；6 表真实数据导入；保留字 as_/yield_ 读写路径有 round-trip 回归测试 |
| Coherence | 设计决策 D1-D5 全部遵循；无 Critical；2 WARNING（非功能性，已记录） |

## 验证证据（fresh，本会话执行）

- **测试**：`.venv/Scripts/python.exe -m pytest tests/test_soil_data_models.py tests/test_import_lechang_data.py tests/test_soil_data_loader_db.py -v` → `13 passed in 12.92s`（含 `test_reserved_word_field_round_trip`）。
- **集成验证**（Task 4，commit f883a42）：8 表建表；6 表导入（topsoil649/profile216/site848/bd1003/second82/formula1233）；`load_soil_data()` 返回真实数据（649≠mock623, 1233≠mock1256）；幂等性（二次导入行数不变）；as_=632/649 非 None（与源吻合），yield_ 事务内 round-trip PASS。
- **代码审查**（review_mode: standard，最终 whole-branch，commit 9951d21）：无 Critical；4 项 Important 已修复（保留字 round-trip 测试 / run_import 单源失败隔离 / area_code 废弃标注 / spec 列名兼容性描述）；5 项 Minor 接受延后（记录于 tasks.md）。

## 7 项完整验证检查

1. **tasks.md 全部完成** — PASS（`grep '\- \[ \]'` 计数 0；含集成验证说明与审查结论记录）。
2. **实现符合 design.md 高层决策** — PASS。D1 按数据源分表、D2 先清除后导入幂等、D3 DB 读取+mock 降级、D4 硬编码列名映射、D5 SQLite/MySQL 双兼容均落实。
3. **实现符合 Design Doc**（`docs/superpowers/specs/2026-07-23-import-lechang-soil-data-design.md`）— PASS。loader `_query_to_dataframe` 用 `mapper.column_attrs.attr.key` 是对 plan 示例代码（`c.name`）的必要修正，非设计偏离。
4. **能力规格场景** — PASS（1 WARNING）。database-models 6 场景全部满足；soil-data-ingestion 场景除「成功导入所有数据源」外全部满足（见 WARNING-1）。
5. **proposal.md 目标** — PASS（1 WARNING）。数据导入底座、幂等脚本、loader 改造均达成（见 WARNING-2）。
6. **delta spec 与 design doc 无矛盾** — PASS。spec.md「顶层键兼容、列名不兼容」与 design D3「接口不变」（指函数签名+顶层键）指不同层面，不矛盾。
7. **Design Doc 可定位** — PASS（`docs/superpowers/specs/2026-07-23-import-lechang-soil-data-design.md` 存在且属本 change）。

## Issues

### CRITICAL
无。

### WARNING（已记录，非功能性，不影响归档）

**WARNING-1：2 张表因源 .xls 加密而为空**
- `agri_chemicalizations`、`grain_yields` 两表行数为 0。原因：`data/lechang/` 下 10 个 .xls 文件被加密，导入脚本按设计跳过并 warning。
- 影响：soil-data-ingestion spec 的「成功导入所有数据源」场景（每张表行数 > 0）部分未满足。但「部分数据文件缺失」场景（跳过+warning+继续）已正确满足。
- 处理：属源数据限制而非实现缺陷。`yield_` 保留字字段已用事务内 insert+rollback 等价实证。若需这两表数据，需提供解密版 .xls。

**WARNING-2：proposal/design 前提「模型 4/5/6 调用 load_soil_data()」与实际不符**
- 经核实（`grep load_soil_data` 全仓），`load_soil_data()` 当前无生产消费者；模型 4/5/6（model_4/5/6.py 及其 agent 包装）接收用户输入特征字典，不通过该函数读 DB。
- 影响：proposal「导入后模型 4/5/6 读取真实乐昌数据」的前提不成立。乐昌土壤数据定位为参考数据入库，供未来接线/RAG 使用。
- 处理：tasks.md 5.4 已重定范围为「验证导入数据经 ORM 可查 + 保留字读写」，属小范围 spec 偏差并记录。未来接线模型时需注意 DB 路径返回英文属性名列（非 mock 中文列名）。

### SUGGESTION
- 5 项 Minor（FAKE_SOURCES 死代码 / load_soil_data except 过宽 / {year} 硬编码 / ThirdSurveyProfile 字段描述 / --dry-run 测试）已记录于 tasks.md 作为 follow-up，不影响本次归档。

## 最终评估

无 Critical 问题。2 项 WARNING 均为非功能性（源数据加密限制 + 文档前提偏差），已记录原因与影响范围。实现正确性、数据完整性（保留字）、幂等性由 13 个测试 + 端到端集成验证覆盖。**Ready for archive（含已记录的改进项）。**
