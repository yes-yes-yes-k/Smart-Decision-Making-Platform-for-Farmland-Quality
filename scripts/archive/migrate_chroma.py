"""迁移 Chroma 向量库数据

从源项目的 Chroma 向量库迁移数据到统一框架的向量库。
支持从 AI_culti_demo -send 和 org-backend 两个源项目迁移。

使用方法:
    python scripts/migrate_chroma.py [--source <path>]

如果不指定 --source，将自动检测源项目的 Chroma 数据目录。
"""
import sys
import os
import shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from framework.config import Config
from framework.vector_store.chroma_store import vector_store

def find_source_chroma_dirs():
    """查找源项目的 Chroma 数据目录"""
    possible_paths = [
        r"D:\17417\Documents\AI_culti_demo -send\chroma_db",
        r"D:\17417\Documents\org-backend\chroma_db",
        r"D:\17417\Documents\AI_culti_demo -send\vector_db",
        r"D:\17417\Documents\org-backend\vector_db",
    ]
    found = []
    for path in possible_paths:
        if os.path.exists(path):
            found.append(path)
    return found

def migrate_from_directory(source_dir: str):
    """从指定目录迁移 Chroma 数据"""
    print(f"\n从 {source_dir} 迁移数据...")

    target_dir = Config.CHROMA_PERSIST_DIR
    os.makedirs(target_dir, exist_ok=True)

    try:
        import chromadb
        from chromadb.config import Settings

        source_client = chromadb.PersistentClient(
            path=source_dir,
            settings=Settings(anonymized_telemetry=False)
        )

        source_collections = source_client.list_collections()
        print(f"  源集合: {[c.name for c in source_collections]}")

        for collection in source_collections:
            data = collection.get()
            if not data or not data.get("ids"):
                print(f"  集合 {collection.name} 为空，跳过")
                continue

            texts = data.get("documents", [])
            metadatas = data.get("metadatas", [])
            ids = data.get("ids", [])

            count = vector_store.add_documents(texts, metadatas, ids)
            print(f"  ✓ 集合 {collection.name}: 迁移了 {count} 条文档")

    except Exception as e:
        print(f"  ✗ 迁移失败: {e}")
        # 回退：直接复制文件
        print(f"  尝试直接复制文件...")
        try:
            for item in os.listdir(source_dir):
                s = os.path.join(source_dir, item)
                d = os.path.join(target_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
            print(f"  ✓ 文件复制完成")
        except Exception as copy_err:
            print(f"  ✗ 文件复制也失败: {copy_err}")

def verify_migration():
    """验证迁移结果"""
    stats = vector_store.get_collection_stats()
    print(f"\n迁移后向量库统计:")
    print(f"  集合名称: {stats.get('name', '')}")
    print(f"  文档数量: {stats.get('count', 0)}")

    # 测试搜索
    if stats.get("count", 0) > 0:
        results = vector_store.search("土壤酸化", n_results=3)
        print(f"  搜索测试: 找到 {results['count']} 条结果")
        for i, r in enumerate(results["results"]):
            source = r.get("metadata", {}).get("source", "unknown")
            content = r.get("content", "")[:100]
            print(f"    {i+1}. [{source}] {content}...")

if __name__ == "__main__":
    print("=" * 50)
    print("Chroma 向量库迁移脚本")
    print("=" * 50)

    source_arg = None
    if len(sys.argv) > 2 and sys.argv[1] == "--source":
        source_arg = sys.argv[2]

    if source_arg:
        sources = [source_arg]
    else:
        sources = find_source_chroma_dirs()

    if not sources:
        print("未找到源项目的 Chroma 数据目录")
        print("请使用 --source 参数指定源路径")
        sys.exit(1)

    print(f"找到 {len(sources)} 个源数据目录")

    for source in sources:
        migrate_from_directory(source)

    verify_migration()
    print("\n向量库迁移完成！")
