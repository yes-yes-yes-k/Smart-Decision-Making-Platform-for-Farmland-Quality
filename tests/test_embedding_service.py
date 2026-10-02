"""测试 EmbeddingService 输入校验与批量降级。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from framework.embedding.service import EmbeddingService


@pytest.fixture
def svc(monkeypatch):
    """创建带确定性桩 _call_api 的 EmbeddingService，避免真实 API 调用。"""
    svc = EmbeddingService.__new__(EmbeddingService)
    svc._api_key = "stub-key"
    svc._api_base = "https://stub/v1"
    svc._model = "BAAI/bge-m3"
    svc._initialized = True

    calls = []

    def _stub_call_api(texts):
        calls.append(list(texts))
        return [[0.1] * 4 for _ in texts]

    svc._call_api = _stub_call_api
    svc._calls = calls
    return svc


def _dim(vec):
    return len(vec) if vec else 0


# ── embed_documents 输入过滤 ──────────────────────────────────────

def test_embed_documents_filters_none_elements(svc):
    """列表中含 None 时应过滤，None 位置返回空向量，其他位置正常。"""
    result = svc.embed_documents(["土壤酸化", None, "有效钾"])
    assert len(result) == 3
    assert _dim(result[0]) > 0    # 正常文本
    assert _dim(result[1]) == 0   # None → 空向量
    assert _dim(result[2]) > 0    # 正常文本
    # _call_api 只收到合法元素
    assert svc._calls == [["土壤酸化", "有效钾"]]


def test_embed_documents_filters_non_string(svc):
    """列表中含数字/布尔等非字符串时应过滤。"""
    result = svc.embed_documents(["土壤酸化", 123, True, "交换性氢"])
    assert len(result) == 4
    assert _dim(result[0]) > 0
    assert _dim(result[1]) == 0   # 数字 → 空向量
    assert _dim(result[2]) == 0   # 布尔 → 空向量
    assert _dim(result[3]) > 0
    assert svc._calls == [["土壤酸化", "交换性氢"]]


def test_embed_documents_all_invalid_returns_empty_list(svc):
    """全部非法时返回对应数量的空向量，不调用 API。"""
    result = svc.embed_documents([None, 0, None])
    assert len(result) == 3
    assert all(_dim(r) == 0 for r in result)
    assert svc._calls == []  # 未调用 API


def test_embed_documents_empty_list(svc):
    """空列表直接返回空列表。"""
    assert svc.embed_documents([]) == []
    assert svc._calls == []


def test_embed_documents_empty_string_is_valid(svc):
    """空字符串/空白是合法输入（API 可接受），不被过滤。"""
    result = svc.embed_documents(["", "  ", "正常文本"])
    assert len(result) == 3
    assert _dim(result[0]) > 0
    assert _dim(result[1]) > 0
    assert _dim(result[2]) > 0
    assert svc._calls == [["", "  ", "正常文本"]]


def test_embed_documents_batches_large_requests(svc):
    svc._batch_size = 2

    result = svc.embed_documents(["a", "b", "c", "d", "e"])

    assert all(_dim(vector) > 0 for vector in result)
    assert svc._calls == [["a", "b"], ["c", "d"], ["e"]]


# ── embed_query 输入校验 ──────────────────────────────────────────

def test_embed_query_none_returns_empty(svc):
    """None → 返回空向量。"""
    assert svc.embed_query(None) == []
    assert svc._calls == []


def test_embed_query_non_string_returns_empty(svc):
    """数字/布尔 → 返回空向量。"""
    assert svc.embed_query(123) == []
    assert svc.embed_query(True) == []
    assert svc._calls == []


def test_embed_query_empty_string_is_valid(svc):
    """空字符串是合法输入。"""
    result = svc.embed_query("")
    assert _dim(result) > 0
    assert svc._calls == [[""]]


def test_embed_query_normal_string(svc):
    """正常文本正常调用。"""
    result = svc.embed_query("土壤酸化")
    assert _dim(result) > 0
    assert svc._calls == [["土壤酸化"]]


# ── is_available 未初始化时的降级 ──────────────────────────────────

def test_uninitialized_embed_documents_returns_empty():
    """未配置 API key 时，embed_documents 返回同长度空向量列表。"""
    svc = EmbeddingService.__new__(EmbeddingService)
    svc._api_key = ""
    svc._api_base = "https://stub/v1"
    svc._model = "BAAI/bge-m3"
    svc._initialized = False

    result = svc.embed_documents(["土壤酸化", "有效钾"])
    assert len(result) == 2
    assert all(_dim(r) == 0 for r in result)


def test_uninitialized_embed_query_returns_empty():
    """未配置 API key 时，embed_query 返回空向量。"""
    svc = EmbeddingService.__new__(EmbeddingService)
    svc._api_key = ""
    svc._api_base = "https://stub/v1"
    svc._model = "BAAI/bge-m3"
    svc._initialized = False
    assert svc.embed_query("土壤酸化") == []
