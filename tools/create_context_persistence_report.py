from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


OUTPUT = Path(r"D:\17417\Documents\agent_culti_demo\outputs\上下文持久化问题解决方案汇报.docx")

NAVY = "17365D"
BLUE = "2F75B5"
LIGHT_BLUE = "D9EAF7"
PALE_BLUE = "F3F7FB"
LIGHT_GRAY = "F2F2F2"
BORDER = "D9D9D9"
TEXT = RGBColor(31, 31, 31)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=110, start=120, bottom=110, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color=BORDER, size="6"):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def prevent_row_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run("第 ")
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, end])
    paragraph.add_run(" 页")


def add_heading(doc, text, level=1):
    p = doc.add_paragraph(text, style=f"Heading {level}")
    keep_with_next(p)
    return p


def add_body(doc, text, bold_lead=None):
    p = doc.add_paragraph(style="Body Text")
    if bold_lead and text.startswith(bold_lead):
        p.add_run(bold_lead).bold = True
        p.add_run(text[len(bold_lead):])
    else:
        p.add_run(text)
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(item, style="List Bullet")
        p.paragraph_format.space_after = Pt(3)


def add_table(doc, headers, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    header = table.rows[0]
    set_repeat_table_header(header)
    prevent_row_split(header)
    for idx, text in enumerate(headers):
        cell = header.cells[idx]
        set_cell_shading(cell, NAVY)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        set_cell_margins(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)
        r.font.size = Pt(9.5)
        if widths:
            cell.width = Cm(widths[idx])
    for row_index, values in enumerate(rows):
        row = table.add_row()
        prevent_row_split(row)
        cells = row.cells
        for idx, value in enumerate(values):
            cell = cells[idx]
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index % 2 == 1:
                set_cell_shading(cell, PALE_BLUE)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(value))
            r.font.size = Pt(9.2)
            if widths:
                cell.width = Cm(widths[idx])
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return table


def add_flow(doc):
    labels = [
        ("请求入口", "HTTP 与 SSE 共用服务"),
        ("上下文解析", "继承 设置 清除 情景试算"),
        ("对象验证", "存在性 类型 权限 版本"),
        ("中央守卫", "能力与对象尺度匹配"),
        ("模型执行", "只使用验证后的标识"),
        ("统一落库", "消息快照 执行快照 溯源"),
    ]
    table = doc.add_table(rows=1, cols=len(labels) * 2 - 1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_repeat_table_header(table.rows[0])
    prevent_row_split(table.rows[0])
    for i, (title, subtitle) in enumerate(labels):
        cell = table.rows[0].cells[i * 2]
        set_cell_shading(cell, LIGHT_BLUE if i not in (2, 3) else "BDD7EE")
        set_cell_margins(cell, 150, 60, 150, 60)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title + "\n")
        r.bold = True
        r.font.size = Pt(9)
        r2 = p.add_run(subtitle)
        r2.font.size = Pt(7.5)
        cell.width = Cm(2.25)
        if i < len(labels) - 1:
            arrow = table.rows[0].cells[i * 2 + 1]
            arrow.width = Cm(0.30)
            arrow.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            ar = arrow.paragraphs[0].add_run("→")
            ar.bold = True
            ar.font.size = Pt(13)
            ar.font.color.rgb = RGBColor(47, 117, 181)
    return table


doc = Document()
section = doc.sections[0]
section.top_margin = Cm(2.0)
section.bottom_margin = Cm(1.8)
section.left_margin = Cm(2.2)
section.right_margin = Cm(2.2)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Microsoft YaHei"
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
normal.font.size = Pt(10.5)
normal.font.color.rgb = TEXT
normal.paragraph_format.line_spacing = 1.35
normal.paragraph_format.space_after = Pt(6)

for style_name in ("Body Text", "List Bullet"):
    style = styles[style_name]
    style.font.name = "Microsoft YaHei"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(10.5)
    style.font.color.rgb = TEXT
    style.paragraph_format.line_spacing = 1.3
    style.paragraph_format.space_after = Pt(6)

title_style = styles["Title"]
title_style.font.name = "Microsoft YaHei"
title_style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
title_style.font.size = Pt(28)
title_style.font.bold = True
title_style.font.color.rgb = RGBColor(0, 0, 0)
title_style.paragraph_format.space_after = Pt(14)
title_ppr = title_style._element.get_or_add_pPr()
title_border = title_ppr.find(qn("w:pBdr"))
if title_border is not None:
    title_ppr.remove(title_border)

