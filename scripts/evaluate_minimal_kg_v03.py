"""Evaluate v0.3 with core, realistic-style, paraphrase and counterfactual questions."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VENV_SITE = ROOT / ".venv" / "Lib" / "site-packages"
if VENV_SITE.exists() and str(VENV_SITE) not in sys.path:
    sys.path.insert(0, str(VENV_SITE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
from sklearn.feature_extraction.text import TfidfVectorizer

from framework.knowledge_graph import assess_graph_claim, rank_graph_evidence


GRAPH_PATH = ROOT / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
CORE_GOLD_PATH = ROOT / "artifacts" / "minimal_kg" / "gold_qa_v0.2.json"
GOLD_PATH = ROOT / "artifacts" / "minimal_kg" / "gold_qa_v0.3.json"
RESULT_PATH = ROOT / "artifacts" / "minimal_kg" / "retrieval_stress_test_v0.3.json"
REPORT_PATH = ROOT / "artifacts" / "minimal_kg" / "retrieval_stress_test_report_v0.3.md"
CHROMA_PATH = ROOT / "chroma_db"
COLLECTION_NAME = "kb_cultivated_land_quality"


POSITIVE_ADDITIONS: list[dict[str, Any]] = [
    # Evidence-gap coverage for the seven formerly disconnected v0.2 entities.
    {"style": "evidence_gap", "category": "障碍诊断", "question": "土壤全氮低到什么程度，可能构成坡耕地养分障碍？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:total_n"), "answer": "材料将土壤全氮低于1.15 g/kg列为坡耕地障碍阈值之一。", "keywords": ["全氮", "1.15", "障碍"]},
    {"style": "evidence_gap", "category": "障碍诊断", "question": "阳离子交换量偏低说明哪类养分问题？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:cec"), "answer": "阳离子交换量低下是坡耕地养分障碍的限制因素。", "keywords": ["阳离子交换量", "养分障碍"]},
    {"style": "evidence_gap", "category": "改良措施", "question": "地里有机质偏低，种植绿肥有没有帮助？", "relation": ("addresses", "measure:green_manure", "obstacle:low_organic_matter"), "answer": "有帮助，种植绿肥并翻埋还田可以提升土壤有机质。", "keywords": ["种植绿肥", "有机质"]},
    {"style": "evidence_gap", "category": "改良措施", "question": "引入客土能不能把有效土层做厚一些？", "relation": ("improves_indicator", "measure:guest_soil", "indicator:effective_depth"), "answer": "材料表明引入客土可改善土壤层次结构并增加有效土层厚度。", "keywords": ["客土", "有效土层厚度"]},
    {"style": "evidence_gap", "category": "障碍诊断", "question": "耕层太薄主要看哪个厚度指标？", "relation": ("characterized_by", "obstacle:shallow_plough", "indicator:plough_depth"), "answer": "耕层浅薄应以耕层厚度作为直接表征指标。", "keywords": ["耕层厚度"]},
    {"style": "evidence_gap", "category": "改良措施", "question": "施肥比例不合理、养分有多有少时，应该怎样调整？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:nutrient_imbalance"), "answer": "应采用测土配方和平衡施肥，避免养分过剩或匮乏。", "keywords": ["测土配方施肥", "养分过剩", "匮乏"]},
    {"style": "evidence_gap", "category": "改良措施", "question": "田里老积水，建设排灌工程管用吗？", "relation": ("addresses", "measure:drainage_project", "obstacle:poor_drainage"), "answer": "管用，排灌工程可降低地下水位、排涝并防止渍害。", "keywords": ["排灌", "排涝", "渍害"]},
    {"style": "evidence_gap", "category": "障碍诊断", "question": "排水不良主要对应哪个评价指标？", "relation": ("characterized_by", "obstacle:poor_drainage", "indicator:drainage"), "answer": "排水不良主要由排水能力或排水条件表征。", "keywords": ["排水能力"]},

    # Realistic user-style questions; these are simulated scenarios, not usage logs.
    {"style": "real_world_style", "category": "改良措施", "question": "地一浇水就板得硬邦邦的，先上什么机械松土办法？", "relation": ("addresses", "measure:deep_loosening", "obstacle:compaction"), "answer": "可先采用深松破除板结和犁底层。", "keywords": ["深松", "板结"]},
    {"style": "real_world_style", "category": "改良措施", "question": "检测报告说pH偏低，撒石灰能不能调回来？", "relation": ("addresses", "measure:liming", "obstacle:acidification"), "answer": "可以，施用石灰可中和土壤酸性。", "keywords": ["石灰", "酸性"]},
    {"style": "real_world_style", "category": "改良措施", "question": "不想把地翻得太狠，有没有少扰动的办法缓解板结？", "relation": ("addresses", "measure:no_till", "obstacle:compaction"), "answer": "可采用免耕等少扰动方式缓解板结。", "keywords": ["免耕", "板结"]},
    {"style": "real_world_style", "category": "改良措施", "question": "肥越施越乱，有的过量有的不足，该怎么配？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:nutrient_imbalance"), "answer": "采用测土配方和平衡施肥，按土壤和作物需求供肥。", "keywords": ["测土配方", "平衡施肥"]},
    {"style": "real_world_style", "category": "改良措施", "question": "雨后田里水排不出去，应该做哪类工程？", "relation": ("addresses", "measure:drainage_project", "obstacle:poor_drainage"), "answer": "应完善灌溉与排水工程，降低地下水位并排涝。", "keywords": ["排水工程", "排涝"]},
    {"style": "real_world_style", "category": "改良措施", "question": "土层太薄，能不能从外面运土来改善？", "relation": ("improves_indicator", "measure:guest_soil", "indicator:effective_depth"), "answer": "可以通过引入客土改善土层结构并增加有效土层厚度。", "keywords": ["客土", "有效土层厚度"]},
    {"style": "real_world_style", "category": "改良措施", "question": "地力差、有机质少，种一季绿肥有用吗？", "relation": ("addresses", "measure:green_manure", "obstacle:low_organic_matter"), "answer": "绿肥翻埋还田有助于提升土壤有机质。", "keywords": ["绿肥", "有机质"]},
    {"style": "real_world_style", "category": "改良措施", "question": "坡地被雨冲刷后，深松深耕能起什么作用？", "relation": ("addresses", "measure:deep_tillage", "obstacle:erosion"), "answer": "深松深耕可改善结构并减轻坡耕地侵蚀退化。", "keywords": ["深松", "深耕", "侵蚀"]},

    # Synonym and paraphrase stress cases.
    {"style": "paraphrase", "category": "障碍诊断", "question": "CEC偏低通常反映红壤坡地哪方面的限制？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:cec"), "answer": "CEC即阳离子交换量，偏低可反映养分障碍。", "keywords": ["阳离子交换量", "养分障碍"]},
    {"style": "paraphrase", "category": "障碍诊断", "question": "氮素水平不足时，应归入哪类肥力限制？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:total_n"), "answer": "全氮不足可归入养分缺乏障碍。", "keywords": ["全氮", "养分"]},
    {"style": "paraphrase", "category": "改良措施", "question": "少耕或不翻耕能处理土体紧实吗？", "relation": ("addresses", "measure:no_till", "obstacle:compaction"), "answer": "材料支持免耕用于缓解土壤板结和紧实退化。", "keywords": ["免耕", "板结"]},
    {"style": "paraphrase", "category": "改良措施", "question": "土地发生酸性障碍时，用调酸材料是否合适？", "relation": ("addresses", "measure:soil_conditioner", "obstacle:acidification"), "answer": "可施用土壤调理剂治理酸化。", "keywords": ["土壤调理剂", "酸化"]},
    {"style": "paraphrase", "category": "改良措施", "question": "外来土掺入后，主要能改善哪项土层指标？", "relation": ("improves_indicator", "measure:guest_soil", "indicator:effective_depth"), "answer": "客土改良可以增加有效土层厚度。", "keywords": ["客土", "有效土层厚度"]},
    {"style": "paraphrase", "category": "障碍诊断", "question": "田块容易内涝，应该关注它的哪项灌排指标？", "relation": ("characterized_by", "obstacle:poor_drainage", "indicator:drainage"), "answer": "应关注排水能力或排水条件。", "keywords": ["排水能力"]},
    {"style": "paraphrase", "category": "改良措施", "question": "土壤有机碳源不足时，绿肥翻埋是否属于培肥办法？", "relation": ("addresses", "measure:green_manure", "obstacle:low_organic_matter"), "answer": "属于，绿肥翻埋可提升土壤有机质。", "keywords": ["绿肥", "有机质"]},
    {"style": "paraphrase", "category": "改良措施", "question": "按需施肥怎样避免地块出现营养比例不协调？", "relation": ("addresses", "measure:formula_fertilization", "obstacle:nutrient_imbalance"), "answer": "测土配方和平衡施肥可避免养分过剩或匮乏。", "keywords": ["测土配方", "养分"]},
]


COUNTERFACTUALS: list[dict[str, Any]] = [
    {"category": "反事实", "question": "盐碱化耕地可以直接撒石灰治理吗？", "relation_type": "addresses", "source": "measure:liming", "target": "obstacle:salinization", "answer": "当前图谱不支持；石灰的已核验证据针对土壤酸化。"},
    {"category": "反事实", "question": "土壤板结只靠测土配方施肥就能解决吗？", "relation_type": "addresses", "source": "measure:formula_fertilization", "target": "obstacle:compaction", "answer": "当前图谱不支持；板结对应深松或免耕证据。"},
    {"category": "反事实", "question": "排水不良可以通过增施有机肥直接解决吗？", "relation_type": "addresses", "source": "measure:organic_fertilizer", "target": "obstacle:poor_drainage", "answer": "当前图谱不支持；排水不良对应排灌工程。"},
    {"category": "反事实", "question": "有机质不足时应当优先施用石灰吗？", "relation_type": "addresses", "source": "measure:liming", "target": "obstacle:low_organic_matter", "answer": "当前图谱不支持；石灰用于酸化，有机质不足可采用绿肥或保护性耕作。"},
    {"category": "反事实", "question": "GB/T 33469 是否规定了土壤速效钾的测定方法？", "relation_type": "prescribes_measurement", "source": "standard:doc-4", "target": "indicator:available_k", "answer": "当前v0.3证据不支持该标准关系，速效钾测定证据来自其他规程。"},
    {"category": "反事实", "question": "种植绿肥可以直接解决土壤板结吗？", "relation_type": "addresses", "source": "measure:green_manure", "target": "obstacle:compaction", "answer": "当前图谱不支持；绿肥对应有机质不足，板结对应深松或免耕。"},
    {"category": "反事实", "question": "土壤酸化主要靠排灌工程改良吗？", "relation_type": "addresses", "source": "measure:drainage_project", "target": "obstacle:acidification", "answer": "当前图谱不支持；排灌工程针对排水不良，酸化对应石灰、调理剂等。"},
    {"category": "反事实", "question": "养分失衡可以只用深松来解决吗？", "relation_type": "addresses", "source": "measure:deep_loosening", "target": "obstacle:nutrient_imbalance", "answer": "当前图谱不支持；养分失衡对应测土配方和平衡施肥。"},
]


# Frozen after the retrieval-term revision. These questions are evaluated but
# are not used to add or tune retrieval terms in this iteration.
HOLDOUT_POSITIVES: list[dict[str, Any]] = [
    {"style": "holdout_real_world", "category": "障碍诊断", "question": "化验单上的交换容量很低，这属于缺肥方面的障碍吗？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:cec"), "answer": "交换容量低可表征养分障碍。", "keywords": ["阳离子交换量", "养分障碍"]},
    {"style": "holdout_real_world", "category": "障碍诊断", "question": "氮含量掉到很低时，能不能作为养分不足的诊断信号？", "relation": ("characterized_by", "obstacle:nutrient_deficiency", "indicator:total_n"), "answer": "全氮偏低可作为养分不足的诊断信号。", "keywords": ["全氮", "养分不足"]},
    {"style": "holdout_real_world", "category": "改良措施", "question": "一下暴雨田块就窝水，补排涝设施有没有用？", "relation": ("addresses", "measure:drainage_project", "obstacle:poor_drainage"), "answer": "排涝和排水工程可缓解排水不良。", "keywords": ["排涝", "排水不良"]},
    {"style": "holdout_real_world", "category": "改良措施", "question": "有效土层不够厚，掺入外源土能改善吗？", "relation": ("improves_indicator", "measure:guest_soil", "indicator:effective_depth"), "answer": "引入客土可增加有效土层厚度。", "keywords": ["客土", "有效土层厚度"]},
    {"style": "holdout_real_world", "category": "改良措施", "question": "土里的有机质一直往下掉，绿肥翻埋能补吗？", "relation": ("addresses", "measure:green_manure", "obstacle:low_organic_matter"), "answer": "绿肥翻埋可提高土壤有机质。", "keywords": ["绿肥", "有机质"]},
    {"style": "holdout_real_world", "category": "改良措施", "question": "土壤酸化地块不用石灰，换调理材料是否可行？", "relation": ("addresses", "measure:soil_conditioner", "obstacle:acidification"), "answer": "可采用土壤调理剂治理酸化。", "keywords": ["土壤调理剂", "酸化"]},
    {"style": "holdout_real_world", "category": "改良措施", "question": "坡地冲刷得厉害，深翻松土能减轻退化吗？", "relation": ("addresses", "measure:deep_tillage", "obstacle:erosion"), "answer": "深松深耕可减轻侵蚀退化。", "keywords": ["深松", "深耕", "侵蚀"]},
    {"style": "holdout_real_world", "category": "障碍诊断", "question": "耕作层越来越薄，诊断时重点看什么厚度？", "relation": ("characterized_by", "obstacle:shallow_plough", "indicator:plough_depth"), "answer": "重点关注耕层厚度。", "keywords": ["耕层厚度"]},
]


HOLDOUT_COUNTERFACTUALS: list[dict[str, Any]] = [
    {"category": "反事实", "question": "地面发硬只修排水沟就够了吗？", "relation_type": "addresses", "source": "measure:drainage_project", "target": "obstacle:compaction", "answer": "当前图谱不支持排水工程直接治理板结。"},
    {"category": "反事实", "question": "氮含量不足能靠免耕补回来吗？", "relation_type": "improves_indicator", "source": "measure:no_till", "target": "indicator:total_n", "answer": "当前图谱不支持免耕直接提高全氮。"},
    {"category": "反事实", "question": "排水不畅的田块先撒石灰有用吗？", "relation_type": "addresses", "source": "measure:liming", "target": "obstacle:poor_drainage", "answer": "当前图谱不支持石灰治理排水不良。"},
    {"category": "反事实", "question": "阳离子交换量低就等于土壤酸化吗？", "relation_type": "characterized_by", "source": "obstacle:acidification", "target": "indicator:cec", "answer": "当前图谱不支持用阳离子交换量直接判定土壤酸化。"},
]


def relation_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return item["type"], item["source"], item["target"]


def build_gold(graph: dict[str, Any]) -> list[dict[str, Any]]:
    relation_index = {relation_key(item): item for item in graph["relations"]}
    core_payload = json.loads(CORE_GOLD_PATH.read_text(encoding="utf-8"))
    questions = []
    for core in core_payload["questions"]:
        item = dict(core)
        item["question_style"] = "core_v02"
        item["split"] = "development"
        item["expected_status"] = "supported"
        questions.append(item)
    counters: Counter[str] = Counter()
    for plan in POSITIVE_ADDITIONS:
        key = tuple(plan["relation"])
        if key not in relation_index:
            raise RuntimeError(f"v0.3关系不存在: {key}")
        relation = relation_index[key]
        counters[plan["style"]] += 1
        questions.append({
            "id": f"V03-{plan['style']}-{counters[plan['style']]:02d}",
            "category": plan["category"],
            "question_style": plan["style"],
            "split": "development",
            "question": plan["question"],
            "expected_status": "supported",
            "expected_answer": plan["answer"],
            "answer_keywords": plan["keywords"],
            "expected_relation_id": relation["id"],
            "expected_relation_type": relation["type"],
            "expected_source_entity": relation["source"],
            "expected_target_entity": relation["target"],
            "expected_evidence": [
                {key: evidence.get(key) for key in ("document_id", "document_title", "page", "quote")}
                for evidence in relation["evidence"]
            ],
        })
    for plan in HOLDOUT_POSITIVES:
        key = tuple(plan["relation"])
        if key not in relation_index:
            raise RuntimeError(f"v0.3留出集关系不存在: {key}")
        relation = relation_index[key]
        counters[plan["style"]] += 1
        questions.append({
            "id": f"V03-{plan['style']}-{counters[plan['style']]:02d}",
            "category": plan["category"],
            "question_style": plan["style"],
            "split": "holdout",
            "question": plan["question"],
            "expected_status": "supported",
            "expected_answer": plan["answer"],
            "answer_keywords": plan["keywords"],
            "expected_relation_id": relation["id"],
            "expected_relation_type": relation["type"],
            "expected_source_entity": relation["source"],
            "expected_target_entity": relation["target"],
            "expected_evidence": [
                {key: item.get(key) for key in ("document_id", "document_title", "page", "quote")}
                for item in relation["evidence"]
            ],
        })
    all_counterfactuals = [
        *((plan, "development") for plan in COUNTERFACTUALS),
        *((plan, "holdout") for plan in HOLDOUT_COUNTERFACTUALS),
    ]
    for index, (plan, split) in enumerate(all_counterfactuals, 1):
        key = (plan["relation_type"], plan["source"], plan["target"])
        if key in relation_index:
            raise RuntimeError(f"反事实关系意外存在: {key}")
        questions.append({
            "id": f"V03-counterfactual-{index:02d}",
            "category": plan["category"],
            "question_style": "counterfactual",
            "split": split,
            "question": plan["question"],
            "expected_status": "unsupported",
            "expected_answer": plan["answer"],
            "answer_keywords": ["不支持"],
            "expected_relation_id": None,
            "expected_relation_type": plan["relation_type"],
            "expected_source_entity": plan["source"],
            "expected_target_entity": plan["target"],
            "expected_evidence": [],
        })
    if len(questions) != 84:
        raise RuntimeError(f"压力测试题量错误: {len(questions)}")
    return questions


def load_scoped_chunks(graph: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], int]:
    collection = chromadb.PersistentClient(path=str(CHROMA_PATH)).get_collection(COLLECTION_NAME)
    data = collection.get(include=["documents", "metadatas"])
    allowed = {int(item["document_id"]) for item in graph["corpus"]}
    documents, metadatas = [], []
    for content, metadata in zip(data.get("documents") or [], data.get("metadatas") or []):
        try:
            document_id = int((metadata or {}).get("document_id"))
        except (TypeError, ValueError):
            continue
        if document_id in allowed:
            documents.append(content or "")
            metadatas.append(metadata or {})
    return documents, metadatas, collection.count()


def local_vector_results(
    graph: dict[str, Any], questions: list[dict[str, Any]], top_k: int,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    documents, metadatas, total = load_scoped_chunks(graph)
    vectorizer = TfidfVectorizer(
        analyzer="char", ngram_range=(2, 4), min_df=1, sublinear_tf=True, norm="l2",
    )
    document_matrix = vectorizer.fit_transform(documents)
    question_matrix = vectorizer.transform([item["question"] for item in questions])
    similarities = question_matrix @ document_matrix.T
    results = {}
    for index, item in enumerate(questions):
        scores = similarities.getrow(index).toarray().ravel()
        indices = scores.argsort()[::-1][:top_k]
        results[item["id"]] = [{
            "rank": rank,
            "retrieval_source": "vector",
            "content": documents[chunk_index],
            "metadata": metadatas[chunk_index],
            "distance": round(1.0 - float(scores[chunk_index]), 8),
        } for rank, chunk_index in enumerate(indices, 1)]
    return results, len(documents), total


def graph_results(
    graph: dict[str, Any], questions: list[dict[str, Any]],
    vectors: dict[str, list[dict[str, Any]]], top_k: int,
) -> dict[str, list[dict[str, Any]]]:
    output = {}
    for item in questions:
        combined, seen = [], set()
        ranked_graph = rank_graph_evidence(graph, item["question"], top_k=40)
        for row in [*ranked_graph, *vectors[item["id"]]]:
            metadata = row.get("metadata") or {}
            key = (metadata.get("document_id"), metadata.get("page"), (row.get("content") or "")[:240])
            if key in seen:
                continue
            seen.add(key)
            combined.append(dict(row))
            if len(combined) == top_k:
                break
        for rank, row in enumerate(combined, 1):
            row["rank"] = rank
        output[item["id"]] = combined
    return output


def row_pair(row: dict[str, Any]) -> tuple[int | None, int | None]:
    metadata = row.get("metadata") or {}
    try:
        document_id = int(metadata.get("document_id"))
    except (TypeError, ValueError):
        document_id = None
    try:
        page = int(metadata.get("page"))
    except (TypeError, ValueError):
        page = None
    return document_id, page


def score_supported(item: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    expected_pairs = {
        (evidence.get("document_id"), evidence.get("page"))
        for evidence in item["expected_evidence"]
    }
    evidence_ranks = [row["rank"] for row in rows if row_pair(row) in expected_pairs]
    relation_ranks = [
        row["rank"] for row in rows if row.get("relation_id") == item["expected_relation_id"]
    ]
    first_evidence = min(evidence_ranks) if evidence_ranks else None
    first_relation = min(relation_ranks) if relation_ranks else None
    return {
        "evidence_hit_at_5": bool(first_evidence and first_evidence <= 5),
        "relation_hit_at_5": bool(first_relation and first_relation <= 5),
        "first_evidence_rank": first_evidence,
        "first_relation_rank": first_relation,
        "reciprocal_rank": 1.0 / first_evidence if first_evidence else 0.0,
    }


def summarise_supported(details: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(details)
    return {
        "question_count": count,
        "evidence_hit_at_5": round(sum(item["score"]["evidence_hit_at_5"] for item in details) / count, 4),
        "relation_hit_at_5": round(sum(item["score"]["relation_hit_at_5"] for item in details) / count, 4),
        "mrr": round(sum(item["score"]["reciprocal_rank"] for item in details) / count, 4),
    }


def preview_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "rank": row["rank"],
        "retrieval_source": row.get("retrieval_source"),
        "relation_id": row.get("relation_id"),
        "relation_type": row.get("relation_type"),
        "score": row.get("score"),
        "document_id": row_pair(row)[0],
        "page": row_pair(row)[1],
        "content": " ".join((row.get("content") or "").split())[:360],
    } for row in rows]


def render_report(result: dict[str, Any]) -> str:
    vector = result["pure_vector_supported"]
    graph = result["graph_supported"]
    styles = result["graph_by_style"]
    lines = [
        "# 耕地质量知识图谱 v0.3 压力测试报告",
        "",
        "## 测试集",
        "",
        f"- 总题量：{result['question_count']} 道",
        "- 原v0.2核心题：40道",
        "- 孤立实体补证题：8道",
        "- 模拟真实场景口语问法：8道（不是线上用户日志）",
        "- 同义改写题：8道",
        "- 反事实/错误前提题：12道（开发集8道、冻结留出集4道）",
        "- 冻结留出集：12道（8道支持性问题、4道反事实），未用于本轮检索词调优",
        f"- 语料范围：15份资料、{result['scoped_chunk_count']}个片段",
        "- 本轮未向外部服务发送新增题目；向量基线为本地字符TF-IDF。",
        "",
        f"## 支持性问题结果（{graph['question_count']}道）",
        "",
        "| 系统 | Evidence Hit@5 | 严格关系 Hit@5 | MRR |",
        "|---|---:|---:|---:|",
        f"| 纯向量 | {vector['evidence_hit_at_5']:.1%} | 不适用 | {vector['mrr']:.1%} |",
        f"| v0.3图谱增强 | {graph['evidence_hit_at_5']:.1%} | {graph['relation_hit_at_5']:.1%} | {graph['mrr']:.1%} |",
        "",
        "## 开发集与冻结留出集",
        "",
        "| 数据集 | 支持性题量 | Evidence Hit@5 | 严格关系 Hit@5 |",
        "|---|---:|---:|---:|",
        f"| 开发集 | {result['graph_by_split']['development']['question_count']} | {result['graph_by_split']['development']['evidence_hit_at_5']:.1%} | {result['graph_by_split']['development']['relation_hit_at_5']:.1%} |",
        f"| 冻结留出集 | {result['graph_by_split']['holdout']['question_count']} | {result['graph_by_split']['holdout']['evidence_hit_at_5']:.1%} | {result['graph_by_split']['holdout']['relation_hit_at_5']:.1%} |",
        "",
        "## 图谱分问法结果",
        "",
        "| 问法 | 题量 | Evidence Hit@5 | 严格关系 Hit@5 |",
        "|---|---:|---:|---:|",
    ]
    labels = {
        "core_v02": "原核心题",
        "evidence_gap": "孤立实体补证题",
        "real_world_style": "真实场景式问法",
        "paraphrase": "同义改写",
    }
    labels["holdout_real_world"] = "冻结真实场景式问法"
    for style in ("core_v02", "evidence_gap", "real_world_style", "paraphrase", "holdout_real_world"):
        item = styles[style]
        lines.append(
            f"| {labels[style]} | {item['question_count']} | "
            f"{item['evidence_hit_at_5']:.1%} | {item['relation_hit_at_5']:.1%} |"
        )
    counter = result["counterfactual"]
    lines.extend([
        "",
        "## 反事实防误答",
        "",
        f"- 正确识别为“当前证据不支持”：{counter['correct']}/{counter['question_count']}（{counter['accuracy']:.1%}）",
        f"- 冻结留出反事实：{counter['by_split']['holdout']['correct']}/{counter['by_split']['holdout']['question_count']}（{counter['by_split']['holdout']['accuracy']:.1%}）",
        "- 这里的“不支持”仅表示当前已核验语料没有该关系，不外推为普遍科学否定。",
        "",
        "## 结论",
        "",
        f"- 开发集严格关系命中率由v0.2的90.0%提高到{result['graph_by_split']['development']['relation_hit_at_5']:.1%}。",
        f"- 未参与调优的冻结留出集严格关系命中率为{result['graph_by_split']['holdout']['relation_hit_at_5']:.1%}。",
        f"- 7个v0.2孤立实体均已通过页码证据接入正式关系；v0.3孤立正式实体为0。",
        "- 关系排序同时使用实体命中、问句意图与证据文本相关性，不再只按关系类型和ID排序。",
        "- 反事实问题在回答层应使用“当前证据不支持”，不能仅凭关系缺失回答“科学上错误”。",
        "",
        "## 输出",
        "",
        f"- 金标准：`{GOLD_PATH.relative_to(ROOT).as_posix()}`",
        f"- 逐题结果：`{RESULT_PATH.relative_to(ROOT).as_posix()}`",
        f"- 本报告：`{REPORT_PATH.relative_to(ROOT).as_posix()}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    questions = build_gold(graph)
    GOLD_PATH.write_text(json.dumps({
        "schema_version": "cultivated-land-gold-qa-v0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": GRAPH_PATH.relative_to(ROOT).as_posix(),
        "question_count": len(questions),
        "style_counts": dict(Counter(item["question_style"] for item in questions)),
        "questions": questions,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    vector_rows, scoped_count, total_count = local_vector_results(graph, questions, 5)
    graph_rows = graph_results(graph, questions, vector_rows, 5)
    vector_details, graph_details, counter_details = [], [], []
    for item in questions:
        if item["expected_status"] == "supported":
            vector_details.append({
                "id": item["id"], "style": item["question_style"], "split": item["split"], "question": item["question"],
                "score": score_supported(item, vector_rows[item["id"]]),
                "top_results": preview_rows(vector_rows[item["id"]]),
            })
            graph_details.append({
                "id": item["id"], "style": item["question_style"], "split": item["split"], "question": item["question"],
                "score": score_supported(item, graph_rows[item["id"]]),
                "top_results": preview_rows(graph_rows[item["id"]]),
            })
        else:
            assessment = assess_graph_claim(graph, item["question"])
            correct = (
                assessment.get("status") == "unsupported"
                and assessment.get("relation_type") == item["expected_relation_type"]
                and assessment.get("source_entity_id") == item["expected_source_entity"]
                and assessment.get("target_entity_id") == item["expected_target_entity"]
            )
            counter_details.append({
                "id": item["id"], "split": item["split"], "question": item["question"], "correct": correct,
                "expected": {
                    "status": "unsupported",
                    "relation_type": item["expected_relation_type"],
                    "source": item["expected_source_entity"],
                    "target": item["expected_target_entity"],
                },
                "actual": assessment,
            })

    by_style: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in graph_details:
        by_style[item["style"]].append(item)
        by_split[item["split"]].append(item)
    counter_correct = sum(item["correct"] for item in counter_details)
    counter_by_split = {}
    for split in ("development", "holdout"):
        split_items = [item for item in counter_details if item["split"] == split]
        split_correct = sum(item["correct"] for item in split_items)
        counter_by_split[split] = {
            "question_count": len(split_items),
            "correct": split_correct,
            "accuracy": round(split_correct / len(split_items), 4),
        }
    result = {
        "schema_version": "cultivated-land-retrieval-stress-test-v0.3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graph": GRAPH_PATH.relative_to(ROOT).as_posix(),
        "question_count": len(questions),
        "scoped_chunk_count": scoped_count,
        "collection_total_chunk_count": total_count,
        "vector_backend": "local-char-tfidf-2-4",
        "pure_vector_supported": summarise_supported(vector_details),
        "graph_supported": summarise_supported(graph_details),
        "graph_by_style": {
            style: summarise_supported(items) for style, items in sorted(by_style.items())
        },
        "graph_by_split": {
            split: summarise_supported(items) for split, items in sorted(by_split.items())
        },
        "counterfactual": {
            "question_count": len(counter_details),
            "correct": counter_correct,
            "accuracy": round(counter_correct / len(counter_details), 4),
            "by_split": counter_by_split,
            "details": counter_details,
        },
        "pure_vector_details": vector_details,
        "graph_details": graph_details,
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(result), encoding="utf-8")
    print(json.dumps({
        "gold": str(GOLD_PATH),
        "result": str(RESULT_PATH),
        "report": str(REPORT_PATH),
        "pure_vector_supported": result["pure_vector_supported"],
        "graph_supported": result["graph_supported"],
        "counterfactual": {
            key: result["counterfactual"][key]
            for key in ("question_count", "correct", "accuracy")
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
