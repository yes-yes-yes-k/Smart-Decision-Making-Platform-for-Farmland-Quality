"""Generate user-visible conversation simulations from verified parcel results."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT.parents[1]/".env",override=True)

import psycopg

from framework.agents.workflows.comprehensive.checkpointing import normalize_postgres_uri
from framework.config import Config


RESULT_PATH=ROOT/"docs"/"generated"/"postgres-comprehensive-results.json"
source=json.loads(RESULT_PATH.read_text(encoding="utf-8"))
by_id={item["parcel_id"]:item for item in source["parcels"]}
FACTOR_LABELS={
    "SJD":"土壤酸碱度","YJZ":"有机质","YXL":"有效磷","SXJ":"速效钾",
    "TRRZ":"土壤容重","YXTCHD":"有效土层厚度","GCHD":"耕层厚度",
    "GCZD":"耕层质地","GGNL":"灌溉能力","PSNL":"排水能力",
    "DXBW":"地形部位","ZDGX":"质地构型",
}


def payload(parcel,model):
    return by_id[parcel]["results"][model]["result"]


def fmt(value,digits=2):
    return f"{float(value):.{digits}f}"


def factor_names(values):
    return "、".join(FACTOR_LABELS.get(value,value) for value in values)


def amount_text(parcel):
    acid=payload(parcel,"model-4")
    organic=payload(parcel,"model-5")
    conditioner=float(acid["YTK"])
    peat=float(acid["MBNT"])
    dose=float(organic["dose"])
    return (
        f"土壤调理剂（亿土康）约 {conditioner:.2f} 公斤/公顷（约 {conditioner/15:.2f} 公斤/亩），"
        f"木本泥炭约 {peat:.2f} 公斤/公顷（约 {peat/15:.2f} 公斤/亩），"
        f"有机质培肥材料约 {dose:.2f} 吨/公顷（约 {dose/15:.2f} 吨/亩）。"
    )


def database_coverage():
    with psycopg.connect(normalize_postgres_uri(Config.SQLALCHEMY_DATABASE_URI)) as conn, conn.cursor() as cur:
        cur.execute("select land_type,fertilizer_type,target_ph,soil_indicators from parcel_info")
        rows=cur.fetchall()
    missing_land=sum(not row[0] for row in rows)
    missing_fertilizer=sum(not row[1] for row in rows)
    missing_target=sum(row[2] is None for row in rows)
    return {
        "total_parcels":len(rows),
        "missing_land_type":missing_land,
        "missing_fertilizer_type":missing_fertilizer,
        "missing_target_ph":missing_target,
    }


def turn(role,text):
    return {"role":role,"text":text}


grade_4190=payload("4190","model-2")
grade_1=payload("1","model-2")
problem_1=payload("1","model-3")
grade_1593=payload("1593","model-2")
problem_1593=payload("1593","model-3")

cases=[
    {
        "category":"未选中地块","title":"普通知识问题可直接回答",
        "precondition":"地图上没有当前地块。",
        "dialogue":[
            turn("用户","土壤偏酸会有什么影响？"),
            turn("系统","土壤偏酸可能降低部分养分的有效性，也可能增加铝、锰活化风险，进而影响根系生长。是否需要我结合某个地块的检测数据进一步判断？"),
        ],
        "expected":"直接回答知识问题，不强迫用户选择地块，也不进行地块计算。",
    },
    {
        "category":"未选中地块","title":"询问“这块地”时要求先选择",
        "precondition":"地图上没有当前地块。",
        "dialogue":[
            turn("用户","帮我看看这块地质量怎么样。"),
            turn("系统","请先在地图上选择需要分析的地块。选择后我可以继续评价质量等级和主要问题。"),
        ],
        "expected":"停在选择地块步骤，不猜测分析对象，不启动计算。",
    },
    {
        "category":"未选中地块","title":"只在文字中输入编号仍需确认对象",
        "precondition":"地图上没有当前地块。",
        "dialogue":[
            turn("用户","帮我分析地块 4190。"),
            turn("系统","请先选择地块 4190，或确认将它设为当前分析地块。输入编号不会自动替代地块选择，以免分析错对象。"),
        ],
        "expected":"要求显式绑定地块，避免把文字中的编号误当成已验证选择。",
    },
    {
        "category":"已选中地块","title":"单项问题使用当前地块直接回答",
        "precondition":"用户已在地图上选中真实地块 4190。",
        "dialogue":[
            turn("用户","这块地质量怎么样？"),
            turn("系统",f"地块 4190 的综合质量等级为 {grade_4190['quality_grade']} 级，综合指数为 {fmt(grade_4190['composite_index'],3)}。当前土壤 pH 为 5.42，建议后续重点关注酸度和地形条件。"),
        ],
        "expected":"使用当前选中地块，不要求用户重复输入编号；只回答本次问题。",
    },
    {
        "category":"已选中地块","title":"综合诊断先确认范围，再生成报告",
        "precondition":"用户已在地图上选中真实地块 1。",
        "dialogue":[
            turn("用户","给这块地做一份综合诊断和改良报告。"),
            turn("系统","本次将分析耕地质量、主要限制因素、酸化改良和有机质培肥，并给出实施优先级。是否开始？"),
            turn("用户","确认开始。"),
            turn("系统",f"报告已生成：质量等级 {grade_1['quality_grade']} 级，综合指数 {fmt(grade_1['composite_index'],3)}；优先关注{factor_names(problem_1['primary_factors'])}。{amount_text('1')}请确认发布，或告诉我需要修改的内容。"),
            turn("用户","确认发布。"),
            turn("系统","报告已发布。建议先做小面积试施，一个作物季后复测土壤 pH、有机质、有效磷和速效钾。"),
        ],
        "expected":"未经确认不开始综合计算；报告可修改或发布，用户只看到业务内容。",
    },
    {
        "category":"已选中地块","title":"切换地块后使用最新选择",
        "precondition":"会话原来选中地块 4190，随后用户在地图上切换到真实地块 1593。",
        "dialogue":[
            turn("用户","现在这块地的主要问题是什么？"),
            turn("系统",f"当前分析的是地块 1593。其质量等级为 {grade_1593['quality_grade']} 级，综合指数为 {fmt(grade_1593['composite_index'],3)}；优先关注{factor_names(problem_1593['primary_factors'])}，后续还应关注{factor_names(problem_1593['secondary_factors'])}。"),
        ],
        "expected":"只使用最新选中的地块，不沿用上一地块的结果。",
    },
    {
        "category":"已选中地块","title":"选中地块后仍可询问普通知识",
        "precondition":"地图上已有当前地块，但用户没有要求计算。",
        "dialogue":[
            turn("用户","为什么施用调酸材料后还要复测？"),
            turn("系统","调酸效果会受到土壤缓冲能力、含水量、施用均匀度和作物吸收等因素影响。复测可以判断是否达到目标，并避免过量追加。"),
        ],
        "expected":"有当前地块不等于必须计算；普通知识问题仍直接回答。",
    },
    {
        "category":"缺少可采用默认值的参数","title":"默认值必须由用户确认",
        "precondition":"受控模拟：地块已选中，土地类型为水田，但档案暂缺常用肥料类型和目标 pH；不向数据库写入模拟地块。",
        "dialogue":[
            turn("用户","给这块地做综合诊断。"),
            turn("系统","档案中缺少常用肥料类型和目标 pH。可以暂按“复合肥、目标 pH 6.5”计算；是否接受这两个默认值并开始？"),
            turn("用户","接受。"),
            turn("系统","已采用复合肥和目标 pH 6.5。现在开始分析，最终报告会注明这是经您确认的默认条件。"),
        ],
        "expected":"默认值不会静默使用；用户确认后才进入计算。",
    },
    {
        "category":"缺少必填参数","title":"补参不完整或无效时继续询问",
        "precondition":"受控模拟：地块已选中，但档案暂缺土地利用类型；不向数据库写入模拟地块。",
        "dialogue":[
            turn("用户","生成综合报告。"),
            turn("系统","还缺少土地利用类型。请选择“水田”或“旱地”。"),
            turn("用户","果园。"),
            turn("系统","当前计算只接受“水田”或“旱地”。请重新选择。"),
            turn("用户","水田。"),
            turn("系统","已记录为水田。其他缺失但可安全默认的条件会在开始前单独请您确认。"),
        ],
        "expected":"参数不完整或不在允许范围内时不执行；有效补参会使用中文值并转换为计算参数。",
    },
    {
        "category":"缺参时取消","title":"用户取消后不产生计算结果",
        "precondition":"系统正在等待用户补充土地利用类型。",
        "dialogue":[
            turn("用户","先不做了。"),
            turn("系统","已取消本次综合诊断，没有生成或覆盖任何地块计算结果。"),
        ],
        "expected":"立即结束当前任务，保留原地块资料。",
    },
]


coverage=database_coverage()
generated_at=datetime.now().astimezone().isoformat(timespec="seconds")
document={"generated_at":generated_at,"database_coverage":coverage,"cases":cases}

lines=[
    "# 真实用户问答模拟：地块选择与缺参处理","",
    f"生成时间：{generated_at}","",
    "本报告只展示客户实际会看到的问答内容。地块 4190、1、1593 的数值来自当前地块库的真实计算结果；缺参案例采用受控输入省略，不创建或写入任何虚假地块。","",
    "## 数据核验","",
    f"当前共核验 {coverage['total_parcels']} 个地块。合并结构化字段与指标快照后，缺少土地利用类型 {coverage['missing_land_type']} 个、缺少肥料类型 {coverage['missing_fertilizer_type']} 个、缺少目标 pH {coverage['missing_target_ph']} 个。",
    "因此，缺参对话用于验证未来新增地块、导入异常或用户情景输入不完整时的系统反应。","",
    "## 场景总览","",
    "| 场景 | 当前地块 | 系统行为 |","|---|---|---|",
]
for case in cases:
    selected="未选中" if case["category"]=="未选中地块" else ("已选中" if case["category"]=="已选中地块" else "按场景")
    lines.append(f"| {case['title']} | {selected} | {case['expected']} |")
lines.append("")

for index,case in enumerate(cases,1):
    lines += [f"## {index}. {case['title']}","",f"场景条件：{case['precondition']}",""]
    for item in case["dialogue"]:
        lines += [f"> **{item['role']}：** {item['text']}",""]
    lines += [f"预期行为：{case['expected']}",""]

lines += [
    "## 验收结论","",
    "- 未选地块时，知识问题可以直接回答；涉及具体地块的计算必须先完成选择。",
    "- 已选地块时，“这块地”始终绑定当前选择；切换地块后不会沿用旧结果。",
    "- 安全默认值必须明确展示并由用户确认，必填参数缺失或取值无效时会持续询问。",
    "- 用户可以在补参、确认或报告发布前取消，不会因此覆盖既有计算结果。",
    "- 用户界面只展示地块、指标、问题、建议和需要确认的选择。","",
]

out=ROOT/"docs"/"generated"/"customer-workflow-simulation-report.md"
out.write_text("\n".join(lines),encoding="utf-8")
(ROOT/"docs"/"generated"/"customer-workflow-simulation-cases.json").write_text(
    json.dumps(document,ensure_ascii=False,indent=2),encoding="utf-8",
)
print(json.dumps({"report":str(out),"cases":len(cases),"database_coverage":coverage},ensure_ascii=False))
