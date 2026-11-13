# 第 5 阶段集成验收

2026-11-11。已通过后端集成、真实库覆盖核查、真实模型验收及当前聊天前端联调。归档待完成。

## 5.1 隔离环境全链路

测试通过 JWT 管理接口导入两条合成输入，在恢复开发库的隔离 PostgreSQL schema 内执行真实 v2 核算。会话和认证使用测试用 SQLite 应用。测试结束回滚并核对临时 schema 已撤销。

| 合成业务年度 | 企业输入 g/ha/a | 预期输入 | 预期输出 | 预期净通量 g/ha/a |
| --- | ---: | ---: | ---: | ---: |
| 2023 | 0 | 18 | 10 | 8 |
| 2024 | 2 | 20 | 10 | 10 |

普通聊天与 SSE 分别验证年度对比、查询 2024 年、自同一查询生成 JPEG 地图/直方图及 CSV 下载。CSV 实际解析核对年度、净通量及公式版本 `cd_flux_mass_balance_v2`。这组用例以确定性 LLM 替身调用真实工具、真实数据库服务和真实制图模板。首次运行发现凸包只有单点时裁剪会丢失有效像元，已改用实际写入的像元范围裁剪，复测两项通过。

## 5.2 真实库覆盖

对 `db_enterprise_qa_cd_20261103` 运行只读查询。通量输入和结果各 0 条。作物镉与有效态镉预测各 40,100 条，全部来自移植数据，两类在梅花镇均有 4,628 条。预测时期未知，单位核验状态沿用预测结果契约。暂无真实年度通量、企业输入可作业务数据验收。合成记录仅用于隔离验收。

## 5.3 真实模型

模型 `deepseek-ai/DeepSeek-V4.1-Flash`，从项目环境加载配置，关闭外部跟踪，提示词使用隔离合成数据。两种入口分别验证四轮对话。

1. 查询 2023 和 2024 年净通量对比，得到 8 和 10 g/ha/a。
2. 用 2024 年已记录参数试算，得到 10 g/ha/a。
3. 将企业输入改为 3 g/ha/a 后重算，得到 11 g/ha/a，业务结果仍只有原来的两条。
4. 指定 2024 年查询作物 Cd 预测，返回原有的 `unsupported_year`。

首次模型验收在第 2 轮停在参数查询。调整工具提示明确要求试算操作，并允许同一范围的空草稿读取已有输入后，HTTP 和 SSE 两项复测通过。通量试算和分年比较以工具的结构化数据为验收依据。

## 5.4 前端联调

前端 `farmland-quality-rag` 的 `master` 已快进到 `c90fbf8`，联调分支为 `codex/cd-chat-attachments`。聊天 API 适配保留普通响应、SSE 完成事件和历史消息的 `cd_artifacts`。两个聊天组件复用附件组件，JPEG 支持预览，CSV 和 GeoTIFF 支持下载。附件请求限制为同源聊天附件路径，校验类型并附 Bearer 认证。预览关闭和组件卸载时释放对象 URL。

使用前端生产构建和本机隔离 Flask 实例执行 Edge 浏览器验收。登录、会话、SSE、历史和附件均调用实际后端路由。测试采用临时 SQLite 与合成预测点，模型用确定性替身。真实模型单独按 5.3 验收。浏览器从实际登录页面进入知识库页面的 AI 智能助手，验证以下操作。

- 登录后查询、生成地图并通过带 Bearer 的请求成功解码 JPEG。
- 下载 CSV，核对文件名、表头和三条合成预测记录。
- 清除消息缓存后刷新，从历史接口恢复附件并再次预览。
- 换用另一测试账号的凭据，下载返回 404，界面提示附件不可访问。

浏览器五项检查通过，页面无 JavaScript 异常。前端生产构建及 10 项单测通过。证据保存在 `artifacts/cd-front-integration/`，包含 `browser-results.json`、`preview.png` 和 `access-denied.png`。可使用该目录的 `serve.py` 与前端 `client/tests/live/cd-attachments.mjs` 复现。

## 5.5 契约及示例

更新 [API 契约](../../../docs/api-contract.md) 和 [v2 管理与迁移说明](../../../docs/cd-flux-v2-api-and-migration.md)，包含对话能力、示例、附件响应、前端 Bearer 取图及已知数据限制。迁移与关闭 v2 的回滚步骤沿用第 2 阶段已验证方案。

## 5.6 回归与归档

相关回归 190 项通过。默认测试跳过两个需真实模型的用例，两项均已在单独的真实模型运行中通过。使用项目虚拟环境和 `CD_MIGRATION_TEST_DB`、`CD_MIGRATION_ENV_FILE` 开启 PostgreSQL 测试。

```text
python -m pytest tests/analysis_context tests/test_cd_flux_conversation.py tests/test_cd_conversation.py tests/test_cd_trial.py tests/test_cd_flux.py tests/test_cd_flux_v2.py tests/test_cd_flux_v2_migration_pg.py tests/test_heavy_metal_cd_visualization.py tests/test_heavy_metal_cd_spatial.py tests/test_heavy_metal_cd_statistics.py tests/test_heavy_metal_cd_ported.py -q --tb=short
```

真实模型复现时先加载项目 `.env`，设置 `CD_LIVE_LLM=1`，再运行 `python -m pytest tests/analysis_context/test_cd_stage5_integration.py -k live_provider -q`。

OpenSpec 严格校验和前后端 diff 检查通过。5.6 的归档部分待完成。
