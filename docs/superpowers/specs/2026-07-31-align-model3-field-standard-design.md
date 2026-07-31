---
comet_change: align-model3-to-field-standard
role: technical-design
canonical_spec: openspec
---

# Design Doc: align-model3-to-field-standard

将 model-3（farmland_diagnosis）字段命名对齐到《数据字段标准化》规范与模型3 V2.0 实现，保留 DB 持久化 + 在线查询架构，移植 V2.0 关键函数，顺带修复 diagnosis_row 与 acidification 两个潜伏 bug。

## 1. 背景与目标

模型提供方发布《数据字段标准化》规范并交付 V2.0 实现（`calculatorall.py` + `mappings_config.py`），采用标准命名体系（SJD/YJZ/YXL/SXJ/TRRZ/GCZD/GGNL/PSNL/DXBW/ZDGX/YXTCHD/GCHD，后缀 LSD/ZAD/ZADJ/QZ）。当前 model-3 使用非标准命名（PH/YJ/...，后缀 _LD/_OD），且障碍诊断存在字段大小写不匹配的生产 bug、acidification 读错列名的 bug。

**目标**：字段全量对齐标准命名；移植 V2.0 诊断语义（ZALX/ZYZAYS/CYZAYS 字符串输出）；修复潜伏 bug；保持 DB+在线查询架构和现有功能完整性。

**非目标**：不改 model-1/model-7；不改 API 对外路由结构；不改 RAG/LLM 基础设施；不迁移旧 DB 数据；不改 openapi.json 对外结构。

## 2. 架构与数据流（保留 + 对齐）

保留现有 DB 持久化 + 在线查询架构，仅对齐字段名与诊断语义：

```
CSV (标准码表头 YJNYQ/SJD/YJZ/.../GCHD，离散列值为中文)
   │
   ▼
bulk_evaluate()  ──存 DB──► evaluation_results (标准列名)
   │  • DISCRETE_CN_MAP: 中文值→码 (GCZD/GGNL/PSNL/DXBW/ZDGX)
   │  • calc_continuous/calc_discrete → xxxLSD
   │  • ZHQZ = Σ(LSD × 权重)  [权重按二级区 EJNYQ_code]
   │  • GDZLDJ = GRADE_CONFIG[YJNYQ_code] 分级
   │  • calc_obstacle_level + translate_obstacle_level → xxxZADJ
   │  • (1-LSD)×权重 / Σ → xxxZAD  (独立列，不覆盖原始值)
   ▼
diagnose()  ──读 DB──► diagnosis_row → 存 DB──► diagnosis_results
   │  • diagnosis_row(row, indicator_names, level_cols, degree_cols)
   │    → (ZALX, ZYZAYS, CYZAYS) 字符串三元组
   │  • replace_abbr_in_text: SJD→pH 等缩写转中文显示名
   ▼
query_parcel()  ──在线查──► {evaluation, diagnosis} (标准字段名)
   │
   ▼
problem_agent.py / thematic_models.py (消费端)
```

V2.0 的 `main()` 是一次性批处理脚本（无 DB），本项目不照搬该批处理模式，而是把 V2.0 的字段命名和关键函数语义移植到现有 DB 架构中。

## 3. 字段重命名映射表（权威表）

| 旧名 | 新名 | 旧后缀/字段 | 新后缀/字段 |
|------|------|------------|------------|
| PH | SJD | _LD (隶属度) | LSD |
| YJ | YJZ | _OD (障碍度) | ZAD |
| YXP | YXL | 障碍等级 (列名) | ZADJ |
| SXK | SXJ | composite_weight | ZHQZ |
| RZ | TRRZ | grade | GDZLDJ |
| GZ | GCZD | JY/EJ (区域列) | YJNYQ/EJNYQ |
| GG | GGNL | obstacle_type | ZALX |
| PS | PSNL | main_factors (list) | ZYZAYS (string) |
| DX | DXBW | secondary_factors (list) | CYZAYS (string) |
| ZD | ZDGX | | |
| YXT | YXTCHD | | |
| GCH | GCHD | | |

- `INDICATOR_NAME_MAP` → `INDICATOR_DISPLAY_MAP`（SJD→pH 等），用途从"列名生成"改为"缩写→中文显示替换"
- `COLUMN_RENAME` 移除（CSV 直接用标准码表头）
- `TEXT_VALUE_MAPS` → `DISCRETE_CN_MAP`（键改为 GCZD/GGNL/PSNL/DXBW/ZDGX，值映射不变）

## 4. 各模块改动设计

