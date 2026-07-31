## Why

现有酸化改良模型基于 GB/T 42817-2023 规则导向的石灰剂量计算，仅使用 pH 和有机质两个输入，缺乏对土壤酸化过程的精确建模。模型提供方已交付基于过程的酸化计算模型（含4个子模型：水田/旱地 × 尿素/复合肥），使用土壤三普数据（pH、交换性氢、交换性铝）计算改良剂需求量（亿土康YTK/木本泥炭MBNT），能更精确地指导酸化改良。

## What Changes

- **BREAKING** 完全替换 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 中的 GB/T 42817-2023 规则导向石灰剂量计算逻辑，改为基于过程的酸化计算模型
- **BREAKING** 酸化改良输出从「石灰施用量(kg/亩)」改为「亿土康YTK(kg/ha) + 木本泥炭MBNT(kg/ha)」
- 新增交换性氢(JHX)、交换性铝(JLA)字段标准码到 `farmland_diagnosis/config.py`
- `framework/domain/other_models/model_4.py` 从占位实现替换为真实过程模型调用入口
- `framework/agents/specialized/acidification_agent.py` 适配新参数（fertilizer_type、land_type、JHX、JLA）
- `framework/agents/nodes.py` 透传 fertilizer_type 参数
- `framework/api/routes/chat.py` 接受 fertilizer_type 顶层参数
- 架构从 DB 持久化查询改为按需计算（类似 model-6 fertility ML）
- API 新增 `fertilizer_type` 参数（可选，默认 `compound` 复合肥；可选 `urea` 尿素）
- ~15 个过程模型默认参数（RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等）部分可配，通过 API 可选参数覆盖

## Capabilities

### New Capabilities

（无新增 capability — 全部在已有 capability 上修改）

### Modified Capabilities

- `farmland-acidification-improvement-model`: 完全替换酸化因子提取、酸化程度分区、改良方案生成、在线查询和输出格式5项需求。输入从 pH+有机质 改为 pH+交换性氢+交换性铝；计算从规则导向改为过程模型（4子模型）；输出从石灰施用量改为 YTK/MBNT；架构从 DB 查询改为按需计算。

## Impact

- **核心代码**：`src/ai_culti_demo/farmland_diagnosis/acidification.py`（完全重写）、`config.py`（新增字段码）
- **框架层**：`framework/domain/other_models/model_4.py`（替换占位）、`framework/agents/specialized/acidification_agent.py`（适配新参数）、`framework/agents/nodes.py`（透传 fertilizer_type）
- **API 层**：`framework/api/routes/chat.py`（接受 fertilizer_type 参数）
- **API 契约**：question_type=2 的响应字段从 `lime_demand`/`amendment_type`/`amendment_rate` 改为 `ytk`/`mbnt`
- **数据库**：现有 acidification_results 表数据不再使用（按需计算不依赖 DB），但保留表结构不删除
- **文档**：openapi.json、api.md、README.md 需同步更新
