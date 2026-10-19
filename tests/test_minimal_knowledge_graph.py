import json
from pathlib import Path

from framework.knowledge_graph import (
    MinimalGraphBuilder,
    PilotDocument,
    assess_graph_claim,
    query_graph,
    rank_graph_evidence,
)


def _relation(graph, relation_type, source, target):
    return next(
        relation for relation in graph["relations"]
        if relation["type"] == relation_type
        and relation["source"] == source
        and relation["target"] == target
    )


def test_minimal_graph_keeps_four_entity_types_and_evidence():
    corpus = [
        PilotDocument(1, "测试标准", "standard"),
        PilotDocument(2, "试验研究", "research"),
    ]
    chunks = [
        {
            "document_id": 1,
            "page": 3,
            "chunk_index": 4,
            "content": "土壤pH是耕地质量评价指标，土壤酸化表现为pH偏低。",
        },
        {
            "document_id": 2,
            "page": 8,
            "chunk_index": 2,
            "content": "针对土壤酸化，可施用石灰进行调酸改良。",
        },
    ]

    graph = MinimalGraphBuilder(corpus).build(chunks)

    assert set(graph["validation"]["entity_counts"]) <= {
        "indicator", "obstacle", "measure", "standard"
    }
    affects = _relation(graph, "affects", "obstacle:acidification", "indicator:soil_ph")
    assert affects["evidence"][0]["page"] == 3
    assert affects["status"] == "candidate"
    _relation(graph, "addresses", "measure:liming", "obstacle:acidification")
    _relation(graph, "defines", "standard:doc-1", "indicator:soil_ph")
    assert graph["validation"]["relations_with_evidence_ratio"] == 1.0


def test_relationship_requires_same_sentence():
    corpus = [PilotDocument(1, "研究", "research")]
    chunks = [{
        "document_id": 1,
        "page": 1,
        "chunk_index": 0,
        "content": "本研究分析了土壤酸化问题。另一章节讨论土壤有机质指标。",
    }]
    graph = MinimalGraphBuilder(corpus).build(chunks)
    assert not any(relation["type"] == "affects" for relation in graph["relations"])


def test_evidence_is_deduplicated():
    corpus = [PilotDocument(1, "研究", "research")]
    chunk = {
        "document_id": 1,
        "page": 2,
        "chunk_index": 1,
        "content": "土壤酸化会导致土壤pH偏低。",
    }
    graph = MinimalGraphBuilder(corpus).build([chunk, chunk])
    relation = _relation(graph, "affects", "obstacle:acidification", "indicator:soil_ph")
    assert len(relation["evidence"]) == 1


def test_query_accepts_alias_and_returns_named_neighbors():
    corpus = [PilotDocument(1, "研究", "research")]
    graph = MinimalGraphBuilder(corpus).build([{
        "document_id": 1,
        "page": 2,
        "chunk_index": 1,
        "content": "土壤酸化会导致土壤pH偏低。",
    }])
    result = query_graph(graph, "pH值")
    assert result["entities"][0]["name"] == "土壤pH"
    assert result["relations"][0]["source_name"] == "土壤酸化"


def test_reviewed_v02_has_only_valid_evidence_backed_relations():
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json"
    graph = json.loads(path.read_text(encoding="utf-8"))

    assert graph["schema_version"] == "minimal-cultivated-land-kg-v0.2"
    assert graph["validation"]["passed"] is True
    assert graph["validation"]["invalid_endpoint_relations"] == []
    assert graph["validation"]["invalid_direction_relations"] == []
    assert graph["validation"]["relations_without_evidence"] == []
    assert graph["validation"]["duplicate_relation_count"] == 0
    assert all(relation["status"].startswith("approved") for relation in graph["relations"])
    assert all(evidence.get("page") is not None for relation in graph["relations"] for evidence in relation["evidence"])


def test_reviewed_v02_applies_rejections_and_alias_boundaries():
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.2.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    entities = {entity["id"]: entity for entity in graph["entities"]}
    relation_keys = {
        (relation["type"], relation["source"], relation["target"])
        for relation in graph["relations"]
    }

    assert "机械组成" not in entities["indicator:texture"]["aliases"]
    assert "容重过高" not in entities["obstacle:compaction"]["aliases"]
    assert ("characterized_by", "obstacle:compaction", "indicator:bulk_density") in relation_keys
    assert ("addresses", "measure:deep_loosening", "obstacle:compaction") in relation_keys
    assert ("addresses", "measure:no_till", "obstacle:compaction") in relation_keys
    assert not any(
        relation["source"] == "obstacle:salinization"
        and relation["target"] in {"indicator:drainage", "indicator:irrigation", "indicator:organic_matter"}
        for relation in graph["relations"]
    )

    result = query_graph(graph, "深松")
    assert [entity["id"] for entity in result["entities"]] == ["measure:deep_loosening"]