### 4.1 config.py
- `COEFFICIENTS` / `WEIGHTS` 键名全量改为标准码（系数/权重值不变）
- 移除 `COLUMN_RENAME`；`TEXT_VALUE_MAPS` → `DISCRETE_CN_MAP`（换键）
- `INDICATOR_NAME_MAP` → `INDICATOR_DISPLAY_MAP`
- 新增 `GRADE_CONFIG`（从 evaluation.py 抽出）
- 新增常量：`ALL_INDICATORS` / `CONTINUOUS_INDICATORS` / `DISCRETE_INDICATORS` / `WEIGHTED_INDICATORS`
- `calc_obstacle_level(row, indicators)`：键名改标准码；`GZ_LD`→`GCZDLSD`、`DX_LD`→`DXBWLSD`；逻辑不变

### 4.2 evaluation.py
- 新增 `translate_obstacle_level(ind, level, orig_val)`（从 evaluate_single inline 抽出，逻辑同 V2.0：SJD→酸化/碱化、TRRZ→板结/松散、YJZ→贫瘠/丰富、YXL/SXJ→缺乏/丰富）
- `evaluate_single`：
  - 用 `CONTINUOUS_INDICATORS` / `DISCRETE_INDICATORS` / `WEIGHTED_INDICATORS` 常量
  - 隶属度列 `ind + 'LSD'`
  - 障碍等级列 `ind + 'ZADJ'`（不再用 INDICATOR_DISPLAY_MAP 拼中文，统一用指标码）
  - 障碍度列 `ind + 'ZAD'`（独立列，不覆盖原始值）
  - 输出 `ZHQZ` / `GDZLDJ`
  - 使用 `GRADE_CONFIG[region_code]` 分级
- `bulk_evaluate`：
  - required 改 `['YJNYQ','EJNYQ'] + ALL_INDICATORS`
  - 移除 `df.rename(columns=COLUMN_RENAME)`
  - 区域映射：`df['YJNYQ'].map(REGION_MAP)` → `YJNYQ_code`；`df['EJNYQ'].map(SECONDARY_REGION_MAP)` → `EJNYQ_code`
  - 离散值转换：用 `DISCRETE_CN_MAP` 把中文值→码
  - 调 `evaluate_single(row, YJNYQ_code, EJNYQ_code)`

### 4.3 diagnosis.py
- `diagnosis_row(row, indicator_names, level_cols, degree_cols)`：改签名对齐 V2.0，返回 `(ZALX, ZYZAYS, CYZAYS)` 字符串三元组（`；`连接）。根治大小写 bug：level_cols 用 `ind+'ZADJ'`、degree_cols 用 `ind+'ZAD'`，统一指标码前缀，set 交集非空
- 阈值与 V2.0 一致：threshold_main=0.20, threshold_cumulative=0.60, threshold_heavy_boost=0.15, threshold_minor=0.10
- 新增 `replace_abbr_in_text(text, abbr_map)`：用 `INDICATOR_DISPLAY_MAP` 把 `SJD(...)`→`pH(...)` 等
- `parse_obstacle_level`：保留（逻辑同 V2.0）
- `diagnose(db_path)`：
  - 读 evaluation_results，对每行调 `diagnosis_row`
  - record 存 `parcel_id`, `ZALX`, `ZYZAYS`, `CYZAYS`，以及各 `xxxZADJ` / `xxxZAD`
- `query_parcel`：返回标准字段名

### 4.4 storage.py
- `evaluation_results` 表：
  - 原始值列：`SJD, YJZ, YXL, SXJ, TRRZ, GCZD, GGNL, PSNL, DXBW, ZDGX, YXTCHD, GCHD`（离散列 TEXT，连续列 REAL）
  - 隶属度列：`SJDLSD, YJZLSD, ...` REAL
  - 障碍等级列：`SJDZADJ, YJZZADJ, ...` TEXT
  - 障碍度列：`SJDZAD, YJZZAD, ...` REAL
  - `ZHQZ` REAL, `GDZLDJ` TEXT
  - 保留 `region_code`, `secondary_region_code`, `parcel_id`, 时间戳
- `diagnosis_results` 表：
  - 移除 `xxx_obstacle_level` / `xxx_obstacle_degree` / `main_factors` / `secondary_factors`（JSON list）
  - 新增 `ZALX` TEXT, `ZYZAYS` TEXT, `CYZAYS` TEXT
  - 保留各 `xxxZADJ` / `xxxZAD`（与 evaluation_results 一致命名）
- `acidification_results` 表：不变
- 删除旧 `farmland_diagnosis.db` 重建（CREATE TABLE IF NOT EXISTS，但旧库列名不匹配故需删库重建）
- `save_evaluation` / `save_diagnosis` / `get_diagnosis`：适配新列；`get_diagnosis` 不再 JSON loads list（ZYZAYS/CYZAYS 直接是 TEXT）

### 4.5 acidification.py（tasks.md 原漏项，本次补入）
- `row.get('PH', 6.5)` → `row.get('SJD', 6.5)`
- `row.get('YJ', 20)` → `row.get('YJZ', 20)`
- `row.get('JY', 'HN')` → `row.get('region_code', 'HN')`（顺带修读错列的旧 bug：原读 'JY' 但表里是 'region_code'，导致酸化评估恒用 HN 区）
- 其余酸化逻辑（classify/generate_amendment/calculate_lime_demand）不变

