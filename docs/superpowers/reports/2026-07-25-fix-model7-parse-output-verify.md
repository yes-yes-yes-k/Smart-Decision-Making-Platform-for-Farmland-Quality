# 验证报告：fix-model7-parse-output

**Change**: fix-model7-parse-output
**Date**: 2026-07-25
**Workflow**: hotfix
**Verify Mode**: light（手动覆盖，实际代码改动仅 2 个文件）

## 变更摘要

修复 model-7（FarmlandGradeObstacleAgent）的 `runner.py` 中 `parse_output` 函数解析 bug。Fortran exe 调用成功并返回原始输出，但 parse_output 函数与 exe 实际输出格式不匹配，导致解析结果为空。修复后 model-7 能正确返回真实的耕地质量等级评价结果。

## 轻量验证 6 项检查结果

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | tasks.md 全部任务已完成 [x] | ✅ PASS | 3/3 任务全部勾选（1.1 修复 parse_output、2.1 单元测试、2.2 端到端验证） |
| 2 | 改动文件与 tasks.md 描述一致 | ✅ PASS | `git diff --stat master...HEAD -- src/ tests/` 显示 2 个文件：runner.py（86 行改动）、test_farmland_grade_eval.py（281 行新增） |
| 3 | 编译通过 | ✅ PASS | `python -m py_compile runner.py` 退出码 0 |
| 4 | 相关测试通过 | ✅ PASS | `pytest test_farmland_grade_eval.py` 19/19 通过（3.78s） |
| 5 | 无明显安全问题 | ✅ PASS | 搜索 password/secret/api_key/token/eval/exec/unsafe/os.system → 0 匹配 |
| 6 | 代码审查策略 | ⏭️ SKIP | review_mode: off（hotfix 默认值），跳过自动代码审查 |

## 测试详情

### test_farmland_grade_eval.py（19/19 通过）

**TestParseOutputRealSample（9 项）**：使用真实 exe 输出样本（A0001 地块）验证各字段解析正确
- test_parses_parcel_info_correctly：parcel_info 包含地块代码、经度、纬度、县区名称、二级农业区名称
- test_parses_all_12_indicators：12 项指标全部正确解析（name/code/raw_value）
- test_parses_composite_index_as_float：综合指数 0.6728（float 类型）
- test_parses_quality_grade_as_string：质量等级 "10等"（字符串）
- test_parses_all_12_obstacle_degrees：12 项障碍度全部正确解析（rank/indicator/degree/level）
- test_obstacle_ranks_are_sequential：rank 1-12 顺序排列
- test_obstacle_degrees_are_sorted_descending：障碍度值从大到小排序
- test_raw_output_preserved：原始输出保留
- test_no_extra_parcel_info_from_quit_prompt：quit 提示行不被误解析

**TestParseOutputBoundaryScenarios（8 项）**：边界场景覆盖
- test_empty_output：空输出
- test_whitespace_only_output：纯空白输出
- test_no_parcel_code_line：无地块代码行
- test_malformed_indicator_line_skipped：格式异常指标行跳过
- test_obstacle_line_with_invalid_degree_skipped：无效障碍度值跳过
- test_partial_sections_only_parcel：仅 parcel section
- test_composite_with_english_colon：英文冒号兼容
- test_potential_table_not_parsed_as_obstacle：潜力值表格不被误解析

**TestRunnerRunIntegration（2 项）**：端到端集成测试（exe 已部署）
- test_run_with_valid_parcel_code_returns_ok：runner.run('A0001') 返回 status=ok 且所有字段非空
- test_run_with_invalid_parcel_code_returns_error：无效地块代码返回 PARCEL_NOT_FOUND

### 回归测试

`test_stability_and_grade_integration.py`：25/26 通过（1 个 pre-existing 失败：`test_run_all_models_returns_nine_modules`，原因是测试代码 mock 不完整，未 mock `gpd.read_file`，在 master 分支上也失败，非本次引入）

## 端到端验证

运行 `runner.run('A0001')` 确认：
- status: ok
- parcel_info: 5 个字段（地块代码、经度、纬度、县区名称、二级农业区名称）
- indicators: 12 项指标
- composite_index: 0.6728
- quality_grade: "10等"
- obstacle_degree: 12 项障碍度（质地构型 0.169 中度障碍 → 有效土层厚度 0.0 无障碍）

## 根因消除确认

- 旧的 section 标记（'地块信息'/'指标评价'/'综合评价'/'障碍度排序'）已完全移除
- 新的 section 标记匹配 exe 实际输出关键词（'地块代码'/'原始指标值'/'耕地质量综合指数'/'障碍度因子'）
- 所有解析字段（parcel_info/indicators/composite_index/quality_grade/obstacle_degree）均正确返回非空值

## 验证结论

✅ **验证通过** — model-7 parse_output 解析 bug 已修复，所有测试通过，无安全问题，无回归。
