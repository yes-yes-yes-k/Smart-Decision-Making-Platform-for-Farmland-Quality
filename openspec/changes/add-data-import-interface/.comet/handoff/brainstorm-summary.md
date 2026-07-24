# Brainstorm Summary

- Change: add-data-import-interface
- Date: 2026-07-25

## 确认的技术方案

### 模块架构
- `framework/api/routes/data_import.py`：Flask Blueprint，POST /api/v1/data/import
- `framework/upload/data_validator.py`：CSV/shapefile/.dat 校验器
- `framework/upload/data_deployer.py`：备份 + 部署 + 清理 + 回滚
- `framework/upload/data_trigger.py`：触发器（ThreadPoolExecutor 超时控制）
- `framework/upload/audit_logger.py`：日志文件审计
- `src/ai_culti_demo/farmland_stability/precompute.py`：【新建】完整预计算流程

### 新建 precompute.py
封装 run_all_models → g_to_records → StabilityStorage.save_results → save_final_results 的完整流程。
- `g_to_records(G)`：用 MODULE_FIELDS 映射 module_1..9，RESULT_CN 做中文 key
- `main(shapefile_dir, manifest) -> dict`：返回 {status, processed, saved_to_db, output_files}

### Adapter 扩展（3 个新方法）
- `core_engine.bulk_evaluate_csv(csv_path) -> dict`
- `core_engine.precompute_stability(shapefile_dir, manifest) -> dict`
- `core_engine.check_grade_eval_deployment() -> dict`

### 触发器超时控制
concurrent.futures.ThreadPoolExecutor + future.result(timeout=600)；超时抛 TimeoutError，路由层捕获并回滚。

## 关键取舍与风险

| 取舍 | 选择 | 风险 |
|------|------|------|
| 同步触发 | 600s 超时 | 大数据量可能超时 → 文档提示上限 |
| 日志文件审计 | logs/data_import.log | 查询需 grep → v1 可接受 |
| 不加并发锁 | 文档提示 | 并发导入可能冲突 → 低频管理操作可接受 |
| CSV 重命名 test.csv | 一致性 | 原文件名仅存审计日志 |
| 新建 precompute.py | 填补空缺 | 范围略扩大 → 但必要且复用性强 |
| shapefile 字段校验时机 | 触发阶段（run_all_models 内置） | 上传阶段不校验字段 → 早期反馈弱，但避免重复打开 shapefile |

### DB 路径修正
- 诊断 DB：`data/farmland_diagnosis/farmland_diagnosis.db`（非 instance/farmland_diagnosis.db）
- 稳定性 DB：`data/farmland_stability/stability_results.db`（非 instance/farmland_stability.db）

## 测试策略

- **单元测试**：校验器、部署器、触发器、审计日志各自独立测试（monkeypatch adapter）
- **集成测试**：端到端测试三种数据类型上传 → 部署 → 触发 → 审计；触发失败回滚；备份保留策略
- **precompute 单元测试**：用小规模 mock GeoDataFrame 测试 g_to_records 转换正确性
- **不模拟 exe**：.dat 触发仅测 check_deployment 的 mock 返回

## Spec Patch

将回写 `openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md`：

1. **Shapefile trigger 场景细化**：`trigger_result` 应包含 `processed`（地块数）、`saved_to_db`（DB 写入数）、`output_files`（输出文件路径列表）
2. **字段校验时机说明**：上传阶段仅校验文件组件完整性；字段级校验由触发阶段 run_all_models 内置 require_columns 执行
3. **CSV 部署文件名**：补充场景说明 CSV 部署时重命名为 test.csv
4. **DB 路径修正**：design.md 中 DB 路径更正（spec.md 未提及具体路径，无需改）
