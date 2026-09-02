from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .report_context import (
    UNSUPPORTED_REPORT_TYPES,
    ReportContextError,
    build_report_context,
    error_result,
    normalize_scope,
)
from .report_templates import REPORT_TEMPLATES
from framework.llm.service import llm_service

logger = logging.getLogger(__name__)

# 报告章节生成用的 system prompt：让 LLM 明确角色和输出边界，
# 避免把"格式要求/效果说明/操作提示"当成正文输出。
REPORT_SECTION_SYSTEM_PROMPT = (
    "你是耕地质量报告的专业撰写者。"
    "用户会提供章节撰写要求和数据，你只输出该章节的正文 HTML，"
    "不要输出任何与正文无关的内容，包括但不限于："
    "格式说明、效果说明、输出要求、操作步骤、示例、注释、"
    "“好的”“根据要求”等对话用语、"
    "“效果说明：X. 使用<xx>标签...”这类复述输出格式的文字。"
    "HTML 中只用 <h2> <h3> <h4> <p> <ul> <li> <table> <thead> <tbody> "
    "<tr> <th> <td> <strong> <em> <br> 这些标签，不要加 <html> <body> <head> "
    "<style> <script> 等外壳标签。"
)


DEFAULT_ACTIONS = [
    "核验核心字段映射和数据来源",
    "确认推荐图层是否可用于当前汇报场景",
    "在真实模型接入后复核诊断结论",
]


# 不依赖上下文的报告类型（仍走旧式纯 AI 生成路径，目前为空集；方案类已被拦截）。
NO_CONTEXT_REPORT_TYPES: set[str] = set()


def build_report_summary(diagnosis: dict[str, Any]) -> dict[str, Any]:
    """将诊断结果整理为稳定、可拆解的汇报摘要。"""

    if diagnosis.get("status") != "ok":
        return {
            "status": "error",
            "error": {
                "code": "MISSING_DIAGNOSIS",
                "message": "需要传入成功的诊断结果",
            },
        }

    topic = diagnosis["topic"]
    findings = [
        {
            "title": "诊断主题",
            "content": f"{topic['name']} 已形成结构化结果。",
        },
        {
            "title": "来源追溯",
            "content": "结果包含数据目录、参考资产和运行时依赖说明。",
        },
    ]
    findings.extend(
        {"title": "判定依据", "content": item}
        for item in diagnosis.get("evidence", [])
    )

    return {
        "status": "ok",
        "diagnosis_id": diagnosis["diagnosis_id"],
        "area": diagnosis["area"],
        "summary": diagnosis["summary"],
        "findings": findings,
        "recommendations": diagnosis.get("recommendations", []),
        "actions": DEFAULT_ACTIONS,
        "source": {
            "diagnosis_topic": topic["id"],
            "recommended_layers": diagnosis.get("recommended_layers", []),
            "reliability": diagnosis.get("reliability", {}),
        },
    }


