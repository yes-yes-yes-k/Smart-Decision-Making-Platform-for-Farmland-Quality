"""用真实地块验证 5 个模型计算流程。每个模型挑 3 个地块。"""
import json
import os
import sys
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

app = create_app("default")
ctx = app.app_context()
ctx.push()

# 挑选 3 个真实地块（不同类型）
REAL_PARCELS = ["1", "2", "3"]  # TYBH=1(旱地), 2(水浇地), 3(水田)

# 显示地块信息
from framework.models.thematic_model import ParcelInfo, ParcelHistorySnapshot
print("=== 真实地块信息 ===")
for pid in REAL_PARCELS:
    p = ParcelInfo.query.filter_by(parcel_id=pid).first()
    if p:
        si = p.soil_indicators or {}
        history = ParcelHistorySnapshot.query.filter_by(parcel_id=pid).order_by("survey_year").all()
        print(f"\n  [{pid}] land_type={p.land_type}, area_code={p.area_code}")
        print(f"    pH={si.get('soil_ph')}, organic_matter={si.get('organic_matter')}, texture={si.get('soil_texture')}")
        print(f"    irrigation={si.get('irrigation_condition')}, drainage={si.get('drainage_capacity')}")
        print(f"    quality_grade={si.get('quality_grade')}, composite_index={si.get('composite_index')}")
        print(f"    history: {len(history)} 条 ({[h.survey_year for h in history]})")
        for h in history:
            hi = h.soil_indicators or {}
            print(f"      {h.survey_year}: pH={hi.get('soil_ph')}, grade={h.quality_grade}, index={h.composite_index}")

# 运行 5 个模型
from framework.agents.manager import AgentManager
mgr = AgentManager()

MODELS = [
    ("model-1", "稳定性风险评价"),
    ("model-2", "质量等级评价"),
    ("model-3", "障碍诊断"),
    ("model-4", "酸化改良"),
    ("model-5", "有机质培肥"),
]

results = {}
for agent_id, name in MODELS:
    print(f"\n{'='*60}")
    print(f"=== {agent_id} {name} ===")
    agent = mgr.agents.get(agent_id)
    for pid in REAL_PARCELS:
        try:
            r = agent.execute({"parcel_id": pid})
            status = r.get("status")
            ds = r.get("data_source")
            persisted = r.get("persisted")
            result = r.get("result", {})

            # 提取关键结果
            key_data = {}
            if agent_id == "model-1":
                for k in ["module_1", "module_2", "module_3", "module_4", "module_5", "module_8"]:
                    v = result.get(k, {})
                    if isinstance(v, dict):
                        key_data[k] = {kk: vv for kk, vv in v.items() if vv is not None}
            elif agent_id == "model-2":
                key_data = {
                    "quality_grade": result.get("quality_grade"),
                    "composite_index": round(result.get("composite_index", 0), 4),
                }
            elif agent_id == "model-3":
                key_data = {
                    "obstacle_type": result.get("obstacle_type"),
                    "primary_factors": result.get("primary_factors"),
                }
            elif agent_id == "model-4":
                key_data = {
                    "YTK": round(result.get("YTK", 0), 2),
                    "MBNT": round(result.get("MBNT", 0), 2),
                }
            elif agent_id == "model-5":
                key_data = {
                    "dose": round(result.get("dose", 0), 2),
                    "simulated": result.get("simulated"),
                }

            print(f"  [{pid}] status={status} db={ds} persisted={persisted}")
            print(f"       {key_data}")
            results.setdefault(agent_id, {})[pid] = {
                "status": status,
                "data_source": ds,
                "persisted": persisted,
                "key_result": key_data,
            }
        except Exception as e:
            print(f"  [{pid}] ERROR: {e}")
            results.setdefault(agent_id, {})[pid] = {"status": "error", "error": str(e)}

# 结果表行数
print(f"\n{'='*60}")
print("=== 结果表行数 ===")
tables = [
    "stability_risk_result", "quality_grade_result", "obstacle_diagnosis_result",
    "acidification_remediation_result", "organic_matter_result",
]
for t in tables:
    count = db.session.execute(db.text(f"SELECT COUNT(*) FROM {t}")).scalar()
    print(f"  {t}: {count}")

db.session.remove()
ctx.pop()

# 保存报告
report_path = _PROJECT_ROOT / "docs" / "superpowers" / "reports" / "2026-08-18-real-parcels-verify.json"
report_path.parent.mkdir(parents=True, exist_ok=True)
with open(report_path, "w", encoding="utf-8") as f:
    json.dump({"real_parcels": REAL_PARCELS, "results": results}, f, ensure_ascii=False, indent=2, default=str)
print(f"\n报告已保存: {report_path}")
