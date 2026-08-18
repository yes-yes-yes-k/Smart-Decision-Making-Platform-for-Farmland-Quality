## Context

当前 5 个专题模型 Agent 的 DB 数据流（`ParcelDataAccessor.get_parcel_indicators`）和持久化框架（`model_execution_log` + 结果表）已就绪，但 `execute` 方法返回占位值（`quality_grade=0`、`obstacle_type=未知`、`model_unavailable`）。原始计算逻辑在 `D:\destkop\模型1-5` 目录中，使用 Python/NumPy/Pandas/Scipy 实现，输入为 Shapefile/CSV。需要移植到框架中，从 DB 的 `soil_indicators` JSON 读取输入，计算后将结果持久化到 V3.0 结果表。

## Goals / Non-Goals

**Goals:**
- 5 个模型各自执行真实计算逻辑，返回非占位结果
- 统一 V3.0 英文 snake_case 字段名到各模型计算所需输入参数的映射
- 计算结果持久化到 V3.0 结果表（已验证 FK 关联正确）
- 每个模型可独立降级（DB 数据缺失时 fallback 到规则/默认值）

**Non-Goals:**
- 不修改 API 接口契约（`run_thematic_model` 入参/返回结构不变）
- 不修改现有数据库 schema（仅新增 `parcel_history_snapshot` 表）
- 不重新设计前端展示逻辑
- 不修改已归档 change 的产物

## Decisions

### D1: 模型系数存储方式 — Python 配置文件

**决策**: 将各模型的系数（隶属度参数 a/c/ut1/ut2、权重、等级阈值、障碍等级阈值）存储在 Python 配置文件中，而非 DB 表。

**理由**: 
- 系数来自学术研究，不频繁变更
- Python 文件支持类型注解和注释，可读性优于 DB JSON
- 避免增加 DB 查询开销
- 原始代码就是 Python 配置（`config.py`、`mappings_config.py`）

**替代方案**: 存储在 `exclusive_rule_config` 或新增 `model_coefficient_config` 表 — 增加查询开销和 migration 复杂度，且 V3.0 未定义此类表。

### D2: Model-1 稳定性 — 实现全部 9 模块（更新：用户确认）

**决策**: Model-1 实现全部 9 个模块（含需历史数据的模块 5-9 和需空间数据的模块 4/8）。新增 `parcel_history_snapshot` 表导入 2018/2021/2024 三期历史数据；模块 4/8 用 PostGIS `ST_DWithin` 查询邻域地块（替代原始 cKDTree）。

**理由**:
- 用户要求「确保计算逻辑都实现」，降级到 3 模块不满足目标
- PostGIS 已可用（geom 列 + GIST 索引），模块 4/8 空间查询可直接用 `ST_DWithin`
- 原始 Shapefile（2018/2021/2024）可导入 `parcel_history_snapshot` 表

**替代方案（已否决）**: 仅实现模块 1-3 降级 — 不满足用户要求。

### D3: Model-5 RF 模型 — 构建时重训 + 提交 .joblib（更新：用户确认）

**决策**: 原始 notebook 未保存模型文件。构建脚本 `scripts/train_dose_rf_models.py` 从 xlsx 读取训练数据，`RandomForestRegressor(n_estimators=100, random_state=230)` 重训，`joblib.dump` 保存到 `data/model_artifacts/{upland|paddy}_dose_rf.joblib`，模型文件提交仓库。运行时延迟加载，scikit-learn 为构建+运行时依赖。

**理由**:
- 原始 notebook 只训练评估，无 `joblib.dump`
- 构建时重训可复现（固定 random_state=230）
- scikit-learn 不可用时降级到规则路径

**替代方案**: 运行时按需训练（首次启动慢）/ KNN 查找替代（偏离 RF 逻辑）— 均否决。

### D4: 键名映射策略 — ParcelDataAccessor 统一映射层

**决策**: 在 `ParcelDataAccessor._map_indicators_to_inputs` 中实现 V3.0 英文 snake_case → 模型输入字段的统一映射，每个 Agent 通过 `agent_id` 选择对应的映射表。

**理由**:
- 当前 `soil_indicators` JSON 使用 V3.0 英文 snake_case（`soil_ph`、`organic_matter`、`available_potassium` 等）
- 原始模型使用拼音缩写（`SJD`、`YJZ`、`SXJ`）或英文字段名（`pH`、`SOMbe`、`AK`）
- 统一映射层避免每个 Agent 重复实现映射逻辑

