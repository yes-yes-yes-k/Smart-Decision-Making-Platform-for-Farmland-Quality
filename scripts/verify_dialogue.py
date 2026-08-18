"""验证真实对话流程：每个专题模型测试 3 个地块，生成对话结果 md 报告。

通过 AgentManager.process() 模拟用户对话，捕获完整的回复内容。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

env_path = _PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

from framework.api.app import create_app
from framework.models.user import db
from framework.models.thematic_model import ParcelInfo

app = create_app("default")
ctx = app.app_context()
ctx.push()

# 测试配置
TEST_PARCELS = [
    {"parcel_id": "1", "desc": "旱地·新丰县马头镇"},
    {"parcel_id": "2", "desc": "水浇地·新丰县丰城街道"},
    {"parcel_id": "3", "desc": "水田·新丰县黄礤镇"},
]

MODELS = [
    (1, "model-1", "耕地质量稳定性与退化风险评价"),
    (2, "model-2", "耕地质量等级评价"),
    (3, "model-3", "耕地质量主要问题与障碍诊断"),
    (4, "model-4", "耕地土壤酸化改良"),
    (5, "model-5", "耕地土壤有机质培肥提升"),
]

# 获取地块信息
print("=== 获取地块信息 ===")
parcel_infos = {}
for tp in TEST_PARCELS:
    pid = tp["parcel_id"]
    p = ParcelInfo.query.filter_by(parcel_id=pid).first()
    if p:
        si = p.soil_indicators or {}
        parcel_infos[pid] = {
            "parcel_id": pid,
            "desc": tp["desc"],
            "land_type": p.land_type,
            "area_code": p.area_code,
            "soil_ph": si.get("soil_ph"),
            "organic_matter": si.get("organic_matter"),
            "soil_texture": si.get("soil_texture"),
            "irrigation_condition": si.get("irrigation_condition"),
            "quality_grade": si.get("quality_grade"),
            "composite_index": si.get("composite_index"),
        }
        print(f"  [{pid}] {tp['desc']} | land={p.land_type} pH={si.get('soil_ph')} OM={si.get('organic_matter')}")

# 运行对话测试
from framework.agents.manager import AgentManager
mgr = AgentManager()

all_results = {}

for q_type, agent_id, model_name in MODELS:
    print(f"\n{'='*60}")
    print(f"  {agent_id} {model_name} (question_type={q_type})")
    print(f"{'='*60}")

    model_results = []
    for tp in TEST_PARCELS:
        pid = tp["parcel_id"]
        question = f"请分析地块 {pid} 的{model_name}"
        context = {
            "question_type": q_type,
            "parcel_id": pid,
            "data": {"parcel_id": pid},
        }

        try:
            response = mgr.process(question, context)
            status = response.get("status")
            data = response.get("data", {})

            # 提取回复内容
            summary = data.get("summary", "")
            details = data.get("details", {})
            agent_detail = details.get(agent_id, {})
            answer = agent_detail.get("answer", "")
            confidence = agent_detail.get("confidence", 0)
            simulated = agent_detail.get("simulated", False)
            evidence = agent_detail.get("evidence", [])

            print(f"\n  [{pid}] {tp['desc']}")
            print(f"  status={status}, confidence={confidence}, simulated={simulated}")
            print(f"  answer: {answer[:200]}...")

            model_results.append({
                "parcel_id": pid,
                "parcel_desc": tp["desc"],
                "question": question,
                "status": status,
                "answer": answer,
                "confidence": confidence,
                "simulated": simulated,
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                "summary": summary,
            })

        except Exception as e:
            print(f"\n  [{pid}] ERROR: {e}")
            model_results.append({
                "parcel_id": pid,
                "parcel_desc": tp["desc"],
                "question": question,
                "status": "error",
                "answer": f"执行失败: {e}",
                "confidence": 0,
                "simulated": True,
                "error": str(e),
            })

    all_results[agent_id] = {
        "model_name": model_name,
        "question_type": q_type,
        "results": model_results,
    }

db.session.remove()
ctx.pop()

# 生成 Markdown 报告
report_dir = _PROJECT_ROOT / "docs" / "superpowers" / "reports"
report_dir.mkdir(parents=True, exist_ok=True)
report_path = report_dir / "2026-08-18-dialogue-verification.md"

with open(report_path, "w", encoding="utf-8") as f:
    f.write("# 专题模型对话验证报告\n\n")
    f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write(f"**数据源**: PostgreSQL db_enterprise_qa (5488 个真实地块)\n\n")
    f.write(f"**测试地块**: {', '.join(tp['desc'] for tp in TEST_PARCELS)}\n\n")
    f.write("---\n\n")

    # 地块信息表
    f.write("## 测试地块信息\n\n")
    f.write("| parcel_id | 描述 | land_type | pH | 有机质 | 质地 | 灌溉 | 原始等级 |\n")
    f.write("|----------|------|-----------|-----|--------|------|------|---------|\n")
    for pid, info in parcel_infos.items():
        f.write(f"| {pid} | {info['desc']} | {info['land_type']} | "
                f"{info['soil_ph']:.2f} | {info['organic_matter']:.1f} | "
                f"{info['soil_texture']} | {info['irrigation_condition']} | "
                f"{info['quality_grade']} |\n")

    f.write("\n---\n\n")

    # 各模型对话结果
    for agent_id, model_data in all_results.items():
        f.write(f"## {agent_id} {model_data['model_name']}\n\n")
        f.write(f"**question_type**: {model_data['question_type']}\n\n")

        for r in model_data["results"]:
            f.write(f"### 地块 {r['parcel_id']} - {r['parcel_desc']}\n\n")
            f.write(f"**用户提问**: {r['question']}\n\n")
            f.write(f"**状态**: {r['status']} | ")
            f.write(f"**置信度**: {r.get('confidence', 0):.2f} | ")
            f.write(f"**降级**: {'是' if r.get('simulated') else '否'} | ")
            f.write(f"**证据数**: {r.get('evidence_count', 0)}\n\n")
            f.write(f"**回复内容**:\n\n")
            f.write(f"> {r.get('answer', '无回复')}\n\n")
            f.write("---\n\n")

    # 汇总
    f.write("## 验证汇总\n\n")
    f.write("| 模型 | 地块 | 状态 | 置信度 | 降级 |\n")
    f.write("|------|------|------|--------|------|\n")
    for agent_id, model_data in all_results.items():
        for r in model_data["results"]:
            f.write(f"| {agent_id} | {r['parcel_id']} | {r['status']} | "
                    f"{r.get('confidence', 0):.2f} | "
                    f"{'是' if r.get('simulated') else '否'} |\n")

    f.write("\n---\n")
    f.write("\n*报告由 verify_dialogue.py 自动生成*\n")

print(f"\n报告已保存: {report_path}")