for name, size in (("Heading 1", 17), ("Heading 2", 12.5)):
    style = styles[name]
    style.font.name = "Microsoft YaHei"
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    style.font.size = Pt(size)
    style.font.bold = True
    style.font.color.rgb = RGBColor(0, 0, 0)
    style.paragraph_format.space_before = Pt(12 if name == "Heading 1" else 8)
    style.paragraph_format.space_after = Pt(6)

footer = section.footer
add_page_number(footer.paragraphs[0])
footer.paragraphs[0].runs[0].font.size = Pt(8.5)
footer.paragraphs[0].runs[0].font.color.rgb = RGBColor(100, 100, 100)

# Cover
p = doc.add_paragraph(style="Title")
p.alignment = WD_ALIGN_PARAGRAPH.LEFT
p.add_run("聊天分析上下文持久化解决方案")
sub = doc.add_paragraph()
sub.paragraph_format.space_after = Pt(24)
r = sub.add_run("问题七后端方案汇报")
r.font.size = Pt(15)
r.font.bold = True
r.font.color.rgb = RGBColor(47, 117, 181)

add_body(doc, "本方案解决聊天过程中空间分析对象丢失、连续追问语义漂移以及模型结果无法准确追溯的问题。后端把省、市、县、片区和地块统一抽象为分析对象，并采用会话当前状态、消息不可变快照和模型执行快照三层持久化。")
add_body(doc, "核心结论是：交互状态保存在会话中，历史语义固化在消息中，运行与统计证据保存在执行日志中。模型只能接收经过后端验证的对象标识，响应、消息与执行记录使用同一上下文版本和 trace_id。")

add_heading(doc, "汇报结论", 1)
add_bullets(doc, [
    "连续追问可以继承已选分析对象，前端刷新或漏传对象时不会立即丢失上下文。",
    "对象切换使用版本控制，避免多个页面或并发请求互相覆盖。",
    "每条历史消息保留创建时的上下文快照，后续切换对象不会改写旧消息含义。",
    "模型执行日志同时保存可索引字段和完整快照，可按行政级别 模型 时间和状态汇总。",
    "HTTP 与 SSE 共用同一服务，错误映射 持久化和响应结构保持一致。",
])

add_heading(doc, "实施结果", 1)
add_table(doc, ["项目", "结果"], [
    ["OpenSpec", "add-chat-analysis-object-context 严格校验通过"],
    ["完整回归", "917 项通过 22 项跳过"],
    ["关键链路", "HTTP SSE 消息快照 执行日志 溯源与统计均覆盖"],
], [4.0, 12.3])

doc.add_page_break()

add_heading(doc, "问题与设计目标", 1)
add_heading(doc, "原有问题", 2)
add_body(doc, "原有聊天请求主要依赖前端在每次调用时传入 parcel_id 或 area_code。连续追问、页面刷新和多端操作时，这些字段可能缺失或相互矛盾。模型即使返回结果，系统也难以回答当时分析的是哪个对象、使用了哪个版本、输入来自哪里。")
add_table(doc, ["问题", "直接影响", "后端要求"], [
    ["对象容易丢失", "追问失去空间语义", "会话保存规范化当前对象"],
    ["对象可能被伪造或越权", "错误数据进入专业模型", "执行前校验存在性 类型和权限"],
    ["历史消息随当前对象变化", "无法复盘当时语义", "消息保存不可变上下文快照"],
    ["多模型各自产生追踪号", "同一请求难以串联", "编排器生成并贯穿同一 trace_id"],
    ["JSON 难以高效统计", "多级统计查询成本高", "常用维度同步写入关系型列"],
], [3.2, 6.0, 7.1])

add_heading(doc, "设计边界", 2)
add_body(doc, "本阶段完成后端通用空间对象、上下文生命周期、模型执行守卫、快照持久化、结果溯源和运行统计接口。不包含前端对象选择器、完整行政区目录导入和统计报表页面。")

doc.add_page_break()
add_heading(doc, "总体数据流", 1)
add_flow(doc)
add_body(doc, "请求先进入统一 ChatRequestService。服务解析本次动作并合并会话状态，只有对象验证成功后才更新会话。中央守卫根据问题类型和专业能力检查空间尺度，随后模型使用验证后的标识执行。完成后，用户消息、助手消息、响应溯源和执行日志共享同一版本与 trace_id。")

add_heading(doc, "通用空间对象模型", 1)
add_body(doc, "AnalysisObject 以 type 和 id 表示空间对象，并可携带 area_code、display_name 和 properties。type 支持 province、city、county、zone 和 parcel。模型能力声明自己支持的对象类型，后端守卫据此决定是否可以执行。")
add_table(doc, ["字段", "用途", "示例"], [
    ["type", "对象空间级别", "county"],
    ["id", "后端规范标识", "440281"],
    ["area_code", "行政区统计和筛选", "440281"],
    ["display_name", "响应中的可读名称", "乐昌市"],
    ["properties", "按类型扩展的非核心属性", "边界版本 数据源"],
], [3.0, 7.0, 6.3])

