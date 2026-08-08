"""智能体能力验证脚本

不启动 Flask HTTP，直接调用 Python API 验证：
1. 6 个 agent 的加载状态（real/stub + 模型可用性）
2. REFERENCE_QUESTIONS 问题库 18 个问题的回答能力
3. model-6 (FertilityMLAgent) 集成的真实 ML 计算能力

用法：
    python scripts/verify_agent_capabilities.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 项目根目录加入 sys.path，并设置 PYTHONPATH=src 以兼容 src 布局
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("PYTHONPATH", str(PROJECT_ROOT / "src"))

# 避免加载 .env 时引发副作用，仅设置最小环境变量
os.environ.setdefault("FLASK_CONFIG", "default")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="backslashreplace")

# Excel 标准模型映射（单一事实源在 gen_full_verification_report，此处引入共享同一份）
# MODEL_TO_STD: model_id -> (std_id, std_name)；未对应 Excel 标准的 model 返回 None
try:
    from scripts.gen_full_verification_report import MODEL_TO_STD, STANDARD_MODEL_MAPPING
except ImportError:  # 直接以文件方式运行时的兜底
    MODEL_TO_STD = {}
    STANDARD_MODEL_MAPPING = []


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def hr() -> None:
    print("-" * 72)


# ---------------------------------------------------------------------------
# 第一部分：Agent 加载状态盘点
# ---------------------------------------------------------------------------

def inspect_agent_load_status() -> dict:
    """检查 6 个 agent 的加载状态及依赖模型文件/数据库是否就绪。"""
    from framework.agents.manager import AgentManager

    manager = AgentManager()
    report: dict = {}

    # 依赖资源检查（注意：DB 实际路径由 storage 模块定义）
    # - farmland_stability: StabilityStorage.DEFAULT_DB_PATH = "data/farmland_stability/stability_results.db"
    # - farmland_diagnosis: DiagnosisStorage 默认基于 __file__ 计算（当前为 src/data/farmland_diagnosis/）
    # 用 storage 类的实际默认路径检查，避免硬编码路径不一致
    from ai_culti_demo.farmland_stability.storage import StabilityStorage
    from ai_culti_demo.farmland_diagnosis.storage import DiagnosisStorage

    stability_db = Path(StabilityStorage().db_path)
    diagnosis_db = Path(DiagnosisStorage().db_path)
    soc_joblib = PROJECT_ROOT / "data" / "fertility" / "models" / "soc_etr_model.joblib"
    dose_joblib = PROJECT_ROOT / "data" / "fertility" / "models" / "dose_etr_model.joblib"
    grade_csv = PROJECT_ROOT / "bin" / "farmland_quality_eval" / "Farmland_quality_Level_Database.csv"

    resource_status = {
        "stability_db_exists": stability_db.exists(),
        "stability_db_path": str(stability_db),
        "diagnosis_db_exists": diagnosis_db.exists(),
        "diagnosis_db_path": str(diagnosis_db),
        "soc_joblib_exists": soc_joblib.exists(),
        "dose_joblib_exists": dose_joblib.exists(),
        "grade_csv_exists": grade_csv.exists(),
    }

    # 判断每个 agent 是 real 还是 stub
    from framework.agents.base import BaseAgent
    from framework.agents.manager import _StubAgent

    for model_id, agent in manager.agents.items():
        is_stub = isinstance(agent, _StubAgent)
        std = MODEL_TO_STD.get(model_id)  # (std_id, std_name) or None
        entry = {
            "model_id": model_id,
            "class": type(agent).__name__,
            "is_stub": is_stub,
            "description": getattr(agent, "description", ""),
            "domain": getattr(agent, "domain", ""),
            "dependencies": getattr(agent, "dependencies", []) or [],
            "model_id_registered": getattr(agent, "model_id", ""),
            # Excel 标准模型对应关系（未对应时为 None）。
            "std_id": std[0] if std else None,
            "std_name": std[1] if std else None,
        }

        # 附加具体模型可用性
        if model_id == "model-1":
            entry["real_model"] = "farmland_stability"
            entry["resource_ready"] = resource_status["stability_db_exists"]
            entry["expected_behavior"] = (
                "真实计算" if resource_status["stability_db_exists"]
                else "回退模拟数据（需 data/farmland_stability/stability_results.db）"
            )
        elif model_id == "model-3":
            entry["real_model"] = "farmland_diagnosis"
            entry["resource_ready"] = resource_status["diagnosis_db_exists"]
            entry["expected_behavior"] = (
                "真实计算" if resource_status["diagnosis_db_exists"]
                else "回退模拟数据（需 data/farmland_diagnosis/farmland_diagnosis.db）"
            )
        elif model_id == "model-4":
            entry["real_model"] = "farmland_acidification"
            entry["resource_ready"] = resource_status["diagnosis_db_exists"]
            entry["expected_behavior"] = (
                "真实计算" if resource_status["diagnosis_db_exists"]
                else "回退模拟数据（与 model-3 共用 farmland_diagnosis.db）"
            )
        elif model_id == "model-6":
            entry["real_model"] = "sklearn ETR (soc_etr + dose_etr)"
            entry["resource_ready"] = (
                resource_status["soc_joblib_exists"] and resource_status["dose_joblib_exists"]
            )
            entry["expected_behavior"] = (
                "真实 ML 计算" if entry["resource_ready"]
                else "fallback 训练集均值（缺 .joblib）"
            )
        elif model_id == "model-2":
            entry["real_model"] = "farmland_grade_eval Python implementation"
            entry["resource_ready"] = resource_status["grade_csv_exists"]
            entry["expected_behavior"] = (
                "真实计算" if entry["resource_ready"]
                else "返回 DEPLOYMENT_ERROR（需部署 CSV 到 bin/farmland_quality_eval/）"
            )
        else:
            entry["real_model"] = None
            entry["resource_ready"] = None
            entry["expected_behavior"] = "占位桩（无真实模型绑定）"

        report[model_id] = entry

    return {"agents": report, "resources": resource_status}


# ---------------------------------------------------------------------------
# 第二部分：问题库验证
# ---------------------------------------------------------------------------

def run_reference_questions() -> dict:
    """对 REFERENCE_QUESTIONS 问题逐个调用 orchestrator，记录结果。"""
    from framework.agents.nodes import REFERENCE_QUESTIONS
    from framework.agents.orchestrator import multi_agent_orchestrator

    results = []
    total = 0
    answered = 0
    type_correct = 0

    for q_type, questions in REFERENCE_QUESTIONS.items():
        for q in questions:
            total += 1
            try:
                request = {"question": q}
                if q_type == 5:
                    request["parcel_code"] = "A0001"
                elif q_type == 6:
                    request["xqmc_code"] = 8
                    request["scenario"] = 1
                output = multi_agent_orchestrator.run(
                    request, conversation_history=[]
                )
            except Exception as exc:
                results.append({
                    "expected_type": q_type,
                    "question": q,
                    "error": f"orchestrator.run failed: {exc}",
                    "answered": False,
                })
                continue

            status = output.get("status")
            question_type = output.get("question_type")
            answer = output.get("answer") or output.get("llm_response") or ""
            model_results = output.get("model_results", {}) or {}
            agent_data = model_results.get("data", {}) if isinstance(model_results, dict) else {}
            agents_invoked = agent_data.get("agents_invoked", [])
            role = agent_data.get("role")
            summary = agent_data.get("summary", "")

            # 判定是否真的回答了
            final_answer = answer or summary
            is_answered = bool(final_answer and final_answer.strip())
            if is_answered:
                answered += 1

            # 判定路由类型是否匹配
            if question_type == q_type:
                type_correct += 1

            # 收集每个 agent 的 simulated 标志
            agent_simulated = {}
            details = agent_data.get("details", {}) or {}
            for aid, detail in details.items():
                if isinstance(detail, dict):
                    agent_simulated[aid] = detail.get("simulated")

            results.append({
                "expected_type": q_type,
                "question": q,
                "status": status,
                "identified_type": question_type,
                "type_match": question_type == q_type,
                "role": role,
                "agents_invoked": agents_invoked,
                "answer_preview": (final_answer[:120] + "...") if len(final_answer) > 120 else final_answer,
                "answered": is_answered,
                "agent_simulated": agent_simulated,
            })

    return {
        "total_questions": total,
        "answered": answered,
        "type_match": type_correct,
        "details": results,
    }


# ---------------------------------------------------------------------------
# 第三部分：model-6 真实 ML 计算能力验证
# ---------------------------------------------------------------------------

def verify_model6_real_computation() -> dict:
    """直接给 FertilityMLAgent 喂测试特征，验证真实 ML 预测。"""
    from framework.agents.specialized.fertility_ml_agent import FertilityMLAgent

    agent = FertilityMLAgent()

    # 测试特征（在合法范围内，避免 rejected）
    test_features = {
        "pH": 6.5,
        "SOCbe": 15.0,
        "TN": 1.2,
        "TP": 0.8,
        "TK": 20.0,
        "AP": 25.0,
        "AK": 180.0,
        "Gap": 5.0,
        "Dose": 300.0,
        "Fertilizer type": 1,
    }

    # 直接调用 execute（绕过 answer_question 的格式化层，看原始结果）
    exec_result = agent.execute(test_features)
    status = exec_result.get("status")
    result = exec_result.get("result", {}) or {}
    metadata = exec_result.get("metadata", {}) or {}

    # 判定真实计算 vs fallback
    # model_6_execution 成功时 status="success"；fallback 时 status="fallback"；
    # 越界时 status="rejected"。FertilityMLAgent.execute 用 MockDataLoader.mark_simulated
    # 强制在顶层加 simulated=True（设计如此），所以 simulated 标志不能作为真实/模拟的判据。
    is_real = (
        status == "success"
        and metadata.get("fallback_reason") is None
        and result.get("soc_prediction") is not None
        and result.get("dose_prediction") is not None
    )

    # 同时调用 answer_question 看自然语言回答
    answer_soc = agent.answer_question("我的田土壤有机碳含量大概多少", {"data": test_features})
    answer_dose = agent.answer_question("我这块地大概需要施多少有机肥", {"data": test_features})

    return {
        "input_features": test_features,
        "execute_status": status,
        "soc_prediction": result.get("soc_prediction"),
        "soc_confidence": result.get("soc_confidence"),
        "dose_prediction": result.get("dose_prediction"),
        "dose_confidence": result.get("dose_confidence"),
        "dose_warning": result.get("dose_warning"),
        "imputation_applied": result.get("imputation_applied"),
        "imputed_features": result.get("imputed_features"),
        "fallback_reason": metadata.get("fallback_reason"),
        "model_version": metadata.get("model_version"),
        "is_real_computation": is_real,
        "answer_soc_preview": (answer_soc.get("answer") or "")[:200],
        "answer_dose_preview": (answer_dose.get("answer") or "")[:200],
        "answer_soc_simulated": answer_soc.get("simulated"),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    section("智能体能力验证报告")
    print(f"项目根目录: {PROJECT_ROOT}")

    # 第一部分
    section("一、Agent 加载状态盘点")
    load_report = inspect_agent_load_status()
    print("\n[资源就绪状态]")
    for k, v in load_report["resources"].items():
        flag = "OK" if v else "MISSING"
        print(f"  {flag} {k}: {v}")

    print("\n[6 个 Agent 加载状态]（含 Excel 标准模型对应关系）")
    print(f"{'Excel标准':<10}{'model_id':<10}{'class':<32}{'stub':<6}{'real_model':<28}{'expected_behavior'}")
    hr()
    for mid, entry in load_report["agents"].items():
        std_label = f"模型{entry['std_id']}" if entry.get("std_id") else "-"
        print(f"{std_label:<10}{mid:<10}{entry['class']:<32}"
              f"{'是' if entry['is_stub'] else '否':<6}"
              f"{(entry['real_model'] or '-'):<28}"
              f"{entry['expected_behavior']}")
    print("\n  注：Excel 标准模型6（耕地综合地力改良提升模型）尚未实现，项目中无对应 agent；"
          "模型2已接入真实耕地质量等级与提升潜力引擎；未对应 Excel 标准的模型会标注为空。")

    # 第二部分
    section("二、问题库回答验证（REFERENCE_QUESTIONS）")
    q_report = run_reference_questions()
    print(f"\n总计 {q_report['total_questions']} 题")
    print(f"  返回非空 answer: {q_report['answered']}/{q_report['total_questions']}")
    print(f"  question_type 匹配: {q_report['type_match']}/{q_report['total_questions']}")
    print("\n[逐题明细]")
    print(f"{'#':<3}{'期望':<4}{'识别':<4}{'匹配':<6}{'role':<10}{'agents_invoked':<28}{'answer_preview'}")
    hr()
    for i, r in enumerate(q_report["details"], 1):
        if "error" in r:
            print(f"{i:<3}{r['expected_type']:<4}{'-':<4}{'-':<6}{'-':<10}{'-':<28}{r['error']}")
            continue
        match_flag = "OK" if r["type_match"] else "MISMATCH"
        agents_str = ",".join(r["agents_invoked"]) if r["agents_invoked"] else "-"
        preview = (r["answer_preview"] or "").replace("\n", " ")
        print(f"{i:<3}{r['expected_type']:<4}{r['identified_type']:<4}{match_flag:<6}"
              f"{(r['role'] or '-'):<10}{agents_str:<28}{preview}")
        if r["agent_simulated"]:
            sim_str = ", ".join(
                f"{k}:{'sim' if v else 'real'}" for k, v in r["agent_simulated"].items()
            )
            print(f"     agent_simulated: {sim_str}")

    # 第三部分
    section("三、model-6 真实 ML 计算能力验证")
    m6 = verify_model6_real_computation()
    print(f"\n输入特征: {m6['input_features']}")
    print(f"execute_status: {m6['execute_status']}")
    print(f"SOC 预测值: {m6['soc_prediction']} g/kg (置信度 {m6['soc_confidence']})")
    print(f"Dose 预测值: {m6['dose_prediction']} t/ha (置信度 {m6['dose_confidence']})")
    print(f"dose_warning: {m6['dose_warning']}")
    print(f"imputation_applied: {m6['imputation_applied']}, imputed_features: {m6['imputed_features']}")
    print(f"fallback_reason: {m6['fallback_reason']}")
    print(f"model_version: {m6['model_version']}")
    print(f"\n[是否真实计算] {'OK' if m6['is_real_computation'] else 'MISSING（fallback）'}")
    print(f"\n[SOC 回答预览] {m6['answer_soc_preview']}")
    print(f"  simulated={m6['answer_soc_simulated']}")
    print(f"\n[Dose 回答预览] {m6['answer_dose_preview']}")

    # 汇总
    section("汇总")
    real_agents = [mid for mid, e in load_report["agents"].items()
                   if not e["is_stub"] and e.get("resource_ready")]
    fallback_agents = [mid for mid, e in load_report["agents"].items()
                       if not e["is_stub"] and not e.get("resource_ready")]
    stub_agents = [mid for mid, e in load_report["agents"].items() if e["is_stub"]]

    print(f"真实可计算 agent: {real_agents or '无'}")
    print(f"已集成但资源未部署（回退模拟）: {fallback_agents or '无'}")
    print(f"占位桩 agent: {stub_agents or '无'}")
    print(f"问题库回答率: {q_report['answered']}/{q_report['total_questions']}")
    print(f"问题类型识别准确率: {q_report['type_match']}/{q_report['total_questions']}")
    print(f"model-6 真实计算: {'OK' if m6['is_real_computation'] else 'MISSING'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
