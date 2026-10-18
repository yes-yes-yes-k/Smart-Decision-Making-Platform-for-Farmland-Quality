# add-acidification-rf-prediction 任务

## 1. 现状与证据核验

- [x] 1.1 固定旧 Web `/predict`、`reduce`、`reflux` 调用链事实：按 `model_id` 查 `Data_type`，批次均值填补，reduce 三段换算，水田 reflux 取绝对值。
- [x] 1.2 只读核对旧系统数据库中的 ModelID 33/35/38、Data_type、Land_type、ModelFilePath。
- [x] 1.3 复制并记录三个 pickle 资产的 SHA-256、大小、来源和项目内相对路径；模型可 `pickle.load` 且具有 `predict`。
- [x] 1.4 核验当前批次 `SimpleImputer(strategy=mean).fit_transform`、空批次/全列缺失拒绝及 reduce/reflux 在线语义。
- [x] 1.5 用项目指定 sklearn 1.9.0 对三个原始 1.3.0 pickle 重序列化；真实特征名输入上的 round-trip 预测逐值相等，manifest 已更新 hash、大小、pickle protocol 与 sklearn 序列化版本。
- [x] 1.6 从三个 pickle 的 `feature_names_in_` 核实真实训练列：reduce 为 `pH/H/Al/OM/NO3/NH4/CEC`；旱地 reflux 为 `H/Al/OM/NO3/NH4/CEC`；**水田 reflux 为 `CEC/NH4/NO3/Al/FeO/OM`（无 H）**。修正此前按 `data_type` 统一字段集导致的错序缺陷，并加测试锁定。

核验来源：`D:\\work\\suan\\AcidificationModel\\api\\SoilAcidification.db`（只读）及旧 Web 路由事实；核验时间记录在 `data/model_artifacts/acidification_rf/manifest.json`。

## 2. 独立 RF 能力设计与实现（提案后执行）

- [x] 2.1 定义独立酸化 RF 的规范输入、模型选择、结果来源和降级错误契约，不修改 model-4 契约。
- [x] 2.2 实现经核验的字段适配、类型转换、冲突检查和特征顺序构造。
- [x] 2.3 实现受控模型加载与 manifest/path 校验，加载失败时返回明确降级，不回退到 model-4 或离线结果。
- [x] 2.4 实现核验后的在线缺失值处理，记录填充字段和实际策略。
- [x] 2.5 实现原始 RF prediction 与 `reduce`/`reflux` 转换分层输出，并保留转换证据和单位。
- [x] 2.6 注册内部 callable 入口；不新增 HTTP `/predict` 代理，不接入离线 CSV 批处理。
- [x] 2.7 地块预填入口：`GET /parcels/{parcel_id}/prefill` 只映射已有既定语义的字段（pH/OM/H/Al/CEC），逐字段披露 provenance，NO3/NH4/FeO 列入 `missing_fields` 交由使用者补充，不做推测性填充。
- [x] 2.8 缺失字段给出可选参考值：`suggestions` 按模型取对应训练集（33→dataset_77、35→dataset_81、38→dataset_94）中位数，附 n、P25–P75、数据集与 `unit_status=unverified`；值不写入 `data`，由使用者显式采用。采用时传 `assumptions`，`predict` 强制 `status=degraded` 并在 `assumed_fields` 回显依据。

## 3. 测试与回归

- [x] 3.1 使用固定核验样本覆盖各已确认 ModelID/Data_type/Land_type 的模型选择和特征映射。
- [x] 3.2 覆盖完整输入、部分缺失、全列缺失、非法值、空批次、模型缺失和冲突。
- [x] 3.3 覆盖 reduce 转换链、水田 reflux 绝对值和未知语义下的降级行为。
- [x] 3.4 验证 model-4 过程模型既有测试与路由行为不变，并证明 RF 不会自动调用或合并 model-4。
- [x] 3.5 使用指定解释器运行定向测试；不把离线 CSV 输出当作 Web 在线等价验证。
- [x] 3.6 验证三个项目 pickle 的真实 load 不产生 `InconsistentVersionWarning`，且 manifest hash 校验通过。

## 4. 文档与发布门禁

- [x] 4.1 记录模型资产清单、来源、hash、大小和未知项。
- [x] 4.2 补充内部 callable 的输入/输出、降级、模型来源和单位说明（代码 docstring/返回元数据）。
- [x] 4.3 确认 HTTP、离线 CSV、model-4 互补交互未被本 change 引入。
- [x] 4.4 通过 OpenSpec 校验；未完成人工确认项保留如下。

## 未完成（需人工确认后执行）

- 模型 pickle 在当前环境加载时产生 sklearn 1.3.0 → 1.9.0 版本警告；已在指定 1.9.0 运行时重序列化三个已纳入项目的 RF 资产，更新 manifest hash/元数据并增加无版本警告测试；未来 sklearn 版本变更仍需重新执行兼容性探针。
- 真实旧路由源码版本快照、模型训练 metadata/特征名未随旧系统提供；当前实现以已核验在线语义和 manifest 为边界，不宣称训练元数据完整。
- 当前 `soil_indicators` 对 NO3/NH4/CEC 没有明确字段语义，parcel mapping 固定返回 `need_verification`，不得直接用于成功预测。
- RF 是否与 model-4 存在业务互补关系仍不在本 change 内。
