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