action_heading = add_heading(doc, "上下文动作", 2)
action_heading.paragraph_format.page_break_before = True
add_table(doc, ["动作", "行为", "版本变化"], [
    ["inherit", "沿用会话当前对象", "不变"],
    ["set", "验证后设置新对象", "加一"],
    ["clear", "清除当前空间对象", "加一"],
    ["scenario", "使用显式输入试算 不绑定空间对象", "会话对象不变"],
], [3.0, 9.5, 3.8])

add_heading(doc, "并发控制", 2)
add_body(doc, "客户端提交 expected_version，后端通过条件更新执行乐观锁。若会话版本已经变化，接口返回 HTTP 409，并提供最新版本和对象。新对象只有在完整验证成功后才落库，因此 422 和 503 不会破坏原有上下文。")

add_heading(doc, "中央执行守卫", 2)
add_body(doc, "专业模型不会直接消费请求中的原始 parcel_id 或 area_code。解析服务先生成 verified identifiers，守卫再检查当前能力是否支持该对象类型。对象不足时返回可恢复交互状态，不调用工具、专业模型或总结 LLM，也不产生模型执行日志。")

add_heading(doc, "三层持久化设计", 1)
add_table(doc, ["层级", "保存内容", "主要用途", "是否可变"], [
    ["会话", "analysis_object context_version updated_at", "连续追问和当前选择", "当前状态可变"],
    ["消息", "analysis_context_snapshot", "固定每条消息创建时的语义", "创建后不变"],
    ["执行日志", "对象字段 输入 输出 模型版本 数据时间 trace_id", "审计 追溯 运行统计", "创建后不变"],
], [2.5, 5.5, 5.4, 2.9])

add_heading(doc, "为什么不只保存会话 JSON", 2)
add_body(doc, "会话 JSON 适合扩展对象类型，但它只表示当前交互状态。用户从地块 A 切换到地块 B 后，如果历史消息仍读取会话当前 JSON，旧结果会被误认为属于地块 B。因此，消息和执行日志必须保存独立快照。")

add_heading(doc, "消息快照", 2)
add_body(doc, "用户消息在模型执行前保存解析后的上下文快照。助手消息在执行完成后保存同一对象版本，并补充 trace_id 和 provenance。使用深拷贝避免后续字典修改污染已经准备好的快照。")

add_heading(doc, "执行快照", 2)
add_body(doc, "model_execution_log 保存 analysis_object_type、analysis_object_id、area_code、context_version、user_id、conversation_id 和 trace_id 等关系型列，同时保存 analysis_context_snapshot、input_params 和 output_result。关系型列服务于筛选和分组，JSON 保存完整证据。")

add_heading(doc, "统一追溯", 2)
add_body(doc, "ResultProvenanceBuilder 从已验证上下文和实际模型执行生成 model_id、model_version、data_as_of、data_version、calculated_at、key_inputs 和 trace_id。LLM 只负责文字总结，不能生成或覆盖这些结构化字段。")

doc.add_page_break()

add_heading(doc, "接口行为与异常保护", 1)
add_body(doc, "空间对象不足属于可恢复的交互状态，不应被当作服务器故障。非法对象、并发版本冲突和验证依赖不可用则返回稳定的 HTTP 错误码。所有拒绝路径都在模型执行前结束。")
add_table(doc, ["场景", "HTTP", "状态或错误码", "保存消息", "调用模型"], [
    ["上下文完整", "200", "completed", "是", "是"],
    ["缺少空间对象", "200", "needs_analysis_object", "是", "否"],
    ["缺少情景输入", "200", "needs_scenario_inputs", "是", "否"],
    ["对象不存在 类型错误或越权", "422", "analysis_object_invalid", "否", "否"],
    ["版本冲突", "409", "analysis_context_conflict", "否", "否"],
    ["验证依赖不可用", "503", "analysis_object_validation_unavailable", "否", "否"],
], [4.7, 1.6, 5.6, 2.2, 2.2])

add_heading(doc, "HTTP 与 SSE 一致性", 2)
add_body(doc, "非流式和流式聊天都调用同一 prepare、persist_assistant 和 build_response 流程。SSE 只改变传输方式，完成事件仍使用同一上下文快照、响应字段和持久化逻辑，并在应用上下文中安全提交数据库事务。")

add_heading(doc, "旧字段兼容", 2)
add_body(doc, "过渡期仍接收旧 parcel_id、parcel_code 和 area_code，但这些值必须经过相同验证，不能直接进入专业模型。系统记录旧字段使用量，便于评估客户端迁移进度。新客户端统一使用 analysis_context。")

