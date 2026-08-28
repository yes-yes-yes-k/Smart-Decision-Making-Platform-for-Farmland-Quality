from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .report_templates import REPORT_TEMPLATES
from framework.llm.service import llm_service


DEFAULT_ACTIONS = [
    "核验核心字段映射和数据来源",
    "确认推荐图层是否可用于当前汇报场景",
    "在真实模型接入后复核诊断结论",
]


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


def generate_report(report_type: str, area_code: str) -> dict[str, Any]:
    """根据报告模板和 AI 生成完整报告。"""

    template = REPORT_TEMPLATES.get(report_type)
    if template is None:
        return {
            "status": "error",
            "error": {
                "code": "UNKNOWN_REPORT_TYPE",
                "message": f"未知的报告类型: {report_type}",
            },
        }

    title = template["title"]
    sections = template["sections"]

    # 准备所有章节的提示词（保持顺序）
    prompts: list[dict[str, str]] = [
        {"heading": s["heading"], "prompt": s["prompt_hint"].replace("area_code", area_code)}
        for s in sections
    ]

    # 并行调用 LLM 生成所有章节
    def _gen_section(idx: int, prompt: str) -> tuple[int, str]:
        result = llm_service.generate(prompt)
        if result.get("success"):
            return idx, result["content"]
        return idx, "<p>（本小节内容因 AI 服务暂时不可用而无法生成，请稍后重试。）</p>"

    section_results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=len(prompts)) as executor:
        futures = {
            executor.submit(_gen_section, i, p["prompt"]): i
            for i, p in enumerate(prompts)
        }
        for future in as_completed(futures):
            idx, content = future.result()
            section_results[idx] = content

    # 按模板顺序拼接 HTML
    sections_html_parts: list[str] = []
    for i, p in enumerate(prompts):
        heading = p["heading"]
        section_content = section_results.get(i, "<p>（生成失败）</p>")
        section_html = (
            f'<div class="report-section">\n'
            f"<h3>{heading}</h3>\n"
            f"{section_content}\n"
            f"</div>"
        )
        sections_html_parts.append(section_html)

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

    return {
        "status": "ok",
        "title": title,
        "content": full_html,
        "report_type": report_type,
        "area_code": area_code,
    }


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

    # 降级方案：使用 reportlab 生成纯文本 PDF
    try:
        from io import BytesIO
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from html.parser import HTMLParser

        # 注册中文字体：兼容 Windows / Linux
        _chinese_font = "ChineseFont"
        _font_paths = [
            # Windows
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

        class _TextExtractor(HTMLParser):
            """从 HTML 中提取纯文本内容。"""

            def __init__(self):
                super().__init__()
                self.lines: list[str] = []
                self._skip = False

            def handle_starttag(self, tag: str, attrs: list) -> None:
                if tag in ("style", "script"):
                    self._skip = True

            def handle_endtag(self, tag: str) -> None:
                if tag in ("style", "script"):
                    self._skip = False
                elif tag in ("p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br"):
                    self.lines.append("")

            def handle_data(self, data: str) -> None:
                if not self._skip:
                    text = data.strip()
                    if text:
                        self.lines.append(text)

        extractor = _TextExtractor()
        extractor.feed(html_content)
        text_lines = extractor.lines

        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName=_chinese_font,
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["Normal"],
            fontName=_chinese_font,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
        )

        story = []
        for line in text_lines:
            if not story:
                story.append(Paragraph(line, title_style))
                story.append(Spacer(1, 6 * mm))
            else:
                story.append(Paragraph(line, body_style))
                story.append(Spacer(1, 2 * mm))

        doc.build(story)
        pdf_bytes = buf.getvalue()
        print(f"[PDF] reportlab 生成成功，行数: {len(text_lines)}, 大小: {len(pdf_bytes)} bytes", flush=True)
        return pdf_bytes
    except ImportError as e:
        print(f"[PDF] reportlab 未安装: {e}", flush=True)
    except Exception as e:
        print(f"[PDF] 降级方案也失败: {e}", flush=True)

    # 最终降级：返回纯文本字节
    print(f"[PDF] 最终降级为纯文本，大小: {len(html_content.encode('utf-8'))} bytes", flush=True)
    return html_content.encode("utf-8")
