# Comet Design Handoff

- Change: align-model3-to-field-standard
- Phase: design
- Mode: compact
- Context hash: 0a1f33df5e7321ec4a7ed926fde231a427031ecd23c5f92f0d303d1fcb97eab5

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/align-model3-to-field-standard/proposal.md

- Source: openspec/changes/align-model3-to-field-standard/proposal.md
- Lines: 1-48
- SHA256: 455d4e5a3c8acc8fdf976aaf985d8f57a3856771eba2b28bb362654ac3ed57b9

```md
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

```

## openspec/changes/align-model3-to-field-standard/design.md

- Source: openspec/changes/align-model3-to-field-standard/design.md
- Lines: 1-79
- SHA256: a614309da40393c3c0d8d07cd217b1255f39eabba50e99ea8a291c23656c9925

```md
## Context

项目 model-3（farmland_diagnosis）当前使用非标准字段命名（PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH，后缀 _LD/_OD），与模型提供方发布的《数据字段标准化》规范不一致。模型提供方已交付 V2.0 实现（calculatorall.py + mappings_config.py），采用标准命名（SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD，后缀 LSD/ZAD/ZADJ），并修复了障碍度覆盖原始值的 bug，新增了障碍诊断输出（ZALX/ZYZAYS/CYZAYS）。

当前 model-3 的代码结构：
- `config.py`：配置（COEFFICIENTS/WEIGHTS/TEXT_VALUE_MAPS/INDICATOR_NAME_MAP/calc_obstacle_level）
- `evaluation.py`：评价逻辑（evaluate_single/bulk_evaluate）
- `diagnosis.py`：诊断逻辑（diagnosis_row/diagnose/query_parcel）
- `storage.py`：SQLite 存储（evaluation_results/diagnosis_results 表）
- `problem_agent.py`（framework 侧）：消费 model-3 输出的 agent

V2.0 的关键改进：
1. 障碍度使用独立列 `xxxZAD`，不覆盖原始指标值
2. 障碍等级使用 `xxxZADJ` 列名
3. 新增 `ZALX`/`ZYZAYS`/`CYZAYS` 障碍诊断输出
4. 障碍诊断逻辑（diagnosis_row）内置在主流程中，包含主要/次要因素判定和中文显示名替换

## Goals / Non-Goals

**Goals:**
- 将 model-3 全部字段命名对齐到《数据字段标准化》规范
- 修复障碍度覆盖原始值的 bug
- 新增障碍诊断输出（ZALX/ZYZAYS/CYZAYS）并暴露到 agent 响应
- 保持 model-3 现有功能完整性（评价、诊断、查询、酸化改良）
- 更新全部相关测试

**Non-Goals:**
- 不修改 model-1（farmland_stability）、model-7（farmland_grade_eval）等其他模型
- 不修改 API 对外路由结构（question_type 路由不变）
- 不修改 RAG、LLM service 等框架基础设施
- 不迁移现有数据库旧数据（diagnosis_results 表已知为空）
- 不修改 openapi.json 的对外接口结构

## Decisions

### 决策1：直接重命名字段，不引入抽象映射层

**选择**：在 model-3 代码中直接将字段名从非标准改为标准命名。

**理由**：引入抽象映射层会增加运行时开销和维护复杂度，且 model-3 是独立模块，字段名变更范围可控。直接重命名更清晰，与 V2.0 实现一致。

**替代方案**：在输入/输出层增加字段映射适配器。否决，因为增加了不必要的间接层，且 V2.0 已使用标准命名，无需再映射。

### 决策2：障碍度使用独立 ZAD 列，保留原始指标值

**选择**：障碍度存储在 `xxxZAD` 列中，不覆盖原始指标值。

**理由**：V2.0 已修复此 bug。当前项目的 `evaluation.py` 中障碍度使用 `_OD` 后缀独立存储（实际上当前项目没有覆盖 bug，是 V2.0 的前一个版本有此 bug），但需要统一命名为 `ZAD`。

### 决策3：障碍诊断逻辑采用 V2.0 的内置方式

**选择**：将障碍诊断（diagnosis_row）的逻辑对齐 V2.0 实现，包括主要/次要因素判定阈值和中文显示名替换。

**理由**：V2.0 的 diagnosis_row 逻辑更完整，包含缩写→中文替换（replace_abbr_in_text），输出的 ZYZAYS/CYZAYS 是可读的中文描述。当前项目的 diagnosis.py 逻辑相似但使用 INDICATOR_NAME_MAP 做映射，需要对齐。

### 决策4：数据库表结构重建，不迁移旧数据

**选择**：修改 storage.py 中的 CREATE TABLE 语句使用新字段名，删除旧 .db 文件后重建。

**理由**：项目记忆记录 diagnosis_results 表为空（pre-existing data gap），evaluation_results 表的数据为测试数据，可重新生成。迁移空数据无意义。

### 决策5：输入 CSV 区域列名改为 YJNYQ/EJNYQ

**选择**：CSV 输入使用 `YJNYQ`（一级农业区）和 `EJNYQ`（二级农业区）作为列名，值为中文区名（如"华南区"）。

**理由**：与 V2.0 和《数据字段标准化》规范一致。COLUMN_RENAME 映射从 `一级农业区→JY` 改为 `YJNYQ→YJNYQ`（即不再需要重命名，直接使用标准列名）。

### 决策6：problem_agent.py 暴露新增诊断输出

**选择**：在 problem_agent.py 的 answer_question 中，将 `grade` 引用改为 `GDZLDJ`，并在响应中暴露 `ZALX`/`ZYZAYS`/`CYZAYS`。

**理由**：用户确认需要暴露到响应中，与标准规范一致。

## Risks / Trade-offs

- **[BREAKING 字段名变更]** → 所有引用 model-3 输出字段的代码必须同步更新；通过全量测试验证覆盖
- **[数据库表结构变更]** → 现有测试数据库需要重建；通过在测试中使用临时目录避免影响
- **[problem_agent.py 消费端变更]** → agent 响应字段名变化可能影响前端；但当前 API 对外路由结构不变，仅内部字段名调整
- **[V2.0 逻辑差异]** → V2.0 的 diagnosis_row 阈值与当前项目可能存在细微差异；通过对比测试验证一致性

```

