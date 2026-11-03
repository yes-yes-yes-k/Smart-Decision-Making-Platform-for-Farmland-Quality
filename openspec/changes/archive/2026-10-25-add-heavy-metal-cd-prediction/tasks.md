# add-heavy-metal-cd-prediction Tasks

## 1. 模型资产与契约核验

- [x] 1.1 拷贝 AcidMap 两个模型资产（`.pth`、mean/scale `.npy`、约束模块 `constrained_nn6.py`/`constrained_nn6C.py`）到 `data/model_artifacts/heavy_metal_cd/`，生成带 SHA-256 的 manifest
- [x] 1.2 固化 crop_cd 14 项、effective_cd 21 项特征名及顺序，断言与 scaler 维数一致（实测 mean.shape 14/21 与常量相符）
- [x] 1.3 固化特殊特征索引（solution=13、Cdsolution=20）——已实测核对
- [x] 1.4 用项目环境 torch 2.14.1+cpu 加载 `.pth`（weights_only=False）并复现基准预测：crop_cd 0.266523、effective_cd 0.423962（与审计同值）

## 2. 领域预测能力（domain callable）

- [x] 2.1 实现模型加载器：受控根目录校验、文件存在与 manifest hash 校验、约束模块类定义随资产加载
- [x] 2.2 实现 torch 前向：标准化、各层 ReLU、线性头与单调项、exp 还原、有限值校验
- [x] 2.3 实现参数级 predict：特征顺序常量 + scaler 维数断言；完整输入返回 success + 数值 + unit_status=unverified
- [x] 2.4 solution/Cdsolution 缺失：采用训练集中位数参考值（-2.1266，附 n/P25-P75/数据源），强制 `degraded`，`assumed_fields` 回显依据
- [x] 2.5 其他必需字段缺失 → `need_input`；非法/非有限输入 → `rejected`；拒绝路径不调用模型推理
- [x] 2.6 提供双模型清单及特征契约、单位核验状态和参数级预测说明

## 3. 地块部分预填

- [x] 3.1 依据当前数据字典确认地块字段映射；仅映射语义、单位与来源均可确认的字段（钾/磷/氮/粉粒/砂粒），逐字段返回 provenance（measured / region_mean_backfill / default / unknown）
- [x] 3.2 未能映射的输入显式列入 `missing_fields`；预填结果标记为非地块级评估，不自动补值或触发预测

## 4. 测试与验证

- [x] 4.1 特征顺序守门测试（特征名与模型列序、scaler 维度断言）
- [x] 4.2 特殊索引测试（solution=13、Cdsolution=20；manifest 与常量双重校验）
- [x] 4.3 基准预测测试（输入=训练均值 → crop_cd 0.266523、effective_cd 0.423962，实测通过）
- [x] 4.4 缺失输入不调用模型测试（monkeypatch 断言 load_model 未被调用）
- [x] 4.5 Cdsolution 缺失走 degraded 测试（返回参考值与 assumed_fields）
- [x] 4.6 地块预填 provenance / missing_fields 测试
- [x] 4.7 运行 OpenSpec change validate 与相关定向 pytest（Cd 15/15、酸化 RF 19/19 通过）；新增依赖仅 torch（已装 2.14.1+cpu）

## 未完成（需人工确认后执行）

- 来源模型资产的发布/分发边界与许可尚未确认；本地拷贝已按用户指示完成，发布前需复核。
- HTTP API 蓝图、JWT 保护与前端接入不在本 change 范围，需另行决策。
- 是否接入正式专题 Agent 或综合诊断工作流不属于当前范围，需另行决策。
- 参考值"手输实测 vs 照抄建议值"的区分是前端契约问题，列入后续联调清单。