def test_v03_has_no_orphan_formal_entities_and_supports_measure_indicator():
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    relation_keys = {
        (relation["type"], relation["source"], relation["target"])
        for relation in graph["relations"]
    }

    assert graph["validation"]["passed"] is True
    assert graph["validation"]["orphan_entity_count"] == 0
    assert graph["validation"]["evidence_with_page_ratio"] == 1.0
    assert (
        "improves_indicator", "measure:guest_soil", "indicator:effective_depth",
    ) in relation_keys


def test_v03_ranking_disambiguates_similar_measures():
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
    graph = json.loads(path.read_text(encoding="utf-8"))
    cases = {
        "坡耕地发生侵蚀退化时，可采取哪种耕作改良措施？": (
            "addresses", "measure:deep_tillage", "obstacle:erosion",
        ),
        "不想把地翻得太狠，有没有少扰动的办法缓解板结？": (
            "addresses", "measure:no_till", "obstacle:compaction",
        ),
        "田里老积水，建设排灌工程管用吗？": (
            "addresses", "measure:drainage_project", "obstacle:poor_drainage",
        ),
        "施肥比例不合理、养分有多有少时，应该怎样调整？": (
            "addresses", "measure:formula_fertilization", "obstacle:nutrient_imbalance",
        ),
    }
    relation_index = {
        (relation["type"], relation["source"], relation["target"]): relation["id"]
        for relation in graph["relations"]
    }
    for question, key in cases.items():
        ranked = rank_graph_evidence(graph, question, top_k=5)
        assert relation_index[key] in {item["relation_id"] for item in ranked}


def test_v03_counterfactual_returns_unsupported_not_false():
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
    graph = json.loads(path.read_text(encoding="utf-8"))

    result = assess_graph_claim(graph, "盐碱化耕地可以直接撒石灰治理吗？")
    assert result["status"] == "unsupported"
    assert result["source_entity_id"] == "measure:liming"
    assert result["target_entity_id"] == "obstacle:salinization"


def test_v04_preserves_reviewed_graph_and_adds_standard_aliases():
    root = Path(__file__).resolve().parents[1]
    v03 = json.loads((
        root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.3.json"
    ).read_text(encoding="utf-8"))
    v04 = json.loads((
        root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json"
    ).read_text(encoding="utf-8"))
    entities = {item["id"]: item for item in v04["entities"]}

    assert v04["schema_version"] == "minimal-cultivated-land-kg-v0.4"
    v03_keys = {
        (item["type"], item["source"], item["target"])
        for item in v03["relations"]
    }
    v04_keys = {
        (item["type"], item["source"], item["target"])
        for item in v04["relations"]
    }
    assert v03_keys <= v04_keys
    assert len(v04["relations"]) == 66
    assert sum(len(item["evidence"]) for item in v04["relations"]) == 94
    assert "广东补充耕地验收" in entities["standard:doc-13"]["aliases"]
    assert "广东补充耕地鉴定规范" in entities["standard:doc-14"]["aliases"]
    assert "GB/T 33469" in entities["standard:doc-4"]["aliases"]
    assert v04["validation"]["v04_phase_1_passed"] is True
    assert v04["validation"]["v04_phase_2_passed"] is True
    assert v04["validation"]["role_relation_count"] == 17


def test_v04_recovers_three_live_relation_misses_at_top_five():
    root = Path(__file__).resolve().parents[1]
    graph = json.loads((
        root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json"
    ).read_text(encoding="utf-8"))
    cases = {
        "广东补充耕地验收时，有效土层厚度是不是农业生产符合性评价指标？":
            "rel:99e721a06ccf4433",
        "广东补充耕地鉴定规范中是否包含有效土层厚度这一项？":
            "rel:86c8fa5cc3cd0353",
        "耕层厚度在 GB/T 33469 中属于需要考虑的补充指标吗？":
            "rel:5e88a7f9ebc436e2",
    }

    for question, expected_relation_id in cases.items():
        ranked = rank_graph_evidence(graph, question, top_k=5)
        assert expected_relation_id in {item["relation_id"] for item in ranked}


def test_v04_role_semantics_acceptance_is_strict():
    root = Path(__file__).resolve().parents[1]
    graph = json.loads((
        root / "artifacts" / "minimal_kg" / "cultivated_land_minimal_graph_v0.4.json"
    ).read_text(encoding="utf-8"))
    acceptance = json.loads((
        root / "artifacts" / "minimal_kg" / "role_semantics_acceptance_v0.4.json"
    ).read_text(encoding="utf-8"))

    for item in acceptance["questions"]:
        if item["expected_status"] == "supported":
            ranked = rank_graph_evidence(graph, item["question"], top_k=5)
            assert ranked[0]["relation_id"] == item["expected_relation_id"]
            assert ranked[0]["relation_semantics"] == item["expected_semantics"]
            continue
        claim = assess_graph_claim(graph, item["question"])
        assert claim["status"] == "unsupported"
        assert claim["relation_type"] == item["expected_relation_type"]
        assert claim["source_entity_id"] == item["expected_source_entity"]["id"]
        assert claim["target_entity_id"] == item["expected_target_entity"]["id"]
