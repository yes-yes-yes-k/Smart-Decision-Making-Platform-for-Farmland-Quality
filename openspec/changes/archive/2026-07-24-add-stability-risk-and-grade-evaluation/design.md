## Context

项目现有耕地质量专题模型体系由 6 个占位 MODEL_SPECS 构成（定义于 `src/ai_culti_demo/thematic_models.py`），仅提供结构化描述而无真实算法实现。CoreEngine（`framework/core_engine/adapter.py`）通过 `run_thematic_model()` 统一调度，role-based-routing 按 question_type 1-4 将用户问题路由到不同 agent 组合。

本次整合三个已成熟的真实模型：
- **模型1（Python）**：耕地质量稳定性与退化风险识别模型，九模块分析，依赖 geopandas/scipy 处理多期 shapefile
- **耕地质量等级和障碍度（Fortran exe）**：基于 GB/T 33469-2016 的交互式评价工具，依赖加密数据库 .dat
- **模型3（Python）**：耕地质量主要问题精准识别与酸化改良模型（calculator.py + calculator2.py），基于 CSV 的批量评价和障碍诊断

生产环境为 Windows + waitress，Fortran exe 可直接运行。现有数据库为 SQLite（development.db / instance/production.db）。

## Goals / Non-Goals

**Goals:**
- 将模型1 整合为项目 thematic model，支持离线预计算（run_all_models）和在线地块查询（get_parcel_result）
- 将耕地质量等级和障碍度 exe 通过 subprocess 集成为请求-响应式模型服务
- 将模型3 整合为项目 thematic model，支持基于 CSV 的批量质量等级评价和障碍诊断
- 模型3 与模型1 整合：障碍诊断结果与退化风险识别结果互补，共同构成综合诊断能力
- 替换对应占位 MODEL_SPECS 为真实模型实现，扩展输出字段
- 扩展 question_type 路由，使三类新模型可通过 /api/v1/chat/ 接口访问
- 提供数据导入接口，支持 shapefile、CSV 和 .dat 数据库的部署与更新

**Non-Goals:**
- 不重新实现 Fortran exe 为 Python（生产环境是 Windows，可直接调用 exe）
- 不改变现有 role-based-routing 的三角色路由架构
- 不对接项目现有 SQLite 数据库作为模型数据源
- 不替换其他不相关占位模型（如 spatial-structure-analysis 等）
- 不在 design.md 阶段确定所有实现细节（具体替换映射、question_type 分配等留待 Design Doc 细化）

## Decisions

### 决策1：模型1 采用离线预计算 + 在线查询双模式

**选择**：`run_all_models()` 作为离线预计算入口，处理 3 期 shapefile 并将 9 模块结果持久化（GeoJSON/Parquet/SQLite）；`get_parcel_result()` 作为在线查询接口对接 `run_thematic_model()`，从持久化结果中按 parcel_id + module 查询。

**理由**：模型1 的 `run_all_models()` 需读取 3 期 shapefile（各约 20MB）并执行空间邻域分析（cKDTree）、历史趋势回归等计算密集操作，单次运行耗时较长，不适合每次 API 请求都执行。而 `get_parcel_result()` 仅从已计算的 GeoDataFrame 中筛选地块结果，响应快。

### 决策2：耕地质量等级和障碍度采用 subprocess 调用 exe

**选择**：通过 subprocess.Popen 启动 `Farmland_quality_evaluation.exe`，通过 stdin 写入地块代码，从 stdout 读取评价结果，解析后返回结构化 JSON。将交互式程序转为单次请求-响应模式。

**理由**：生产环境是 Windows，exe 可直接运行；subprocess 方式保留 Fortran 算法的准确性，无需重新实现隶属函数、等级划分等复杂逻辑。

### 决策3：模型3 与模型1 整合为综合诊断能力

**选择**：模型3 的 calculator.py（批量质量等级评价）和 calculator2.py（障碍诊断）独立集成，但障碍诊断结果与模型1 的退化风险识别结果在 agent 层进行整合。模型3 的障碍诊断侧重指标层面的障碍识别和组合判定，模型1 的退化风险侧重空间和时间维度的稳定性分析，两者互补。

**理由**：模型3 的障碍诊断基于单期数据的指标隶属度和障碍度计算，输出障碍类型（单一/多重）和因素排序；模型1 的退化风险基于多期数据的空间分析和趋势回归，输出稳定性和风险等级。两者结合可提供更全面的诊断结果。

