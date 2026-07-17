"""重新索引 uploads/ 中的文档到向量存储"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
from framework.upload.document_parser import parse_document
from framework.upload.file_upload import get_file_type
from framework.vector_store.chroma_store import vector_store


def reindex_uploads():
    upload_dir = Config.UPLOAD_FOLDER
    if not os.path.exists(upload_dir):
        print(f"uploads 目录不存在: {upload_dir}")
        return

    files = [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]
    print(f"发现 {len(files)} 个文件")

    stats = vector_store.get_collection_stats()
    print(f"索引前向量存储文档数: {stats['count']}")

    indexed = 0
    skipped = 0
    for filename in files:
        file_path = os.path.join(upload_dir, filename)
        file_type = get_file_type(filename)
        if file_type == 'other':
            print(f"  跳过(不支持): {filename}")
            skipped += 1
            continue

        content = parse_document(file_path, file_type)
        if not content or not content.strip():
            print(f"  跳过(无内容): {filename}")
            skipped += 1
            continue

        chunks = [content[i:i+800] for i in range(0, len(content), 800)]
        doc_name = filename
        metadatas = [{"source": doc_name} for _ in chunks]
        ids = [f"{uuid.uuid4().hex}" for _ in chunks]

        vector_store.add_documents(chunks, metadatas, ids)
        print(f"  已索引: {filename} ({len(chunks)} 片段)")
        indexed += 1

    stats = vector_store.get_collection_stats()
    print(f"\n索引完成: {indexed} 个文档已索引, {skipped} 个跳过")
    print(f"索引后向量存储文档数: {stats['count']}")


if __name__ == "__main__":
    reindex_uploads()
