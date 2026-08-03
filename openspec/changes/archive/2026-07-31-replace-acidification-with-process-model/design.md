## Context

现有酸化改良模型（系统 model-4 / AcidificationRemediationAgent）基于 GB/T 42817-2023 规则导向的石灰剂量计算，仅使用 pH（SJD）和有机质（YJZ）两个输入。模型提供方已交付基于过程的酸化计算模型（D:\destkop\模型5），包含4个子模型（水田/旱地 × 尿素/复合肥），使用土壤三普数据（pHstart、交换性氢Hex、交换性铝Alex）和~15个默认参数计算改良剂需求量（亿土康YTK/木本泥炭MBNT）。

当前架构：
- `src/ai_culti_demo/farmland_diagnosis/acidification.py`：规则导向计算（calculate_lime_demand/generate_amendment）+ DB 查询（query_acidification）
- `framework/agents/specialized/acidification_agent.py`（model-4）：尝试调用 query_acidification，失败时回退到 mock
- `framework/domain/other_models/model_4.py`：占位实现
- question_type=2 → model-4（路由不变）

约束：
- 字段标准码体系中无交换性氢/铝定义（config.py 的 ALL_INDICATORS 不含 JHX/JLA）
- API 层（chat.py）已透传 parcel_id/parcel_code/land_type，需新增 fertilizer_type
- nodes.py 已透传 land_type，需新增 fertilizer_type

## Goals / Non-Goals

**Goals:**
- 完全替换 GB/T 42817-2023 规则逻辑为基于过程酸化计算模型
- 支持4个子模型选择（land_type × fertilizer_type）
- 新增交换性氢(JHX)/交换性铝(JLA)字段标准码
- 按需计算架构（API 参数 → 直接计算 YTK/MBNT，不依赖 DB 预计算）
- ~15 个默认参数部分可配（通过 API 可选参数覆盖）
- 仅输出 YTK/MBNT，不暴露中间产酸量分解

**Non-Goals:**
- 不修改 question_type 路由架构（type 2 → model-4 不变）
- 不修改其他模型（model-1/2/3/5/6/7）
- 不删除现有 acidification_results 表（保留结构，不再使用）
- 不暴露 Adep/Acrop/ANcy/Aagri/Aback 中间产酸量
- 不实现批量预计算和 DB 持久化（按需计算即可）

## Decisions

### D1: 架构方向 — 按需计算（非 DB 持久化）

**选择**：API 参数直接计算 YTK/MBNT，不依赖 DB 预计算。

**理由**：
- 新模型仅需3个三普输入（pHstart/Hex/Alex）+ 默认参数，计算量小（纯数学公式，无 ML 推理）
- Hex/Alex 不在现有 evaluation_results 表 schema 中，DB 预计算需要先扩展 schema 再批量导入
- 与 model-6（fertility ML）一致的按需计算模式
- 用户已确认选择「按需计算（推荐）」

**替代方案（已否决）**：保留 DB 持久化 — 需扩展 schema、批量预计算、维护数据一致性，复杂度高且收益低。

### D2: 字段标准码命名 — JHX / JLA

**选择**：
- JHX = 交换性氢（Exchangeable Hydrogen）
- JLA = 交换性铝（Exchangeable Aluminum）

**理由**：
- 遵循现有命名规则（拼音首字母缩写：J=交换性，HX=氢，LA=铝）
- 与 config.py 中 SJD/YJZ 等命名风格一致
- 需添加到 ALL_INDICATORS 和 CONTINUOUS_INDICATORS

### D3: 模型入口 — framework/domain/other_models/model_4.py

**选择**：`model_4.py` 作为统一入口函数 `model_4_execution()`，内部调用 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 的过程计算函数。

**理由**：
- 与 model_6.py 模式一致（framework 层入口 → 调用 src 层实现）
- acidification_agent.py 通过 model_4_execution 获取结果，保持调用链统一

### D4: 参数传递 — fertilizer_type 作为 API 顶层参数

**选择**：
- `fertilizer_type`：API 顶层可选参数，默认 `compound`（复合肥），可选 `urea`（尿素）
- `land_type`：已有参数，默认 `upland`（旱地），可选 `paddy`（水田）
- 两者组合选择4个子模型之一

**理由**：
- 与 land_type 透传机制一致（chat.py → nodes.py → agent → model）
- 用户已确认「API 参数+默认复合肥」

### D5: 部分可配参数 — 3个三普输入必填 + ~15个默认参数可选覆盖

**选择**：
- 必填输入：pHstart(=SJD)、Hex(=JHX)、Alex(=JLA)
- 可选覆盖参数（通过 API context 传入）：RPH（降水pH）、R（年降水量）、Y（籽粒产量）、S（秸秆产量）、FertN（施肥量）、Ndep（N沉降）、pHtarget（目标pH）
- 不可配参数（元素含量 Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/YN/SN）：保持模型内置默认值

**理由**：
- 用户已确认「部分可配」
- 三普输入必须由用户提供（无默认值）
- 农业管理参数（产量、施肥量）可能因地区差异需要调整
- 元素含量参数为作物特性，一般不需要调整

### D6: 输出格式 — 仅 YTK/MBNT

**选择**：model_4_execution 返回 `{status, ytk, mbnt, land_type, fertilizer_type, model_version, warning}`

**理由**：
- 用户已确认「仅输出 YTK/MBNT」
- 中间产酸量（Adep/Acrop/ANcy/Aagri/Aback）对用户无直接意义

## Risks / Trade-offs

- **[风险] 字段码 JHX/JLA 未在现有数据管道中流转** → 缓解：在 config.py 新增定义，API 层直接接受 JHX/JLA 值（不依赖 CSV 导入管道，因为按需计算不需要批量导入）
- **[风险] 现有 acidification_results 表数据失效** → 缓解：保留表结构不删除，仅停止写入；按需计算不读取该表
- **[风险] API 响应字段从 lime_demand 改为 ytk/mbnt 是 BREAKING 变更** → 缓解：在 proposal 中明确标记 BREAKING，文档同步更新
- **[权衡] ~15个参数中仅7个可配，其余内置** → 用户确认可接受；如需扩展可在后续 change 中开放更多参数
- **[风险] land_type 与 fertilizer_type 的非法值处理** → 缓解：非法值回退到默认值并追加 warning 提示（与 model-6 land_type 处理模式一致）
