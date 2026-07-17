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
    assert hasattr(Document, 'file_hash')
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
    doc.file_hash = "abc123def456"

    result = doc.to_dict()
    assert result["doc_name"] == "test.pdf"
    assert result["file_type"] == "pdf"
    assert result["file_size"] == 1024
    assert result["chunk_count"] == 5
    assert result["file_hash"] == "abc123def456"
    print("✓ 文档模型 to_dict 方法正常")

def test_compute_file_hash_empty_file():
    """测试空文件的SHA-256哈希"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    test_file = os.path.join(os.path.dirname(__file__), "test_empty_hash.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("")

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(b"").hexdigest()
    assert result == expected
    assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    print("✓ 空文件哈希正确")
    os.remove(test_file)

def test_compute_file_hash_small_file():
    """测试小文件SHA-256哈希正确性与一致性"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    content = "这是测试文本内容，用于验证哈希计算。\n第二行内容。"
    test_file = os.path.join(os.path.dirname(__file__), "test_small_hash.txt")
    with open(test_file, 'wb') as f:
        f.write(content.encode('utf-8'))

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
    assert result == expected

    # 相同内容不同文件名，哈希应一致
    test_file2 = os.path.join(os.path.dirname(__file__), "test_small_hash_copy.txt")
    with open(test_file2, 'wb') as f:
        f.write(content.encode('utf-8'))
    result2 = compute_file_hash(test_file2)
    assert result == result2
    print("✓ 小文件哈希正确且一致")
    os.remove(test_file)
    os.remove(test_file2)

def test_compute_file_hash_large_file_chunked():
    """测试大文件分块读取哈希正确性（超过8192字节触发多次分块）"""
    import hashlib
    from framework.upload.file_upload import compute_file_hash
    # 生成 20000 字节内容，确保超过 chunk_size=8192 触发多次分块
    content = "A" * 20000
    test_file = os.path.join(os.path.dirname(__file__), "test_large_hash.txt")
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write(content)

    result = compute_file_hash(test_file)
    expected = hashlib.sha256(content.encode('utf-8')).hexdigest()
    assert result == expected

    # 验证自定义 chunk_size 不影响结果
    result_custom_chunk = compute_file_hash(test_file, chunk_size=1024)
    assert result == result_custom_chunk
    print("✓ 大文件分块哈希正确")
    os.remove(test_file)

if __name__ == "__main__":
    test_allowed_file()
    test_get_file_type()
    test_parse_txt()
    test_parse_md()
    test_document_model_fields()
    test_document_to_dict()
    print("\n所有文档上传和管理功能测试通过！")
