## 1. 底层入口重命名与资产检查

- [ ] 1.1 盘点 `model_6.py`、`model_6_execution` 的全部源码、测试、脚本和文档引用，建立迁移清单
- [ ] 1.2 将真实肥力 ML 引擎迁移为 `framework/domain/other_models/model_5.py`，把入口统一为 `model_5_execution`，删除 RF 用途的 `model_6.py`
- [ ] 1.3 更新 `framework/domain/other_models/__init__.py`、训练/加载脚本和所有内部导入，确认仓库不存在残留的 `model_6_execution` RF 引用
- [ ] 1.4 校验全局 ETR、韶关旱地 RF、韶关水田 RF 的 joblib 和 metadata 均可加载，版本号与 `SG_RF_v2_20260804` 一致

## 2. 输入适配与底层模型契约

- [ ] 2.1 实现外部字段到规范字段的适配：`SJD/YJZ/TD/TL/TJ/YXL/SXJ/YJZTSZ/YJFLX` → `pH/SOCbe/TN/TP/TK/AP/AK/Gap/Fertilizer type`
- [ ] 2.2 保留 `SOMbe→SOCbe` 兼容，并实现规范字段优先、冲突字段拒绝、单位/类型/范围校验
- [ ] 2.3 将非韶关、韶关旱地、韶关水田三条推理路径统一到 `model_5_execution`，返回实际模型版本、置信度、warning 和 fallback 元数据
- [ ] 2.4 为模型文件缺失、scikit-learn/joblib 缺失、输入缺失、输入越界和字段冲突定义稳定的机器可读错误

## 3. model-5 Agent 接入

- [ ] 3.1 改造 `OrganicMatterAgent`，通过统一 `analyze(payload)`/`execute(task)` 调用 `model_5_execution`，不再使用默认规则值冒充真实 RF
- [ ] 3.2 将 `area_code`、`land_type`、规范字段和外部源字段从 Agent 上下文透传到底层适配器
- [ ] 3.3 在成功、均值填充、通用模型和规则降级场景分别设置 `simulated`、`reliability`、`fallback` 和 `need_input`
- [ ] 3.4 更新 `AgentManager` 和能力目录，使 `model-5` 描述真实/降级 ML 能力；保持 `model-6` `_StubAgent`、placeholder 描述和注册逻辑不变

## 4. 单模型 API 与聊天路由

- [ ] 4.1 更新 `/api/v1/models/run` 的 model-5 映射，使用 `organic-matter-improvement` 调用 `OrganicMatterAgent`，返回结构化 ML 结果
- [ ] 4.2 更新 API 请求适配，支持 `area_code`、`land_type`、规范字段和外部源字段，并在冲突/缺失时返回明确错误
- [ ] 4.3 更新聊天节点和编排器上下文透传，确保 type 5 请求的 `agents_invoked` 为 `model-5` 且能选择旱地/水田模型
- [ ] 4.4 验证 type 6 仍只调用 model-6 占位 Agent，不加载或调用任何 RF 引擎
- [ ] 4.5 更新模型 API、聊天 API 和模型目录文档，区分 model-5 真实/降级 ML 与 model-6 占位能力

## 5. 测试与验收

- [ ] 5.1 增加源字段适配、冲突检测、`SOMbe` 兼容和范围校验单元测试
- [ ] 5.2 增加 `model_5_execution` 的全局、韶关旱地、韶关水田、非韶关降级、模型缺失和版本号回归测试
- [ ] 5.3 增加 `OrganicMatterAgent` 单模型分析测试，断言真实输入返回 `simulated=false`，降级输入带明确原因
- [ ] 5.4 增加 `/api/v1/models/run` model-5 端到端测试，断言公开 model_id、返回字段和实际模型版本
- [ ] 5.5 增加 `/api/v1/chat/` type 5/type 6 路由测试，断言 type 5 调用 model-5、type 6 保持占位
- [ ] 5.6 使用项目指定 Python 解释器运行专项测试和完整测试套件，处理失败及新增警告
- [ ] 5.7 运行 OpenSpec 验收检查，确认所有规范场景都有对应测试，仓库不存在 RF 用途的 `model_6.py`
