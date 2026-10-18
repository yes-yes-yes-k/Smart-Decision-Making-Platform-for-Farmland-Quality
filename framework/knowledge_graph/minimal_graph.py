from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import re
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PilotDocument:
    document_id: int
    title: str
    role: str


@dataclass(frozen=True)
class TermSpec:
    code: str
    name: str
    aliases: tuple[str, ...]


INDICATORS = (
    TermSpec("indicator:soil_ph", "土壤pH", ("土壤pH", "pH值", "酸碱度")),
    TermSpec("indicator:organic_matter", "土壤有机质", ("土壤有机质", "有机质")),
    TermSpec("indicator:total_n", "全氮", ("土壤全氮", "全氮")),
    TermSpec("indicator:available_p", "有效磷", ("有效磷", "速效磷")),
    TermSpec("indicator:available_k", "速效钾", ("速效钾", "有效钾")),
    TermSpec("indicator:bulk_density", "土壤容重", ("土壤容重", "容重")),
    TermSpec("indicator:plough_depth", "耕层厚度", ("耕层厚度", "有效耕层厚度")),
    TermSpec("indicator:effective_depth", "有效土层厚度", ("有效土层厚度", "有效土层")),
    TermSpec("indicator:texture", "土壤质地", ("土壤质地", "耕层质地", "机械组成")),
    TermSpec("indicator:cec", "阳离子交换量", ("阳离子交换量", "阳离子交换容量", "CEC")),
    TermSpec("indicator:irrigation", "灌溉能力", ("灌溉能力", "灌溉保证率", "灌溉保障率")),
    TermSpec("indicator:drainage", "排水能力", ("排水能力", "排涝能力", "排水条件")),
)

OBSTACLES = (
    TermSpec("obstacle:acidification", "土壤酸化", ("土壤酸化", "酸性障碍", "pH偏低", "酸化障碍")),
    TermSpec("obstacle:salinization", "土壤盐渍化", ("土壤盐渍化", "盐渍化", "盐碱化", "盐分障碍")),
    TermSpec("obstacle:compaction", "土壤板结", ("土壤板结", "土壤紧实", "容重过高", "紧实化")),
    TermSpec("obstacle:erosion", "土壤侵蚀", ("土壤侵蚀", "水土流失", "表土流失")),
    TermSpec("obstacle:nutrient_deficiency", "养分缺乏", ("养分缺乏", "养分不足", "肥力不足", "土壤贫瘠")),
    TermSpec("obstacle:nutrient_imbalance", "养分失衡", ("养分失衡", "养分不协调", "比例失衡")),
    TermSpec("obstacle:low_organic_matter", "有机质不足", ("有机质不足", "有机质偏低", "有机质含量低")),
    TermSpec("obstacle:shallow_plough", "耕层变浅", ("耕层变浅", "耕层浅薄", "有效土层不足")),
    TermSpec("obstacle:poor_drainage", "排水不良", ("排水不良", "排涝困难", "渍害", "涝害")),
)

MEASURES = (
    TermSpec("measure:liming", "施用石灰", ("施用石灰", "石灰调酸", "石灰改良")),
    TermSpec("measure:organic_fertilizer", "增施有机肥", ("增施有机肥", "施用有机肥", "有机肥培肥")),
    TermSpec("measure:straw_return", "秸秆还田", ("秸秆还田", "腐熟还田")),
    TermSpec("measure:deep_tillage", "深松深耕", ("深松深耕", "深耕", "深松", "深翻")),
    TermSpec("measure:formula_fertilization", "测土配方施肥", ("测土配方施肥", "配方施肥", "精准施肥")),
    TermSpec("measure:green_manure", "绿肥种植", ("绿肥种植", "种植绿肥", "绿肥还田")),
    TermSpec("measure:guest_soil", "客土改良", ("客土改良", "客土置换", "换土")),
    TermSpec("measure:drainage_project", "排灌工程改良", ("排灌工程改良", "灌排改造", "完善排水")),
    TermSpec("measure:soil_conditioner", "施用土壤调理剂", ("土壤调理剂", "改土剂", "调理剂改良")),
    TermSpec("measure:conservation_tillage", "保护性耕作", ("保护性耕作", "免耕", "少耕", "覆盖耕作")),
)

