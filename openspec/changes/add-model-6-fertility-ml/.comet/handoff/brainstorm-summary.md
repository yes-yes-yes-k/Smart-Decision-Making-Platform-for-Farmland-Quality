# Brainstorm Summary

- Change: add-model-6-fertility-ml
- Date: 2026-07-18

## 确认的技术方案

### 模块架构
- `framework/domain/other_models/model_6.py`：纯计算层，`model_6_execution(input_data) -> Dict`，惰性单例加载 .joblib
- `framework/agents/specialized/fertility_ml_agent.py`：`FertilityMLAgent` 薄包装，`dependencies=[]`
- `scripts/train_fertility_models.py`：CLI 训练脚本，直接用 notebook 最优参数，不重新网格搜索
- `data/fertility/` 存训练数据（3 xlsx），`data/fertility/models/` 存模型产物（2 joblib + 2 json），全部入库
- 删除 `framework/agents/specialized/comprehensive_agent.py`

### 关键技术决策
1. **模型加载**：惰性单例 + `threading.Lock` + double-checked locking；首次 `model_6_execution()` 触发加载，模块导入零文件 IO
2. **特征准备**：input 层 strip 尾随空格（`"TN "` → `"TN"`），`float()` 强制转换，缺失字段用训练集均值填充
3. **范围校验**：10 个特征定义合法区间（基于领域知识），任一越界 → `status: "rejected"`，`out_of_range_features` 列出越界详情，不执行预测
4. **按需预测**：`AgentManager._should_execute_agent` 关键词过滤（大小写不敏感），非肥力问题跳过 model-6，不触发模型加载；不修改 ROLE_AGENTS 路由表
5. **Fallback 策略**：sklearn 缺失 / 模型文件缺失 / 未预期异常 → `status: "fallback"`，返回训练集均值占位，confidence 降为 0.3
6. **`FertilityMLAgent.answer_question`**：关键词优先级 Dose > SOC > 综合 > 默认综合；`sources: []` 始终为空
7. **`details["model-6"]` breaking change**：从 `{diagnosis, zoning_suggestions, priority_measures}` 变为 `{status, result, metadata}`（无外部消费者）
8. **测试**：单元测试用 monkeypatch mock（CI 零依赖、零模型文件依赖），集成测试用真实 .joblib（`skipif` 跳过）

### Notebook 验证关键事实
- `Fertilizer type` 已是 int64 数值型（1=秸秆，2=有机肥），无需编码
- notebook 未保存模型（`joblib.dump` 被注释），训练脚本将是首次保存
- 训练集仅 52 样本（解释了 Dose R²=0.47 偏低根因）
- `TN` / `TP` 列名有尾随空格，训练脚本保留原样
- 无 StandardScaler（树模型不需要）
- 手动数据划分（Excel 的 Xtrain/Ytrain/Xtest/Ytest sheets）

### 训练脚本输出
- `data/fertility/models/soc_etr_model.joblib` + `soc_metadata.json`
- `data/fertility/models/dose_etr_model.joblib` + `dose_metadata.json`
- metadata 含 `feature_names`（保留尾随空格）、`feature_means`、`hyperparameters`、`metrics`（cv_r2/cv_rmse/test_r2/test_rmse）、`model_version` 等

## 关键取舍与风险

**取舍**：
- Dose 模型 R²=0.47 低质量 → 不藏不掖，`dose_warning` 明文标注"仅供参考"，但仍然提供预测值
- 任一模型缺失即整体降级（不混合正常+fallback）→ 牺牲灵活性换代码简洁
- 训练数据仅 52 样本 → 通过 metadata 记录 `training_samples` 供上游感知
- 按需预测关键词过滤可能漏掉某些肥力相关表述 → 测试覆盖常见问法，未来可扩展

**风险**：
- `details["model-6"]` 结构 breaking change —— 已确认无外部消费者
- sklearn 安装增加容器/部署体积约 100-200MB —— 接受
- 关键词过滤可能漏掉某些肥力相关表述 —— 测试覆盖常见问法

## 测试策略

- **单元测试**（`tests/test_fertility_ml_prediction.py`）：12 个用例，全部 mock，覆盖 success / fallback / rejected / 边界条件 / 字符串转换 / 特征名规范化
- **集成测试**：3 个用例用真实 .joblib 验证预测值范围，`skipif` 跳过
- **Agent 测试**（`tests/test_agent_specialized.py`）：7 个用例覆盖 execute 结构、answer_question 三分支、fallback/rejected 状态、dependencies=[]
- **AgentManager 测试**（`tests/test_agent_manager.py`）：4 个用例覆盖 `_should_execute_agent` 过滤、topological_sort 独立性、skipped 状态

## Spec Patch

需回写到 OpenSpec delta spec：

### Patch 1: `specs/fertility-ml-prediction/spec.md`
- SOC 预测能力下新增 Scenario：「输入特征越界时拒绝预测」
- Dose 预测能力下新增 Scenario：「Dose 预测时显式标注低置信度」

### Patch 2: `specs/professional-model-agents/spec.md`
- FertilityMLAgent 智能体下新增 Scenario：「非肥力相关问题跳过 model-6」
- FertilityMLAgent 智能体下新增 Scenario：「输入越界时返回拒绝响应」
