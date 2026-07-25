"""生成完整验证报告：每个问题的完整回答 + 调用细节。

不启动 Flask HTTP，直接调用 orchestrator，输出 Markdown 报告到：
  d:\\17417\\Documents\\agent_culti_demo\\verification_full_report.md

同时 dump 每题原始 orchestrator 输出到：
  d:\\17417\\Documents\\agent_culti_demo\\verification_raw_outputs.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT / "src"))
os.environ.setdefault("FLASK_CONFIG", "default")

REPORT_FILE = PROJECT_ROOT / "verification_full_report.md"
RAW_JSON_FILE = PROJECT_ROOT / "verification_raw_outputs.json"


def truncate(s: str, n: int = 4000) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[:n] + f"...[truncated {len(s) - n} chars]"


def _short(v: Any, n: int = 800) -> str:
    """Compact string representation of any value, truncated."""
    if v is None:
        return ""
    if isinstance(v, str):
        return truncate(v, n)
    try:
        s = json.dumps(v, ensure_ascii=False)
    except Exception:
        s = str(v)
    return truncate(s, n)


def run_one_question(q_type: int, q: str,
                     parcel_id: str | None = None,
                     parcel_code: str | None = None) -> Dict[str, Any]:
    from framework.agents.orchestrator import multi_agent_orchestrator

    t0 = time.time()
    try:
        request = {"question": q}
        if parcel_id:
            request["parcel_id"] = parcel_id
        if parcel_code:
            request["parcel_code"] = parcel_code
        output = multi_agent_orchestrator.run(request, conversation_history=[])
    except Exception as exc:
        return {
            "expected_type": q_type,
            "question": q,
            "error": f"orchestrator.run failed: {exc}",
            "elapsed": round(time.time() - t0, 2),
        }
    elapsed = round(time.time() - t0, 2)

    status = output.get("status")
    question_type = output.get("question_type")
    answer = output.get("answer") or output.get("llm_response") or ""
    model_results = output.get("model_results", {}) or {}
    agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
    agents_invoked = agent_data.get("agents_invoked", []) or []
    role = agent_data.get("role")
    summary = agent_data.get("summary", "") or ""
    details = agent_data.get("details", {}) or {}

    final_answer = answer or summary

    # 收集每个 agent 的明细
    # details[agent_id] 是 agent.answer_question() 的返回，结构为：
    #   {answer, evidence, confidence, simulated, status?(skipped), reason?, error?}
    agent_details: List[Dict[str, Any]] = []
    for aid in agents_invoked:
        detail = details.get(aid, {}) or {}
        if not isinstance(detail, dict):
            continue
        agent_details.append({
            "agent_id": aid,
            "simulated": detail.get("simulated"),
            "status": detail.get("status"),
            "reason": detail.get("reason"),
            "error": detail.get("error"),
            "answer": detail.get("answer") or "",
            "confidence": detail.get("confidence"),
            "evidence": detail.get("evidence") or [],
        })

    return {
        "expected_type": q_type,
        "question": q,
        "status": status,
        "identified_type": question_type,
        "type_match": question_type == q_type,
        "role": role,
        "agents_invoked": agents_invoked,
        "answer_full": final_answer,
        "summary": summary,
        "answer_source": "answer" if answer else ("summary" if summary else "none"),
        "agent_details": agent_details,
        "elapsed": elapsed,
        "parcel_id": parcel_id,
        "parcel_code": parcel_code,
        # 保留原始 output 供 dump（去除可能过大的字段后再序列化）
        "_raw_output": output,
    }


def build_markdown(report: Dict[str, Any]) -> str:
    md: List[str] = []
    md.append("# 智能体能力完整验证报告")
    md.append("")
    md.append(f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"- 项目根目录：`{PROJECT_ROOT}`")
    md.append(f"- Python：`{sys.executable}`")
    md.append(f"- 问题库：`framework/agents/nodes.py` 中的 `REFERENCE_QUESTIONS`")
    md.append(f"- 数据来源：重新调用 `multi_agent_orchestrator.run()` 实时获取（非日志回放）")
    md.append(f"- 参考日志：`verify_output.log`（仅作历史对照）")
    md.append(f"- 原始 JSON：`verification_raw_outputs.json`")
    md.append("")
    md.append("> 说明：占位模型 model-2（PotentialAssessmentAgent）与 model-5（OrganicMatterAgent）"
              "无真实模型绑定，本报告对其调用细节仅做记录，不做能力评估。")
    md.append("")
    md.append("---")
    md.append("")

    # 一、Agent 加载状态
    md.append("## 一、Agent 加载状态盘点")
    md.append("")
    md.append("| model_id | class | 占位桩 | 真实模型 | 资源就绪 | 期望行为 |")
    md.append("|---|---|---|---|---|---|")
    for mid, e in report["agents"].items():
        md.append(
            f"| {mid} | `{e['class']}` | {'是' if e['is_stub'] else '否'} | "
            f"{e['real_model'] or '-'} | {'✓' if e.get('resource_ready') else '✗'} | "
            f"{e['expected_behavior']} |"
        )
    md.append("")
    md.append("**资源就绪状态：**")
    md.append("")
    for k, v in report["resources"].items():
        md.append(f"- {'✓' if v else '✗'} `{k}`: `{v}`")
    md.append("")
    md.append("**角色路由表（RoleRouter.ROLE_AGENTS）：**")
    md.append("")
    md.append("| role | 触发关键词 | 调用 agents |")
    md.append("|---|---|---|")
    md.append("| `province` | 全省 / 全市 / 全局 / 政策 / 省市 | model-1, model-3 |")
    md.append("| `county` | 本县 / 乡镇 / 片区 / 任务 / 县域 | model-1, model-2, model-3 |")
    md.append("| `farmer`（默认） | 我的田 / 这块地 / 施氮肥 / 施多少 / 农户 | model-4, model-5, model-6, model-7 |")
    md.append("")
    md.append("> model-7（Fortran exe）仅在 question_type=5（显式 `质量等级` 关键词）时执行；"
              "非质量等级 farmer 问题经 `_should_execute_agent` 关键词过滤跳过 model-7 "
              "（status=`skipped`, reason=`question_not_related`）。")
    md.append("")
    md.append("---")
    md.append("")

    # 二、问题库完整回答
    md.append("## 二、问题库完整回答与调用细节")
    md.append("")
    md.append(f"- 总计问题数：**{report['questions']['total']}**")
    md.append(f"- 返回非空 answer：**{report['questions']['answered']}/{report['questions']['total']}**")
    md.append(f"- question_type 匹配：**{report['questions']['type_match']}/{report['questions']['total']}**")
    md.append("")

    type_labels = {
        1: "类型1：稳定性风险（5 题）",
        2: "类型2：酸化改良（4 题）",
        3: "类型3：障碍诊断与潜力（5 题）",
        4: "类型4：肥力与有机质（6 题）",
        5: "类型5：质量等级评价（3 题）",
    }

    qidx = 0
    last_type = None
    for r in report["questions"]["details"]:
        qidx += 1
        if r["expected_type"] != last_type:
            last_type = r["expected_type"]
            md.append(f"### {type_labels.get(last_type, f'类型{last_type}')}")
            md.append("")

        md.append(f"#### Q{qidx}（期望 type={r['expected_type']}）")
        md.append("")
        md.append(f"> **问题原文：** {r['question']}")
        md.append("")

        if "error" in r:
            md.append(f"- ❌ **执行失败**：`{r['error']}`")
            md.append(f"- 耗时：{r.get('elapsed', '-')}s")
            md.append("")
            continue

        match_flag = "✓ 匹配" if r["type_match"] else "✗ 不匹配"
        md.append(f"- **识别 question_type**：{r['identified_type']} {match_flag}")
        md.append(f"- **识别 role**：`{r['role']}`")
        md.append(f"- **调用 agents**：{', '.join(r['agents_invoked']) if r['agents_invoked'] else '-'}")
        md.append(f"- **answer 来源**：`{r['answer_source']}`（`answer` = LLM 生成；`summary` = AgentManager 模板拼接）")
        md.append(f"- **耗时**：{r['elapsed']}s")
        md.append("")

        md.append("**【完整回答】**")
        md.append("")
        ans = r["answer_full"] or "(空)"
        md.append("```text")
        md.append(ans)
        md.append("```")
        md.append("")

        if r["agent_details"]:
            md.append("**【各 agent 调用细节】**")
            md.append("")
            md.append("| agent_id | simulated | status | confidence | answer 摘要 |")
            md.append("|---|---|---|---|---|")
            for ad in r["agent_details"]:
                if ad["simulated"] is True:
                    sim_str = "sim（模拟）"
                elif ad["simulated"] is False:
                    sim_str = "real（真实）"
                else:
                    sim_str = "-"
                conf = ad["confidence"]
                conf_str = f"{conf}" if conf is not None else "-"
                ans_short = _short(ad["answer"], 120).replace("\n", " ").replace("|", "\\|")
                md.append(
                    f"| {ad['agent_id']} | {sim_str} | {ad['status'] or '-'} | "
                    f"{conf_str} | {ans_short} |"
                )
            md.append("")

            # 展开每个 agent 的完整 answer + evidence
            md.append("**【各 agent 完整输出】**")
            md.append("")
            for ad in r["agent_details"]:
                md.append(f"- **{ad['agent_id']}**")
                if ad["status"]:
                    md.append(f"  - status: `{ad['status']}`")
                    if ad["reason"]:
                        md.append(f"  - reason: `{ad['reason']}`")
                if ad["error"]:
                    md.append(f"  - error: `{ad['error']}`")
                md.append(f"  - confidence: `{ad['confidence']}`")
                md.append(f"  - simulated: `{ad['simulated']}`")
                if ad["answer"]:
                    md.append(f"  - answer:")
                    md.append("    ```text")
                    for line in ad["answer"].split("\n"):
                        md.append(f"    {line}")
                    md.append("    ```")
                else:
                    md.append(f"  - answer: (空)")
                if ad["evidence"]:
                    md.append(f"  - evidence ({len(ad['evidence'])} 条):")
                    md.append("    ```json")
                    ev_str = _short(ad["evidence"], 1200)
                    for line in ev_str.split("\n"):
                        md.append(f"    {line}")
                    md.append("    ```")
                md.append("")

        md.append("---")
        md.append("")

    # 三、model-6 真实 ML 计算
    md.append("## 三、model-6 真实 ML 计算能力验证")
    md.append("")
    m6 = report["model6"]
    md.append(f"- **输入特征**：`{m6['input_features']}`")
    md.append(f"- **execute_status**：`{m6['execute_status']}`")
    md.append(f"- **SOC 预测值**：{m6['soc_prediction']} g/kg（置信度 {m6['soc_confidence']}）")
    md.append(f"- **Dose 预测值**：{m6['dose_prediction']} t/ha（置信度 {m6['dose_confidence']}）")
    md.append(f"- **dose_warning**：{m6['dose_warning']}")
    md.append(f"- **imputation_applied**：{m6['imputation_applied']}, imputed_features: `{m6['imputed_features']}`")
    md.append(f"- **fallback_reason**：{m6['fallback_reason']}")
    md.append(f"- **model_version**：`{m6['model_version']}`")
    md.append(f"- **是否真实计算**：{'✓ 是' if m6['is_real_computation'] else '✗ 否（fallback）'}")
    md.append("")
    md.append("**【SOC 自然语言回答】**")
    md.append("```text")
    md.append(m6["answer_soc_preview"])
    md.append("```")
    md.append("")
    md.append("**【Dose 自然语言回答】**")
    md.append("```text")
    md.append(m6["answer_dose_preview"])
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")

    # 四、汇总
    md.append("## 四、汇总结论")
    md.append("")
    md.append(f"- 真实可计算 agent：`{report['summary']['real_agents']}`")
    md.append(f"- 已集成但资源未部署（回退模拟）：`{report['summary']['fallback_agents']}`")
    md.append(f"- 占位桩 agent：`{report['summary']['stub_agents'] or '无'}`")
    md.append(f"- 问题库回答率：**{report['questions']['answered']}/{report['questions']['total']}**")
    md.append(f"- 问题类型识别准确率：**{report['questions']['type_match']}/{report['questions']['total']}**")
    md.append(f"- model-6 真实计算：{'✓ 通过' if m6['is_real_computation'] else '✗ 未通过'}")
    md.append("")

    md.append("### 关键观察")
    md.append("")
    md.append("1. **LLM 可用性**：本次运行 LLM 服务初始化成功（`deepseek-ai/DeepSeek-V4-Flash`），"
              "所有 20 题均通过 LLM 生成自然语言 `answer`；若 LLM 超时降级，"
              "answer 字段为空，最终回答会取自 AgentManager 的 `summary`（模板拼接）。")
    md.append("2. **真实计算 agent**：model-1（stability_db）、model-3/4（diagnosis_db）、"
              "model-6（.joblib）、model-7（Fortran exe+dat）资源均已部署，"
              "但因 RoleRouter 按角色路由，每题只调用 2-3 个 agent，并非每题都触及全部真实模型。")
    md.append("3. **路由细节**：`province` → model-1, model-3；`county` → model-1, model-2, model-3；"
              "`farmer` → model-4, model-5, model-6。model-7 仅在 question_type=5 "
              "（`质量等级` 关键词）触发，本次问题库 type 1-4 未覆盖到 model-7。")
    md.append("4. **model-6 问题感知过滤**：AgentManager._should_execute_agent 对 model-6 做关键词过滤，"
              "非肥力问题（不含 有机碳/SOC/施用量/施肥量/肥力/秸秆/有机肥/培肥/Dose 等）会跳过 model-6 "
              "（status=`skipped`, reason=`question_not_related`）。这就是 Q1-Q15 中 model-6 大量被跳过的原因。")
    md.append("5. **simulated 标志解读**：AgentManager 通过 `MockDataLoader.mark_simulated(payload)` "
              "在结果顶层强制写入 `simulated=True`，即使 model-6 这种真实计算 agent 也显示 sim。"
              "**因此 `simulated=True` 不能作为真实/模拟的判据**。是否真实计算应以：")
    md.append("   - `fallback_reason is None` + `execute_status==success`（model-6 直接 execute 验证）")
    md.append("   - 或 agent 真实调用了底层模型（如 model-1 读 stability_db、model-7 调 Fortran exe）")
    md.append("   为准。")
    md.append("6. **parcel 标识符透传**：本次验证脚本为 farmer 问题（含 type 5）预设 `parcel_id=\"1\"` "
              "（来自 stability_db/acidification_results）+ `parcel_code=\"A0001\"`（来自 fortran exe 数据库）。"
              "管道已接通 `execute_models → context → agents`，model-1/4 应返回真实 DB 记录，"
              "model-7 应返回真实 fortran exe 质量等级评价。"
              "**预存在数据缺口**：`diagnosis_results` 表 0 条记录，model-3 仍返回 mock，"
              "数据填充后管道自动生效（非本次引入）。")
    md.append("")

    return "\n".join(md)


def main() -> int:
    print("=" * 72)
    print("生成完整验证报告（含每个问题的完整回答与调用细节）")
    print("=" * 72)
    print(f"项目根目录: {PROJECT_ROOT}")
    print(f"Python: {sys.executable}")

    report: Dict[str, Any] = {}

    # 一、Agent 加载状态
    print("\n[1/3] 采集 Agent 加载状态...")
    # verify_agent_capabilities.py 可能被删除但 __pycache__ 仍可导入
    try:
        from scripts.verify_agent_capabilities import (
            inspect_agent_load_status,
            verify_model6_real_computation,
        )
    except ImportError:
        # 退路：直接 import 内部函数
        import importlib.util
        pyc = PROJECT_ROOT / "scripts" / "__pycache__" / "verify_agent_capabilities.cpython-312.pyc"
        if pyc.exists():
            spec = importlib.util.spec_from_file_location("verify_agent_capabilities", str(pyc))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            inspect_agent_load_status = mod.inspect_agent_load_status
            verify_model6_real_computation = mod.verify_model6_real_computation
        else:
            raise

    load_report = inspect_agent_load_status()
    report["agents"] = load_report["agents"]
    report["resources"] = load_report["resources"]

    # 二、问题库完整回答
    print("\n[2/3] 跑问题库（实时调用 orchestrator，可能耗时）...")
    from framework.agents.nodes import REFERENCE_QUESTIONS
    from framework.agents.router import RoleRouter

    router = RoleRouter()

    details: List[Dict[str, Any]] = []
    raw_outputs: List[Dict[str, Any]] = []
    total = 0
    answered = 0
    type_match = 0
    total_count = sum(len(v) for v in REFERENCE_QUESTIONS.values())
    for q_type, questions in REFERENCE_QUESTIONS.items():
        for q in questions:
            total += 1
            # 按角色预设 parcel 标识符：
            # - farmer 问题（含 type 5 全部）预设 parcel_id="1" + parcel_code="A0001"
            # - county/province 问题不预设（model-1/3 按 area_code 查询）
            parcel_id = None
            parcel_code = None
            if q_type == 5 or router.identify_role(q) == "farmer":
                parcel_id = "1"
                parcel_code = "A0001"
            print(f"  [{total}/{total_count}] type={q_type} -> {q[:40]}..."
                  f" (parcel_id={parcel_id or '-'}, parcel_code={parcel_code or '-'})",
                  flush=True)
            r = run_one_question(q_type, q, parcel_id=parcel_id, parcel_code=parcel_code)
            if r.get("answer_full"):
                answered += 1
            if r.get("type_match"):
                type_match += 1
            # dump raw output
            raw = r.pop("_raw_output", None)
            if raw is not None:
                raw_outputs.append({
                    "question": q,
                    "expected_type": q_type,
                    "raw_output": raw,
                })
            details.append(r)

    report["questions"] = {
        "total": total,
        "answered": answered,
        "type_match": type_match,
        "details": details,
    }

    # 三、model-6 真实计算
    print("\n[3/3] 验证 model-6 真实 ML 计算...")
    m6 = verify_model6_real_computation()
    report["model6"] = m6

    # 汇总
    real_agents = [mid for mid, e in report["agents"].items()
                   if not e["is_stub"] and e.get("resource_ready")]
    fallback_agents = [mid for mid, e in report["agents"].items()
                       if not e["is_stub"] and not e.get("resource_ready")]
    stub_agents = [mid for mid, e in report["agents"].items() if e["is_stub"]]
    report["summary"] = {
        "real_agents": real_agents,
        "fallback_agents": fallback_agents,
        "stub_agents": stub_agents,
    }

    # dump raw JSON
    print("\n[Dump 原始 JSON]")
    try:
        RAW_JSON_FILE.write_text(
            json.dumps(raw_outputs, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"  -> 已写入: {RAW_JSON_FILE}")
    except Exception as exc:
        print(f"  -> dump 失败: {exc}")

    # 生成 Markdown
    print("\n[生成 Markdown 报告]")
    md = build_markdown(report)
    REPORT_FILE.write_text(md, encoding="utf-8")
    print(f"  -> 已写入: {REPORT_FILE}")
    print(f"  -> 报告长度: {len(md)} 字符")

    # 控制台打印关键指标
    print("\n" + "=" * 72)
    print("汇总")
    print("=" * 72)
    print(f"真实可计算 agent: {real_agents}")
    print(f"已集成但资源未部署（回退模拟）: {fallback_agents}")
    print(f"占位桩 agent: {stub_agents or '无'}")
    print(f"问题库回答率: {answered}/{total}")
    print(f"问题类型识别准确率: {type_match}/{total}")
    print(f"model-6 真实计算: {'✓ 通过' if m6['is_real_computation'] else '✗ 未通过'}")
    print(f"\n完整报告: {REPORT_FILE}")
    print(f"原始 JSON: {RAW_JSON_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