## openspec/changes/align-model3-to-field-standard/tasks.md

- Source: openspec/changes/align-model3-to-field-standard/tasks.md
- Lines: 1-65
- SHA256: 719191da0b3019986c846014a9f54a395ccd84f1519f765c640a5c961e177ab9

```md
## 1. 配置层字段标准化（config.py）

- [ ] 1.1 更新 COEFFICIENTS 字典：将指标键名从 PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH 改为 SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD
- [ ] 1.2 更新 WEIGHTS 字典：将指标键名同步改为标准命名
- [ ] 1.3 更新 COLUMN_RENAME：将映射从 `一级农业区→JY`/`二级农业区→EJ` 改为 `YJNYQ→YJNYQ`/`EJNYQ→EJNYQ`（即直接使用标准列名，移除中文列名映射）
- [ ] 1.4 更新 TEXT_VALUE_MAPS：将键名从 DX/GZ/ZD/GG/PS 改为 DXBW/GCZD/ZDGX/GGNL/PSNL
- [ ] 1.5 更新 INDICATOR_NAME_MAP：将键名从 PH/YJ/etc. 改为 SJD/YJZ/etc.，值保持中文显示名
- [ ] 1.6 更新 calc_obstacle_level 函数：将所有指标引用从 PH/YJ/YXP/SXK/RZ/GZ/GG/PS/DX/ZD/YXT/GCH 改为标准命名，隶属度引用从 xxx_LD 改为 xxxLSD

## 2. 评价逻辑标准化（evaluation.py）

- [ ] 2.1 更新 evaluate_single：将 continuous_cols/discrete_cols/weighted_indicators 列表改为标准命名，隶属度后缀从 _LD 改为 LSD，障碍度后缀从 _OD 改为 ZAD
- [ ] 2.2 更新 evaluate_single：将 composite_weight 改为 ZHQZ，grade 改为 GDZLDJ
- [ ] 2.3 更新 evaluate_single：障碍等级列名从 `INDICATOR_NAME_MAP[ind]+'障碍等级'` 改为 `ind+'ZADJ'`（使用标准指标代码+ZADJ后缀）
- [ ] 2.4 新增障碍诊断输出：在 evaluate_single 中集成 diagnosis_row 逻辑，生成 ZALX/ZYZAYS/CYZAYS 字段
- [ ] 2.5 更新 bulk_evaluate：将 required 列表从 JY/EJ/PH/etc. 改为 YJNYQ/EJNYQ/SJD/etc.，区域映射字段从 JY 改为 YJNYQ
- [ ] 2.6 更新 bulk_evaluate：移除 COLUMN_RENAME 中的中文列名映射依赖，直接使用 YJNYQ/EJNYQ 标准列名

## 3. 诊断逻辑标准化（diagnosis.py）

- [ ] 3.1 更新 diagnosis_row：将 _OD 后缀改为 ZAD，`障碍等级` 改为 ZADJ 后缀匹配逻辑
- [ ] 3.2 更新 diagnosis_row：对齐 V2.0 的 replace_abbr_in_text 逻辑，使用 INDICATOR_DISPLAY_MAP 将缩写替换为中文显示名
- [ ] 3.3 更新 diagnose 函数：将 weighted_indicators 列表改为标准命名，字段引用从 _OD 改为 ZAD
- [ ] 3.4 更新 diagnose 函数：障碍等级引用从 `INDICATOR_NAME_MAP[ind]+'障碍等级'` 改为 `ind+'ZADJ'`
- [ ] 3.5 更新 query_parcel：确保返回的 evaluation 和 diagnosis 数据使用标准字段名

## 4. 存储层标准化（storage.py）

- [ ] 4.1 更新 create_tables：将 evaluation_results 表列名从 PH/YJ/etc. 改为 SJD/YJZ/etc.，隶属度列从 xxx_LD 改为 xxxLSD
- [ ] 4.2 更新 create_tables：将 composite_weight 改为 ZHQZ，grade 改为 GDZLDJ
- [ ] 4.3 更新 create_tables：将 diagnosis_results 表的障碍等级列从 `xxx_obstacle_level` 改为 `xxxZADJ`，障碍度列从 `xxx_obstacle_degree` 改为 `xxxZAD`
- [ ] 4.4 更新 create_tables：在 diagnosis_results 表中新增 ZALX/ZYZAYS/CYZAYS 列
- [ ] 4.5 更新 save_evaluation：将所有字段引用改为标准命名
- [ ] 4.6 更新 save_diagnosis：将所有字段引用改为标准命名，新增 ZALX/ZYZAYS/CYZAYS 字段存储
- [ ] 4.7 删除旧数据库文件（farmland_diagnosis.db），确保表结构重建

## 5. 消费端更新（problem_agent.py）

- [ ] 5.1 更新 answer_question：将 evaluation.get("grade") 改为 evaluation.get("GDZLDJ")
- [ ] 5.2 更新 answer_question：将 diagnosis.get("obstacle_type") 改为 diagnosis.get("ZALX")，main_factors 改为 ZYZAYS，secondary_factors 改为 CYZAYS
- [ ] 5.3 在 agent 响应中暴露 ZALX/ZYZAYS/CYZAYS 字段

## 6. 模块导出更新（__init__.py）

- [ ] 6.1 更新 __init__.py 导出列表，确保新增的障碍诊断函数和配置正确导出

## 7. 测试更新（tests/test_farmland_diagnosis.py）

- [ ] 7.1 更新 test_region_map/test_coefficients_exists/test_weights_exists/test_indicator_name_map：将字段引用改为标准命名
- [ ] 7.2 更新 test_calc_obstacle_level_* 测试：将 row 字典键名从 PH/YJ/SXK 改为 SJD/YJZ/SXJ
- [ ] 7.3 更新 test_storage_* 测试：将 record 字典字段名改为标准命名（SJD/YJZ/etc.，xxxLSD，ZHQZ，GDZLDJ）
- [ ] 7.4 更新 test_evaluate_single/test_bulk_evaluate：将输入数据和断言字段改为标准命名
- [ ] 7.5 更新 test_diagnosis_row_* 测试：将 _OD 后缀改为 ZAD，障碍等级改为 ZADJ
- [ ] 7.6 更新 test_diagnose_flow：验证 ZALX/ZYZAYS/CYZAYS 输出
- [ ] 7.7 新增测试：验证障碍度不覆盖原始指标值（ZAD 列独立于原始值）

## 8. 文档纳入

- [ ] 8.1 确认 docs/model-integration-analysis.md 和 docs/model-provider-spec.md 纳入版本控制

## 9. 验证

- [ ] 9.1 运行 tests/test_farmland_diagnosis.py 全部测试通过
- [ ] 9.2 运行项目整体测试套件确认无回归
- [ ] 9.3 验证标准测试数据输入后输出字段名符合 Excel 规范

```

