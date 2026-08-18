## Why

验证报告显示 5 个专题模型的 DB 数据流和持久化框架已就绪，但计算逻辑未实现——Model-2 返回 `quality_grade=0`，Model-3 返回 `obstacle_type=未知`，Model-4 外部模型不可用，Model-5 仅执行简单规则，Model-1 完全降级。地块数据已从 DB 正确读取（`data_source=db`），但计算结果为占位值，无法为农业生产提供真实决策支持。原始计算逻辑已提供在 `D:\destkop\模型1-5` 目录中，需要移植到框架中。

## What Changes

- **Model-1 稳定性**: 移植 9 模块计算逻辑（等级边界安全度、指标支撑均衡度、关键指标临界度、空间邻域一致性、历史变化趋势、掉级风险、关键因子退化风险、退化空间集聚风险、持续低质风险），从 Shapefile 历史数据改为 DB 读取
- **Model-2 质量等级**: 移植隶属度函数（峰型/戒上型）+ 12 指标加权和 + 等级判定，配置 4 个二级农业区的系数（a/c/ut1/ut2）和权重
- **Model-3 障碍诊断**: 移植隶属度计算 + 障碍等级判定 + 障碍度计算 + 障碍诊断（主要/次要因子识别），配置 2 个一级农业区的系数和 4 个二级农业区的权重
- **Model-4 酸化改良**: 移植 4 个产酸平衡函数（水田尿素/水田复合肥/旱地尿素/旱地复合肥），计算石灰施用量（YTK）和有机肥施用量（MBNT），替代外部 .exe 模型
- **Model-5 有机质培肥**: 移植 Random Forest 模型预测 Dose，加载训练好的模型文件（旱地/水田各一个），替代简单规则降级路径
- **共享基础设施**: 统一 `soil_indicators` JSON 键名映射（V3.0 英文 snake_case → 模型计算所需字段名），修复 `ParcelDataAccessor._map_indicators_to_inputs` 的映射不完整问题
- **持久化**: 确保每个模型的计算结果正确持久化到 V3.0 结果表（stability_risk_result、quality_grade_result 等）

## Capabilities

### New Capabilities

- `farmland-stability-risk-evaluation`: Model-1 耕地质量稳定性与退化风险评价的 9 模块计算逻辑（边界安全度、支撑均衡度、邻域一致性、历史趋势、掉级风险、退化集聚等），从 DB 读取地块指标和历史数据

### Modified Capabilities

- `farmland-quality-grade-evaluation`: 增加 12 指标隶属度计算（峰型/戒上型函数）和 4 个二级农业区加权评价的 spec 要求，替代当前返回 `quality_grade=0` 的占位实现
- `farmland-obstacle-diagnosis-model`: 增加障碍等级判定（基于指标阈值）、障碍度计算（`(1-隶属度)*权重/总和`）和障碍诊断（主要/次要因子识别）的 spec 要求，替代当前返回 `obstacle_type=未知` 的占位实现
- `farmland-acidification-improvement-model`: 增加产酸平衡模型（4 函数：水田/旱地 × 尿素/复合肥）计算石灰和有机肥施用量的 spec 要求，替代当前 `model_unavailable` 的外部 .exe 依赖
- `fertility-ml-prediction`: 增加 Random Forest 模型加载和 Dose 预测的 spec 要求，替代当前简单规则降级路径
- `professional-model-agents`: 统一 `soil_indicators` JSON 键名映射 spec，确保 V3.0 英文 snake_case 字段名正确映射到各模型计算所需的输入参数

## Impact

- **代码**: `framework/agents/specialized/` 下 5 个 Agent 文件、`framework/domain/data/parcel_data_accessor.py`、`framework/domain/other_models/` 下模型计算模块
- **配置**: 新增模型系数配置文件（隶属度参数 a/c/ut1/ut2、权重、等级阈值）
- **数据**: 新增 RF 训练模型文件（旱地/水田 .joblib 或 .xlsx）
- **依赖**: 可能新增 `scikit-learn`（RF 模型加载）、`scipy`（空间邻域计算 cKDTree）
- **数据库**: 不修改 schema，但需确保 `soil_indicators` JSON 包含全部 12 个指标字段
- **测试**: 需新增每个模型计算逻辑的单元测试（使用真实系数验证计算结果）
