"""耕地质量报告模板定义。

为四类耕地质量专题报告提供结构化章节模板。
每个模板包含标题和章节列表；章节支持三种渲染模式（kind）：
- "llm"     注入上下文的 AI 生成（默认，prompt_hint 作为回退）
- "data"    纯数据表渲染，不经 LLM（data_renderer(ctx) -> HTML）
- "summary" 计算结论 + AI 润色（prompt_builder(ctx) 注入真实用量）

治理类模板（酸化治理/有机质提升）已接入 model-4/5 真实用量；
方案类模板（保护与提升/补充耕地）暂不开放生成，保持原结构不动。
"""
from __future__ import annotations

from typing import Any, Callable, Optional, TypedDict


# ---------------------------------------------------------------------------
# 结构定义
# ---------------------------------------------------------------------------

class Section(TypedDict, total=False):
    """报告章节结构。"""

    heading: str
    kind: str                       # "llm" | "data" | "summary"，缺省按 "llm"
    prompt_hint: str                # 回退提示词（无 prompt_builder 时用）
    prompt_builder: Callable[[dict[str, Any]], str]   # 注入真实数据的 prompt 构造器
    data_renderer: Callable[[dict[str, Any]], str]    # data 章节：直接返回 HTML，不调 LLM


class ReportTemplate(TypedDict):
    """报告模板结构。"""

    title: str
    sections: list[Section]


# ---------------------------------------------------------------------------
# 公共渲染辅助
# ---------------------------------------------------------------------------

def _fmt(v: Any) -> str:
    """数值格式化。None → '—'，float 保留两位。"""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int, float)):
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def _scope_label(scope: Optional[dict]) -> str:
    if not scope:
        return "未指定"
    return f"{scope.get('type', '?')}={scope.get('id', '?')}"


def _model4_rows(ctx: dict[str, Any]) -> list[dict]:
    m4 = ctx.get("model_results", {}).get("model-4")
    if not m4:
        return []
    return m4 if isinstance(m4, list) else [m4]


def _model5_data(ctx: dict[str, Any]) -> Optional[dict]:
    return ctx.get("model_results", {}).get("model-5")


# 地块指标中文名映射
_INDICATOR_LABELS: dict[str, str] = {
    "soil_ph": "土壤 pH",
    "organic_matter": "有机质 (g/kg)",
    "available_potassium": "速效钾 (mg/kg)",
    "available_phosphorus": "有效磷 (mg/kg)",
    "total_n": "全氮 (g/kg)",
    "bulk_density": "容重 (g/cm³)",
    "topsoil_thickness": "表土厚度 (cm)",
    "terrain_position": "地形部位",
    "soil_structure": "土壤结构",
    "soil_texture": "质地",
    "irrigation_condition": "灌溉能力",
    "drainage_capacity": "排水能力",
}


