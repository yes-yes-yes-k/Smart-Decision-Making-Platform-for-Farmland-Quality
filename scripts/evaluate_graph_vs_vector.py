from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VENV_SITE = ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
import requests
from sklearn.feature_extraction.text import TfidfVectorizer

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - the project environment includes python-dotenv
    load_dotenv = None


GRAPH_PATH = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json"
GOLD_PATH = ROOT / "artifacts" / "minimal_kg" / "gold_qa_v0.2.json"
RESULT_PATH = ROOT / "artifacts" / "minimal_kg" / "retrieval_comparison_v0.2.json"
REPORT_PATH = ROOT / "artifacts" / "minimal_kg" / "retrieval_comparison_report_v0.2.md"
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "kb_cultivated_land_quality"

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def relation_key(relation_type: str, source: str, target: str) -> tuple[str, str, str]:
    return relation_type, source, target


# Four categories, ten questions each. Questions are intentionally phrased as
# normal user requests rather than copies of the evidence text.
QUESTION_PLANS: list[dict[str, Any]] = [
    # 指标解释
    {"category": "指标解释", "question": "土壤板结通常可用哪个土壤物理指标来表征？", "relation": ("characterized_by", "obstacle:compaction", "indicator:bulk_density"), "answer": "土壤板结可表现为或伴随土壤容重升高。", "keywords": ["土壤板结", "容重"]},
    {"category": "指标解释", "question": "GB/T 33469 的耕地质量评价是否把灌溉能力列为指标？", "relation": ("includes_indicator", "standard:doc-4", "indicator:irrigation"), "answer": "是，GB/T 33469 将灌溉能力纳入耕地质量评价指标。", "keywords": ["灌溉能力", "指标"]},
    {"category": "指标解释", "question": "GB/T 33469 中排水能力在评价体系里是什么角色？", "relation": ("includes_indicator", "standard:doc-4", "indicator:drainage"), "answer": "排水能力是 GB/T 33469 耕地质量评价指标之一。", "keywords": ["排水能力", "指标"]},
    {"category": "指标解释", "question": "耕层厚度是否属于 GB/T 33469 的区域补充性指标？", "relation": ("includes_indicator", "standard:doc-4", "indicator:plough_depth"), "answer": "是，耕层厚度被列入 GB/T 33469 的区域补充性指标。", "keywords": ["耕层厚度", "区域", "指标"]},
    {"category": "指标解释", "question": "广东省补充耕地质量鉴定规范是否把土壤pH纳入评价检测指标？", "relation": ("includes_indicator", "standard:doc-14", "indicator:soil_ph"), "answer": "是，该规范将土壤pH（酸碱度）纳入评价检测指标。", "keywords": ["土壤", "酸碱度", "指标"]},
    {"category": "指标解释", "question": "广东省补充耕地质量鉴定规范中有效土层厚度属于什么指标？", "relation": ("includes_indicator", "standard:doc-14", "indicator:effective_depth"), "answer": "有效土层厚度属于农业生产符合性评价指标。", "keywords": ["有效土层厚度", "农业生产", "指标"]},
    {"category": "指标解释", "question": "广东省补充耕地质量验收细则是否评价土壤有机质？", "relation": ("includes_indicator", "standard:doc-13", "indicator:organic_matter"), "answer": "是，验收细则把土壤有机质纳入农业生产符合性评价指标。", "keywords": ["土壤有机质", "评价指标"]},
    {"category": "指标解释", "question": "补充耕地质量鉴定规范如何规定耕层土壤质地的测定？", "relation": ("prescribes_measurement", "standard:doc-11", "indicator:texture"), "answer": "该规范规定开展耕层土壤质地（机械组成）测定。", "keywords": ["耕层", "土壤质地", "测定"]},
    {"category": "指标解释", "question": "补充耕地质量鉴定规范对土壤有效磷如何检测？", "relation": ("prescribes_measurement", "standard:doc-11", "indicator:available_p"), "answer": "该规范引用相应土壤检测方法并设置土壤有效磷测定。", "keywords": ["土壤有效磷", "测定"]},
    {"category": "指标解释", "question": "《补充耕地质量鉴定技术规范（试行）》是否规定土壤速效钾的测定？", "relation": ("prescribes_measurement", "standard:doc-11", "indicator:available_k"), "answer": "是，该规范引用 NY/T 889 规定土壤速效钾测定。", "keywords": ["速效钾", "测定"]},

    # 障碍诊断
    {"category": "障碍诊断", "question": "判断红壤坡耕地土壤板结时，容重信息有什么作用？", "relation": ("characterized_by", "obstacle:compaction", "indicator:bulk_density"), "answer": "容重升高可作为土壤板结的表征信息。", "keywords": ["板结", "容重"]},
    {"category": "障碍诊断", "question": "材料中土壤板结障碍可优先采用哪种机械改良措施？", "relation": ("addresses", "measure:deep_loosening", "obstacle:compaction"), "answer": "可采用深松措施破除土壤板结。", "keywords": ["土壤板结", "深松"]},
    {"category": "障碍诊断", "question": "除深松外，资料还提出哪种少扰动耕作方式解决土壤板结？", "relation": ("addresses", "measure:no_till", "obstacle:compaction"), "answer": "资料提出采用免耕技术解决土壤板结和退化。", "keywords": ["土壤板结", "免耕"]},
    {"category": "障碍诊断", "question": "诊断为土壤酸化后，最直接的调酸措施是什么？", "relation": ("addresses", "measure:liming", "obstacle:acidification"), "answer": "最直接的措施是施用石灰中和土壤酸性。", "keywords": ["土壤酸化", "施用石灰"]},
    {"category": "障碍诊断", "question": "云贵高原酸化土壤可以采用什么调理剂类措施？", "relation": ("addresses", "measure:soil_conditioner", "obstacle:acidification"), "answer": "可以施用土壤调理剂治理酸化土壤。", "keywords": ["土壤调理剂", "酸化土壤"]},
    {"category": "障碍诊断", "question": "长期不合理施肥造成酸化时，应采用什么施肥管理措施？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:acidification"), "answer": "应采用测土配方和平衡施肥，减少酸性或生理酸性肥料影响。", "keywords": ["测土配方施肥", "酸化"]},
    {"category": "障碍诊断", "question": "土壤酸化治理中，秸秆还田主要通过什么思路发挥作用？", "relation": ("addresses", "measure:straw_return", "obstacle:acidification"), "answer": "秸秆还田可增加有机质并增强土壤pH缓冲，帮助维持酸碱平衡。", "keywords": ["秸秆还田", "土壤", "酸碱平衡"]},
    {"category": "障碍诊断", "question": "坡耕地发生侵蚀退化时，可采取哪种耕作改良措施？", "relation": ("addresses", "measure:deep_tillage", "obstacle:erosion"), "answer": "可采用深松与深耕改善土壤结构并减轻侵蚀退化。", "keywords": ["深松", "深耕", "侵蚀"]},
    {"category": "障碍诊断", "question": "土壤肥力或养分不足时，可采用哪种有机培肥措施？", "relation": ("addresses", "measure:organic_fertilizer", "obstacle:nutrient_deficiency"), "answer": "可增施有机肥改善土壤肥力和养分不足。", "keywords": ["有机肥", "土壤肥力"]},
    {"category": "障碍诊断", "question": "表层有机质消耗明显时，哪类耕作方式有助于缓解？", "relation": ("addresses", "measure:conservation_tillage", "obstacle:low_organic_matter"), "answer": "少耕、免耕等保护性耕作有助于减少表层有机质消耗。", "keywords": ["少耕", "免耕", "有机质"]},

    # 改良措施
    {"category": "改良措施", "question": "施用石灰主要针对哪一种耕地障碍？", "relation": ("addresses", "measure:liming", "obstacle:acidification"), "answer": "施用石灰主要用于治理土壤酸化。", "keywords": ["施用石灰", "土壤酸化"]},
    {"category": "改良措施", "question": "深松主要用于解决哪类土壤结构障碍？", "relation": ("addresses", "measure:deep_loosening", "obstacle:compaction"), "answer": "深松主要用于破除土壤板结。", "keywords": ["深松", "土壤板结"]},
    {"category": "改良措施", "question": "免耕在现有证据中对应治理什么问题？", "relation": ("addresses", "measure:no_till", "obstacle:compaction"), "answer": "免耕在现有证据中用于解决土壤板结和退化。", "keywords": ["免耕", "土壤板结"]},
    {"category": "改良措施", "question": "深松深耕对坡耕地侵蚀退化有什么作用？", "relation": ("addresses", "measure:deep_tillage", "obstacle:erosion"), "answer": "深松深耕可改善结构并减轻坡耕地侵蚀退化。", "keywords": ["深松", "深耕", "侵蚀退化"]},
    {"category": "改良措施", "question": "测土配方施肥能否用于酸化土壤的综合治理？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:acidification"), "answer": "可以，测土配方和平衡施肥可减少施肥导致的酸化风险。", "keywords": ["测土配方施肥", "酸化"]},
    {"category": "改良措施", "question": "测土配方施肥对养分缺乏障碍有什么作用？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:nutrient_deficiency"), "answer": "测土配方施肥可按养分状况补充肥力，缓解养分缺乏。", "keywords": ["测土配方施肥", "土壤肥力"]},
    {"category": "改良措施", "question": "增施有机肥主要可以缓解哪类肥力障碍？", "relation": ("addresses", "measure:organic_fertilizer", "obstacle:nutrient_deficiency"), "answer": "增施有机肥可缓解养分缺乏或土壤肥力不足。", "keywords": ["有机肥", "肥力"]},
    {"category": "改良措施", "question": "土壤调理剂在云贵高原材料中主要用于治理什么障碍？", "relation": ("addresses", "measure:soil_conditioner", "obstacle:acidification"), "answer": "土壤调理剂主要用于治理土壤酸化。", "keywords": ["土壤调理剂", "土壤酸化"]},
    {"category": "改良措施", "question": "秸秆还田在酸化耕地调控中有什么作用？", "relation": ("addresses", "measure:straw_return", "obstacle:acidification"), "answer": "秸秆还田可提高有机质和pH缓冲能力，辅助治理酸化。", "keywords": ["秸秆还田", "有机质", "土壤"]},
    {"category": "改良措施", "question": "保护性耕作如何帮助有机质不足的耕地？", "relation": ("addresses", "measure:conservation_tillage", "obstacle:low_organic_matter"), "answer": "少耕、免耕等保护性耕作可减少表层有机质消耗。", "keywords": ["少耕", "免耕", "有机质"]},

    # 标准依据
    {"category": "标准依据", "question": "GB/T 33469 对土壤容重测定有什么规定？", "relation": ("prescribes_measurement", "standard:doc-4", "indicator:bulk_density"), "answer": "GB/T 33469 的规范性附录规定了土壤容重测定方法。", "keywords": ["土壤容重", "测定", "附录"]},
    {"category": "标准依据", "question": "GB/T 33469 是否给出土壤有机质的测定依据？", "relation": ("prescribes_measurement", "standard:doc-4", "indicator:organic_matter"), "answer": "是，GB/T 33469 的附录给出土壤有机质测定要求。", "keywords": ["土壤有机质", "测定", "附录"]},
    {"category": "标准依据", "question": "GB/T 33469 如何规定土壤质地或机械组成测定？", "relation": ("prescribes_measurement", "standard:doc-4", "indicator:texture"), "answer": "GB/T 33469 将土壤机械组成分级并在附录规定测定方法。", "keywords": ["土壤机械组成", "测定", "附录"]},
    {"category": "标准依据", "question": "NY/T 1634 对土壤有效磷测定引用了哪些方法？", "relation": ("prescribes_measurement", "standard:doc-3", "indicator:available_p"), "answer": "NY/T 1634 引用土壤有效磷测定方法，包括酸性或石灰性土壤的相应方法。", "keywords": ["土壤有效磷", "测定"]},
    {"category": "标准依据", "question": "NY/T 1634 中土壤速效钾依据什么方法测定？", "relation": ("prescribes_measurement", "standard:doc-3", "indicator:available_k"), "answer": "NY/T 1634 引用 NY/T 889，并设置土壤缓效钾和速效钾测定。", "keywords": ["速效钾", "测定"]},
    {"category": "标准依据", "question": "NY/T 1634 对土壤容重样品采集和测定有什么要求？", "relation": ("prescribes_measurement", "standard:doc-3", "indicator:bulk_density"), "answer": "NY/T 1634 要求土壤容重等物理性状使用原状土样，可用环刀采集。", "keywords": ["土壤容重", "原状土样", "环刀"]},
    {"category": "标准依据", "question": "广东省补充耕地质量鉴定规范采用什么标准测土壤pH？", "relation": ("prescribes_measurement", "standard:doc-14", "indicator:soil_ph"), "answer": "该规范引用 NY/T 1121.2 进行土壤pH测定。", "keywords": ["1121.2", "土壤", "测定"]},
    {"category": "标准依据", "question": "广东省补充耕地质量鉴定规范如何执行土壤容重检测？", "relation": ("prescribes_measurement", "standard:doc-14", "indicator:bulk_density"), "answer": "该规范引用 NY/T 1121.4 或 GB/T 33469 的相关方法检测土壤容重。", "keywords": ["土壤容重", "测定"]},
    {"category": "标准依据", "question": "补充耕地质量鉴定规范测有效磷时依据什么标准？", "relation": ("prescribes_measurement", "standard:doc-11", "indicator:available_p"), "answer": "该规范依据 NY/T 1121.7 开展土壤有效磷测定。", "keywords": ["1121.7", "有效磷", "测定"]},
    {"category": "标准依据", "question": "NY/T 1634 能否作为土壤盐碱化程度判定依据？", "relation": ("assessment_basis", "standard:doc-3", "obstacle:salinization"), "answer": "可以，相关材料引用 NY/T 1634 的检测结果判定盐碱化程度。", "keywords": ["盐碱化程度", "检测结果", "判定"]},
]


