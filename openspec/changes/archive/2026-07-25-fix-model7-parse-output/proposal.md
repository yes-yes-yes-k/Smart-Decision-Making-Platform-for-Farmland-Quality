## Why

model-7（FarmlandGradeObstacleAgent）通过 subprocess 调用 `Farmland_quality_evaluation.exe` 获取耕地质量等级评价结果。当前 exe 调用本身成功并返回原始输出，但 `runner.py` 的 `parse_output` 函数与 exe 实际输出格式不匹配（section 标记识别错误、障碍度字段提取逻辑问题），导致解析结果为空，agent 无法返回真实的质量等级、综合指数和障碍度诊断结果。

该 bug 使 model-7 虽然加载为"真实计算"agent，但实际评价结果无法正确解析返回，违背了 `professional-model-agents` spec 中 `FarmlandGradeObstacleAgent 智能体` requirement 的"质量等级查询"和"障碍度诊断"场景验收条件。

## What Changes

- 修复 `src/ai_culti_demo/farmland_grade_eval/runner.py` 的 `parse_output` 函数，使其正确识别 Fortran exe 输出的 section 标记和字段格式
- 修正障碍度排序表的解析逻辑，确保能提取 12 项指标的障碍度值并按从大到小排序
- 修正质量等级、综合指数等关键字段的提取逻辑
- 补充/更新对应单元测试，覆盖真实 exe 输出格式的解析场景

## Capabilities

### New Capabilities
无

### Modified Capabilities
无（spec 级别行为不变，仅修复实现层 bug 以满足已有验收场景）

## Impact

- **受影响代码**：`src/ai_culti_demo/farmland_grade_eval/runner.py`（`parse_output` 函数及相关辅助函数）
- **受影响测试**：`farmland_grade_eval` 模块对应的测试文件
- **不受影响**：exe 调用逻辑、agent 注册、API 接口、数据库 schema
- **依赖**：无新增依赖
