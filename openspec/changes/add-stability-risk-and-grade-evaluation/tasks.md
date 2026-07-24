## 1. 环境与依赖准备

- [x] 1.1 在 requirements.txt 中新增 geopandas、scipy 依赖（明确兼容版本）
- [x] 1.2 在开发环境安装 geopandas 及其 Windows 依赖（GDAL/PROJ/GEOS），验证 `import geopandas` 成功
- [ ] 1.3 编写 geopandas Windows 安装说明文档（记录 conda/wheel 安装方式）

## 2. 数据部署

- [ ] 2.1 创建数据目录 `data/farmland_stability/`，将模型1 的 3 期 shapefile（2018/2021/2024 测试数据）复制到该目录
- [ ] 2.2 创建数据目录 `data/farmland_diagnosis/`，将模型3 的 CSV 测试数据（test.csv、test_with_LD.csv、test_with_LD_diagnosis.csv）复制到该目录
- [x] 2.3 创建 exe 部署目录（如 `bin/farmland_quality_eval/`），将 `Farmland_quality_evaluation.exe` 和 `Farmlands_Quality_Level_Database.dat` 复制到该目录
- [ ] 2.4 在 `.gitignore` 中排除 shapefile 数据、CSV 数据和 exe/.dat 二进制文件（避免大文件入库）
- [ ] 2.5 编写数据部署说明文档（记录文件位置和目录结构）

## 3. 模型1（耕地质量稳定性与退化风险）集成

- [x] 3.1 将模型1 核心代码（`代码03_耕地质量稳定性与退化风险_九模块总流程.py`）整合为项目模块（如 `src/ai_culti_demo/farmland_stability/model.py`），移除硬编码路径，改为项目相对路径
- [x] 3.2 实现离线预计算入口（CLI 命令或脚本），调用 `run_all_models()` 处理 `data/farmland_stability/` 下的 3 期 shapefile，将结果持久化（GeoJSON/Parquet/SQLite 格式）
- [x] 3.3 实现在线查询接口，调用 `get_parcel_result()` 从持久化结果中按 parcel_id + module 查询，对接 `run_thematic_model()` 的统一调用契约
- [x] 3.4 实现预计算结果未就绪时的 `status: "not_ready"` 响应逻辑
- [x] 3.5 实现地块 ID 不存在时的 `status: "not_found"` 错误响应
- [x] 3.6 实现 12 指标 LSD/QZ + ZHQZ + GDZLDJ 必需字段的校验逻辑
- [x] 3.7 在 `thematic_models.py` 的 MODEL_SPECS 中注册模型1（替换对应占位模型或新增 model_id），包含九模块输出字段说明和中文名称映射

## 4. 耕地质量等级和障碍度（Fortran exe）集成

- [x] 4.1 实现 exe 调用包装器（如 `src/ai_culti_demo/farmland_grade_eval/runner.py`），通过 subprocess.Popen 启动 exe，stdin 发送地块代码 + "quit"，从 stdout 捕获输出
- [x] 4.2 实现 exe 输出解析器，将文本输出解析为结构化 JSON（地块信息、12 指标原始值/隶属度、综合指数、质量等级、障碍度排序）
- [x] 4.3 处理 GBK/UTF-8 编码差异，确保中文字段不乱码
- [x] 4.4 实现 subprocess 超时控制（终止进程并返回 `status: "timeout"`）
- [x] 4.5 实现 exe 文件缺失和 .dat 数据库缺失的错误处理（返回明确错误信息）
- [x] 4.6 实现地块代码无效（exe 返回"未找到"）的错误处理
- [x] 4.7 实现系统启动时的 exe/.dat 部署校验逻辑
- [x] 4.8 将 exe 评价能力对接 `run_thematic_model()` 统一调用契约，在 MODEL_SPECS 中注册（替换 obstacle-factor-identification 或新增 model_id）

## 5. 模型3（耕地质量主要问题精准识别与酸化改良）集成

- [x] 5.1 将模型3 的 calculator.py 和 calculator2.py 整合为项目模块（如 `src/ai_culti_demo/farmland_diagnosis/`），移除硬编码路径，改为项目相对路径
- [x] 5.2 将 mappings_config.py 配置整合为项目配置文件（如 `config/farmland_diagnosis_config.py`），支持区域映射、隶属度系数、权重的配置管理
- [x] 5.3 实现批量评价入口（CLI 命令或脚本），调用 calculator.py 处理 `data/farmland_diagnosis/test.csv`，计算隶属度、综合权重和质量等级，输出 `test_with_LD.csv`
- [x] 5.4 实现批量障碍诊断入口，调用 calculator2.py 处理 calculator.py 的输出，识别障碍类型、主要/次要因素，输出完整诊断结果
- [x] 5.5 实现酸化因子提取和酸化程度分区逻辑（从 calculator.py 的 pH 隶属度和障碍度结果中提取）
- [x] 5.6 实现改良方案生成逻辑（基于酸化程度分区结果生成调理剂施用量建议和改良措施）
- [x] 5.7 实现在线障碍诊断查询接口，从批量评价和诊断结果中按地块 ID 查询，对接 `run_thematic_model()` 的统一调用契约
- [x] 5.8 实现在线酸化改良查询接口，从批量评价和诊断结果中按地块 ID 查询酸化程度和改良方案，对接 `run_thematic_model()` 的统一调用契约
- [x] 5.9 在 MODEL_SPECS 中注册模型3 的两个能力（障碍诊断和酸化改良），包含输出字段说明和中文名称映射