## openspec/changes/align-model3-to-field-standard/specs/farmland-obstacle-diagnosis-model/spec.md

- Source: openspec/changes/align-model3-to-field-standard/specs/farmland-obstacle-diagnosis-model/spec.md
- Lines: 1-76
- SHA256: 4706331dbf44c391de57c168a7ba05b9ded2e31a1ac1270a0f1fa6482c6b9364

```md
## MODIFIED Requirements

### Requirement: 模型3 批量质量等级评价
系统 SHALL 提供基于 CSV 的批量质量等级评价入口，对包含 12 项指标（SJD/pH、YJZ/有机质、YXL/有效磷、SXJ/速效钾、TRRZ/容重、GCZD/耕层质地、GGNL/灌溉能力、PSNL/排水能力、DXBW/地形部位、ZDGX/质地构型、YXTCHD/有效土层、GCHD/耕层厚度）和区域信息（YJNYQ 一级农业区、EJNYQ 二级农业区）的 CSV 数据执行隶属度计算、综合权重计算和质量等级划分(1-10等)。障碍度 SHALL 存储在独立的 `xxxZAD` 列中，不得覆盖原始指标值。

#### Scenario: 执行批量评价
- **WHEN** 管理员触发批量评价，且 CSV 文件已部署到指定目录，包含必需字段（YJNYQ、EJNYQ、SJD、YJZ、YXL、SXJ、TRRZ、GCZD、GGNL、PSNL、DXBW、ZDGX、YXTCHD、GCHD）
- **THEN** 系统 SHALL 调用评价逻辑处理 CSV，计算各指标隶属度（`xxxLSD` 列）、综合权重（`ZHQZ` 列）、质量等级（`GDZLDJ` 列），并按区域配置的阈值划分质量等级，输出包含 `xxxLSD`、`ZHQZ`、`GDZLDJ` 的结果

#### Scenario: 障碍度不覆盖原始值
- **WHEN** 系统计算障碍度时
- **THEN** 障碍度 SHALL 存储在独立的 `xxxZAD` 列中，原始指标值（如 SJD、YJZ 等） SHALL 保持不变，不得被覆盖为 NaN

#### Scenario: CSV 字段缺失
- **WHEN** 批量评价被触发，但 CSV 文件缺少必需字段（如 YJNYQ、SJD、YJZ 等）
- **THEN** 系统 SHALL 返回明确的错误信息，列出缺失的字段，不执行部分计算

#### Scenario: 区域名称无效
- **WHEN** CSV 中存在未在 REGION_MAP 或 SECONDARY_REGION_MAP 中定义的区域名称
- **THEN** 系统 SHALL 返回错误信息，列出无效区域名称所在的行号

### Requirement: 模型3 障碍诊断
系统 SHALL 基于评价输出（包含隶属度 `xxxLSD`、综合权重 `ZHQZ`、质量等级 `GDZLDJ`）执行障碍诊断，计算各指标障碍度（`xxxZAD`）和障碍等级（`xxxZADJ`），识别障碍类型（`ZALX`：单一障碍/多障碍/无明显障碍）、主要障碍因素（`ZYZAYS`）和次要障碍因素（`CYZAYS`）。

#### Scenario: 执行障碍诊断
- **WHEN** 评价输出已就绪，且包含所有指标隶属度和障碍度字段
- **THEN** 系统 SHALL 对每行数据进行障碍诊断，输出 `ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素描述，含中文指标名）、`CYZAYS`（次要障碍因素描述，无次要因素时显示"无"）

