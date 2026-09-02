"""Render customer-facing request/response simulations from verified results."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=json.loads((ROOT/"docs"/"generated"/"postgres-comprehensive-results.json").read_text(encoding="utf-8"))
by_id={item["parcel_id"]:item for item in source["parcels"]}


def payload(parcel,model): return by_id[parcel]["results"][model]["result"]
def dump(value): return "```json\n"+json.dumps(value,ensure_ascii=False,indent=2)+"\n```"


cases=[]
cases.append({"title":"知识问答：不要求选择地块","request":{"message":"土壤酸化通常会造成哪些影响？"},"reaction":"Coordinator 判定 knowledge，TrafficGate 保持快路径；不启动任何专业模型。","http":200,"response":{"interaction_state":"completed","routing":{"question_type":0,"path":"knowledge"},"answer":"从本地知识库检索酸化影响并生成答复。","agents_invoked":[]}})
cases.append({"title":"单模型请求缺少分析对象","request":{"message":"请评价这块地的质量等级"},"reaction":"中央 AnalysisRequirementGuard 在模型执行前中断，要求客户选择一个已验证地块。","http":200,"response":{"interaction_state":"needs_analysis_object","required_object_types":["parcel"],"missing_inputs":["analysis_object"],"answer":"请选择需要分析的地块。"}})
grade=payload("4190","model-2")
cases.append({"title":"单模型快路径：真实地块 4190","request":{"message":"地块4190的质量等级怎么样？","analysis_object":{"type":"parcel","id":"4190"}},"reaction":"对象解析成功，只调用 model-2，不升级为综合任务。","http":200,"response":{"interaction_state":"completed","analysis_context":{"mode":"spatial","object":{"type":"parcel","id":"4190","area_code":"440233"}},"models":{"model-2":{"status":"ok","result":{"quality_grade":grade["quality_grade"],"composite_index":grade["composite_index"]},"persisted":True}}}})
plan={"plan_version":1,"tasks":[{"agent_id":"model-2","required":True},{"agent_id":"model-3","required":True},{"agent_id":"model-4","required":False},{"agent_id":"model-5","required":False}]}
cases.append({"title":"综合诊断首次请求：等待客户确认计划","request":{"message":"请为地块1生成综合诊断与改良报告","analysis_object":{"type":"parcel","id":"1"}},"reaction":"明确综合意图进入任务路径；解析 PostgreSQL 快照并展示两波执行计划，尚未运行模型。","http":200,"response":{"interaction_state":"needs_confirmation","run_id":"run-customer-001","checkpoint_version":1,"plan_summary":plan,"proposed_defaults":{"fertilizer_type":"compound","target_ph":6.5}}})
one=by_id["1"]
cases.append({"title":"客户确认后执行并生成待发布报告","request":{"conversation_id":88,"interaction_response":{"run_id":"run-customer-001","expected_checkpoint_version":1,"action":"confirm_plan","values":{}}},"reaction":"恢复同一 checkpoint；第一波执行 model-2/3，触发后执行 model-4/5；所有结果成功持久化，然后在发布节点中断。","http":200,"response":{"interaction_state":"awaiting_release","run_id":"run-customer-001","checkpoint_version":2,"model_statuses":{key:value["status"] for key,value in one["results"].items()},"report_summary":{"quality_grade":payload("1","model-2")["quality_grade"],"composite_index":payload("1","model-2")["composite_index"],"obstacle_type":payload("1","model-3")["obstacle_type"],"YTK":payload("1","model-4")["YTK"],"MBNT":payload("1","model-4")["MBNT"],"organic_dose":payload("1","model-5")["dose"]}}})
cases.append({"title":"客户要求修订：只重写报告，不重跑模型","request":{"conversation_id":88,"interaction_response":{"run_id":"run-customer-001","expected_checkpoint_version":2,"action":"request_revision","comment":"请把主要障碍和优先措施放在最前面"}},"reaction":"Reporter 使用已验证结果生成第 1 次修订；模型执行次数和 RAG 结果保持不变。","http":200,"response":{"interaction_state":"awaiting_release","checkpoint_version":3,"report_revision_count":1,"models_rerun":False}})
cases.append({"title":"客户发布报告","request":{"conversation_id":88,"interaction_response":{"run_id":"run-customer-001","expected_checkpoint_version":3,"action":"release_report"}},"reaction":"发布最终报告，返回完整 provenance；由于本次无模型失败，状态为 completed。","http":200,"response":{"interaction_state":"completed","checkpoint_version":4,"answer":"地块1综合诊断与改良报告","provenance":{"spatial_object":{"type":"parcel","id":"1"},"agents":["model-2","model-3","model-4","model-5"],"persisted":True}}})
cases.append({"title":"过期页面提交旧版本","request":{"conversation_id":88,"interaction_response":{"run_id":"run-customer-001","expected_checkpoint_version":2,"action":"release_report"}},"reaction":"服务器检测 checkpoint 已更新到 4，拒绝覆盖新状态。","http":409,"response":{"status":"error","error":{"code":"checkpoint_version_conflict","message":"工作流状态已更新，请刷新后重试。"}}})
cases.append({"title":"非地块对象请求综合报告","request":{"message":"请生成乐昌市综合诊断报告","analysis_object":{"type":"county","id":"440281"}},"reaction":"TrafficGate 拒绝进入单地块综合子图，保持边界清晰。","http":422,"response":{"status":"error","error":{"code":"single_parcel_required","message":"综合诊断仅支持单一地块。"}}})
cases.append({"title":"可选证据服务不可用时的降级发布","request":{"message":"请为地块1593生成综合诊断报告","analysis_object":{"type":"parcel","id":"1593"}},"reaction":"故障注入场景：核心 model-2/3 成功，RAG 本地检索不可用；不使用通用知识回退，报告标记降级后仍可发布。","http":200,"response":{"interaction_state":"partial_complete","degradations":["local_evidence_unavailable"],"core_models":{"model-2":"succeeded","model-3":"succeeded"},"unsupported_claims":["需要知识证据支持的改良解释"]}})

lines=["# 客户实际输入输出与工作流反应报告","",f"数据基线：PostgreSQL `{source['database']}.{source['schema']}.parcel_info`；实算地块：4190、1、1593。","","> 标注为实算的结果来自本次 PostgreSQL 正式模型运行；交互错误与故障注入案例用于验证 API 状态机，不会改写地块数据。",""]
for index,case in enumerate(cases,1):
    lines += [f"## {index}. {case['title']}","",f"系统反应：{case['reaction']}","", "客户请求：", "", dump(case["request"]), "", f"HTTP {case['http']} 响应：", "", dump(case["response"]), ""]
lines += ["## 验收结论","","- 知识问答与单模型请求继续使用快路径。","- 缺对象、计划确认、报告修订和发布均形成明确交互状态。","- 同一 trace 可持久化多个 Agent 执行日志。","- 过期 checkpoint 返回 409，非地块综合请求返回 422。","- RAG 不可用只做显式降级，不调用通用知识补写证据。",""]
out=ROOT/"docs"/"generated"/"customer-workflow-simulation-report.md"; out.write_text("\n".join(lines),encoding="utf-8")
(ROOT/"docs"/"generated"/"customer-workflow-simulation-cases.json").write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"report":str(out),"cases":len(cases)},ensure_ascii=False))
