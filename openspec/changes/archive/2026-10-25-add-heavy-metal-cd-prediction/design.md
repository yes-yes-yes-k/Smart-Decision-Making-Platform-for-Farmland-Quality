# add-heavy-metal-cd-prediction Design

## Context

AcidMap 的作物 Cd（crop_cd）与有效态 Cd（effective_cd）是两个独立的 PyTorch 小型神经网络。项目环境已安装 torch 2.14.1+cpu，实测可直接加载 AcidMap 原 `.pth` 权重并复现基准预测（crop_cd 0.266523 / effective_cd 0.423962，与 numpy 等价验证同值）；特殊特征分别为 crop_cd 的 `solution`（特征索引 13）和 effective_cd 的 `Cdsolution`（索引 20），索引错位会静默改变预测（crop_cd 误用兜底索引 2 偏差约 +30%）。当前地块数据缺少多数模型特征、总镉 TCd 和上述上游络合值，故模型计算能力与地块可用性必须分开表达。

## Goals / Non-Goals

### Goals

- 为两个模型提供本地、确定性、可测试的 torch 推理（直接加载 `.pth`，不转换格式）。
- 固定并验证特征顺序、scaler 维数和特殊特征索引。
- 保留输入来源、缺失原因及模型输出单位未核实的事实。
- 缺失 `solution`/`Cdsolution` 时提供训练集中位数参考值并强制 `degraded`（用户已拍板）。
- 明确区分参数级预测、地块预填与地块级评估。

### Non-Goals

- 不复刻训练过程、MSM 络合计算、空间插值或地图生成。
- 不推断当前系统字段之间未经确认的语义/单位对应关系。
- 不提供 Cd 安全等级或自动化治理建议。
- 不包含 HTTP API 蓝图 / JWT 路由（本阶段只做领域函数与测试）。

## Decisions

### Decision 1: 本地 torch 推理与受控资产

项目侧直接用 torch 加载 AcidMap 的 `.pth` 权重（`weights_only=False`，来源已核验），不转换 numpy、不引入新依赖、不依赖 AcidMap 在线服务。模型资产（`.pth`、mean/scale `.npy`、约束模块 `constrained_nn6.py`/`constrained_nn6C.py`）置于 `data/model_artifacts/heavy_metal_cd/`，manifest 记录模型身份、源文件、特征契约、文件大小和 SHA-256。加载时验证资产路径在受控根目录内、文件存在且摘要匹配；`.pth` 反序列化需要的类定义随资产一并加载。

### Decision 2: 两个模型分离且特征顺序固定

分别维护 crop_cd 的 14 项和 effective_cd 的 21 项特征常量，与 scaler 维度作一致性断言。`solution` 与 `Cdsolution` 索引分别固定为 13 和 20，并以特征顺序守门测试防止错列。torch 前向按模型原生 forward 执行（标准化输入、各层 ReLU、线性头与单调项、外部指数还原）；保留模型输出的原始数值。

### Decision 3: solution/Cdsolution 缺失按用户拍板降级，其余缺失不静默填补

- `solution`/`Cdsolution` 缺失时：使用训练集参考值（中位数 -2.1266，n=40100，P25 -3.0787 / P75 -1.2319，数据源 soilgd 输入表）作为显式 assumptions，结果强制 `degraded` 并在 `assumed_fields` 回显依据；调用方未显式采用参考值时同样按 degraded 处理并注明。
- 其他必需字段缺失或输入非法（不可转换、非有限数值）时：返回 `need_input` / `rejected` 状态，不得用区域均值、训练集统计量或零值补齐，且不调用模型推理。

### Decision 4: 参数预测与地块预填分层

参数级领域函数仅表示用户提交完整参数后运行模型。地块预填仅映射有证据支持的字段，逐字段给出 provenance；不能确认映射或当前无数据的模型字段列入 `missing_fields`。即使部分字段可预填，也不得自动运行预测，除非所有必需输入由调用方补全并提交。响应明确声明这不是地块级评估。

### Decision 5: 输出不附加未核实的安全等级

返回数值和模型标识；结果单位的核验状态为 `unverified`。不使用 AcidMap 中来源未核实的 0.2/0.3 mg/kg 阈值，不映射到 GB 标准或安全等级。

### Decision 6: 本阶段交付领域函数，不做 HTTP API

按用户拍板，本 change 先交付可调用的领域函数（domain callable）与测试，不新增 Flask Blueprint、不注册 JWT 路由。预测状态区分 `success`、`degraded`、`rejected`、`need_input`；具体 reason 为稳定机器码，缺失输入时模型推理函数不得被调用。API 蓝图与前端接入留待后续单独决策。

## Migration and Rollback

无需数据库迁移。回滚时移除领域模块、资产目录及相关测试；不需要清理业务数据。既有 API 与模型不受影响。

## Risks / Trade-offs

- 若资产或特征次序与来源审计不一致，输出会静默错误；manifest 校验、逐模型特征顺序测试、特殊索引测试和基准预测测试是发布门禁。
- torch `weights_only=False` 加载 pickle 类定义存在任意代码执行面；来源为已核验的 AcidMap 资产且 hash 固定，资产目录受控、不运行时读取外部路径。
- 当前地块数据不能支持完整输入，预填体验有限；不以伪造数据换取表面完整度。
- 上游 `solution`/`Cdsolution` 的生成依赖仓库外 MSM，模型虽可参数级调用，现实地块自动预测仍受阻；参考值降级只适用于演示/试算，不能作为实测输入。
- 若源模型输入单位未充分核实，数值预测不能直接用于法规或风险分级判断。

## Open Questions

- 来源模型资产是否可随本仓库发布，以及其分发/许可边界需在实际复制资产前确认（资产已按用户指示拷贝，发布前仍需复核许可）。
- HTTP API 蓝图、JWT 保护与前端接入留待后续单独决策。
- 是否需要将 Cd 预测注册为正式专题 Agent、接入综合诊断编排，另行评估。
- 参考值交互契约：前端如何区分"手输实测"与"照抄建议值"（同值不同来源无法由后端区分），列入后续联调清单。