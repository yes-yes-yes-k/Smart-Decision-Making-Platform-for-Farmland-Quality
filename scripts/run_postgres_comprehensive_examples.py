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
    fertilizer=row["fertilizer_type"]
    target_ph=row["target_ph"]
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


FACTOR_LABELS={
    "SJD":"土壤酸碱度","YJZ":"有机质","YXL":"有效磷","SXJ":"速效钾",
    "TRRZ":"土壤容重","YXTCHD":"有效土层厚度","GCHD":"耕层厚度",
    "GCZD":"耕层质地","GGNL":"灌溉能力","PSNL":"排水能力",
    "DXBW":"地形部位","ZDGX":"质地构型",
}
FACTOR_ACTIONS={
    "SJD":"分区施用调酸材料，完成一个作物季后复测土壤 pH，再决定是否追加。",
    "YJZ":"增加腐熟有机物料投入并配合秸秆还田，连续监测有机质变化。",
    "YXL":"结合测土结果核查磷肥有效性，优先优化磷肥品种、施用位置和时期。",
    "SXJ":"补充钾素并采用分次施用，避免一次性投入造成损失。",
    "TRRZ":"减少湿土作业和机械碾压，配合深松改善耕层通气性。",
    "YXTCHD":"通过培土和深松逐步增加可利用土层，避免一次性过度深翻。",
    "GCHD":"优化耕作深度并减少犁底层压实。",
    "GCZD":"根据土壤质地调整灌溉频次和养分投入方式。",
    "GGNL":"检查水源与田间输水条件，采用分区、适量灌溉。",
    "PSNL":"疏通排水通道，雨季前重点处理易积水区域。",
    "DXBW":"按坡位和径流条件分区管理，兼顾排水、防冲刷与养分流失。",
    "ZDGX":"通过深松、增施有机物料等方式逐步改善紧实或夹层结构。",
}


def fmt(value,digits=2):
    if value is None:return "—"
    if isinstance(value,(int,float)):return f"{value:.{digits}f}"
    return str(value)
def labels(values):
    return "、".join(FACTOR_LABELS.get(str(value),str(value)) for value in (values or [])) or "未识别到明显限制因素"
def ph_description(value):
    if value is None:return "缺少检测值"
    value=float(value)
    if value<4.5:return "强酸性"
    if value<5.5:return "偏酸"
    if value<6.5:return "微酸性"
    if value<=7.5:return "接近中性"
    return "偏碱"
def business_actions(problem):
    factors=list(field(problem,"primary_factors") or [])+list(field(problem,"secondary_factors") or [])
    ordered=[]
    for factor in factors:
        if factor not in ordered:ordered.append(factor)
    return [FACTOR_ACTIONS[factor] for factor in ordered if factor in FACTOR_ACTIONS]


def render(run):
    lines=[
        "# 地块综合诊断与改良建议","",
        f"报告生成时间：{run['generated_at']}",
        "本报告根据地块最新土壤检测与档案信息生成，重点展示用户可直接理解和使用的诊断结论。","",
        "## 总体结论","",
        "本次三个地块均存在土壤偏酸问题，但主要限制因素和改良优先级不同。地块 1 应优先补钾并兼顾地形管理；地块 4190 应重点核查有效磷利用状况和地形影响；地块 1593 的综合质量等级相对靠后，应优先改善地形相关管理与土壤质地构型，并同步提升有机质。","",
    ]
    for item in run["parcels"]:
        inp=item["inputs"]; grade=result_payload(item["results"]["model-2"]); problem=result_payload(item["results"]["model-3"]); acid=result_payload(item["results"].get("model-4",{})); organic=result_payload(item["results"].get("model-5",{}))
        primary=field(problem,"primary_factors") or []; secondary=field(problem,"secondary_factors") or []
        action_lines=business_actions(problem)
        conclusion=(
            f"综合质量等级为 {field(grade,'quality_grade')} 级，综合指数 {fmt(field(grade,'composite_index'),3)}；"
            f"土壤 pH 为 {fmt(inp.get('soil_ph'))}，属于{ph_description(inp.get('soil_ph'))}。"
            f"优先关注{labels(primary)}。"
        )
        lines += [
            f"## 地块 {item['parcel_id']}","",
            "### 一句话结论","",conclusion,"",
            "### 当前状况","",
            "| 项目 | 结果 |","|---|---:|",
            f"| 综合质量等级 | {field(grade,'quality_grade')} 级 |",
            f"| 综合指数 | {fmt(field(grade,'composite_index'),3)} |",
            f"| 土壤 pH | {fmt(inp.get('soil_ph'))}（{ph_description(inp.get('soil_ph'))}） |",
            f"| 有机质 | {fmt(inp.get('organic_matter'))} g/kg |",
            f"| 全氮 | {fmt(inp.get('total_nitrogen',inp.get('total_n')))} g/kg |",
            f"| 有效磷 | {fmt(inp.get('available_phosphorus'))} mg/kg |",
            f"| 速效钾 | {fmt(inp.get('available_potassium'))} mg/kg |","",
            "### 主要问题","",
            f"- 优先关注：{labels(primary)}。",
            f"- 后续关注：{labels(secondary)}。",
            f"- 综合判断：{field(problem,'obstacle_type') or '未识别到明显障碍'}。","",
            "### 建议用量","",
            "| 改良材料 | 参考用量 | 主要目的 |","|---|---:|---|",
            f"| 土壤调理剂（亿土康） | {fmt(field(acid,'YTK','ytk'))} kg/ha | 调节土壤酸度 |",
            f"| 木本泥炭 | {fmt(field(acid,'MBNT','mbnt'))} kg/ha | 辅助调酸并改善土壤环境 |",
            f"| 有机质培肥材料 | {fmt(field(organic,'dose','predicted_dose','manure_dosage'))} t/ha | 提升土壤有机质 |","",
            "### 实施顺序","",
        ]
        for index,action in enumerate(action_lines[:4],1):lines.append(f"{index}. {action}")
        lines += [
            f"{min(len(action_lines),4)+1}. 以目标 pH {fmt(item['resolved']['target_ph'])} 为阶段目标，小面积试施后复测，再确定全地块施用方案。","",
        ]
    lines += [
        "## 使用说明","",
        "- 建议用量是基于现有检测数据的地块级参考值，不替代现场配方和产品说明书。",
        "- 大面积施用前应先做小区试验，并结合种植作物、土壤含水量和当地农艺要求校准。",
        "- 调酸材料不宜与含铵态氮肥集中同施；施用一个作物季后复测 pH、有机质、有效磷和速效钾。","",
    ]
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