def compact_text(value: str) -> str:
    return _SPACE.sub("", value or "").lower()


def match_text(value: str) -> str:
    """Normalize harmless display punctuation for entity-name matching only."""
    return _PUNCTUATION.sub("", compact_text(value))


def load_graph() -> dict[str, Any]:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def build_gold(graph: dict[str, Any]) -> list[dict[str, Any]]:
    relation_index = {
        relation_key(r["type"], r["source"], r["target"]): r
        for r in graph["relations"]
    }
    entities = {entity["id"]: entity for entity in graph["entities"]}
    gold = []
    category_counters: Counter[str] = Counter()
    for plan in QUESTION_PLANS:
        key = tuple(plan["relation"])
        if key not in relation_index:
            raise RuntimeError(f"金标准关系不存在: {key}")
        relation = relation_index[key]
        category_counters[plan["category"]] += 1
        item_id = f"{plan['category'][:2].upper()}-{category_counters[plan['category']]:02d}"
        evidence = [
            {
                "document_id": ev.get("document_id"),
                "document_title": ev.get("document_title"),
                "page": ev.get("page"),
                "quote": ev.get("quote"),
            }
            for ev in relation["evidence"]
        ]
        gold.append({
            "id": item_id,
            "category": plan["category"],
            "question": plan["question"],
            "expected_answer": plan["answer"],
            "answer_keywords": plan["keywords"],
            "expected_relation_id": relation["id"],
            "expected_relation_type": relation["type"],
            "expected_source_entity": {
                "id": relation["source"],
                "name": entities[relation["source"]]["name"],
            },
            "expected_target_entity": {
                "id": relation["target"],
                "name": entities[relation["target"]]["name"],
            },
            "expected_evidence": evidence,
        })
    if len(gold) != 40 or set(category_counters.values()) != {10}:
        raise RuntimeError(f"金标准数量/分类不正确: {dict(category_counters)}")
    return gold


