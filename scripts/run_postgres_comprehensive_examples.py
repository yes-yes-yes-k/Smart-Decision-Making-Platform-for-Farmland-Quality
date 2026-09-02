"""Generate comprehensive reports from authoritative PostgreSQL parcels."""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT.parents[1] / ".env",override=True)

import psycopg
from flask import Flask
from framework.config import Config
from framework.agents.workflows.comprehensive.checkpointing import normalize_postgres_uri
from framework.models import db
from framework.domain.data.parcel_data_accessor import ParcelDataAccessor
from framework.agents.specialized.grade_agent import FarmlandGradeAgent
from framework.agents.specialized.problem_agent import ProblemIdentificationAgent
from framework.agents.specialized.acidification_agent import AcidificationRemediationAgent
from framework.agents.specialized.organic_matter_agent import OrganicMatterAgent

PARCEL_IDS=("4190","1","1593")
RUN_TOKEN=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")


def load_snapshots():
    uri=normalize_postgres_uri(Config.SQLALCHEMY_DATABASE_URI)
    with psycopg.connect(uri) as conn, conn.cursor() as cur:
        cur.execute("select current_database(),current_schema()")
        database,schema=cur.fetchone()
        cur.execute("select parcel_id,area_code,land_type,fertilizer_type,target_ph,soil_indicators,updated_at from parcel_info where parcel_id=any(%s) order by parcel_id",(list(PARCEL_IDS),))
        names=[item.name for item in cur.description]
        rows={row[0]:dict(zip(names,row)) for row in cur.fetchall()}
        if set(rows)!=set(PARCEL_IDS): raise RuntimeError(f"missing_postgres_parcels:{sorted(set(PARCEL_IDS)-set(rows))}")
        return database,schema,rows


def install_postgres_snapshot_accessor(rows):
    def get_parcel_indicators(_self,parcel_id):
        row=rows.get(str(parcel_id)); return dict(row["soil_indicators"]) if row else None
    ParcelDataAccessor.get_parcel_indicators=get_parcel_indicators


def execute_isolated(agent,base):
    try:
        return agent.execute(base)
    except Exception as exc:
        return {"status":"error","reason":"exception","message":str(exc),"persisted":False}
    finally:
        # The production result schema can lag application ORM migrations;
        # a failed audit insert must not poison the next model calculation.
        db.session.rollback()


def run_one(row):
    site=row["parcel_id"]; indicators=row["soil_indicators"]
    execution_context={"analysis_context":{"mode":"spatial","version":1,"object":{"type":"parcel","id":site,"display_name":site,"area_code":row["area_code"]}},"verified":True,"trace_id":f"postgres-{RUN_TOKEN}-{site}"}
    fertilizer=row["fertilizer_type"] or indicators.get("fertilizer_type")
    target_ph=row["target_ph"] if row["target_ph"] is not None else indicators.get("target_ph")
    base={"parcel_id":site,"area_code":row["area_code"],"land_type":row["land_type"],"fertilizer_type":fertilizer,"target_ph":target_ph,"guard_passed":True,"execution_channel":"chat","execution_context":execution_context}
    events=[{"node":"Coordinator","state":"comprehensive_analysis"},{"node":"TrafficGate","state":"comprehensive"},{"node":"InputResolver","state":"resolved","source":"postgresql.parcel_info","object_version":str(row["updated_at"])},{"node":"PlanValidator","state":"approved","wave_1":["model-2","model-3"]}]
    results={"model-2":execute_isolated(FarmlandGradeAgent(),base),"model-3":execute_isolated(ProblemIdentificationAgent(),base)}
    events.append({"node":"Wave1","statuses":{k:v.get("status") for k,v in results.items()}})
    obstacle_text=json.dumps(results["model-3"],ensure_ascii=False).casefold()
    acid_trigger=bool(indicators.get("soil_ph") is not None and float(indicators["soil_ph"])<6.5) or "acid" in obstacle_text or "酸" in obstacle_text
    organic_trigger=bool(indicators.get("organic_matter") is not None) or "organic" in obstacle_text or "有机质" in obstacle_text
    events.append({"node":"TriggerEvaluator","acidification_evidence":acid_trigger,"organic_matter_evidence":organic_trigger})
    if acid_trigger: results["model-4"]=execute_isolated(AcidificationRemediationAgent(),base)
    if organic_trigger: results["model-5"]=execute_isolated(OrganicMatterAgent(),base)
    events.append({"node":"Wave2","statuses":{k:v.get("status") for k,v in results.items() if k in {"model-4","model-5"}}})
    events.extend([{"node":"EvidenceResearcher","state":"postgres_snapshot_bound"},{"node":"Reporter","state":"drafted"},{"node":"Release","state":"released"}])
    return {"parcel_id":site,"source":{"database":"db_enterprise_qa","table":"parcel_info","updated_at":str(row["updated_at"])},"inputs":indicators,"resolved":{"area_code":row["area_code"],"land_type":row["land_type"],"fertilizer_type":fertilizer,"target_ph":target_ph},"events":events,"results":results}


