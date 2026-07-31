## 1. 字段标准码新增

- [x] 1.1 在 `src/ai_culti_demo/farmland_diagnosis/config.py` 的 `ALL_INDICATORS` 列表新增 `JHX`（交换性氢）和 `JLA`（交换性铝）
- [x] 1.2 在 `CONTINUOUS_INDICATORS` 列表新增 `JHX` 和 `JLA`（两者均为连续指标）
- [x] 1.3 在 `INDICATOR_DISPLAY_MAP` 新增 `'JHX': '交换性氢'` 和 `'JLA': '交换性铝'` 映射

## 2. 过程模型核心实现

- [x] 2.1 在 `src/ai_culti_demo/farmland_diagnosis/acidification.py` 实现4个过程子模型函数：`paddy_urea`、`paddy_compound`、`upland_urea`、`upland_compound`（移植自模型5源码 02_酸化模型计算-地块.py）
- [x] 2.2 实现统一入口函数 `calculate_acidification_amendment(pHstart, Hex, Alex, land_type, fertilizer_type, **optional_params)` → 返回 `{ytk, mbnt, sub_model, ...}`
- [x] 2.3 定义4个子模型的默认参数集合（DEFAULT_PARAMS），包含 RPH/R/Y/S/元素含量/FertN/Ndep/pHtarget 等~15个参数
- [x] 2.4 实现可选参数覆盖逻辑：API 传入的可选参数（RPH/R/Y/S/FertN/Ndep/pHtarget）覆盖默认值，元素含量参数（Yp/Yk/Yca/Ymg/Sp/Sk/Sca/Smg/YN/SN）保持内置不可配
- [x] 2.5 实现输入校验：SJD 范围 [3.0, 10.0]、JHX/JLA 非负；越界返回 `status="rejected"` + 越界字段列表
- [x] 2.6 实现子模型选择逻辑：land_type × fertilizer_type → 4子模型之一；非法值回退默认（upland + compound）并追加 warning
- [x] 2.7 保留旧函数 `classify_acidification`/`generate_amendment`/`calculate_lime_demand` 标记为 deprecated（不删除，避免破坏其他引用），但 `query_acidification`/`evaluate_acidification` 改为委托新模型或标记 deprecated

## 3. model_4.py 入口实现

- [x] 3.1 在 `framework/domain/other_models/model_4.py` 实现 `model_4_execution(input_data, land_type=None, fertilizer_type=None)` 入口函数
- [x] 3.2 `model_4_execution` 内部调用 `calculate_acidification_amendment`，处理输入映射（SJD→pHstart、JHX→Hex、JLA→Alex）
- [x] 3.3 `model_4_execution` 返回标准化结构：`{status, ytk, mbnt, land_type, fertilizer_type, model_version, warning, customized_params}`
- [x] 3.4 支持 parcel_id 补充 SJD：若 input_data 包含 parcel_id 但无 SJD，从 evaluation_results 表查询 SJD

## 4. AcidificationRemediationAgent 适配

- [x] 4.1 更新 `framework/agents/specialized/acidification_agent.py` 的 `execute` 方法，调用 `model_4_execution` 而非旧 `query_acidification`
- [x] 4.2 更新 `answer_question` 方法，从 context 提取 `fertilizer_type` 并透传给 `model_4_execution`
- [x] 4.3 更新 answer 生成逻辑：使用 ytk/mbnt 替代 lime_demand/amendment_rate，移除 GB/T 42817-2023 引用
- [x] 4.4 更新 MOCK_INPUTS：新增 `jhx`（交换性氢）和 `jla`（交换性铝）默认值，保留 `exchangeable_al` 用于向后兼容
- [x] 4.5 移除 `_get_real_acidification` 中的 DB 查询逻辑，改为直接调用 `model_4_execution`

## 5. API 层透传

- [x] 5.1 在 `framework/agents/nodes.py` 的 `execute_models` 函数中，将 `fertilizer_type` 加入透传参数列表（与 `land_type` 并列）
- [x] 5.2 在 `framework/api/routes/chat.py` 的 `chat` 函数中，从请求体提取 `fertilizer_type` 并注入 `orchestrator_request`
- [x] 5.3 确保 `fertilizer_type` 在 context 中流转到 AcidificationRemediationAgent（与 land_type 流转路径一致）

## 6. 测试

- [x] 6.1 新增 `tests/test_model4_acidification.py`：测试4个子模型的计算正确性（使用模型5源码示例值 pHstart=4.31, Hex=1.56, Alex=4.08 验证 YTK/MBNT 输出）
- [x] 6.2 测试子模型选择：land_type × fertilizer_type 的4种组合各选对子模型
- [x] 6.3 测试非法参数回退：land_type="foo" / fertilizer_type="bar" → 回退默认 + warning
- [x] 6.4 测试输入校验：缺少 JHX/JLA → rejected；SJD 越界 → rejected
- [x] 6.5 测试可选参数覆盖：传入 FertN=200 → 计算结果与默认不同 + customized_params 标注
- [x] 6.6 测试 parcel_id 补充 SJD：提供 parcel_id + JHX + JLA（无 SJD）→ 从 DB 查 SJD 并计算
- [x] 6.7 更新 `tests/test_agent_specialized.py` 中 AcidificationRemediationAgent 的 mock，适配新参数和返回结构
- [x] 6.8 验证 question_type=2 路由仍指向 model-4（回归测试）

## 7. 文档更新

- [x] 7.1 更新 `docs/openapi.json`：新增 `fertilizer_type` 请求参数；更新响应字段（lime_demand → ytk/mbnt）
- [x] 7.2 更新 `docs/api.md`：酸化改良 API 参数说明和响应字段说明
- [x] 7.3 更新 `README.md`：酸化模型描述（从规则导向改为过程模型，4子模型）