def load_api_config() -> tuple[str, str, str]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("SILICONFLOW_KEY") or os.environ.get("SILICONFLOW_API_KEY") or ""
    base = os.environ.get("SILICONFLOW_API_BASE") or os.environ.get("SILICONFLOW_BASE_URL") or "https://api.siliconflow.cn/v1"
    model = os.environ.get("SILICONFLOW_EMBED_MODEL") or "BAAI/bge-m3"
    if not key:
        raise RuntimeError("未配置 SILICONFLOW_API_KEY，无法执行纯向量基线")
    return key, base.rstrip("/"), model


def embed_questions(questions: list[str]) -> tuple[list[list[float]], str]:
    key, base, model = load_api_config()
    response = requests.post(
        f"{base}/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "input": questions},
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    vectors = [item["embedding"] for item in payload.get("data", [])]
    if len(vectors) != len(questions):
        raise RuntimeError(f"向量数量不匹配: {len(vectors)} != {len(questions)}")
    return vectors, model


def chroma_vector_results(
    graph: dict[str, Any], gold: list[dict[str, Any]], vectors: list[list[float]], top_k: int,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    allowed_ids = sorted({int(item["document_id"]) for item in graph["corpus"]})
    scope_filter = {"document_id": {"$in": allowed_ids}}
    query = collection.query(
        query_embeddings=vectors,
        n_results=top_k,
        where=scope_filter,
        include=["documents", "metadatas", "distances"],
    )
    output: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(gold):
        rows = []
        for rank, content in enumerate(query["documents"][index], 1):
            metadata = query.get("metadatas", [[]])[index][rank - 1] or {}
            rows.append({
                "rank": rank,
                "retrieval_source": "vector",
                "content": content,
                "metadata": metadata,
                "distance": query.get("distances", [[]])[index][rank - 1],
            })
        output[item["id"]] = rows
    scoped_count = len(collection.get(where=scope_filter, include=[]).get("ids") or [])
    return output, scoped_count, collection.count()


def load_scoped_chunks(graph: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], int]:
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    data = collection.get(include=["documents", "metadatas"])
    allowed_ids = {int(item["document_id"]) for item in graph["corpus"]}
    documents = []
    metadatas = []
    for content, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
        try:
            document_id = int((metadata or {}).get("document_id"))
        except (TypeError, ValueError):
            continue
        if document_id not in allowed_ids:
            continue
        documents.append(content)
        metadatas.append(metadata or {})
    if not documents:
        raise RuntimeError("v0.2 的15份代表性资料在 Chroma 中没有可用片段")
    return documents, metadatas, collection.count()


def local_tfidf_results(
    graph: dict[str, Any], gold: list[dict[str, Any]], top_k: int,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    documents, metadatas, total_count = load_scoped_chunks(graph)
    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 4),
        min_df=1,
        sublinear_tf=True,
        norm="l2",
    )
    document_matrix = vectorizer.fit_transform(documents)
    question_matrix = vectorizer.transform([item["question"] for item in gold])
    similarities = question_matrix @ document_matrix.T
    output: dict[str, list[dict[str, Any]]] = {}
    for index, item in enumerate(gold):
        scores = similarities.getrow(index).toarray().ravel()
        ranked_indices = scores.argsort()[::-1][:top_k]
        output[item["id"]] = [
            {
                "rank": rank,
                "retrieval_source": "vector",
                "content": documents[chunk_index],
                "metadata": metadatas[chunk_index],
                "distance": round(1.0 - float(scores[chunk_index]), 8),
            }
            for rank, chunk_index in enumerate(ranked_indices, 1)
        ]
    return output, len(documents), total_count