def generate_report(report_type: str, scope: Any, area_code: Any = None) -> dict[str, Any]:
    """根据报告模板、上下文与 AI 生成完整报告。

    签名：``generate_report(report_type, scope, area_code=None)``。
    - ``scope``：``{"type": "parcel"|"region", "id": str}``，或旧式字符串 area_code（按 region 兼容）。
    - ``area_code``：旧式兼容字段，``scope`` 缺省时按 region 范围解析。

    不支持的报告类型（方案类）直接返回 ``UNSUPPORTED_REPORT_TYPE``；
    上下文聚合失败返回 ``CONTEXT_UNAVAILABLE``，不进入纯 AI 生成。
    """
    # 4.1 不支持的报告类型（方案类模板前端拦截，聚合层亦拒绝）
    if report_type in UNSUPPORTED_REPORT_TYPES:
        return error_result("UNSUPPORTED_REPORT_TYPE", f"暂不支持的报告类型: {report_type}")

    template = REPORT_TEMPLATES.get(report_type)
    if template is None:
        return error_result("UNKNOWN_REPORT_TYPE", f"未知的报告类型: {report_type}")

    title = template["title"]
    sections = template["sections"]

    # 1.2 归一化范围（兼容旧 area_code 字符串调用）
    try:
        scope_norm = normalize_scope(scope, area_code)
    except ReportContextError as e:
        return error_result(e.code, e.message)

    # 4.2 上下文聚合（方案类已在上方拦截；NO_CONTEXT_REPORT_TYPES 走旧式纯 AI 路径）
    ctx: dict[str, Any] = {}
    if report_type not in NO_CONTEXT_REPORT_TYPES:
        t0 = time.time()
        try:
            ctx = build_report_context(report_type, scope_norm)
        except ReportContextError as e:
            logger.error("[Report] 上下文聚合失败 report_type=%s scope=%s code=%s: %s",
                         report_type, scope_norm, e.code, e.message)
            return error_result(e.code or "CONTEXT_UNAVAILABLE", e.message)
        meta = ctx.get("source_meta", {})
        sampling = meta.get("sampling", {})
        logger.info(
            "[Report] 上下文聚合完成 %.1fs: total=%s, db_hits=%s, computed=%s, sampling=%s",
            time.time() - t0,
            meta.get("total_parcels", 0),
            sampling.get("db_hits", 0),
            sampling.get("computed", 0),
            sampling.get("applied"),
        )

    # 4.3 按 kind 分流：data → data_renderer 直接产 HTML；llm/summary → prompt_builder/prompt_hint 生成 prompt
    section_plan: list[dict[str, Any]] = []
    for idx, sec in enumerate(sections):
        kind = sec.get("kind", "llm")
        heading = sec.get("heading", "")
        if kind == "data":
            renderer = sec.get("data_renderer")
            section_plan.append({
                "idx": idx,
                "kind": "data",
                "heading": heading,
                "content": renderer(ctx) if renderer else "<p>（数据章节未配置渲染器）</p>",
            })
        else:
            # llm / summary
            builder = sec.get("prompt_builder")
            if builder is not None:
                prompt = builder(ctx)
            else:
                hint = sec.get("prompt_hint", "")
                # 回退：把 area_code 占位符替换为范围 id，保持旧模板可用
                prompt = hint.replace("area_code", scope_norm.get("id", ""))
            section_plan.append({
                "idx": idx,
                "kind": kind,
                "heading": heading,
                "prompt": prompt,
            })

    # 4.4 并行调用 LLM 生成需 AI 的章节，data 章节按原位插入
    def _gen_section(idx: int, prompt: str) -> tuple[int, str]:
        ts = time.time()
        # 传入带 system role 的 messages，明确只输出正文、不要复述格式要求
        messages = [{"role": "system", "content": REPORT_SECTION_SYSTEM_PROMPT}]
        result = llm_service.generate(prompt, messages=messages)
        dt = time.time() - ts
        heading = next((s["heading"] for s in section_plan if s["idx"] == idx), f"#{idx}")
        if result.get("success"):
            logger.info("[Report] LLM 章节完成 %.1fs: %s", dt, heading)
            return idx, result["content"]
        # 4.6 部分章节 LLM 失败用占位 HTML 替代，整体仍标记完成
        logger.warning("[Report] LLM 章节失败 %.1fs: %s", dt, heading)
        return idx, "<p>（本小节内容因 AI 服务暂时不可用而无法生成，请稍后重试。）</p>"

    llm_plan = [s for s in section_plan if s["kind"] in ("llm", "summary")]
    section_results: dict[int, str] = {}
    if llm_plan:
        t_llm = time.time()
        with ThreadPoolExecutor(max_workers=max(1, len(llm_plan))) as executor:
            futures = {
                executor.submit(_gen_section, s["idx"], s["prompt"]): s["idx"]
                for s in llm_plan
            }
            for future in as_completed(futures):
                idx, content = future.result()
                section_results[idx] = content
        logger.info("[Report] 全部 LLM 章节完成 %.1fs（%d 章节并行）",
                    time.time() - t_llm, len(llm_plan))
    # data 章节直接填入
    for s in section_plan:
        if s["kind"] == "data":
            section_results[s["idx"]] = s["content"]

    # 按模板顺序拼接 HTML
    sections_html_parts: list[str] = []
    for i, s in enumerate(section_plan):
        heading = s["heading"]
        section_content = section_results.get(s["idx"], "<p>（生成失败）</p>")
        section_html = (
            f'<div class="report-section">\n'
            f"<h3>{heading}</h3>\n"
            f"{section_content}\n"
            f"</div>"
        )
        sections_html_parts.append(section_html)

    # 4.5 自动追加"数据来源与计算依据"小节
    if ctx:
        source_html = _render_source_meta(ctx.get("source_meta", {}), scope_norm)
        if source_html:
            sections_html_parts.append(source_html)

    sections_html = "\n".join(sections_html_parts)

    body_html = (
        f'<div class="report-container">\n'
        f"<h2>{title}</h2>\n"
        f"{sections_html}\n"
        f"</div>"
    )

    full_html = (
        "<style>\n"
        "body {\n"
        '    font-family: "Microsoft YaHei", "PingFang SC", sans-serif;\n'
        "    line-height: 1.8;\n"
        "}\n"
        "h2 {\n"
        "    font-size: 24px;\n"
        "    color: #1a1a1a;\n"
        "    border-bottom: 2px solid #2e7d32;\n"
        "    padding-bottom: 8px;\n"
        "    margin-bottom: 24px;\n"
        "}\n"
        "h3 {\n"
        "    font-size: 18px;\n"
        "    color: #2e7d32;\n"
        "    margin-top: 20px;\n"
        "    margin-bottom: 12px;\n"
        "}\n"
        "p {\n"
        "    text-indent: 2em;\n"
        "    margin: 8px 0;\n"
        "}\n"
        "table {\n"
        "    border-collapse: collapse;\n"
        "    width: 100%;\n"
        "    margin: 12px 0;\n"
        "}\n"
        "table th, table td {\n"
        "    border: 1px solid #ddd;\n"
        "    padding: 8px 12px;\n"
        "    text-align: left;\n"
        "}\n"
        "table th {\n"
        "    background-color: #f5f5f5;\n"
        "}\n"
        "</style>\n"
        f"{body_html}"
    )

    # region 范围仍写 area_code 维持历史列表查询
    result_area_code = scope_norm["id"] if scope_norm["type"] == "region" else ""
    return {
        "status": "ok",
        "title": title,
        "content": full_html,
        "report_type": report_type,
        "area_code": result_area_code,
        "scope": scope_norm,
    }