### 决策4：模型3 采用批量 CSV 评价 + 在线诊断查询模式

**选择**：模型3 的 calculator.py 作为批量评价入口（处理 CSV 数据并输出隶属度、等级、障碍度），结果持久化后可通过在线查询接口按地块 ID 查询障碍诊断结果。

**理由**：模型3 的 calculator.py 设计为批量处理 CSV 文件，与模型1 的 shapefile 输入不同。将批量评价结果持久化后，可通过统一接口查询单地块诊断结果。

### 决策5：数据策略为模型自带数据 + 导入接口

**选择**：将模型1 的 3 期 shapefile（2018/2021/2024）、模型3 的 CSV 测试数据和 .dat 加密数据库部署到项目 data/ 目录作为初始数据源；同时设计数据导入接口支持后续数据更新。

**理由**：模型1 的算法依赖特定的 shapefile 字段结构，模型3 的算法依赖特定的 CSV 字段结构，项目现有 SQLite 数据库无此数据；.dat 数据库经过异或加密，直接使用原文件最可靠。

## Risks / Trade-offs

- **[geopandas Windows 依赖复杂] → Mitigation**：geopandas 依赖 GDAL/PROJ/GEOS，Windows 安装可能困难。使用 conda 或预编译 wheel 安装；在 requirements.txt 中明确版本；提供安装文档。
- **[Fortran exe 进程启动开销] → Mitigation**：每次请求启动 exe 约 1-2 秒（含数据库解密）。对于实时性要求高的场景，后续可考虑长驻进程池优化；当前先保证正确性。
- **[.dat 加密数据库密钥内嵌] → Mitigation**：密钥 "YouYCKEY" 内嵌在 exe 中，数据库文件不可单独解密。保持 exe 和 .dat 配套使用，不尝试单独解密。
- **[shapefile/CSV 数据量大] → Mitigation**：3 期 shapefile 各约 20MB，模型3 的 CSV 测试数据约 7MB，预计算结果可能更大。预计算结果持久化为压缩格式；离线预计算在非高峰时段执行。
- **[占位模型替换的兼容性] → Mitigation**：替换占位 MODEL_SPECS 后，对应 question_type 的响应字段结构会变化。在 design 阶段明确字段映射；保留 fallback 机制处理数据缺失情况。
- **[subprocess 异常处理] → Mitigation**：exe 崩溃、超时、数据库缺失等异常需妥善处理。设置 subprocess 超时；捕获异常返回明确错误信息；不阻塞主服务。

## Migration Plan

1. **依赖安装**：在开发环境安装 geopandas、scipy 及其 Windows 依赖；更新 requirements.txt
2. **数据部署**：将模型1 的 3 期 shapefile 复制到 `data/farmland_stability/`；将模型3 的 CSV 复制到 `data/farmland_diagnosis/`；将 exe 和 .dat 复制到项目指定目录
3. **模型1 集成**：将九模块代码整合为项目模块；实现离线预计算脚本；实现在线查询接口对接 run_thematic_model()
4. **exe 集成**：实现 subprocess 调用包装器；解析 exe 输出为结构化 JSON；对接 run_thematic_model()
5. **模型3 集成**：将 calculator.py 和 calculator2.py 整合为项目模块；实现批量评价入口；实现在线障碍诊断查询接口；对接 run_thematic_model()
6. **路由扩展**：在 nodes.py 中扩展 question_type 关键词路由；在 agent 层实现 answer_question 对接
7. **测试验证**：单元测试覆盖三个模型；集成测试覆盖 /api/v1/chat/ 端到端
8. **回滚策略**：保留占位 MODEL_SPECS 的 git 历史；若新模型集成失败，可通过 git revert 回退到占位模型

## Open Questions

1. 模型1/模型3 具体替换哪个占位 MODEL_SPECS？
2. question_type 分配：新增 5-6 还是复用现有 1-4？
3. 离线预计算的触发方式：CLI 命令、定时任务、还是 API 触发？
4. 预计算结果持久化格式：GeoJSON、Parquet、还是 SQLite 表？
5. 模型3 的酸化改良方案生成逻辑（calculator.py 后续部分）是什么？
6. 模型3 与模型1 的数据格式差异如何处理（shapefile vs CSV）？
7. 模型3 的批量评价结果如何与模型1 的在线查询结果整合？
