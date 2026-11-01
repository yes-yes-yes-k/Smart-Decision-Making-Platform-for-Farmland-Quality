# add-acidification-rf-http-api-and-parcel-prefill 任务

## 1. HTTP 接口

- [x] 1.1 新增 `GET /api/v1/acidification-rf/models`，返回模型编号、类型与土地类型，不含资产路径与哈希。
- [x] 1.2 新增 `POST /api/v1/acidification-rf/predict`，支持单条与批量，JWT 保护；输入类错误 400，模型资产不可用 503。
- [x] 1.3 在 `create_app()` 注册 `acidification_rf` 蓝图，不修改既有端点。

## 2. 地块输入预填

- [x] 2.1 新增 `GET /api/v1/acidification-rf/parcels/<parcel_id>/prefill`，按土地类型自动匹配返酸模型，支持 `model_id` 覆盖并校验土地类型一致。
- [x] 2.2 只映射已有既定语义的字段（pH/有机质/交换性氢/交换性铝/阳离子交换量/目标 pH），逐字段透传 `provenance`，无标注记 `unknown`。
- [x] 2.3 `NO3`、`NH4`、`FeO` 列入 `missing_fields`，不写入 `data`，不做猜测性填充。
- [x] 2.4 地块不存在返回 404，土地类型不匹配返回 400，模型资产异常返回 503。

## 3. 缺失字段参考值

- [x] 3.1 生成 `data/model_artifacts/acidification_rf/reference_values.json`：按模型对应 `dataset_77/81/94` 统计 `NO3`、`NH4`、`FeO` 的 `n`、最小、四分位、中位数、最大、均值，标注单位未核验。
- [x] 3.2 预填响应新增 `suggestions`，给出中位数、依据类型、数据集、样本量、四分位区间与 `unit_status`；参考值不进入 `data`。
- [x] 3.3 `predict` 支持 `assumptions`；非空时 `status` 强制 `degraded`，`assumed_fields` 回显依据；非字典输入返回 400 `invalid_assumptions`。
- [x] 3.4 `warnings` 输出可直接展示的中文提示，覆盖回填值、默认值、缺失字段与参考值。

## 4. 特征集修正

- [x] 4.1 从三个模型 pickle 的 `feature_names_in_` 核实特征与顺序，记录水田 reflux 为 `CEC/NH4/NO3/Al/FeO/OM`。
- [x] 4.2 特征定义改为按模型编号维护（33/35/38），输入严格按 `_MODEL_COLUMNS` 列序构造。
- [x] 4.3 水田缺 `FeO` 时返回缺列信息，不再以旱地字段继续计算。
- [x] 4.4 `map_parcel_indicators` 的未知字段补入 `FeO`。

## 5. 测试与验证

- [x] 5.1 domain 测试：模型资产校验、在线语义、批次均值填补、预填字段映射、来源披露、缺失不填充、参考值、假定字段降级。
- [x] 5.2 路由测试：认证、模型清单、预测三态、预填、404/400/503、`assumptions` 校验。
- [x] 5.3 model-4 回归测试保持通过；酸化 RF 相关测试合计 48 项通过。
- [x] 5.4 真实开发库端到端验证：旱地地块 5149 与水田地块 92 完成预填、采用参考值、预测全链路。

## 未完成（需人工确认后执行）

- `NO3`、`NH4`、`FeO` 的单位与检测方法未核验，`unit_status` 保持 `unverified`。
- 地块级氮素与亚铁数据是否存在未确认；未确认前不开放地块级自动映射。
- 前端"采用参考值必须提交 `assumptions`"的契约尚未联调确认；未提交时后端无法识别。
- 三普样点空间匹配与插值口径未定，不在本 change 范围。