#### Scenario: 障碍度计算
- **WHEN** 系统计算各指标障碍度
- **THEN** 障碍度 SHALL 按 `(1-隶属度)*权重 / 总和` 计算，存储在 `xxxZAD` 列中，障碍等级存储在 `xxxZADJ` 列中（含方向描述，如"重度酸化"、"中度板结"）

#### Scenario: 无明显障碍
- **WHEN** 某地块所有指标的障碍度均低于阈值（主要障碍度 < 20%，次要障碍度 < 10%）
- **THEN** 系统 SHALL 返回 `ZALX` 为"无明显障碍"，`ZYZAYS` 和 `CYZAYS` 为空

#### Scenario: 单一障碍
- **WHEN** 某地块只有一个指标的障碍度达到主要障碍阈值（>= 20%），且没有其他中度以上障碍
- **THEN** 系统 SHALL 返回 `ZALX` 为"单一障碍"，`ZYZAYS` 仅列出该指标，`CYZAYS` 显示"无"

#### Scenario: 多障碍
- **WHEN** 某地块有多个指标的障碍度达到主要或次要障碍阈值
- **THEN** 系统 SHALL 返回 `ZALX` 为"多障碍"，`ZYZAYS` 和 `CYZAYS` 按障碍度降序列出主要和次要因素

