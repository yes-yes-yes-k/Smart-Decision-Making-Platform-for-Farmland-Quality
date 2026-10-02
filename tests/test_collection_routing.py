"""测试分领域 collection 路由（离线，不触发 Chroma 初始化）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from framework.config import Config
from framework.vector_store.chroma_store import (
    ChromaVectorStore,
    slugify,
    collection_name_for,
)
from framework.rag.category_router import route_category


class FakeCollection:
    def __init__(self, name):
        self.name = name


class FakeClient:
    def __init__(self):
        self.created = []

    def get_or_create_collection(self, name, embedding_function=None):
        self.created.append(name)
        return FakeCollection(name)


def test_slugify_normalizes():
    assert slugify(" Acidification ") == "acidification"
    assert slugify("organic_matter") == "organic_matter"
    # 纯中文无 ASCII → 归一为 other（回退到默认库）
    assert slugify("酸化改良") == "other"


def test_collection_name_default_for_other():
    assert collection_name_for(None) == Config.CHROMA_COLLECTION_NAME
    assert collection_name_for("") == Config.CHROMA_COLLECTION_NAME
    assert collection_name_for("other") == Config.CHROMA_COLLECTION_NAME


def test_collection_name_specific():
    assert collection_name_for("acidification") == "kb_acidification"


def test_get_collection_routes_by_category():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._client = FakeClient()
    store._collections = {}
    store._bm25 = {}

    c1 = store._get_collection("acidification")
    c2 = store._get_collection("acidification")
    assert c1 is c2  # 懒创建后缓存命中
    assert c1.name == "kb_acidification"
    assert store._client.created == ["kb_acidification"]


def test_get_collection_default_for_other_category():
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._client = FakeClient()
    store._collections = {}
    store._bm25 = {}
    c = store._get_collection("other")
    assert c.name == Config.CHROMA_COLLECTION_NAME


def test_targeted_collection_hit_and_miss():
    acid = FakeCollection("kb_acidification")
    default = FakeCollection(Config.CHROMA_COLLECTION_NAME)

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store._collections = {Config.CHROMA_COLLECTION_NAME: default, "kb_acidification": acid}
    store._bm25 = {}

    # 命中：category 具体且 collection 存在 → 定向
    assert store._targeted_collection("acidification") is acid
    # 未命中：collection 不存在 → 全库回退
    assert store._targeted_collection("grade") is None
    # 空 / other → 全库回退
    assert store._targeted_collection(None) is None
    assert store._targeted_collection("other") is None
    # 多标签领域必须跨 collection 检索，不能只看文档的主分类集合。
    assert store._targeted_collection("heavy_metal") is None


def test_new_agent_domain_routing():
    assert route_category("镉污染的空间风险如何评估") == "heavy_metal"
    assert route_category("未来粮食产能预测") == "food_security"
    assert route_category("耕地质量全链条分析") == "cultivated_land_quality"