TERM_GROUPS: Mapping[str, tuple[TermSpec, ...]] = {
    "indicator": INDICATORS,
    "obstacle": OBSTACLES,
    "measure": MEASURES,
}

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；;])|\n+")
_SPACE = re.compile(r"\s+")
_CJK = re.compile(r"[\u4e00-\u9fff]")
_MATCH_PUNCTUATION = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_AFFECT_CUES = (
    "影响", "导致", "制约", "限制", "相关", "表现为", "偏低", "过高",
    "不足", "缺乏", "降低", "增加", "主要由", "障碍因子",
)
_ADDRESS_CUES = (
    "针对", "改良", "治理", "调控", "施用", "防治", "缓解", "改善",
    "提升", "采取", "措施", "修复",
)
_STANDARD_INDICATOR_CUES = (
    "定义", "是指", "测定", "检测", "评价指标", "指标包括", "按照", "依据",
)
_STANDARD_ACTION_CUES = (
    "规定", "要求", "应当", "应采用", "可采用", "按照", "依据", "措施", "改良", "治理",
)


def _normalise(text: str) -> str:
    return _SPACE.sub(" ", text or "").strip()


def _sentences(text: str) -> Iterable[str]:
    for sentence in _SENTENCE_SPLIT.split(text or ""):
        sentence = _normalise(sentence)
        if 12 <= len(sentence) <= 600 and len(_CJK.findall(sentence)) >= 8:
            yield sentence


def _mentions(sentence: str, specs: Sequence[TermSpec]) -> set[str]:
    found: set[str] = set()
    lowered = sentence.lower()
    for spec in specs:
        if any(alias.lower() in lowered for alias in spec.aliases):
            found.add(spec.code)
    return found


def _edge_id(relation_type: str, source: str, target: str) -> str:
    raw = f"{relation_type}|{source}|{target}".encode("utf-8")
    return "rel:" + hashlib.sha1(raw).hexdigest()[:16]