def entity_mentions(graph: dict[str, Any], question: str) -> set[str]:
    compact_question = compact_text(question)
    normalized_question = match_text(question)
    mentions = set()
    query_expansions = {
        "obstacle:low_organic_matter": ("有机质消耗", "有机质偏低", "有机质不足"),
    }
    for entity in graph["entities"]:
        terms = [entity.get("name", ""), *(entity.get("aliases") or [])]
        terms.extend(item.get("term", "") for item in entity.get("related_terms") or [])
        terms.extend(query_expansions.get(entity["id"], ()))
        exact_term_match = any(
            match_text(term) and match_text(term) in normalized_question
            for term in terms
        )
        # Users normally cite standards by their short identifier rather than by
        # the full entity name, e.g. "GB/T 33469" instead of
        # "耕地质量等级 GB/T 33469-2016".
        standard_identifiers = {
            compact_text(match.group(0)).removesuffix("-2016")
            for term in terms
            for match in re.finditer(r"(?:GB|NY)/T\s*\d+(?:\.\d+)?(?:-\d{4})?", term, re.IGNORECASE)
        }
        identifier_match = any(identifier in compact_question for identifier in standard_identifiers)
        if exact_term_match or identifier_match:
            mentions.add(entity["id"])
    return mentions


def graph_relation_priority(category: str, relation_type: str) -> int:
    preferred = {
        "指标解释": {"characterized_by": 5, "includes_indicator": 4, "prescribes_measurement": 3},
        "障碍诊断": {"characterized_by": 5, "assessment_basis": 4, "addresses": 3},
        "改良措施": {"addresses": 5},
        "标准依据": {"prescribes_measurement": 5, "includes_indicator": 4, "assessment_basis": 4},
    }
    return preferred.get(category, {}).get(relation_type, 1)