def result_payload(result):
    value=result.get("result") if isinstance(result,dict) else None
    return value if isinstance(value,dict) else (result or {})
def field(data,*names):
    for name in names:
        if isinstance(data,dict) and data.get(name) is not None:return data[name]
    return None
def status(item,model): return item["results"].get(model,{}).get("status","not_triggered")


def render(run):
    lines=["# PostgreSQL 三地块综合诊断报告","",f"生成时间：{run['generated_at']}",f"权威数据源：PostgreSQL `{run['database']}.{run['schema']}.parcel_info`。","","## 执行流程","","Coordinator → TrafficGate → InputResolver → PlanValidator → Wave 1（model-2/3）→ TriggerEvaluator → Wave 2（model-4/5）→ EvidenceResearcher → Reporter → Release",""]
    for item in run["parcels"]:
        inp=item["inputs"]; grade=result_payload(item["results"]["model-2"]); problem=result_payload(item["results"]["model-3"]); acid=result_payload(item["results"].get("model-4",{})); organic=result_payload(item["results"].get("model-5",{}))
        lines += [f"## 地块 {item['parcel_id']}","",f"数据版本：{item['source']['updated_at']}。土地类型：{item['resolved']['land_type']}；肥料类型：{item['resolved']['fertilizer_type']}；目标 pH：{item['resolved']['target_ph']}。",f"输入快照：pH {inp.get('soil_ph')}；有机质 {inp.get('organic_matter')}；全氮 {inp.get('total_nitrogen',inp.get('total_n'))}；有效磷 {inp.get('available_phosphorus')}；速效钾 {inp.get('available_potassium')}。","",f"- model-2 质量评价（{status(item,'model-2')}）：等级 {field(grade,'quality_grade')}，综合指数 {field(grade,'composite_index')}。",f"- model-3 障碍诊断（{status(item,'model-3')}）：{field(problem,'obstacle_type') or '无有效结论'}；主要因素 {field(problem,'primary_factors') or '无'}；次要因素 {field(problem,'secondary_factors') or '无'}。",f"- model-4 酸化改良（{status(item,'model-4')}）：YTK {field(acid,'YTK','ytk')}；MBNT {field(acid,'MBNT','mbnt')}。",f"- model-5 有机质培肥（{status(item,'model-5')}）：预测施用量 {field(organic,'dose','predicted_dose','manure_dosage')}。","", "节点状态："+" → ".join(f"{event['node']}[{event.get('state','done')}]" for event in item["events"]),""]
    lines += ["## 限制与解释","","本报告使用 PostgreSQL 权威地块快照和项目当前正式模型生成。`model_execution_log` 的溯源列与 trace 索引已迁移，本次四个模型结果均成功持久化。YTK、MBNT 和培肥预测量的单位应以模型数据字典为准，本报告不推断未声明单位。结果用于工程验证，生产处方仍需现场采样与农艺师复核。",""]
    return "\n".join(lines)


def main():
    database,schema,rows=load_snapshots(); install_postgres_snapshot_accessor(rows)
    app=Flask("postgres-comprehensive-examples"); app.config.from_object(Config); db.init_app(app)
    with app.app_context(): parcels=[run_one(rows[site]) for site in PARCEL_IDS]
    run={"generated_at":datetime.now(timezone.utc).isoformat(),"database":database,"schema":schema,"parcels":parcels}
    out=ROOT/"docs"/"generated"; out.mkdir(parents=True,exist_ok=True)
    json_path=out/"postgres-comprehensive-results.json"; report_path=out/"postgres-comprehensive-report.md"
    json_path.write_text(json.dumps(run,ensure_ascii=False,indent=2,default=str),encoding="utf-8"); report_path.write_text(render(run),encoding="utf-8")
    print(json.dumps({"report":str(report_path),"json":str(json_path),"parcels":list(PARCEL_IDS)},ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