class MinimalGraphBuilder:
    """Build an auditable four-node-type pilot graph from indexed chunks.

    Relationships are candidates, not expert assertions. They are created only
    when both endpoints occur in the same sentence, and every relationship keeps
    its original evidence location.
    """

    def __init__(self, corpus: Sequence[PilotDocument], *, max_evidence: int = 8):
        self.corpus = tuple(corpus)
        self.max_evidence = max_evidence
        self._docs = {doc.document_id: doc for doc in corpus}
        self._standard_ids = {
            doc.document_id for doc in corpus if doc.role in {"standard", "policy"}
        }
        self._terms = {
            spec.code: (kind, spec)
            for kind, specs in TERM_GROUPS.items()
            for spec in specs
        }

    def build(self, chunks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        evidence_by_edge: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        mentioned: set[str] = set()
        covered_documents: set[int] = set()

        for chunk in chunks:
            document_id = int(chunk.get("document_id") or 0)
            if document_id not in self._docs:
                continue
            for sentence in _sentences(str(chunk.get("content") or "")):
                groups = {
                    kind: _mentions(sentence, specs)
                    for kind, specs in TERM_GROUPS.items()
                }
                if not any(groups.values()):
                    continue
                for values in groups.values():
                    mentioned.update(values)
                covered_documents.add(document_id)
                evidence = {
                    "document_id": document_id,
                    "document_title": self._docs[document_id].title,
                    "page": chunk.get("page"),
                    "chunk_index": chunk.get("chunk_index"),
                    "quote": sentence[:360],
                }

                if any(cue in sentence for cue in _AFFECT_CUES):
                    for obstacle in groups["obstacle"]:
                        for indicator in groups["indicator"]:
                            self._append(evidence_by_edge, ("affects", obstacle, indicator), evidence)
                if any(cue in sentence for cue in _ADDRESS_CUES):
                    for measure in groups["measure"]:
                        for obstacle in groups["obstacle"]:
                            self._append(evidence_by_edge, ("addresses", measure, obstacle), evidence)

                if document_id in self._standard_ids:
                    standard_code = f"standard:doc-{document_id}"
                    mentioned.add(standard_code)
                    if any(cue in sentence for cue in _STANDARD_INDICATOR_CUES):
                        for concept in groups["indicator"]:
                            self._append(evidence_by_edge, ("defines", standard_code, concept), evidence)
                    if any(cue in sentence for cue in _STANDARD_ACTION_CUES):
                        for kind in ("obstacle", "measure"):
                            for concept in groups[kind]:
                                self._append(evidence_by_edge, ("supports", standard_code, concept), evidence)

        entities = self._build_entities(mentioned)
        relations = []
        for (relation_type, source, target), evidence in sorted(evidence_by_edge.items()):
            doc_count = len({item["document_id"] for item in evidence})
            relations.append({
                "id": _edge_id(relation_type, source, target),
                "type": relation_type,
                "source": source,
                "target": target,
                "status": "candidate",
                "confidence": min(0.95, round(0.55 + 0.10 * doc_count, 2)),
                "supporting_document_count": doc_count,
                "evidence": evidence,
            })

        return {
            "schema_version": "minimal-cultivated-land-kg-v0.1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": {
                "entity_types": ["indicator", "obstacle", "measure", "standard"],
                "relation_types": ["affects", "addresses", "defines", "supports"],
                "review_status": "candidate",
            },
            "corpus": [asdict(doc) for doc in self.corpus],
            "entities": entities,
            "relations": relations,
            "validation": self._validation(entities, relations, covered_documents),
        }

    def _append(self, target, key, evidence):
        existing = target[key]
        fingerprint = (evidence["document_id"], evidence.get("page"), evidence["quote"])
        if any((e["document_id"], e.get("page"), e["quote"]) == fingerprint for e in existing):
            return
        if len(existing) < self.max_evidence:
            existing.append(dict(evidence))

    def _build_entities(self, mentioned: set[str]) -> list[dict[str, Any]]:
        entities = []
        for code in sorted(mentioned):
            if code.startswith("standard:doc-"):
                document_id = int(code.rsplit("-", 1)[-1])
                doc = self._docs[document_id]
                entities.append({
                    "id": code,
                    "type": "standard",
                    "name": doc.title,
                    "aliases": [],
                    "document_id": document_id,
                })
                continue
            kind, spec = self._terms[code]
            entities.append({
                "id": code,
                "type": kind,
                "name": spec.name,
                "aliases": list(spec.aliases),
            })
        return entities

    def _validation(self, entities, relations, covered_documents):
        entity_counts = Counter(entity["type"] for entity in entities)
        relation_counts = Counter(relation["type"] for relation in relations)
        evidence_complete = all(relation.get("evidence") for relation in relations)
        page_located = sum(
            1 for relation in relations for evidence in relation["evidence"]
            if evidence.get("page") is not None
        )
        evidence_count = sum(len(relation["evidence"]) for relation in relations)
        return {
            "corpus_document_count": len(self.corpus),
            "covered_document_count": len(covered_documents),
            "entity_count": len(entities),
            "entity_counts": dict(sorted(entity_counts.items())),
            "relation_count": len(relations),
            "relation_counts": dict(sorted(relation_counts.items())),
            "evidence_count": evidence_count,
            "relations_with_evidence_ratio": 1.0 if evidence_complete else 0.0,
            "evidence_with_page_ratio": round(page_located / evidence_count, 4) if evidence_count else 0.0,
        }


def build_pilot_graph(corpus: Sequence[PilotDocument], chunks: Iterable[Mapping[str, Any]]):
    return MinimalGraphBuilder(corpus).build(chunks)


def query_graph(graph: Mapping[str, Any], query: str) -> dict[str, Any]:
    """Return matching entities and their evidence-backed one-hop relations."""
    query = _normalise(query).lower()
    entities = {entity["id"]: entity for entity in graph.get("entities", [])}
    exact = []
    partial = []
    for entity in entities.values():
        terms = [entity.get("name", ""), *(entity.get("aliases") or [])]
        lowered_terms = [str(term).lower() for term in terms]
        if query in lowered_terms:
            exact.append(entity)
        elif any(query in term for term in lowered_terms):
            partial.append(entity)
    # Exact canonical-name/alias matches take precedence so a narrow term such
    # as “深松” does not also select the composite entity “深松深耕”.
    matched = exact or partial
    matched_ids = {entity["id"] for entity in matched}
    relations = []
    for relation in graph.get("relations", []):
        if relation.get("source") not in matched_ids and relation.get("target") not in matched_ids:
            continue
        item = dict(relation)
        item["source_name"] = entities.get(item["source"], {}).get("name", item["source"])
        item["target_name"] = entities.get(item["target"], {}).get("name", item["target"])
        relations.append(item)
    relations.sort(key=lambda item: (-item.get("supporting_document_count", 0), item["type"]))
    return {"query": query, "entities": matched, "relations": relations}


_RELATION_DIRECTIONS = {
    "addresses": ("measure", "obstacle"),
    "improves_indicator": ("measure", "indicator"),
    "characterized_by": ("obstacle", "indicator"),
    "includes_indicator": ("standard", "indicator"),
    "prescribes_measurement": ("standard", "indicator"),
    "assessment_basis": ("standard", "obstacle"),
    "classifies_basic_indicator": ("standard", "indicator"),
    "classifies_regional_supplementary_indicator": ("standard", "indicator"),
    "assigns_by_field_survey": ("standard", "indicator"),
    "assigns_by_laboratory_test": ("standard", "indicator"),
}

_GENERIC_NGRAMS = {
    "土壤", "耕地", "资料", "材料", "问题", "什么", "哪些", "哪种",
    "如何", "是否", "可以", "能够", "主要", "用于", "作用", "措施",
    "指标", "标准", "评价", "进行", "现有", "对应", "一种", "方面",
}


def _match_normalise(value: str) -> str:
    return _MATCH_PUNCTUATION.sub("", _normalise(value).lower())


def _entity_terms(entity: Mapping[str, Any]) -> list[tuple[str, int, str]]:
    terms = [(str(entity.get("name") or ""), 12, "name")]
    terms.extend((str(term), 12, "alias") for term in entity.get("aliases") or [])
    terms.extend(
        (str(item.get("term") or ""), 8, "related_term")
        for item in entity.get("related_terms") or []
    )
    terms.extend(
        (str(term), 10, "retrieval_term")
        for term in entity.get("retrieval_terms") or []
    )
    return [(term, weight, kind) for term, weight, kind in terms if term]


def entity_match_scores(
    graph: Mapping[str, Any], query: str,
) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Return explicit entity matches and the terms that triggered each match."""
    normalised_query = _match_normalise(query)
    scores: dict[str, int] = {}
    matched_terms: dict[str, list[str]] = {}
    excluded_phrases = [
        _match_normalise(match.group(1))
        for match in re.finditer(r"除(.{1,12}?)外", query)
    ]
    for entity in graph.get("entities", []):
        entity_id = str(entity["id"])
        best = 0
        hits = []
        for term, weight, kind in _entity_terms(entity):
            normalised_term = _match_normalise(term)
            if not normalised_term or normalised_term not in normalised_query:
                continue
            if kind in {"name", "alias"} and any(
                phrase == normalised_term for phrase in excluded_phrases
            ):
                continue
            best = max(best, weight)
            hits.append(term)
        # Standards are commonly cited by a shortened identifier.
        for term, _, _ in _entity_terms(entity):
            for match in re.finditer(
                r"(?:GB|NY)/T\s*\d+(?:\.\d+)?(?:-\d{4})?", term, re.IGNORECASE,
            ):
                identifier = _match_normalise(match.group(0)).removesuffix("2016")
                if identifier and identifier in normalised_query:
                    best = max(best, 12)
                    hits.append(match.group(0))
        if best:
            scores[entity_id] = best
            matched_terms[entity_id] = list(dict.fromkeys(hits))
    return scores, matched_terms


def _query_intent_priorities(query: str) -> dict[str, int]:
    priorities = {relation_type: 0 for relation_type in _RELATION_DIRECTIONS}
    if any(term in query for term in ("措施", "改良", "治理", "缓解", "怎么办", "咋办", "解决", "处理")):
        priorities["addresses"] = 35
        priorities["improves_indicator"] = 20
    if any(term in query for term in ("改善", "提高", "提升", "增加", "降低")):
        priorities["improves_indicator"] = max(priorities["improves_indicator"], 30)
    if any(term in query for term in ("表征", "判断", "诊断", "阈值", "反映", "哪个指标")):
        priorities["characterized_by"] = 35
    if any(term in query for term in ("测定", "检测", "测量", "方法")):
        priorities["prescribes_measurement"] = 35
    if any(term in query for term in ("列为指标", "纳入", "包含", "评价指标")):
        priorities["includes_indicator"] = 35
    if any(term in query for term in ("判定依据", "评定依据", "作为依据")):
        priorities["assessment_basis"] = 35
    if any(term in query for term in ("基础性指标", "基础指标", "基本指标", "全国基础项")):
        priorities["classifies_basic_indicator"] = 55
    if any(term in query for term in (
        "区域补充性指标", "区域补充指标", "补充性指标", "补充指标", "地区补充项",
        "区域补充项", "地方补充项",
    )):
        priorities["classifies_regional_supplementary_indicator"] = 55
    if any(term in query for term in (
        "实地踏勘", "现场踏勘", "现场调查", "现场赋值", "踏勘指标", "现场量", "现场测",
        "现场目测",
    )):
        priorities["assigns_by_field_survey"] = 55
    if any(term in query for term in (
        "实验室检测", "实验室化验", "送实验室", "送检", "送样检测", "土样检测",
        "样品检测", "化验指标", "检测结果赋值", "检测后再赋值",
    )):
        priorities["assigns_by_laboratory_test"] = 55
    return priorities


def _char_ngrams(value: str) -> set[str]:
    text = _match_normalise(value)
    grams = set()
    for size in (2, 3, 4):
        grams.update(text[index:index + size] for index in range(max(0, len(text) - size + 1)))
    return {gram for gram in grams if gram not in _GENERIC_NGRAMS}


def _lexical_relevance(query: str, candidate: str) -> float:
    query_grams = _char_ngrams(query)
    if not query_grams:
        return 0.0
    candidate_grams = _char_ngrams(candidate)
    overlap = query_grams & candidate_grams
    weighted = sum(2 if len(gram) >= 3 else 1 for gram in overlap)
    denominator = sum(2 if len(gram) >= 3 else 1 for gram in query_grams)
    return weighted / max(denominator, 1)


def rank_graph_evidence(
    graph: Mapping[str, Any], query: str, *, top_k: int = 20,
) -> list[dict[str, Any]]:
    """Rank evidence without using gold labels or an external embedding model.

    The score combines explicit ontology mentions, relation intent and lexical
    overlap with the evidence. This resolves relations that share one endpoint,
    such as several measures that all address soil acidification.
    """
    entities = {str(entity["id"]): entity for entity in graph.get("entities", [])}
    mention_scores, matched_terms = entity_match_scores(graph, query)
    priorities = _query_intent_priorities(query)
    ranked = []
    for relation in graph.get("relations", []):
        source_id = str(relation["source"])
        target_id = str(relation["target"])
        endpoint_ids = [entity_id for entity_id in (source_id, target_id) if entity_id in mention_scores]
        if not endpoint_ids:
            continue
        endpoint_score = sum(mention_scores[entity_id] for entity_id in endpoint_ids) * 10
        two_endpoint_bonus = 100 if len(endpoint_ids) == 2 else 0
        intent_score = priorities.get(str(relation["type"]), 0)
        endpoint_text = " ".join(
            term for entity_id in (source_id, target_id)
            for term, _, _ in _entity_terms(entities[entity_id])
        )
        for item in relation.get("evidence") or []:
            candidate_text = f"{endpoint_text} {item.get('quote', '')}"
            lexical_score = round(_lexical_relevance(query, candidate_text) * 100, 4)
            score = endpoint_score + two_endpoint_bonus + intent_score + lexical_score
            ranked.append({
                "score": round(score, 4),
                "relation_id": relation["id"],
                "relation_type": relation["type"],
                "source_entity": entities[source_id]["name"],
                "target_entity": entities[target_id]["name"],
                "relation_label": relation.get("display_label"),
                "relation_semantics": relation.get("semantics"),
                "matched_entity_ids": endpoint_ids,
                "matched_terms": {
                    entity_id: matched_terms[entity_id] for entity_id in endpoint_ids
                },
                "retrieval_source": "graph",
                "content": item.get("quote", ""),
                "metadata": {
                    "document_id": item.get("document_id"),
                    "source": item.get("document_title"),
                    "page": item.get("page"),
                    "chunk_index": item.get("chunk_index"),
                },
            })
    ranked.sort(key=lambda row: (-row["score"], row["relation_type"], row["relation_id"]))
    for index, row in enumerate(ranked[:top_k], 1):
        row["graph_rank"] = index
    return ranked[:top_k]


def assess_graph_claim(graph: Mapping[str, Any], query: str) -> dict[str, Any]:
    """Classify a two-entity natural-language claim as supported or unsupported.

    Unsupported means the reviewed graph contains both concepts but no approved
    relation of the direction allowed by the schema. It does not assert that the
    claim is universally false outside the reviewed corpus.
    """
    entities = {str(entity["id"]): entity for entity in graph.get("entities", [])}
    mention_scores, matched_terms = entity_match_scores(graph, query)
    pairs = []
    for left_id, right_id in itertools.combinations(mention_scores, 2):
        left = entities[left_id]
        right = entities[right_id]
        for relation_type, direction in _RELATION_DIRECTIONS.items():
            if (left["type"], right["type"]) == direction:
                source_id, target_id = left_id, right_id
            elif (right["type"], left["type"]) == direction:
                source_id, target_id = right_id, left_id
            else:
                continue
            pairs.append((
                mention_scores[left_id] + mention_scores[right_id],
                relation_type, source_id, target_id,
            ))
    if not pairs:
        return {
            "status": "indeterminate",
            "matched_entities": sorted(mention_scores),
            "matched_terms": matched_terms,
            "reason": "未识别出符合图谱关系方向的两个实体。",
            "alternatives": rank_graph_evidence(graph, query, top_k=5),
        }
    priorities = _query_intent_priorities(query)
    pairs.sort(key=lambda item: (-(item[0] + priorities.get(item[1], 0)), item[1], item[2], item[3]))
    _, relation_type, source_id, target_id = pairs[0]
    matches = [
        relation for relation in graph.get("relations", [])
        if relation["type"] == relation_type
        and relation["source"] == source_id
        and relation["target"] == target_id
    ]
    return {
        "status": "supported" if matches else "unsupported",
        "relation_type": relation_type,
        "source_entity_id": source_id,
        "target_entity_id": target_id,
        "matched_entities": sorted(mention_scores),
        "matched_terms": matched_terms,
        "relation_ids": [relation["id"] for relation in matches],
        "reason": (
            "存在经材料核验的正式关系。" if matches
            else "当前已核验语料中没有该实体对的正式关系；只能表述为未获支持。"
        ),
        "alternatives": rank_graph_evidence(graph, query, top_k=5),
    }