def graph_candidates(graph: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    mentions = entity_mentions(graph, item["question"])
    entities = {entity["id"]: entity for entity in graph["entities"]}
    ranked = []
    for relation in graph["relations"]:
        endpoint_hits = int(relation["source"] in mentions) + int(relation["target"] in mentions)
        if endpoint_hits == 0:
            continue
        score = endpoint_hits * 10 + graph_relation_priority(item["category"], relation["type"])
        for evidence in relation["evidence"]:
            ranked.append({
                "score": score,
                "relation_id": relation["id"],
                "relation_type": relation["type"],
                "source_entity": entities[relation["source"]]["name"],
                "target_entity": entities[relation["target"]]["name"],
                "retrieval_source": "graph",
                "content": evidence["quote"],
                "metadata": {
                    "document_id": evidence.get("document_id"),
                    "source": evidence.get("document_title"),
                    "page": evidence.get("page"),
                },
            })
    ranked.sort(key=lambda row: (-row["score"], row["relation_type"], row["relation_id"]))
    for rank, row in enumerate(ranked, 1):
        row["graph_rank"] = rank
    return ranked


def graph_enhanced_results(
    graph: dict[str, Any], gold: list[dict[str, Any]], vector: dict[str, list[dict[str, Any]]], top_k: int,
) -> dict[str, list[dict[str, Any]]]:
    output = {}
    for item in gold:
        combined = []
        seen = set()
        for row in [*graph_candidates(graph, item), *vector[item["id"]]]:
            metadata = row.get("metadata") or {}
            key = (
                metadata.get("document_id") or metadata.get("source"),
                metadata.get("page"),
                compact_text(row.get("content", ""))[:240],
            )
            if key in seen:
                continue
            seen.add(key)
            combined.append(dict(row))
            if len(combined) >= top_k:
                break
        for rank, row in enumerate(combined, 1):
            row["rank"] = rank
        output[item["id"]] = combined
    return output


def expected_pairs(item: dict[str, Any]) -> set[tuple[int | None, int | None]]:
    return {(ev.get("document_id"), ev.get("page")) for ev in item["expected_evidence"]}


def row_pair(row: dict[str, Any]) -> tuple[int | None, int | None]:
    metadata = row.get("metadata") or {}
    document_id = metadata.get("document_id")
    try:
        document_id = int(document_id) if document_id is not None else None
    except (TypeError, ValueError):
        document_id = None
    page = metadata.get("page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    return document_id, page


def score_one(item: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected = expected_pairs(item)
    hit_ranks = [row["rank"] for row in rows if row_pair(row) in expected]
    first = min(hit_ranks) if hit_ranks else None
    text = compact_text(" ".join(row.get("content", "") for row in rows[:5]))
    keyword_hits = [keyword for keyword in item["answer_keywords"] if compact_text(keyword) in text]
    graph_relation_ranks = [
        row["rank"] for row in rows
        if row.get("relation_id") == item["expected_relation_id"]
    ]
    return {
        "hit_at_1": bool(first and first <= 1),
        "hit_at_3": bool(first and first <= 3),
        "hit_at_5": bool(first and first <= 5),
        "first_relevant_rank": first,
        "reciprocal_rank": 1.0 / first if first else 0.0,
        "keyword_recall_at_5": len(keyword_hits) / max(len(item["answer_keywords"]), 1),
        "matched_keywords": keyword_hits,
        "relation_hit_at_5": bool(graph_relation_ranks and min(graph_relation_ranks) <= 5),
    }


def summarize(scored: list[dict[str, Any]]) -> dict[str, float | int]:
    count = len(scored)
    return {
        "question_count": count,
        "evidence_hit_at_1": round(sum(x["hit_at_1"] for x in scored) / count, 4),
        "evidence_hit_at_3": round(sum(x["hit_at_3"] for x in scored) / count, 4),
        "evidence_hit_at_5": round(sum(x["hit_at_5"] for x in scored) / count, 4),
        "mrr": round(sum(x["reciprocal_rank"] for x in scored) / count, 4),
        "mean_keyword_recall_at_5": round(sum(x["keyword_recall_at_5"] for x in scored) / count, 4),
        "relation_hit_at_5": round(sum(x["relation_hit_at_5"] for x in scored) / count, 4),
    }


def evaluate_system(gold: list[dict[str, Any]], retrieved: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    details = []
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in gold:
        score = score_one(item, retrieved[item["id"]])
        result = {
            "id": item["id"],
            "category": item["category"],
            "question": item["question"],
            "score": score,
            "top_results": [
                {
                    **{key: row.get(key) for key in ("rank", "retrieval_source", "relation_id", "relation_type", "distance") if row.get(key) is not None},
                    "document_id": row_pair(row)[0],
                    "page": row_pair(row)[1],
                    "source": (row.get("metadata") or {}).get("source"),
                    "content": normalise_preview(row.get("content", "")),
                }
                for row in retrieved[item["id"]][:5]
            ],
        }
        details.append(result)
        by_category[item["category"]].append(score)
    return {
        "summary": summarize([item["score"] for item in details]),
        "by_category": {category: summarize(scores) for category, scores in sorted(by_category.items())},
        "details": details,
    }


def normalise_preview(text: str, limit: int = 360) -> str:
    text = _SPACE.sub(" ", text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pct(value: float) -> str:
    return f"{value:.1%}"


def render_report(result: dict[str, Any]) -> str:
    vector = result["systems"]["pure_vector"]
    graph = result["systems"]["graph_enhanced"]
    if result.get("vector_backend") == "siliconflow":
        vector_description = (
            "- 纯向量：问题文本经 SiliconFlow BAAI/bge-m3 生成语义向量，"
            "在相同的 v0.2 语料范围内执行向量相似度检索，不使用图谱。"
        )
        data_boundary = (
            "- 经用户授权，本次仅向 SiliconFlow BGE-M3 发送40道问题文本；"
            "未发送原始资料、标准答案或证据原文。"
        )
    else:
        vector_description = "- 纯向量：完全离线的字符 n-gram TF-IDF 向量与余弦相似度，不使用图谱。"
        data_boundary = (
            "- 本地稀疏向量基线不调用外部服务，结果不能直接代表线上语义向量模型。"
        )
    lines = [
        "# v0.2 金标准问答与检索对比报告",
        "",
        "## 评估设置",
        "",
        f"- 金标准问答：{result['gold_question_count']} 道，每类 10 道",
        f"- 分类：指标解释、障碍诊断、改良措施、标准依据",
        f"- 向量基线：{result['embedding_model']}",
        f"- 评估语料：v0.2 对应15份资料，共 {result['collection_chunk_count']} 个片段（集合总计 {result['collection_total_chunk_count']} 个片段）",
        f"- Top-K：{result['top_k']}",
        vector_description,
        "- 图谱增强：先召回 v0.2 已核验关系证据，再以纯向量结果补足并去重。",
        "",
        "## 总体结果",
        "",
        "| 系统 | Evidence Hit@1 | Hit@3 | Hit@5 | MRR | 答案关键词召回@5 |",
        "|---|---:|---:|---:|---:|---:|",
        f"| 纯向量 | {pct(vector['summary']['evidence_hit_at_1'])} | {pct(vector['summary']['evidence_hit_at_3'])} | {pct(vector['summary']['evidence_hit_at_5'])} | {pct(vector['summary']['mrr'])} | {pct(vector['summary']['mean_keyword_recall_at_5'])} |",
        f"| 图谱增强 | {pct(graph['summary']['evidence_hit_at_1'])} | {pct(graph['summary']['evidence_hit_at_3'])} | {pct(graph['summary']['evidence_hit_at_5'])} | {pct(graph['summary']['mrr'])} | {pct(graph['summary']['mean_keyword_recall_at_5'])} |",
        "",
        "## 分类结果（Evidence Hit@5 / MRR）",
        "",
        "| 分类 | 纯向量 Hit@5 | 图谱增强 Hit@5 | 纯向量 MRR | 图谱增强 MRR |",
        "|---|---:|---:|---:|---:|",
    ]
    for category in ("指标解释", "障碍诊断", "改良措施", "标准依据"):
        v = vector["by_category"][category]
        g = graph["by_category"][category]
        lines.append(
            f"| {category} | {pct(v['evidence_hit_at_5'])} | {pct(g['evidence_hit_at_5'])} | {pct(v['mrr'])} | {pct(g['mrr'])} |"
        )

    v5 = vector["summary"]["evidence_hit_at_5"]
    g5 = graph["summary"]["evidence_hit_at_5"]
    vmrr = vector["summary"]["mrr"]
    gmrr = graph["summary"]["mrr"]
    lines.extend([
        "",
        "## 结论",
        "",
        f"- 图谱增强相对纯向量的 Evidence Hit@5 变化：{(g5 - v5):+.1%}。",
        f"- 图谱增强相对纯向量的 MRR 变化：{(gmrr - vmrr):+.1%}。",
        f"- 图谱关系命中率@5：{pct(graph['summary']['relation_hit_at_5'])}。",
        "- 该结果衡量检索证据命中，不等同于大模型最终回答正确率。金标准中已保存期望答案，下一阶段可接入固定生成模型评估答案事实一致性。",
        "",
        "## 评估边界",
        "",
        "- 金标准来自 v0.2 已核验关系，适合验证当前耕地质量最小图谱的域内检索能力。",
        "- 图谱增强系统使用图谱证据作为优先召回，纯向量使用同一批15份资料和相同 Top-K。",
        data_boundary,
        "- 未用 LLM 自动裁判，避免模型自评偏差；采用文档ID、页码、关系ID和答案关键词进行确定性评分。",
        "",
        "## 输出文件",
        "",
        f"- 金标准：`{GOLD_PATH.relative_to(ROOT).as_posix()}`",
        f"- 完整逐题结果：`{RESULT_PATH.relative_to(ROOT).as_posix()}`",
        f"- 本报告：`{REPORT_PATH.relative_to(ROOT).as_posix()}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--gold-only", action="store_true", help="仅生成金标准，不调用向量接口")
    parser.add_argument(
        "--vector-backend",
        choices=("local_tfidf", "siliconflow"),
        default="local_tfidf",
    )
    args = parser.parse_args()

    graph = load_graph()
    gold = build_gold(graph)
    GOLD_PATH.write_text(json.dumps({
        "schema_version": "cultivated-land-gold-qa-v0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": GRAPH_PATH.relative_to(ROOT).as_posix(),
        "question_count": len(gold),
        "category_counts": dict(Counter(item["category"] for item in gold)),
        "questions": gold,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.gold_only:
        print(json.dumps({"gold": str(GOLD_PATH), "question_count": len(gold)}, ensure_ascii=False))
        return 0

    if args.vector_backend == "siliconflow":
        vectors, model = embed_questions([item["question"] for item in gold])
        vector_retrieved, scoped_chunks, total_chunks = chroma_vector_results(
            graph, gold, vectors, args.top_k,
        )
    else:
        vector_retrieved, scoped_chunks, total_chunks = local_tfidf_results(graph, gold, args.top_k)
        model = "local-char-tfidf-2-4"
    graph_retrieved = graph_enhanced_results(graph, gold, vector_retrieved, args.top_k)
    vector_eval = evaluate_system(gold, vector_retrieved)
    graph_eval = evaluate_system(gold, graph_retrieved)
    result = {
        "schema_version": "cultivated-land-retrieval-eval-v0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": GRAPH_PATH.relative_to(ROOT).as_posix(),
        "source_gold": GOLD_PATH.relative_to(ROOT).as_posix(),
        "gold_question_count": len(gold),
        "top_k": args.top_k,
        "embedding_model": model,
        "vector_backend": args.vector_backend,
        "collection": COLLECTION_NAME,
        "collection_chunk_count": scoped_chunks,
        "collection_total_chunk_count": total_chunks,
        "systems": {
            "pure_vector": vector_eval,
            "graph_enhanced": graph_eval,
        },
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "gold": str(GOLD_PATH),
        "result": str(RESULT_PATH),
        "report": str(REPORT_PATH),
        "pure_vector": vector_eval["summary"],
        "graph_enhanced": graph_eval["summary"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