def _render_source_meta(meta: dict[str, Any], scope: dict[str, str]) -> str:
    """渲染"数据来源与计算依据"小节。

    由 source_meta 渲染地块编号、指标快照时间、模型版本、采样标注。
    """
    if not meta:
        return ""
    total = meta.get("total_parcels", 0)
    missing = meta.get("missing_parcels") or []
    versions = meta.get("model_versions") or []
    computed_at = meta.get("computed_at", "")
    data_table = meta.get("data_source_table", "parcel_info")
    sampling = meta.get("sampling") or {}

    parts: list[str] = [
        '<div class="report-section">',
        "<h3>数据来源与计算依据</h3>",
        "<ul>",
        f"<li>范围：{scope.get('type', '?')} = {scope.get('id', '?')}</li>",
        f"<li>数据来源表：{data_table}</li>",
        f"<li>地块总数：{total}</li>",
    ]
    if missing:
        sample_missing = missing[:20]
        suffix = f"（共 {len(missing)} 个，已截断展示前 {len(sample_missing)} 个）" if len(missing) > 20 else ""
        parts.append(
            "<li>缺失指标地块：" + "、".join(str(p) for p in sample_missing) + suffix + "</li>"
        )
    if versions:
        parts.append("<li>模型版本：" + "、".join(versions) + "</li>")
    if computed_at:
        parts.append(f"<li>计算时间：{computed_at}</li>")
    if sampling:
        applied = sampling.get("applied")
        if applied:
            parts.append(
                "<li>区域采样：已启用（阈值 "
                f"{sampling.get('threshold', '?')}，需补算 {sampling.get('need_compute', '?')}，"
                f"实际采样 {sampling.get('sampled', '?')}）</li>"
            )
        else:
            parts.append(
                f"<li>区域采样：未启用（库命中 {sampling.get('db_hits', 0)}，"
                f"补算 {sampling.get('computed', 0)}）</li>"
            )
    parts.append("</ul>")
    parts.append("</div>")
    return "\n".join(parts)


