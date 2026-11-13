# 第3阶段验收

2026-11-10：完成对话查询和独立试算接入；图表/附件仍属于第4阶段。

## 3.1 查询与能力目录

现有cd_conversation_query新增flux（统计）、flux_results（分页明细）、flux_parameters（定义及已有值）、flux_predict（纯试算）和flux_compare（年度对比）。source、field、years、all_regions、分页参数采用结构化工具契约。自然语言执行链仅允许此工具，不注册管理导入/业务重算。

无范围追问，明确全域才传all_regions；已有服务器验证的地区/地块参数与全域请求冲突时拒绝扩大范围。同名地区返回候选。普通查询区分无数据/未计算、缺参数、参数单位问题、关闭服务和执行异常。已有预测不支持按年筛选的行为保留。

## 3.2 多轮草稿

草稿记录flux类别、schema_version、来源、地区/地块、年度、参数单位及来源、公式版本。相同范围可补参和改值；切换范围重新校验并读取匹配的单一地块年度输入，不以行政均值替代。只从明确v2单位契约记录补值；修改值后要求本轮单位。

企业未知与明确0分开；年度必须明确。容重和厚度默认列出值及情景假设，必须用户原话“同意使用通量默认值：bulk_density_g_cm3”或soil_depth_m（多项逗号分隔）才接受，服务器ContextVar校验，工具无自行确认参数。草稿仍使用现有revision与用户/会话隔离，已有迟到响应保护测试继续通过。

## 3.3 保存

成功且有完整净收支的通量试算进入可保存快照；末期浓度若缺条件保持未知。只有明确保存指令才创建CdTrial，payload新增schema_version=2及calculation_type。保持服务器所属消息读取、唯一键幂等、事务、越权拒绝和失败重试；并发测试同时涵盖flux类别。新增查询或未完成结果清除本轮可保存状态，避免保存旧结果。

## 3.4 HTTP/SSE 一致

共享answer_cd封装，HTTP/SSE返回同一data.cd_conversation结构（include_model_results=true）。工具结果的日期转成可序列化表示；草稿只在内部快照持久化。两种入口分别验证默认确认、改参数、保存、重复保存、新修订保存及查询后拒绝保存旧结果。

## 3.5 测试证据

使用项目根虚拟环境；CD_MIGRATION_TEST_DB=db_enterprise_qa_cd_20261103，CD_MIGRATION_ENV_FILE=<根>/.env，MPLCONFIGDIR指向工作区artifacts/matplotlib-config。

```text
python -m pytest tests/test_cd_flux_conversation.py tests/test_cd_flux_v2.py tests/test_cd_conversation.py tests/test_cd_trial.py tests/analysis_context -q --tb=short
```

110 passed。PostgreSQL测试验证省市县乡镇查询、地块年度参数读取、来源筛选、切换年度重新取值、纯试算不改变业务输出表。分析上下文完整测试覆盖原有HTTP/SSE、所有权、版本及旧Cd预测回归。范围不明确和未经确认的默认不扫描/不采用。

限制：聊天LLM使用确定性替身，实际数值调用真实纯计算，数据库测试使用隔离事务并回滚。这证明工具协议/保存/计算链路，不是已完成真实模型自然语言验收。真实模型联调属于5.3，仍未勾选。真实通量表为空；本次没有向业务表写入合成通量。第4、5阶段未开始。
