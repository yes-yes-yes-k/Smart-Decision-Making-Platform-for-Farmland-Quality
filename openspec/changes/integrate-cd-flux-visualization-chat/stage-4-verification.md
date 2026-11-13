# 第 4 阶段验收

2026-11-11 完成后端附件接入。实际聊天界面及真实模型联调在第 5 阶段验收。

## 会话归属和文件登记

每组文件的清单记录用户、会话、原查询消息版本、范围和生成状态。生成过程在临时目录完成，检查文件非空后统一发布。相同查询版本和选项复用已完成文件。失败返回错误状态并清理临时文件。

会话所有者可以列出、预览和下载附件。每次访问均查询当前会话归属。删除会话后立即撤销访问并尝试清理文件。旧制图入口使用独立目录和所有者检查，新生成的旧接口文件归生成用户，历史无归属文件仅允许管理员访问。

## 图表与 CSV

“画成图”“生成地图”“生成直方图”沿用当前 Cd 查询。预测与通量均生成 JPEG 地图和像元直方图，预测可追加“并导出GeoTIFF”。默认关闭插值，预测图可以明确追加“并使用线性插值”等指令。通量图限单年度，通量插值和栅格请求返回说明。

地图最多使用 2 万个点，标明可用点数、实际点数、模板外剔除、边界来源及是否截断。模板网格限制 1600 万像元。图表元信息带原查询范围、指标、年度或时期未知、单位状态和像元统计口径。通量图像使用可跨平台显示的英文标题和数字分档，响应元信息保留中文说明。

“下载刚才的数据”或“导出CSV”导出相同查询条件下的记录。通量保留来源、年度、地块、样点、版本和单位状态。预测 CSV 包含所选范围的预测记录，缺坐标的记录仍可导出。超过 10 万行返回错误。CSV 为 UTF-8 BOM，来源标识中的公式前缀按文本处理。

## HTTP、SSE 和前端契约

普通聊天、SSE 完成事件和历史消息均通过 `data.cd_artifacts` 或历史消息的 `cd_artifacts` 返回附件结构，包含 `status`、`attachments`、`scope`、`query_revision`、`metadata`。每个附件有不透明 ID、类型、MIME、标题、大小和同源 URL。附件响应独立于 `include_model_results`。

- GET `/api/v1/chat/conversations/<id>/attachments` 列出会话已完成附件。
- GET `/api/v1/chat/conversations/<id>/attachments/<artifact_id>/<kind>` 获取内容。

前端带现有 Authorization Bearer 请求文件，图片以响应 Blob 创建预览 URL，退出预览时释放。CSV 与 TIFF 按响应文件名下载，历史消息可按相同方式重开。API 响应禁止共享缓存，不在 URL 或消息存储访问令牌。

生成沿用服务器已验证的查询条件。切换分析对象后先查询新对象，失败查询不会继承旧范围。附件指令采用确定性匹配，后端测试用替身模拟 LLM 的查询调用。

## 测试

```text
python -m pytest tests/analysis_context tests/test_cd_flux_conversation.py tests/test_cd_conversation.py tests/test_cd_trial.py tests/test_cd_flux.py tests/test_cd_flux_v2.py tests/test_cd_flux_v2_migration_pg.py tests/test_heavy_metal_cd_visualization.py tests/test_heavy_metal_cd_spatial.py tests/test_heavy_metal_cd_statistics.py tests/test_heavy_metal_cd_ported.py -q --tb=short
```

相关回归 188 项通过。PostgreSQL 夹具使用恢复开发库中的隔离事务并回滚。覆盖普通聊天和 SSE 导出、历史、越权、旧入口、路径拒绝、删除撤销、重试复用、部分文件清理、超限、模板外、缺依赖、默认关闭插值及真实 JPEG/GeoTIFF 写出。字体调整后复跑附件专项。

真实通量业务记录仍为空。通量制图测试使用可复算的样本，实际前端预览和真实模型验收仍待第 5 阶段。
