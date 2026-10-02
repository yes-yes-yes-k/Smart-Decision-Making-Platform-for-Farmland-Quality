from framework.upload.document_parser import parse_document


def test_csv_is_parsed(tmp_path):
    path = tmp_path / "soil.csv"
    path.write_text("指标,数值\npH,5.2\n", encoding="utf-8")

    text = parse_document(str(path), "csv")

    assert "指标" in text
    assert "5.2" in text


def test_excel_reads_all_sheets(tmp_path):
    import pandas as pd

    path = tmp_path / "soil.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"指标": ["pH"]}).to_excel(writer, sheet_name="酸化", index=False)
        pd.DataFrame({"污染物": ["镉"]}).to_excel(writer, sheet_name="重金属", index=False)

    text = parse_document(str(path), "xlsx")

    assert "工作表: 酸化" in text
    assert "工作表: 重金属" in text
    assert "镉" in text


def test_docx_keeps_paragraphs_and_tables(tmp_path):
    from docx import Document

    path = tmp_path / "mixed.docx"
    document = Document()
    document.add_paragraph("酸化治理说明")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "材料"
    table.cell(0, 1).text = "石灰"
    document.save(path)

    text = parse_document(str(path), "docx")

    assert "酸化治理说明" in text
    assert "材料 | 石灰" in text