## 6. 模型3 与模型1 整合

- [x] 6.1 在 agent 层实现模型3（障碍诊断）与模型1（退化风险）的整合逻辑
- [x] 6.2 实现综合诊断接口，同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，整合退化风险和障碍诊断结果
- [x] 6.3 设计综合诊断结果的输出格式，包含稳定性评价、退化风险、障碍类型、障碍因素等综合信息

## 7. 占位模型替换与路由扩展

- [x] 7.1 确定具体替换映射：模型1/模型3 替换哪个占位 MODEL_SPECS
- [x] 7.2 确定新模型的 question_type 分配（新增 5-6-7 或复用现有），更新 `framework/domain/nodes.py` 的 QUESTION_TYPE 关键词映射
- [x] 7.3 在 `nodes.py` 中新增稳定性风险关键词路由到模型1
- [x] 7.4 在 `nodes.py` 中新增质量等级/障碍度关键词路由到耕地质量等级评价模型
- [x] 7.5 在 `nodes.py` 中新增障碍诊断/障碍组合关键词路由到模型3 的障碍诊断能力
- [x] 7.6 在 `nodes.py` 中新增酸化程度/改良方案关键词路由到模型3 的酸化改良能力
- [x] 7.7 更新被替换占位模型的 MODEL_SPECS 定义，将 `reliability` 从 `demo_stub` 改为 `real_model`，扩展输出字段
- [ ] 7.8 实现缺少地块代码时的提示逻辑（质量等级/障碍度/酸化改良查询需要地块代码）

## 8. Agent 实现

- [x] 8.1 修改 `StabilityRiskAgent`（对应模型1），将 answer_question 从模拟数据改为调用模型1 在线查询接口（get_parcel_result）
- [x] 8.2 新增 `FarmlandGradeObstacleAgent`，实现 answer_question 通过 subprocess 调用 exe
- [x] 8.3 新增 `ObstacleDiagnosisAgent`，实现 answer_question 调用模型3 的在线障碍诊断查询接口
- [x] 8.4 新增 `AcidificationImprovementAgent`，实现 answer_question 调用模型3 的在线酸化改良查询接口
- [x] 8.5 在 `framework/agents/manager.py` 中注册新 agent（FarmlandGradeObstacleAgent、ObstacleDiagnosisAgent、AcidificationImprovementAgent）和更新 StabilityRiskAgent 的路由

## 9. API 与端到端集成

- [ ] 9.1 验证 `/api/v1/chat/` 接口能正确路由稳定性风险问题到 StabilityRiskAgent 并返回模型1 真实结果
- [ ] 9.2 验证 `/api/v1/chat/` 接口能正确路由质量等级/障碍度问题到 FarmlandGradeObstacleAgent 并返回 exe 评价结果
- [ ] 9.3 验证 `/api/v1/chat/` 接口能正确路由障碍诊断问题到 ObstacleDiagnosisAgent 并返回模型3 诊断结果
- [ ] 9.4 验证 `/api/v1/chat/` 接口能正确路由酸化改良问题到 AcidificationImprovementAgent 并返回模型3 改良方案
- [ ] 9.5 验证综合诊断接口能同时调用 StabilityRiskAgent 和 ObstacleDiagnosisAgent，返回整合结果
- [ ] 9.6 实现数据导入接口（如需），支持上传新 shapefile/CSV 并触发重新预计算/评价
- [ ] 9.7 验证 CoreEngine.run_thematic_model() 能正确调度三个新模型
- [ ] 9.8 验证响应字段结构符合统一调用契约（status、model、summary、findings、reliability 等）

## 10. 测试验证

- [ ] 10.1 编写模型1 离线预计算的单元测试（验证 9 模块输出字段完整性）
- [ ] 10.2 编写模型1 在线查询的单元测试（含正常查询、数据未就绪、地块不存在场景）
- [ ] 10.3 编写 exe 调用包装器的单元测试（含正常调用、超时、文件缺失、地块无效场景）
- [ ] 10.4 编写模型3 批量评价的单元测试（验证隶属度、综合权重、质量等级计算）
- [ ] 10.5 编写模型3 障碍诊断的单元测试（验证障碍类型、主要/次要因素识别）
- [ ] 10.6 编写模型3 酸化改良的单元测试（验证酸化程度分区、改良方案生成）
- [ ] 10.7 编写所有 agent 的单元测试（验证路由和错误处理）
- [ ] 10.8 编写综合诊断整合的单元测试（验证模型1 和模型3 结果整合）
- [ ] 10.9 编写路由扩展的单元测试（验证关键词路由到正确 agent）
- [ ] 10.10 编写端到端集成测试（/api/v1/chat/ → 路由 → agent → 模型 → 响应）
- [ ] 10.11 运行全量回归测试，确保未替换的占位模型和其他功能不受影响
