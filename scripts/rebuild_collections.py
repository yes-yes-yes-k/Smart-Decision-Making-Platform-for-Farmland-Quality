"""按 category 将 enterprise_kb 旧 chunk 迁移到分领域 collection。

旧 enterprise_kb 保留为 fallback；category 为空/other 的 chunk 仍留在默认库，不重复写入。
使用方法:
    python scripts/rebuild_collections.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chromadb
import sqlite3
from chromadb.config import Settings

from framework.config import Config
from framework.vector_store.chroma_store import vector_store


def _build_source_category_map() -> dict:
    """读 kb_document 表，构建 source(doc_name/file_path) → category 映射。"""
    mapping = {}
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           'instance', 'development.db')
    if not os.path.exists(db_path):
        print(f"数据库不存在: {db_path}")
        return mapping
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT doc_name, file_path, category FROM kb_document")
        for doc_name, file_path, category in cursor.fetchall():
            cat = category or "other"
            mapping[doc_name] = cat
            mapping[file_path] = cat
        conn.close()
        print(f"数据库中找到 {len(mapping)} 条 source→category 映射")
    except Exception as e:
        print(f"查询数据库失败: {e}")
    return mapping


def rebuild_collections():
    source_cat = _build_source_category_map()

    persist_dir = os.path.abspath(Config.CHROMA_PERSIST_DIR)
    client = chromadb.PersistentClient(
        path=persist_dir,
        settings=Settings(anonymized_telemetry=False, allow_reset=False),
    )

    old = client.get_collection(name=Config.CHROMA_COLLECTION_NAME)
    data = old.get()
    ids = data.get("ids", [])
    documents = data.get("documents", [])
    metadatas = data.get("metadatas", [])

    migrated = 0
    skipped = 0
    for i, doc_id in enumerate(ids):
        text = documents[i]
        meta = dict(metadatas[i] or {})
        source = meta.get("source", "")
        category = source_cat.get(source, "other")
        if not category or category.strip().lower() == "other":
            skipped += 1
            continue
        meta["category"] = category
        vector_store.add_documents([text], [meta], [doc_id], category=category)
        migrated += 1

    print(f"\n迁移完成: 迁移 {migrated} 个 chunk，跳过 {skipped} 个（留在默认库）")


if __name__ == "__main__":
    print("=" * 50)
    print("分领域 collection 重建脚本")
    print("=" * 50)
    rebuild_collections()