doc.add_page_break()

add_heading(doc, "多级统计能力", 1)
add_body(doc, "方案可以支持省、市、县、片区和地块级统计，但统计对象需要区分业务指标和运行指标。会话当前 JSON 不参与事实统计，避免对象切换造成口径漂移。")
add_table(doc, ["统计类型", "事实来源", "典型维度", "典型指标"], [
    ["业务统计", "parcel_info 与专题结果表", "行政区 空间对象 时间", "等级分布 平均指标 障碍因素"],
    ["运行统计", "model_execution_log", "对象类型 area_code 模型 状态 时间", "调用次数 成功率 降级率"],
    ["交互监控", "analysis context 事件", "错误码 旧字段 请求状态", "待选对象比例 409 422 503 次数"],
], [3.0, 5.0, 5.0, 3.3])

add_heading(doc, "已有统计接口", 2)
add_body(doc, "query_execution_statistics 支持按 object_type、area_code、model_id、status、started_from 和 started_to 过滤，并按对象类型、区域、模型和状态聚合。dashboard 同时返回上下文交互指标、执行统计和 Schema 指标。")

add_heading(doc, "统计扩展条件", 2)
add_bullets(doc, [
    "行政区对象应维护稳定编码和父子关系，才能可靠上卷到省市县级。",
    "片区和地块需要映射到所属行政区，执行日志应写入标准 area_code。",
    "业务统计必须基于专题结果事实表，不应把聊天次数当作耕地质量结论。",
    "后续统计页面只需消费聚合接口，无需解析会话 JSON。",
])

add_heading(doc, "监控指标", 2)
add_table(doc, ["指标", "反映的问题"], [
    ["needs_analysis_object", "前端对象选择和会话继承是否顺畅"],
    ["needs_scenario_inputs", "情景试算输入是否完整"],
    ["HTTP 422", "无效 越权或类型不匹配对象"],
    ["HTTP 409", "并发切换和客户端版本刷新问题"],
    ["HTTP 503", "对象验证依赖可用性"],
    ["legacy_field_used", "旧客户端迁移进度"],
], [4.3, 12.0])

add_heading(doc, "验证与交付情况", 1)
add_body(doc, "实现按 OpenSpec 任务逐项完成并审核。合并最新 master 后，针对 Schema 2.0、上下文快照、HTTP 与 SSE 一致性、执行守卫、溯源、统计和模型集成进行了专项验证，并执行完整回归。")
add_table(doc, ["验证项", "结果", "覆盖重点"], [
    ["OpenSpec 严格校验", "通过", "需求 设计 规格和任务一致"],
    ["专项回归", "77 项通过", "冲突相关 HTTP SSE Schema 2.0 溯源与统计"],
    ["完整回归", "917 项通过 22 项跳过", "项目全量功能"],
    ["OpenAPI JSON", "通过", "接口文档可解析"],
    ["迁移往返", "通过", "数据库升级与回退"],
], [4.1, 4.2, 8.0])

add_heading(doc, "关键风险与控制", 1)
add_table(doc, ["风险", "控制措施"], [
    ["前端漏传对象", "优先继承会话当前对象 对象不足时返回可恢复状态"],
    ["并发覆盖", "expected_version 乐观锁 冲突返回最新上下文"],
    ["越权或伪造标识", "后端验证后生成 verified identifiers"],
    ["历史语义漂移", "每条消息保存不可变上下文快照"],
    ["统计扫描 JSON 性能差", "常用维度同步写入执行日志关系型列"],
    ["LLM 改写溯源", "结构化 provenance 由后端生成 LLM 只处理正文"],
], [5.2, 11.1])

add_heading(doc, "后续工作", 1)
add_bullets(doc, [
    "补齐完整行政区目录、父子关系和地块归属映射。",
    "建设前端通用空间对象选择器，并按 interaction_state 引导用户。",
    "基于现有执行统计接口建设省市县片区地块多级看板。",
    "持续监控旧字段使用量，完成兼容字段下线计划。",
])

add_heading(doc, "建议汇报顺序", 1)
add_body(doc, "建议先说明上下文丢失会导致模型结果对象不明确，再展示总体数据流和三层持久化。随后说明中央守卫如何阻断无效执行，以及关系型索引如何支持多级统计。最后用完整回归和 OpenSpec 校验结果收束，明确后续只需补齐行政区数据和前端展示。")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
doc.core_properties.title = "聊天分析上下文持久化解决方案"
doc.core_properties.subject = "问题七后端方案汇报"
doc.core_properties.author = "项目组"
doc.save(OUTPUT)
print(OUTPUT)