def generate_pdf(html_content: str) -> bytes:
    """将 HTML 报告内容转换为 PDF 字节流。

    优先使用 WeasyPrint，不可用时降级为纯文本 PDF。
    """
    print(f"[PDF] 开始生成 PDF，内容长度: {len(html_content)} 字符", flush=True)

    try:
        from weasyprint import HTML

        pdf_bytes = HTML(string=html_content).write_pdf()
        print(f"[PDF] WeasyPrint 生成成功，大小: {len(pdf_bytes)} bytes", flush=True)
        return pdf_bytes
    except ImportError as e:
        print(f"[PDF] WeasyPrint 未安装: {e}", flush=True)
    except Exception as e:
        print(f"[PDF] WeasyPrint 生成失败: {e}，降级为 reportlab", flush=True)

    # 降级方案：使用 reportlab 生成带结构和样式的 PDF
    try:
        from io import BytesIO
        from html import unescape as _html_unescape
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem,
        )
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.sequencer import setSequencer
        from html.parser import HTMLParser

        # 注册中文字体：兼容 Windows / Linux
        _chinese_font = "ChineseFont"
        _font_paths = [
            # Windows
            "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑（与 CSS 中 Microsoft YaHei 对应）
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            # Linux 常见中文字体路径
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
        ]
        _font_registered = False
        for fp in _font_paths:
            try:
                pdfmetrics.registerFont(TTFont(_chinese_font, fp))
                print(f"[PDF] 已注册中文字体: {fp}", flush=True)
                _font_registered = True
                break
            except Exception:
                continue
        if not _font_registered:
            _chinese_font = "Helvetica"
            print("[PDF] 未找到中文字体，使用 Helvetica（中文可能无法显示）", flush=True)

        # ── 定义一套与内嵌 CSS 匹配的段落样式 ──────────────────────────────
        styles = getSampleStyleSheet()
        s_report_title = ParagraphStyle(
            "ReportTitle", parent=styles["Title"],
            fontName=_chinese_font, fontSize=20, leading=26,
            alignment=TA_LEFT, textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=14, borderPadding=(0, 0, 6, 0),
        )
        s_h2 = ParagraphStyle(
            "H2", parent=styles["Heading2"],
            fontName=_chinese_font, fontSize=18, leading=24,
            textColor=colors.HexColor("#1a1a1a"),
            spaceBefore=10, spaceAfter=14,
        )
        s_h3 = ParagraphStyle(
            "H3", parent=styles["Heading3"],
            fontName=_chinese_font, fontSize=14, leading=20,
            textColor=colors.HexColor("#2e7d32"),   # 绿色标题，匹配 CSS
            spaceBefore=14, spaceAfter=8,
        )
        s_body = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontName=_chinese_font, fontSize=10.5, leading=17,
            firstLineIndent=21,                 # 首行缩进 ≈ 2em
            alignment=TA_LEFT,
            spaceAfter=4,
        )
        s_body_no_indent = ParagraphStyle(
            "BodyNoIndent", parent=s_body, firstLineIndent=0,
        )
        s_table_cell = ParagraphStyle(
            "TableCell", parent=styles["Normal"],
            fontName=_chinese_font, fontSize=9.5, leading=14,
            alignment=TA_LEFT,
        )
        s_table_header = ParagraphStyle(
            "TableHeader", parent=s_table_cell,
            textColor=colors.HexColor("#1a1a1a"),
        )
        s_li = ParagraphStyle(
            "ListItem", parent=s_body, firstLineIndent=0, leftIndent=12, bulletIndent=0,
        )

        THEME_GREEN = colors.HexColor("#2e7d32")
        TABLE_BORDER = colors.HexColor("#dddddd")
        TABLE_HEAD_BG = colors.HexColor("#f5f5f5")

        # ── 结构化 HTML 解析器：生成 reportlab Flowable 列表 ────────────────
        class _StructureParser(HTMLParser):
            """把 HTML 解析为一组带样式语义的『块』，再由上层转为 Flowable。"""

            def __init__(self):
                super().__init__()
                # blocks: list of dict:
                #   {"type": "title|h2|h3|p|ul|table|spacer", ...}
                self.blocks: list[dict] = []
                self._buf: list[str] = []               # 当前文本累积
                # 标签栈
                self._stack: list[str] = []
                # 列表累积
                self._ul_items: list[str] = []
                # 表格累积
                self._table_rows: list[list[str]] = []  # 所有行（含表头）
                self._row_types: list[bool] = []        # 每行是否为表头行（含 th）
                self._cur_row: list[str] = []
                self._cur_row_has_th = False
                self._cur_cell_buf: list[str] = []
                # <style>/<script> 跳过
                self._skip = False

            def _flush_text(self) -> str:
                text = "".join(self._buf)
                self._buf = []
                # 合并空白、还原实体
                text = " ".join(text.split())
                return _html_unescape(text)

            def _flush_cell(self, is_th: bool) -> None:
                text = "".join(self._cur_cell_buf)
                text = " ".join(text.split())
                self._cur_row.append(_html_unescape(text))
                if is_th:
                    self._cur_row_has_th = True
                self._cur_cell_buf = []

            def handle_starttag(self, tag: str, attrs: list) -> None:
                tag = tag.lower()
                if tag in ("style", "script"):
                    self._skip = True
                    return
                if self._skip:
                    return
                self._stack.append(tag)

                if tag == "br":
                    # 强制换行：在缓冲里放一个显式标记
                    self._buf.append("\n")
                elif tag == "table":
                    self._table_rows = []
                    self._row_types = []
                elif tag == "tr":
                    self._cur_row = []
                    self._cur_row_has_th = False
                elif tag in ("th", "td"):
                    self._cur_cell_buf = []

            def handle_endtag(self, tag: str) -> None:
                tag = tag.lower()
                if tag in ("style", "script"):
                    self._skip = False
                    return
                if self._skip:
                    return
                # 弹出匹配的栈顶（忽略不匹配）
                if self._stack and self._stack[-1] == tag:
                    self._stack.pop()

                if tag in ("h2",):
                    text = self._flush_text()
                    if text:
                        self.blocks.append({"type": "h2", "text": text})
                elif tag == "h3":
                    text = self._flush_text()
                    if text:
                        self.blocks.append({"type": "h3", "text": text})
                elif tag == "p":
                    text = self._flush_text()
                    if text:
                        self.blocks.append({"type": "p", "text": text})
                elif tag == "div":
                    text = self._flush_text()
                    if text:
                        # div 当作不带首行缩进的段落（一般用于容器/小节包装）
                        self.blocks.append({"type": "p", "text": text, "no_indent": True})
                elif tag == "li":
                    text = self._flush_text()
                    if text:
                        self._ul_items.append(text)
                elif tag == "ul":
                    if self._ul_items:
                        self.blocks.append({"type": "ul", "items": list(self._ul_items)})
                    self._ul_items = []
                elif tag == "th":
                    self._flush_cell(is_th=True)
                elif tag == "td":
                    self._flush_cell(is_th=False)
                elif tag == "tr":
                    if self._cur_row:
                        self._table_rows.append(list(self._cur_row))
                        self._row_types.append(self._cur_row_has_th)
                    self._cur_row = []
                    self._cur_row_has_th = False
                elif tag == "table":
                    if self._table_rows:
                        # 统计连续的表头行（从第 0 行开始含 th 的行数）
                        header_rows = 0
                        for is_h in self._row_types:
                            if is_h:
                                header_rows += 1
                            else:
                                break
                        self.blocks.append({
                            "type": "table",
                            "rows": [list(r) for r in self._table_rows],
                            "header_rows": header_rows,
                        })
                    self._table_rows = []
                    self._row_types = []

            def handle_data(self, data: str) -> None:
                if self._skip:
                    return
                # 根据当前所在标签，决定把文本累积到哪里
                if "table" in self._stack and ("th" in self._stack or "td" in self._stack):
                    self._cur_cell_buf.append(data)
                else:
                    self._buf.append(data)

        parser = _StructureParser()
        parser.feed(html_content)

        # ── 把结构化 blocks 转为 reportlab Flowables ──────────────────────
        def _para(text: str, style: ParagraphStyle) -> Paragraph:
            # reportlab Paragraph 支持简单 HTML 标签；手动换行转 <br/>
            safe = text.replace("\n", "<br/>")
            return Paragraph(safe, style)

        story: list = []
        for blk in parser.blocks:
            btype = blk["type"]
            if btype == "h2":
                # 报告大标题（一般第一个 h2 就是 report title）
                if not story:
                    story.append(_para(blk["text"], s_report_title))
                    # 模拟 CSS 中 h2 的绿色下划线
                    story.append(Table(
                        [[""]],
                        colWidths=[170 * mm],
                        style=TableStyle([
                            ("LINEBELOW", (0, 0), (-1, -1), 2, THEME_GREEN),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ]),
                    ))
                else:
                    story.append(_para(blk["text"], s_h2))
                    story.append(Table(
                        [[""]],
                        colWidths=[170 * mm],
                        style=TableStyle([
                            ("LINEBELOW", (0, 0), (-1, -1), 1.5, THEME_GREEN),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ]),
                    ))
                story.append(Spacer(1, 4 * mm))
            elif btype == "h3":
                story.append(_para(blk["text"], s_h3))
            elif btype == "p":
                st = s_body_no_indent if blk.get("no_indent") else s_body
                story.append(_para(blk["text"], st))
                story.append(Spacer(1, 1.2 * mm))
            elif btype == "ul":
                # 用带前缀圆点的段落模拟列表（兼容性更好，兼容 reportlab 各版本）
                for it in blk["items"]:
                    story.append(_para("•  " + it, s_li))
                story.append(Spacer(1, 2 * mm))
            elif btype == "table":
                rows = blk["rows"]
                header_rows = blk["header_rows"]
                if not rows:
                    continue
                # 归一化列数（短行补空）
                ncols = max(len(r) for r in rows)
                norm_rows = []
                for ri, r in enumerate(rows):
                    rr = list(r) + [""] * (ncols - len(r))
                    cs = s_table_header if (ri < header_rows) else s_table_cell
                    norm_rows.append([
                        _para(cell, cs) if (cell and cell.strip()) else Paragraph("", cs)
                        for cell in rr
                    ])

                # 列宽：平均分配可用宽度
                content_width = 170 * mm
                col_widths = [content_width / ncols] * ncols

                tbl = Table(norm_rows, colWidths=col_widths, repeatRows=header_rows)
                tstyle_cmds = [
                    # 全部格子加边框（与 CSS 一致）
                    ("GRID", (0, 0), (-1, -1), 0.5, TABLE_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
                if header_rows > 0:
                    tstyle_cmds += [
                        ("BACKGROUND", (0, 0), (-1, header_rows - 1), TABLE_HEAD_BG),
                    ]
                tbl.setStyle(TableStyle(tstyle_cmds))
                story.append(Spacer(1, 1.5 * mm))
                story.append(tbl)
                story.append(Spacer(1, 2 * mm))

        # 生成 PDF
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            topMargin=20 * mm, bottomMargin=20 * mm,
            leftMargin=20 * mm, rightMargin=20 * mm,
            title="耕地质量报告",
        )
        doc.build(story)
        pdf_bytes = buf.getvalue()
        print(f"[PDF] reportlab 结构化生成成功，块数: {len(parser.blocks)}, 大小: {len(pdf_bytes)} bytes", flush=True)
        return pdf_bytes
    except ImportError as e:
        print(f"[PDF] reportlab 未安装: {e}", flush=True)
    except Exception as e:
        import traceback
        print(f"[PDF] reportlab 结构化降级失败: {e}\n{traceback.format_exc()}", flush=True)

    # 最终降级：返回纯文本字节
    print(f"[PDF] 最终降级为纯文本，大小: {len(html_content.encode('utf-8'))} bytes", flush=True)
    return html_content.encode("utf-8")
