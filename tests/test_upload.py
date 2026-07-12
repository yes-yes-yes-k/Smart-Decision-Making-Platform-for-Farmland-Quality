"""测试文档上传和管理功能"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.upload.file_upload import allowed_file, get_file_type
from framework.upload.document_parser import parse_document

def test_allowed_file():
    """测试文件类型验证"""
    assert allowed_file("test.txt") is True
    assert allowed_file("test.md") is True
    assert allowed_file("test.pdf") is True
    assert allowed_file("test.docx") is True
    assert allowed_file("test.xlsx") is True
    assert allowed_file("test.zip") is False
    assert allowed_file("test.exe") is False
    assert allowed_file("noextension") is False
    print("✓ 文件类型验证正确")

def test_get_file_type():
    """测试文件类型获取"""
    assert get_file_type("test.txt") == "txt"
    assert get_file_type("test.md") == "md"
    assert get_file_type("test.pdf") == "pdf"
    assert get_file_type("test.docx") == "docx"
    assert get_file_type("test.xlsx") == "xlsx"
    assert get_file_type("test.xls") == "xlsx"
    assert get_file_type("test.unknown") == "other"
    print("✓ 文件类型获取正确")

def test_parse_txt():
    """测试文本文件解析"""
    test_file = os.path.join(os.path.dirname(__file__), "test_temp.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("这是测试文本内容。\n第二行内容。")

    content = parse_document(test_file, "txt")
    assert "测试文本内容" in content
    assert "第二行内容" in content
    print("✓ 文本文件解析成功")

    os.remove(test_file)

def test_parse_md():
    """测试 Markdown 文件解析"""
    test_file = os.path.join(os.path.dirname(__file__), "test_temp.md")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("# 标题\n\nMarkdown 内容")

    content = parse_document(test_file, "md")
    assert "标题" in content
    assert "Markdown 内容" in content
    print("✓ Markdown 文件解析成功")

    os.remove(test_file)

def test_document_model_fields():
    """测试文档模型字段定义"""
    from framework.models.document import Document
    assert Document.__tablename__ == 'kb_document'
    assert hasattr(Document, 'doc_name')
    assert hasattr(Document, 'file_path')
    assert hasattr(Document, 'file_type')
    assert hasattr(Document, 'file_size')
    assert hasattr(Document, 'chunk_count')
    assert hasattr(Document, 'status')
    assert hasattr(Document, 'category')
    assert hasattr(Document, 'create_by')
    print("✓ 文档模型字段定义正确")

def test_document_to_dict():
    """测试文档模型 to_dict 方法"""
    from framework.models.document import Document
    doc = Document()
    doc.id = 1
    doc.doc_name = "test.pdf"
    doc.file_type = "pdf"
    doc.file_size = 1024
    doc.chunk_count = 5
    doc.status = 1
    doc.category = "report"
    doc.create_by = 1

    result = doc.to_dict()
    assert result["doc_name"] == "test.pdf"
    assert result["file_type"] == "pdf"
    assert result["file_size"] == 1024
    assert result["chunk_count"] == 5
    print("✓ 文档模型 to_dict 方法正常")

if __name__ == "__main__":
    test_allowed_file()
    test_get_file_type()
    test_parse_txt()
    test_parse_md()
    test_document_model_fields()
    test_document_to_dict()
    print("\n所有文档上传和管理功能测试通过！")