### 4.6 problem_agent.py
- `evaluation.get("grade")` → `evaluation.get("GDZLDJ")`
- `diagnosis.get("obstacle_type")` → `diagnosis.get("ZALX")`
- `diagnosis.get("main_factors", [])` (list) → `diagnosis.get("ZYZAYS", "")` (string)
- `diagnosis.get("secondary_factors", [])` (list) → `diagnosis.get("CYZAYS", "")` (string)
- answer 文本拼接：从 list 的 `'; '.join(...)` 改为直接用 ZYZAYS/CYZAYS 字符串（已是 `；`连接的可读描述）
- evidence 构造：从 main_factors 拆分改为直接引用 ZYZAYS 字符串或取前几项
- 模拟数据回退路径（MOCK_INDICATOR_GRADES）保持不变

### 4.7 __init__.py
- 导出新增常量：`GRADE_CONFIG`, `INDICATOR_DISPLAY_MAP`, `DISCRETE_CN_MAP`, `ALL_INDICATORS` 等
- 导出新增函数：`translate_obstacle_level`, `replace_abbr_in_text`
- 移除已删除的 `COLUMN_RENAME`, `TEXT_VALUE_MAPS`, `INDICATOR_NAME_MAP` 导出

## 5. 边界条件与 bug 修复

1. **diagnosis_row 大小写 bug（根治）**：统一用指标码生成 `SJDZAD`/`SJDZADJ`，set 交集非空，生产环境诊断不再恒返回"无明显障碍"
2. **acidification 读错列 bug（根治）**：`JY`→`region_code`，酸化评估不再恒用 HN 区
3. **障碍度不覆盖原始值**：`xxxZAD` 独立列，原始 SJD/YJZ 等保持不变（spec 已要求）
4. **CSV 编码兼容**：保留 utf-8/gbk 回退
5. **discrete 值未映射**：保留 V2.0 的警告打印 + NaN 处理
6. **sum_terms=0**：障碍度全部置 0.0（避免除零）
7. **CYZAYS 为空**：显示"无"（V2.0 行为）
8. **GCZD/DXBW 障碍等级依赖隶属度**：`calc_obstacle_level` 读 `GCZDLSD`/`DXBWLSD`，需在隶属度计算后调用

## 6. 测试策略

- 全量更新 `tests/test_farmland_diagnosis.py`：
  - 所有 row 字典键名改标准码（SJD/YJZ/SXJ 等）
  - record 字段名改标准码（xxxLSD, ZHQZ, GDZLDJ）
  - CSV 测试数据表头改标准码（YJNYQ/SJD/YJZ...）
  - 断言字段改标准码（`'SJDLSD' in result`, `result['GDZLDJ']`）
  - diagnosis 测试：`_OD`→`ZAD`，障碍等级列→`xxxZADJ`
- 新增测试：
  1. 障碍度不覆盖原始值：断言 `result['SJD']` 仍为原值，`result['SJDZAD']` 独立存在
  2. diagnosis_row 返回字符串三元组（ZALX/ZYZAYS/CYZAYS 均为 str）
  3. 端到端：bulk_evaluate → diagnose → query_parcel 返回 ZALX/ZYZAYS/CYZAYS
  4. acidification 用 region_code 正确分区（不再恒 HN）
- 可选 golden test：用 V2.0 `test.csv`/`test_result.csv` 对照输出字段名与等级
- 运行整体测试套件确认 model-1/model-7 无回归

## 7. Spec Patch

在 `specs/farmland-obstacle-diagnosis-model/spec.md` 的"模型3 数据导入接口"或新增小节补充验收场景：

> **Scenario: 酸化改良模块字段对齐**
> - **WHEN** 酸化改良模块从 evaluation_results 读取地块数据
> - **THEN** 系统 SHALL 使用标准字段名（SJD/pH、YJZ/有机质、region_code）读取，不得引用旧字段名（PH/YJ/JY）

属补充验收场景，不改变 delta spec 范围结构。

## 8. 实施顺序建议

1. config.py（常量 + calc_obstacle_level）— 基础
2. storage.py（表结构重建）— 数据层
3. evaluation.py（evaluate_single + bulk_evaluate + translate_obstacle_level）
4. diagnosis.py（diagnosis_row + replace_abbr_in_text + diagnose + query_parcel）
5. acidification.py（字段引用修正）
6. __init__.py（导出）
7. problem_agent.py（消费端）
8. tests/test_farmland_diagnosis.py（全量更新 + 新增）
9. 验证：单测 + 整体回归
10. 文档纳入：docs/model-integration-analysis.md, docs/model-provider-spec.md