**映射表**:
| V3.0 snake_case | Model-2/3 缩写 | Model-4 | Model-5 |
|-----------------|----------------|---------|---------|
| soil_ph | SJD | SJD | pH |
| organic_matter | YJZ | — | SOMbe |
| available_phosphorus | YXL | — | AP |
| available_potassium | SXJ | — | AK |
| bulk_density | TRRZ | — | — |
| topsoil_thickness | YXTCHD | — | — |
| plow_layer_thickness | GCHD | — | — |
| exchangeable_hydrogen | — | Hex | — |
| exchangeable_aluminum | — | Alex | — |
| total_nitrogen | — | — | TN |

### D5: 离散指标编码 — 英文/中文双映射（更新：DB 实际存英文值）

**决策**: DB `soil_indicators` 实际存储**英文值**（"loam"/"dry"/"lower"），非中文。保留原始 `DISCRETE_CN_MAP`（中文→代码），新增 `DISCRETE_EN_MAP`（英文→代码，如 "loam"→RT、"dry"→BM/US、"lower"→LHR）。映射时先尝试英文，再回退中文。

**理由**:
- 探索发现 DB 种子数据 `soil_texture`="loam"、`irrigation_condition`="dry"、`terrain_position`="lower"
- 原始 `DISCRETE_CN_MAP` 仅处理中文值，无法直接用于英文 DB 值
- 双映射兼容英文（当前 DB）和中文（可能的未来数据）

### D7: 二级农业区代码 — area_code→ejnyq 映射（新增：用户确认）

**决策**: 在 `coefficients.py` 定义 `AREA_TO_REGION` 映射表（如 `"440281"→{"secondary":"NL","primary":"HN","ejnyq_idx":3}`），不修改 DB schema，运行时查表。乐昌(440281)属华南区(HN)/南岭丘陵山地林农区(NL, index 3)。

**理由**:
- ParcelInfo 有 area_code 但无 ejnyq 字段
- Model-2 用 ejnyq_idx(0-3) 选系数，Model-3 用一级区(HN/CJ)选隶属度+二级区(MNY/YXG/NL/QN)选权重
- 映射表避免 schema 变更，area_code 是稳定的行政区码

### D8: Model-4 酸化常数 — 硬编码为函数默认参数（新增：用户确认）

**决策**: 4 个产酸平衡函数的农作物常数（RPH/R/Y/S/Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/FertN/Ndep）保留为函数默认参数（与原始 `02_酸化模型计算.py` 一致），不同 land_type×fertilizer_type 用不同默认值。`pHtarget` 从 `ParcelInfo.target_ph` 读取覆盖默认。

**理由**: 常数来自农学研究不常变；硬编码与原始逻辑完全一致；避免过度配置化。

### D6: 模型计算模块位置 — `framework/domain/calculations/`

**决策**: 新建 `framework/domain/calculations/` 目录，每个模型一个计算模块：
- `stability_calculation.py`（Model-1）
- `grade_calculation.py`（Model-2）
- `obstacle_calculation.py`（Model-3）
- `acidification_calculation.py`（Model-4）
- `organic_matter_calculation.py`（Model-5）
- `coefficients.py`（统一系数配置）

**理由**:
- 计算逻辑与 Agent 编排逻辑分离（Agent 负责 DB 读取 + 降级 + 持久化，计算模块负责纯计算）
- 计算模块无副作用，易于单元测试
- 符合项目现有 `framework/domain/` 目录结构

## Risks / Trade-offs

- **[Model-1 历史数据]** Shapefile parcel_id 与 DB parcel_id 可能不一致 → 导入脚本建立映射表，缺失地块降级
- **[PostGIS 邻域性能]** 模块 4/8 空间查询需限制 radius → GIST 索引已存在
- **[Model-5 RF 重训]** 重训结果与原始 notebook 可能不完全一致 → 固定 random_state=230，对照原始评估 RMSE
- **[离散英文映射不完整]** 英文→代码映射可能缺值 → 未知值降级为默认隶属度 0.5
- **[scikit-learn 依赖]** Model-5 需要 scikit-learn 加载 RF 模型 → 构建时+运行时依赖，不可用时降级到规则路径
- **[种子数据补全]** verify 脚本测试地块需补 exchangeable_aluminum/plow_layer_thickness/soil_structure → 在 build 阶段补全
- **[Model-2/3 系数层级]** Model-2 用二级区 index 选系数，Model-3 用一级区选隶属度+二级区选权重 → coefficients.py 明确区分两层

## Open Questions

无。所有技术决策已确定，不依赖未解决的未知项。