def render_parcel_indicators_table(ctx: dict[str, Any]) -> str:
    """地块土壤指标概览（data 章节，不经 LLM）。

    单地块范围：从 indicators_snapshot 渲染该地块的 soil_indicators 指标表。
    区域范围：渲染 region_stats 聚合表（均值/最小/最大/样本数）。
    指标全空时显示降级提示。
    """
    scope = ctx.get("scope", {})
    region = ctx.get("region_stats")

    # 区域范围 → 渲染聚合统计
    if scope.get("type") == "region" and region:
        parts: list[str] = ["<table><thead><tr><th>指标</th><th>均值</th><th>最小</th><th>最大</th><th>样本数</th></tr></thead><tbody>"]
        for key in ("soil_ph", "organic_matter", "available_potassium", "available_phosphorus", "total_n"):
            s = region.get(key)
            if s:
                label = _INDICATOR_LABELS.get(key, key)
                parts.append(
                    f"<tr><td>{label}</td><td>{_fmt(s.get('mean'))}</td>"
                    f"<td>{_fmt(s.get('min'))}</td><td>{_fmt(s.get('max'))}</td>"
                    f"<td>{s.get('count', '—')}</td></tr>"
                )
        parts.append("</tbody></table>")
        if len(parts) <= 2:
            return "<p>（区域内暂无有效土壤指标统计数据）</p>"
        return "".join(parts)

    # 单地块范围 → 渲染该地块指标
    snapshot = ctx.get("indicators_snapshot") or []
    if not snapshot:
        return "<p>该地块土壤指标数据缺失，建议补充检测后重新生成。</p>"

    rec = snapshot[0]
    indicators = rec.get("soil_indicators") or {}
    if not indicators or not any(v is not None for v in indicators.values()):
        return "<p>该地块土壤指标数据缺失，建议补充检测后重新生成。</p>"

    parts = ["<table><thead><tr><th>指标</th><th>数值</th></tr></thead><tbody>"]
    for key, label in _INDICATOR_LABELS.items():
        if key in indicators:
            parts.append(f"<tr><td>{label}</td><td>{_fmt(indicators.get(key))}</td></tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 酸化治理（model-4）：数据表 + prompt 注入
# ---------------------------------------------------------------------------

def render_acidification_dosage_table(ctx: dict[str, Any]) -> str:
    """model-4 用量表（data 章节，不经 LLM）。"""
    rows = _model4_rows(ctx)
    region = ctx.get("region_stats")
    if not rows and not region:
        return "<p>（暂无 model-4 酸化改良用量数据）</p>"

    parts: list[str] = []
    if rows:
        parts.append(
            "<table><thead><tr>"
            "<th>地块编号</th><th>土壤 pH</th><th>交换性氢</th><th>交换性铝</th>"
            "<th>石灰/调理剂用量 (kg/亩)</th><th>有机肥/泥炭用量 (kg/亩)</th>"
            "<th>来源</th>"
            "</tr></thead><tbody>"
        )
        for r in rows:
            pid = r.get("parcel_id", "—")
            ph = _fmt(r.get("soil_ph"))
            hex_ = _fmt(r.get("exchangeable_hydrogen"))
            alex = _fmt(r.get("exchangeable_aluminum"))
            lime = _fmt(r.get("lime_dosage") if r.get("lime_dosage") is not None else r.get("soil_conditioner_dosage"))
            of = _fmt(r.get("organic_fertilizer_dosage") if r.get("organic_fertilizer_dosage") is not None else r.get("woody_peat_dosage"))
            src = "已落库" if r.get("source") == "db" else "现场补算"
            parts.append(
                f"<tr><td>{pid}</td><td>{ph}</td><td>{hex_}</td><td>{alex}</td>"
                f"<td>{lime}</td><td>{of}</td><td>{src}</td></tr>"
            )
        parts.append("</tbody></table>")

    if region:
        parts.append("<p>区域统计：</p><ul>")
        for key in ("soil_ph", "lime_dosage", "soil_conditioner_dosage", "woody_peat_dosage"):
            s = region.get(key)
            if s:
                parts.append(
                    f"<li>{key}：均值 {_fmt(s.get('mean'))}，最小 {_fmt(s.get('min'))}，"
                    f"最大 {_fmt(s.get('max'))}（n={s.get('count')}）</li>"
                )
        parts.append("</ul>")

    return "".join(parts)


def _acid_data_brief(ctx: dict[str, Any]) -> str:
    """供 prompt 注入的 model-4 用量简报（限制条数防撑爆）。"""
    rows = _model4_rows(ctx)
    if not rows:
        return "（无 model-4 用量数据）"
    lines: list[str] = []
    for r in rows[:50]:
        pid = r.get("parcel_id", "?")
        ph = _fmt(r.get("soil_ph"))
        lime = _fmt(r.get("lime_dosage") if r.get("lime_dosage") is not None else r.get("soil_conditioner_dosage"))
        of = _fmt(r.get("organic_fertilizer_dosage") if r.get("organic_fertilizer_dosage") is not None else r.get("woody_peat_dosage"))
        lines.append(f"- 地块 {pid}: pH={ph}, 石灰/调理剂={lime} kg/亩, 有机肥/泥炭={of} kg/亩")
    if len(rows) > 50:
        lines.append(f"- …（共 {len(rows)} 个地块，已截断展示前 50 个）")
    return "\n".join(lines)


def acid_treatment_prompt(ctx: dict[str, Any]) -> str:
    """治理技术与措施章节：注入真实用量，约束不得编造。"""
    return (
        f"范围：{_scope_label(ctx.get('scope'))}\n"
        f"以下为 model-4 酸化改良用量计算结果（仅依据提供的数据，不得编造未给出的数值）：\n"
        f"{_acid_data_brief(ctx)}\n\n"
        "围绕上述用量，提出石灰类改良剂的酸化治理技术与措施，说明该技术的适用条件、施用量与方法。"
        "以 HTML 输出，使用 <h3> 小标题、<ul>/<li> 列表、<table> 表格。"
    )


def acid_summary_prompt(ctx: dict[str, Any]) -> str:
    """结论章节：用量结论前置 + AI 润色。"""
    return (
        "计算结论（model-4，须基于此润色，不得编造数值）：\n"
        f"{_acid_data_brief(ctx)}\n\n"
        "总结酸化治理方案的核心结论：酸化现状、推荐治理技术路线、治理用量与核验安排。"
        "未提供可靠模型结果时，不得编造 pH 提升幅度、增产潜力或经济效益。"
        "以 HTML 输出，<ul>/<li> 列出核心结论，<p> 呈现展望。"
    )


# ---------------------------------------------------------------------------
# 有机质提升（model-5）：数据表 + prompt 注入
# ---------------------------------------------------------------------------

def render_organic_matter_dosage_table(ctx: dict[str, Any]) -> str:
    """model-5 用量与有机质分布（data 章节，不经 LLM）。"""
    m5 = _model5_data(ctx)
    region = ctx.get("region_stats")
    if not m5 and not region:
        return "<p>有机肥施用量：暂无可靠估计；预期提升量：暂无可靠估计。</p>"

    parts: list[str] = []
    if m5:
        parts.append("<table><thead><tr>")
        if m5.get("organic_matter") is not None:
            parts.append("<th>有机质 (g/kg)</th>")
        parts.append("<th>有机肥施用量 (kg/亩)</th><th>等级</th><th>预期提升量 (g/kg)</th>")
        if m5.get("organic_fertilizer_type"):
            parts.append("<th>肥料类型</th>")
        parts.append("<th>来源</th></tr></thead><tbody><tr>")
        if m5.get("organic_matter") is not None:
            parts.append(f"<td>{_fmt(m5.get('organic_matter'))}</td>")
        dosage = m5.get("organic_fertilizer_dosage")
        parts.append(f"<td>{_fmt(dosage) if dosage is not None else '暂无可靠估计'}</td>")
        parts.append(f"<td>{_fmt(m5.get('level'))}</td>")
        parts.append("<td>暂无可靠估计</td>")
        if m5.get("organic_fertilizer_type"):
            parts.append(f"<td>{_fmt(m5.get('organic_fertilizer_type'))}</td>")
        parts.append(
            f"<td>{'真实模型' if dosage is not None else '定量不可用'}</td>"
        )
        parts.append("</tr></tbody></table>")

    if region:
        parts.append("<p>区域统计：</p><ul>")
        for key in ("soil_ph", "organic_matter", "m5_organic_fertilizer_dosage"):
            s = region.get(key)
            if s:
                parts.append(
                    f"<li>{key}：均值 {_fmt(s.get('mean'))}"
                    + (f"，最小 {_fmt(s.get('min'))}，最大 {_fmt(s.get('max'))}" if s.get('min') is not None else "")
                    + f"（n={s.get('count')}）</li>"
                )
        parts.append("</ul>")

    return "".join(parts)


def _parcel_indicators_brief(ctx: dict[str, Any]) -> str:
    """从 indicators_snapshot 提取地块实际指标摘要（pH、有机质）。"""
    snapshot = ctx.get("indicators_snapshot") or []
    if not snapshot:
        return ""
    ind = snapshot[0].get("soil_indicators") or {}
    parts: list[str] = []
    if ind.get("soil_ph") is not None:
        parts.append(f"pH={_fmt(ind.get('soil_ph'))}")
    if ind.get("organic_matter") is not None:
        parts.append(f"有机质={_fmt(ind.get('organic_matter'))} g/kg")
    return "；".join(parts)


def _organic_data_brief(ctx: dict[str, Any]) -> str:
    m5 = _model5_data(ctx)
    parcel_ind = _parcel_indicators_brief(ctx)
    if not m5:
        brief = "有机肥施用量：暂无可靠估计；预期提升量：暂无可靠估计。"
        if parcel_ind:
            brief = f"地块实测指标：{parcel_ind}\n{brief}"
        return brief
    brief = (
        f"- 有机肥施用量: "
        + (f"{_fmt(m5.get('organic_fertilizer_dosage'))} kg/亩" if m5.get("organic_fertilizer_dosage") is not None else "暂无可靠估计")
        + f"（等级 {m5.get('level', '未知')}）"
        + (f"；有机质: {_fmt(m5.get('organic_matter'))} g/kg" if m5.get('organic_matter') is not None else "")
        + "；预期提升量: 暂无可靠估计"
    )
    if parcel_ind:
        brief += f"\n- 地块实测指标：{parcel_ind}"
    return brief


def organic_fertilizer_prompt(ctx: dict[str, Any]) -> str:
    """有机培肥方案章节：注入真实用量与地块指标。"""
    m5 = _model5_data(ctx)
    data_brief = _organic_data_brief(ctx)
    if not m5:
        return (
            f"范围：{_scope_label(ctx.get('scope'))}\n"
            f"{data_brief}\n\n"
            "Model-5 暂无可靠定量结果。请仅给出定性核验建议："
            "说明应补充的土壤检测、模型输入、肥料来源核验和田间试验步骤；"
            "不得给出施用量、提升量、县域平均值或其他未提供的数字。"
            "以 HTML 输出，<h3> 小标题、<table> 表格、<ul>/<li> 列表。"
        )
    return (
        f"范围：{_scope_label(ctx.get('scope'))}\n"
        f"以下为 model-5 有机质培肥用量计算结果与地块实测指标（仅依据提供的数据，不得编造未给出的数值）：\n"
        f"{data_brief}\n\n"
        "只有非空的真实模型用量可以作为处方引用；空值必须表述为暂无可靠估计。"
        "据此制定有机肥源规划、秸秆还田、绿肥种植和差异化培肥核验方案。"
        "以 HTML 输出，<h3> 小标题、<table> 表格、<ul>/<li> 列表。"
    )


def organic_summary_prompt(ctx: dict[str, Any]) -> str:
    """结论章节：用量结论前置 + AI 润色。"""
    return (
        "计算结论（model-5，须基于此润色，不得编造数值）：\n"
        f"{_organic_data_brief(ctx)}\n\n"
        "总结有机质提升方案的核心结论：现状评估、推荐技术路线、监测与核验安排。"
        "未提供可靠模型结果时，不得编造有机质提升幅度、增产潜力或施用量。"
        "以 HTML 输出，<ul>/<li> 列出核心结论，<p> 呈现展望。"
    )


# ---------------------------------------------------------------------------
# 1. 耕地质量保护与提升方案（暂不开放生成，保持原结构）
# ---------------------------------------------------------------------------

FARMLAND_PROTECTION_UPGRADE: ReportTemplate = {
    "title": "耕地质量保护与提升方案",
    "sections": [
        {
            "heading": "前言/背景",
            "prompt_hint": (
                "围绕 area_code 对应区域，阐述耕地质量保护与提升的政策背景、战略意义 "
                "以及编制本方案的总体目标和依据。请结合国家耕地保护法律法规、"
                "粮食安全战略和区域农业发展规划，说明方案编制的必要性和紧迫性。"
                "以 HTML 格式输出，使用 <h2>、<h3> 作为层级标题，<p> 作为段落，"
                "关键数据使用 <ul>/<li> 列表呈现。"
            ),
        },
        {
            "heading": "区域概况",
            "prompt_hint": (
                "基于 area_code 描述目标区域的自然地理条件、气候特征、土壤类型、"
                "土地利用现状、农业产业结构和社会经济概况。重点说明与耕地质量相关的"
                "地形地貌、水文条件、耕作制度等背景信息。"
                "使用 <h2>/<h3> 标题层级，关键指标以 <table> 表格呈现，"
                "地貌描述使用 <p> 段落，分类信息使用 <ul>/<li> 列表。"
            ),
        },
        {
            "heading": "耕地质量现状分析",
            "prompt_hint": (
                "针对 area_code 区域，全面分析耕地质量等级分布、土壤理化性状"
                "（有机质、pH、氮磷钾、微量元素等）、耕层厚度、灌排条件、"
                "农田基础设施状况等。引用耕地质量评价标准和等级划分依据，"
                "结合区域实际数据进行定性与定量分析。"
                "使用 <h2>/<h3> 标题层级，土壤指标以 <table> 表格呈现，"
                "等级分布使用 <ul>/<li> 列表，趋势分析使用 <p> 段落。"
            ),
        },
        {
            "heading": "主要障碍因素",
            "prompt_hint": (
                "结合 area_code 区域耕地质量现状，系统识别和诊断影响耕地质量的主要"
                "障碍因素，如土壤酸化、有机质偏低、耕层浅薄、土壤板结、养分失衡、"
                "灌溉排水不畅、水土流失、污染风险等。对每个障碍因素进行成因分析，"
                "并评估其影响范围和严重程度。"
                "使用 <h2>/<h3> 标题层级，障碍因素以 <ul>/<li> 列表呈现，"
                "影响评估以 <table> 表格呈现，详细分析使用 <p> 段落。"
            ),
        },
        {
            "heading": "保护策略",
            "prompt_hint": (
                "围绕 area_code 区域耕地质量保护目标，提出系统性保护策略，包括："
                "耕地数量管控（永久基本农田保护、占补平衡）、耕地质量监测网络建设、"
                "土壤污染防治、农田生态环境保护、耕作层剥离再利用等。"
                "每项策略应说明具体措施、实施路径和预期效果。"
                "使用 <h2>/<h3> 标题层级，策略要点以 <ul>/<li> 列表呈现，"
                "措施对比以 <table> 表格呈现，详细说明使用 <p> 段落。"
            ),
        },
        {
            "heading": "提升路径",
            "prompt_hint": (
                "针对 area_code 区域，提出耕地质量提升的具体路径和技术方案，包括："
                "土壤改良（酸化治理、有机质提升、深耕深松）、农田基础设施建设"
                "（灌排体系、田间道路、农田防护林）、地力培肥（秸秆还田、绿肥种植、"
                "测土配方施肥）、高标准农田建设等。说明各路径的适用条件、技术要点、"
                "投资需求和预期效益。"
                "使用 <h2>/<h3> 标题层级，技术方案以 <table> 表格呈现，"
                "路径说明以 <ul>/<li> 列表呈现，详细描述使用 <p> 段落。"
            ),
        },
        {
            "heading": "保障措施",
            "prompt_hint": (
                "围绕 area_code 区域，提出确保方案落地实施的保障措施，包括："
                "组织领导与责任分工、资金筹措与投入保障、技术支撑与科技服务、"
                "政策法规与制度保障、宣传培训与社会参与、监督考核与评估机制等。"
                "使用 <h2>/<h3> 标题层级，保障措施以 <ul>/<li> 列表呈现，"
                "责任分工以 <table> 表格呈现，详细说明使用 <p> 段落。"
            ),
        },
        {
            "heading": "结论与建议",
            "prompt_hint": (
                "总结 area_code 区域耕地质量保护与提升方案的核心要点，"
                "提出针对性政策建议和行动建议，展望方案实施后的预期成效。"
                "建议应具备可操作性和时效性，明确优先序和关键时间节点。"
                "使用 <h2>/<h3> 标题层级，总结要点以 <ul>/<li> 列表呈现，"
                "建议以编号列表呈现，展望使用 <p> 段落。"
            ),
        },
    ],
}

# ---------------------------------------------------------------------------
# 2. 补充耕地方案（暂不开放生成，保持原结构）
# ---------------------------------------------------------------------------

SUPPLEMENTARY_FARMLAND: ReportTemplate = {
    "title": "补充耕地方案",
    "sections": [
        {
            "heading": "前言/背景",
            "prompt_hint": (
                "围绕 area_code 对应区域，阐述补充耕地工作的政策背景、法律法规要求、"
                "耕地占补平衡制度以及编制本方案的目的和意义。说明区域经济社会发展"
                "对建设用地的需求与耕地保护之间的矛盾，以及补充耕地的必要性和紧迫性。"
                "以 HTML 格式输出，使用 <h2>、<h3> 作为层级标题，<p> 作为段落，"
                "政策依据使用 <ul>/<li> 列表呈现。"
            ),
        },
        {
            "heading": "区域耕地资源概况",
            "prompt_hint": (
                "基于 area_code 描述区域耕地资源总量、空间分布、利用类型、质量等级、"
                "权属状况和后备资源概况。分析区域耕地资源的变化趋势和驱动因素，"
                "说明当前耕地保护面临的形势和挑战。"
                "使用 <h2>/<h3> 标题层级，耕地资源数据以 <table> 表格呈现，"
                "分布特征以 <p> 段落描述，变化趋势以 <ul>/<li> 列表呈现。"
            ),
        },
        {
            "heading": "耕地缺口分析",
            "prompt_hint": (
                "针对 area_code 区域，基于建设用地需求预测和耕地保有量目标，"
                "测算规划期内耕地占补平衡缺口。分析已占用耕地的数量、质量和区位，"
                "以及已补充耕地的数量、质量和验收情况。明确需要补充耕地的规模和时序安排。"
                "使用 <h2>/<h3> 标题层级，缺口测算数据以 <table> 表格呈现，"
                "分析逻辑以 <p> 段落说明，分类统计以 <ul>/<li> 列表呈现。"
            ),
        },
        {
            "heading": "补充耕地潜力评估",
            "prompt_hint": (
                "围绕 area_code 区域，系统评估补充耕地潜力，包括："
                "宜耕未利用地开发潜力、土地复垦潜力（工矿废弃地、闲置宅基地等）、"
                "土地整理潜力（农用地整理、建设用地整理）、耕地提质改造潜力等。"
                "对各类潜力进行分级评价，测算可补充耕地面积和质量预期。"
                "使用 <h2>/<h3> 标题层级，潜力评估数据以 <table> 表格呈现，"
                "潜力分级以 <ul>/<li> 列表呈现，评估方法以 <p> 段落说明。"
            ),
        },
        {
            "heading": "空间布局优化",
            "prompt_hint": (
                "针对 area_code 区域，基于补充耕地潜力评估结果，结合国土空间规划"
                "和生态保护要求，优化补充耕地的空间布局。明确补充耕地的优先区域、"
                "限制区域和禁止区域，制定分区管控方案。"
                "说明各区域补充耕地的类型、规模、时序和空间衔接关系。"
                "使用 <h2>/<h3> 标题层级，空间布局以 <table> 表格呈现，"
                "分区说明以 <ul>/<li> 列表呈现，布局原则以 <p> 段落说明。"
            ),
        },
        {
            "heading": "实施路径与目标",
            "prompt_hint": (
                "围绕 area_code 区域，制定补充耕地的实施路径，包括："
                "年度实施计划、重点项目安排、技术标准和验收要求。"
                "明确近期（1-3年）、中期（3-5年）和远期（5-10年）的补充耕地目标，"
                "分解到具体项目和地块，说明各阶段的关键任务和里程碑。"
                "使用 <h2>/<h3> 标题层级，实施计划以 <table> 表格呈现，"
                "阶段目标以 <ul>/<li> 列表呈现，路径说明使用 <p> 段落。"
            ),
        },
        {
            "heading": "投资估算",
            "prompt_hint": (
                "针对 area_code 区域补充耕地各项工程，进行投资估算和经济分析。"
                "包括土地开发、复垦、整理、提质改造等各项工程的单位成本估算、"
                "总投资规模、资金来源和筹措方案。进行成本效益分析，"
                "评估补充耕地的经济可行性和社会效益。"
                "使用 <h2>/<h3> 标题层级，投资估算以 <table> 表格呈现，"
                "资金来源以 <ul>/<li> 列表呈现，效益分析使用 <p> 段落。"
            ),
        },
        {
            "heading": "保障措施",
            "prompt_hint": (
                "围绕 area_code 区域，提出确保补充耕地方案有效实施的保障措施，包括："
                "组织领导与部门协同、资金保障与多元投入、技术支撑与标准规范、"
                "监督管理与考核评估、公众参与与信息公开、后期管护与长效利用等。"
                "使用 <h2>/<h3> 标题层级，保障措施以 <ul>/<li> 列表呈现，"
                "责任分工以 <table> 表格呈现，详细说明使用 <p> 段落。"
            ),
        },
        {
            "heading": "结论",
            "prompt_hint": (
                "总结 area_code 区域补充耕地方案的核心结论，包括补充耕地的总体规模、"
                "空间布局、实施路径和预期效果。强调方案对保障区域粮食安全、"
                "促进可持续发展的战略意义。"
                "使用 <h2>/<h3> 标题层级，核心结论以 <ul>/<li> 列表呈现，"
                "总结性陈述使用 <p> 段落。"
            ),
        },
    ],
}

# ---------------------------------------------------------------------------
# 3. 地块酸化治理方案（接入 model-4 用量）
# ---------------------------------------------------------------------------

ACIDIFICATION_TREATMENT: ReportTemplate = {
    "title": "地块酸化治理方案",
    "sections": [
        {
            "heading": "前言/背景",
            "kind": "llm",
            "prompt_hint": (
                "阐述土壤酸化的概念、危害和治理意义，说明区域土壤酸化问题的严峻性"
                "和治理的紧迫性。介绍国家关于土壤酸化治理的政策要求和行动部署，"
                "以及编制本方案的目的和总体思路。"
                "以 HTML 格式输出，使用 <h3> 作为层级标题，<p> 作为段落，"
                "政策背景使用 <ul>/<li> 列表呈现。"
            ),
        },
        {
            "heading": "酸化现状与分布",
            "kind": "llm",
            "prompt_builder": lambda ctx: (
                f"范围：{_scope_label(ctx.get('scope'))}\n"
                f"地块土壤 pH 与酸化指标快照（仅依据提供的数据，不得编造未给出的数值）：\n{_acid_data_brief(ctx)}\n\n"
                "基于上述 pH/交换性氢/交换性铝数据，分析土壤酸化现状：pH 空间分布、"
                # "不同酸化等级面积与占比、酸化深度剖面特征。"
                "使用 <h3> 标题，pH 分布以 <table> 表格呈现，酸化等级以 <ul>/<li> 呈现。"
            ),
        },
        {
            "heading": "酸化成因分析",
            "kind": "llm",
            "prompt_hint": (
                "深入分析土壤酸化的成因，包括自然因素（成土母质、气候、地形）"
                "和人为因素（过量施用化肥、酸沉降、不合理耕作、连作障碍）。"
                "分析钙镁盐基离子淋失规律、铝活化机制及酸化对养分有效性的影响。"
                "使用 <h3> 标题，成因以 <ul>/<li> 呈现，机理以 <p> 说明。"
            ),
        },
        {
            "heading": "治理用量测算（model-4）",
            "kind": "data",
            "data_renderer": render_acidification_dosage_table,
        },
        {
            "heading": "治理技术与措施",
            "kind": "summary",
            "prompt_builder": acid_treatment_prompt,
        },
        # {
        #     "heading": "改良材料选择",
        #     "kind": "summary",
        #     "prompt_builder": lambda ctx: (
        #         f"范围：{_scope_label(ctx.get('scope'))}\n"
        #         f"model-4 推荐用量（须基于此润色，不得编造数值）：\n{_acid_data_brief(ctx)}\n\n"
        #         "基于上述用量推荐适宜改良材料（石灰石粉、白云石粉、钙镁磷肥、"
        #         "生物炭、腐殖酸类、木本泥炭等）的种类、规格与用量，比较改良效果、"
        #         "可获得性。使用 <h3> 标题，材料对比以 <table> 呈现。"
        #     ),
        # },
        # {
        #     "heading": "实施计划",
        #     "kind": "llm",
        #     "prompt_hint": (
        #         "制定酸化治理分阶段实施计划：治理区域划分与优先序、年度任务分解、"
        #         "技术培训与示范、物资采购调配、施工质量管控、进度里程碑。"
        #         "明确近期（1-2年）、中期（3-5年）目标与验收标准。"
        #         "使用 <h3> 标题，实施计划以 <table> 呈现，阶段任务以 <ul>/<li> 呈现。"
        #     ),
        # },
        {
            "heading": "效果评估方案",
            "kind": "llm",
            "prompt_hint": (
                "设计酸化治理效果评估方案：监测点位布设、监测指标（pH、交换性酸、"
                "交换性铝、盐基饱和度、CEC、有机质、产量品质）、监测频率、"
                "评价标准、前后对比与跟踪机制。"
                "使用 <h3> 标题，监测指标以 <table> 呈现，评估标准以 <ul>/<li> 呈现。"
            ),
        },
        {
            "heading": "保障措施",
            "kind": "llm",
            "prompt_hint": (
                "提出保障措施：组织保障与责任、资金筹措与投入、技术支撑与服务、"
                "政策支持与激励、宣传引导与农户参与、质量监管与考核。"
                "使用 <h3> 标题，保障措施以 <ul>/<li> 呈现，责任分工以 <table> 呈现。"
            ),
        },
        {
            "heading": "结论",
            "kind": "summary",
            "prompt_builder": acid_summary_prompt,
        },
    ],
}

# ---------------------------------------------------------------------------
# 4. 地块有机质提升方案（接入 model-5 用量）
# ---------------------------------------------------------------------------

ORGANIC_MATTER_IMPROVEMENT: ReportTemplate = {
    "title": "地块有机质提升方案",
    "sections": [
        {
            "heading": "前言/背景",
            "kind": "llm",
            "prompt_hint": (
                "阐述土壤有机质的重要功能（养分供给、结构改良、保水保肥、生物活性），"
                "说明区域耕地有机质提升的紧迫性和战略意义。介绍国家关于耕地质量保护"
                "与有机质提升的政策要求及编制本方案的总体思路。"
                "以 HTML 输出，<h3> 标题，<p> 段落，政策背景以 <ul>/<li> 呈现。"
            ),
        },
        {
            "heading": "地块土壤指标概览",
            "kind": "data",
            "data_renderer": render_parcel_indicators_table,
        },
        {
            "heading": "有机质现状分析",
            "kind": "llm",
            "prompt_builder": lambda ctx: (
                f"范围：{_scope_label(ctx.get('scope'))}\n"
                f"地块有机质与 pH 等指标快照（仅依据提供的数据，不得编造数值）：\n{_organic_data_brief(ctx)}\n\n"
                "基于上述数据，分析有机质空间分布、不同等级面积与占比、"
                "与土壤类型和耕作制度的关系、历史演变趋势。"
                "使用 <h3> 标题，有机质数据以 <table> 呈现，等级分布以 <ul>/<li> 呈现。"
            ),
        },
        # {
        #     "heading": "提升目标",
        #     "kind": "llm",
        #     "prompt_hint": (
        #         "制定有机质提升目标：总体目标（区域平均提升幅度）、分级目标"
        #         "（不同等级耕地的提升值）、分阶段目标（近期/中期/远期）。"
        #         "说明依据、可行性论证与考核指标。"
        #         "使用 <h3> 标题，目标指标以 <table> 呈现，阶段目标以 <ul>/<li> 呈现。"
        #     ),
        # },
        {
            "heading": "有机培肥用量测算（model-5）",
            "kind": "data",
            "data_renderer": render_organic_matter_dosage_table,
        },
        {
            "heading": "有机培肥方案",
            "kind": "summary",
            "prompt_builder": organic_fertilizer_prompt,
        },
        {
            "heading": "技术路线",
            "kind": "llm",
            "prompt_hint": (
                "设计有机质提升技术路线：外源碳投入（秸秆还田、有机肥、绿肥）、"
                "内源碳固定（保护性耕作、生物炭）、碳损失控制（合理轮作、水土保持）。"
                "说明原理、适用条件、操作要点与协同效应。"
                "使用 <h3> 标题，技术路线以 <ul>/<li> 呈现，参数以 <table> 呈现。"
            ),
        },
        # {
        #     "heading": "实施计划",
        #     "kind": "llm",
        #     "prompt_hint": (
        #         "制定有机质提升分阶段实施计划：示范区建设、年度任务分解、"
        #         "有机肥源建设与供应、技术培训、物资调配、质量管控与验收。"
        #         "明确近期/中期/远期实施重点与里程碑。"
        #         "使用 <h3> 标题，实施计划以 <table> 呈现，阶段任务以 <ul>/<li> 呈现。"
        #     ),
        # },
        {
            "heading": "效果监测",
            "kind": "llm",
            "prompt_hint": (
                "设计有机质提升效果监测方案：长期定位监测点布局、监测指标"
                "（有机质含量与组分、容重、孔隙度、团聚体、微生物量碳、酶活性、产量）、"
                "采样检测方法、监测频率、数据管理平台、预警机制。"
                "使用 <h3> 标题，监测指标以 <table> 呈现，方案以 <ul>/<li> 呈现。"
            ),
        },
        {
            "heading": "保障措施",
            "kind": "llm",
            "prompt_hint": (
                "提出保障措施：组织保障与责任、资金投入与补贴、技术支撑与服务网络、"
                "政策激励与长效机制、宣传培训与示范、监测评估与动态调整。"
                "使用 <h3> 标题，保障措施以 <ul>/<li> 呈现，责任分工以 <table> 呈现。"
            ),
        },
        {
            "heading": "结论",
            "kind": "summary",
            "prompt_builder": organic_summary_prompt,
        },
    ],
}

# ---------------------------------------------------------------------------
# 汇总导出字典
# ---------------------------------------------------------------------------

REPORT_TEMPLATES: dict[str, ReportTemplate] = {
    "farmland_protection_upgrade": FARMLAND_PROTECTION_UPGRADE,
    "supplementary_farmland": SUPPLEMENTARY_FARMLAND,
    "acidification_treatment": ACIDIFICATION_TREATMENT,
    "organic_matter_improvement": ORGANIC_MATTER_IMPROVEMENT,
}
