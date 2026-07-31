## Why

模型提供方已发布《数据字段标准化》规范和模型3 V2.0实现，定义了所有模型统一的字段命名体系（SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD，后缀 LSD/ZAD/ZADJ/QZ）。当前项目 model-3（farmland_diagnosis）使用的是非标准命名（PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH，后缀 _LD/_OD），且障碍度计算存在覆盖原始值的 bug，缺少障碍诊断输出（ZALX/ZYZAYS/CYZAYS）。需要将 model-3 对齐到标准规范和 V2.0 实现，以便未来三个模型能够无缝集成。

## What Changes

- **BREAKING** 将 model-3 全部 12 项指标字段名从非标准命名（PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH）改为标准命名（SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD）
- **BREAKING** 将隶属度后缀从 `_LD` 改为 `LSD`（如 `PH_LD` → `SJDLSD`）
- **BREAKING** 将障碍度后缀从 `_OD` 改为 `ZAD`（如 `PH_OD` → `SJDZAD`）
- **BREAKING** 将障碍等级列名从 `xxx障碍等级` 改为 `xxxZADJ`（如 `PH障碍等级` → `SJDZADJ`）
- **BREAKING** 将综合权重字段从 `composite_weight` 改为 `ZHQZ`
- **BREAKING** 将质量等级字段从 `grade` 改为 `GDZLDJ`
- **BREAKING** 将区域输入字段从 `JY`/`EJ`（中文列名映射）改为 `YJNYQ`/`EJNYQ`（标准列名）
- 修复障碍度计算覆盖原始指标值的 bug（改用独立 `xxxZAD` 列，不覆盖原始值）
- 新增障碍诊断输出：`ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素）、`CYZAYS`（次要障碍因素）
- 将新增诊断输出暴露到 `problem_agent.py` 的 agent 响应中
- 更新 `storage.py` 表结构列名（重建不迁移旧数据）
- 更新 `tests/test_farmland_diagnosis.py` 全部测试用例的字段名
- 纳入两个文档：`docs/model-integration-analysis.md`（集成分析报告）和 `docs/model-provider-spec.md`（模型提供方修改规范）

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `farmland-obstacle-diagnosis-model`: 字段命名标准化（12项指标+隶属度+障碍度+障碍等级+综合权重+质量等级+区域字段），修复障碍度覆盖原始值 bug，新增障碍诊断输出（ZALX/ZYZAYS/CYZAYS），输入 CSV 区域列名改为 YJNYQ/EJNYQ

## Impact

**受影响代码：**
- `src/ai_culti_demo/farmland_diagnosis/config.py` — COEFFICIENTS/WEIGHTS/TEXT_VALUE_MAPS/INDICATOR_NAME_MAP/calc_obstacle_level 全部字段重命名
- `src/ai_culti_demo/farmland_diagnosis/evaluation.py` — evaluate_single/bulk_evaluate 字段重命名 + 新增障碍诊断输出
- `src/ai_culti_demo/farmland_diagnosis/diagnosis.py` — diagnosis_row/diagnose 字段重命名
- `src/ai_culti_demo/farmland_diagnosis/storage.py` — evaluation_results/diagnosis_results 表结构列名重命名
- `src/ai_culti_demo/farmland_diagnosis/__init__.py` — 导出接口微调
- `framework/agents/specialized/problem_agent.py` — 消费端字段名更新（grade→GDZLDJ, 新增 ZALX/ZYZAYS/CYZAYS）
- `tests/test_farmland_diagnosis.py` — 全部测试用例字段名更新

**受影响文档：**
- `docs/model-integration-analysis.md`（新增，集成分析报告）
- `docs/model-provider-spec.md`（新增，模型提供方修改规范）

**不受影响：**
- model-1（farmland_stability）、model-7（farmland_grade_eval）等其他模型
- API 对外路由结构（question_type 路由不变）
- RAG、LLM service 等框架基础设施
- 数据库：重建表结构，不迁移旧数据（diagnosis_results 表已知为空）
