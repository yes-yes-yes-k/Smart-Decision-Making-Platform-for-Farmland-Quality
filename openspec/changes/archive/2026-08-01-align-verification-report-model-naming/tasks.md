# Tasks

## 1. 建立标准模型映射表

- [x] 1.1 在 `scripts/gen_full_verification_report.py` 中定义 `STANDARD_MODEL_MAPPING` 常量，包含 6 个标准模型与项目 model_id 的映射（模型6 为 None 占位符）
- [x] 1.2 在 `scripts/verify_agent_capabilities.py` 中引入相同映射，为每个 agent 附加 `std_name` 字段

## 2. 调整验证报告模型展示

- [x] 2.1 修改 `build_markdown` 中"Agent 加载状态盘点"表格，按 Excel 标准顺序展示 6 个模型，使用标准命名
- [x] 2.2 为模型6"耕地综合地力改良提升模型"添加占位符行（显示"未实现"）
- [x] 2.3 在表格末尾附加 model-2 和 model-5 的"未对应 Excel 标准的占位桩"说明
- [x] 2.4 更新"问题类型路由表"说明，标注每个 type 对应的 Excel 标准模型名称

## 3. 调整 verify_agent_capabilities.py 命名

- [x] 3.1 修改 `inspect_agent_load_status` 输出，附加标准模型名称
- [x] 3.2 修改控制台打印格式，显示标准模型名称

## 4. 重新生成验证报告

- [x] 4.1 运行 `gen_full_verification_report.py` 重新生成报告
- [x] 4.2 检查报告中模型展示顺序和命名是否匹配 Excel 标准表格
