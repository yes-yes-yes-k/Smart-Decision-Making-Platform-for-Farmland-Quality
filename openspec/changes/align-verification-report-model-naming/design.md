## Design

### 方案概述

在验证脚本中引入一个 **标准模型映射表**（`STANDARD_MODEL_MAPPING`），将 Excel 标准模型编号（1-6）映射到项目内部 model_id。验证报告的"Agent 加载状态盘点"章节按 Excel 标准顺序展示模型，使用标准命名，并为模型6 显示占位符。

### 标准模型映射表

```python
STANDARD_MODEL_MAPPING = [
    {"std_id": 1, "std_name": "耕地质量等级稳定性与退化风险识别模型", "model_id": "model-1"},
    {"std_id": 2, "std_name": "耕地质量提升潜力评估模型", "model_id": "model-7"},
    {"std_id": 3, "std_name": "耕地质量主要问题精准识别模型", "model_id": "model-3"},
    {"std_id": 4, "std_name": "耕地土壤酸化改良模型", "model_id": "model-4"},
    {"std_id": 5, "std_name": "耕地土壤有机质培肥提升模型", "model_id": "model-6"},
    {"std_id": 6, "std_name": "耕地综合地力改良提升模型", "model_id": None},  # 占位符
]
```

### 改动点

1. **`scripts/gen_full_verification_report.py`**:
   - `build_markdown` 中"Agent 加载状态盘点"表格按 `STANDARD_MODEL_MAPPING` 顺序展示
   - 表格列改为：`标准模型 | 项目model | Agent类 | 状态 | 资源就绪 | 期望行为`
   - 模型6 行显示"占位符（未实现）"
   - 当前的 model-2 和 model-5 在表格末尾标注为"未对应 Excel 标准的占位桩"

2. **`scripts/verify_agent_capabilities.py`**:
   - `inspect_agent_load_status` 输出中附加标准模型名称字段
   - 不改变实际检查逻辑，仅改变展示命名

### 不改动

- agent 注册逻辑（`manager.py`）
- 问题类型路由（`router.py`、`nodes.py`）
- API 契约
- 实际的 model_id 值（仍为 model-1 到 model-7）

### 验证方式

重新运行 `gen_full_verification_report.py`，检查报告中模型展示顺序和命名是否匹配 Excel 标准表格。