### Requirement: 模型3 障碍组合类型识别
系统 SHALL 识别障碍组合类型，支持单一障碍、双重障碍和多因素叠加障碍等组合类型的判定。障碍类型结果存储在 `ZALX` 字段中。

#### Scenario: 识别障碍组合类型
- **WHEN** 系统完成障碍诊断后，识别到多个中度以上障碍因素
- **THEN** 系统 SHALL 返回 `ZALX` 为"多障碍"，并在 `ZYZAYS` 中列出障碍组合描述（如"pH(重度酸化, 11.2%)；速效钾(重度缺乏, 26.5%)"）

### Requirement: 模型3 在线障碍诊断查询
系统 SHALL 提供在线查询接口，按地块 ID 从批量评价和障碍诊断结果中查询障碍诊断信息，对接 `run_thematic_model()` 的统一调用契约。查询结果 SHALL 包含标准字段命名的评价和诊断数据。

#### Scenario: 查询指定地块的障碍诊断结果
- **WHEN** 调用方以地块 ID 发起在线查询，且批量评价和障碍诊断结果已就绪
- **THEN** 系统 SHALL 返回该地块的 `ZALX`（障碍类型）、`ZYZAYS`（主要障碍因素）、`CYZAYS`（次要障碍因素）、`GDZLDJ`（质量等级）和各指标障碍度排序

#### Scenario: 诊断数据未就绪
- **WHEN** 调用方发起在线查询，但批量评价和障碍诊断尚未完成或结果文件缺失
- **THEN** 系统 SHALL 返回 `status: "not_ready"` 和"数据未就绪，请先执行批量评价"的提示

#### Scenario: 酸化改良模块字段对齐
- **WHEN** 酸化改良模块（evaluate_acidification / query_acidification）从 evaluation_results 读取地块数据执行酸化分区与改良方案生成
- **THEN** 系统 SHALL 使用标准字段名读取数据：pH 值取自 `SJD` 列、有机质取自 `YJZ` 列、区域代码取自 `region_code` 列；不得引用旧字段名（`PH`、`YJ`、`JY`），并 SHALL 按地块实际 `region_code` 选择酸化分级配置（不得因字段缺失恒回退到默认区）

### Requirement: 模型3 数据导入接口
系统 SHALL 提供数据导入接口，支持上传新的 CSV 数据并触发重新评价和诊断。CSV 数据 SHALL 使用标准字段命名（YJNYQ、EJNYQ、SJD、YJZ 等）。

#### Scenario: 导入新 CSV 数据
- **WHEN** 用户通过导入接口上传 CSV 文件
- **THEN** 系统 SHALL 将文件部署到数据目录，并提示用户触发批量评价以更新诊断结果

#### Scenario: 导入数据格式校验
- **WHEN** 用户上传的 CSV 缺少必需字段（如 YJNYQ、EJNYQ、12 项标准指标字段）
- **THEN** 系统 SHALL 拒绝导入并返回缺失字段列表

```
