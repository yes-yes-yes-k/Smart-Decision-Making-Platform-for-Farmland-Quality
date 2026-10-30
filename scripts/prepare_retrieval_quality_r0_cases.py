"""Freeze small source-grounded retrieval checks without importing the application.

This reads only the original M1 corpus. Reference spans are audit material and
must never be passed to retrieval, extraction, or answer generation as input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "artifacts/knowledge_platform/evidence-m1-v1/corpus"
DEFAULT_OUTPUT = ROOT / "artifacts/knowledge_platform/retrieval-quality-r1/r0-20261030"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_cases() -> dict:
    corpora = {}

    def evidence(doc: int, chunk: int, quote: str, role: str = "direct_support") -> dict:
        if doc not in corpora:
            corpora[doc] = json.loads((CORPUS / f"{doc}.json").read_text(encoding="utf-8"))
        corpus = corpora[doc]
        source = next(c for c in corpus["chunks"] if c["chunk_index"] == chunk)
        text = source["content"]
        if text.count(quote) != 1:
            raise ValueError(f"Quote must occur exactly once: document={doc}, chunk={chunk}")
        start = text.index(quote)
        return {
            "document_id": doc, "content_sha256": corpus["content_sha256"],
            "corpus_file": (CORPUS / f"{doc}.json").relative_to(ROOT).as_posix(),
            "corpus_file_sha256": sha256(CORPUS / f"{doc}.json"),
            "chunk_index": chunk, "page_one_based": source["page"],
            "offset_unit": "unicode_codepoint", "span_convention": "[start,end)",
            "start": start, "end": start + len(quote), "quote": quote,
            "chunk_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "role": role, "source_section": "body",
            "location_status": "exact_in_frozen_chunk_original_page_audit_separate",
        }

    def part(ident: str, question: str, points: list[str], refs: list[dict],
             constraints: list[str], answerability: str = "supported_in_selected_source") -> dict:
        return {"id": ident, "question": question, "answerability": answerability,
                "answer_points": points, "reference_evidence": refs,
                "applicability_and_prohibited_inference": constraints,
                "support_review": "AI_source_reading_not_expert_certification",
                "unresolved": []}

    cases = [
        {"id": "U1", "kind": "primary", "query": "长期施用生物炭对土壤有机碳有什么影响，效果能持续多久？",
         "reference_document_ids": [449], "subquestions": [
             part("U1.SOC", "长期生物炭施用下SOC如何变化？", ["研究报告SOC增加；年度施用和单次施用须分别表达。"], [
                 evidence(449, 50, "application of biochar boosts SOC content by 52.5%, with these"),
                 evidence(449, 51, "average SOC increases are smaller with a single biochar application")],
                 ["原分块双栏交错；引文及上下文须结合来源审计。", "不把SOC含量变化直接换成碳储量或年固碳速率。"]),
             part("U1.time", "报告的观察时长和施用频次是什么？", ["报告3—5年及超过5年的效应，不能外推永久有效。"], [
                 evidence(449, 50, "after 3 to 5 y and 83.5% after more than 5 y (P < 0.05)."),
                 evidence(449, 54, "term sites (5 to 11 y) subjected to annual biochar application, its")],
                 ["时间结果与年度施用条件绑定。", "不同站点、单次/年度施用和分析层次不得合成一个实验。"]),
         ]},
        {"id": "U2", "kind": "primary", "query": "酸性镉污染稻田施石灰后，稻米镉和水稻产量分别如何变化？",
         "reference_document_ids": [1149], "subquestions": [
             part("U2.Cd", "稻米镉是否变化？", ["目标pH石灰处理中稻米镉下降；区分CaO-T和CaCO3-T。"], [
                 evidence(1149, 35, "straw, and root reduced by 80.6%, 46.7%, 41.9% (P<0.05) for the CaO-"),
                 evidence(1149, 35, "T and 59.8%, 59.8%, 30.9% (P<0.05) for the CaCO3-T as compared to")],
                 ["同页列混排，必须连同grain/straw/root顺序和CK对照核对，不能将三种组织数值混用。", "只适用于该来源报告的酸性稻田条件。"]),
             part("U2.yield", "产量是否显著变化？", ["来源报告产量影响不显著，不能写成显著增产。"], [
                 evidence(1149, 62, "by 59.8–98.0% (P<0.01), and insignificantly influenced the yield of"),
                 evidence(1149, 62, "rice grain. These were mainly attributed to the transformation of soil")],
                 ["同段百分数合并了Cd指标，不当作产量效应值。", "不显著不等于证明效应严格为零。"]),
             part("U2.condition", "试验的pH目标及适用边界？", ["田间试验从pH5.35向目标7.0调节，不能外推到所有土壤。"], [
                 evidence(1149, 31, "out to evaluate the accuracy of the established liming model. One-way and limestone (11.0t ha (cid:0) 1) were estimated to raise soil pH from 5.35 to"),
                 evidence(1149, 31, "analysis of variance (ANOVA) and least significant difference (LSD) the target of 7.0. The pH of the soils with the predicted liming ratio")],
                 ["原文双栏夹杂，不能将整条引文当连续语义句。", "石灰材料、施用量及pH结果单独保存。"]),
         ]},
        {"id": "U3", "kind": "primary", "query": "长期施用粪肥对土壤物理性质的影响，是否取决于土壤和作物类型？",
         "reference_document_ids": [104], "subquestions": [
             part("U3.physical", "报告哪些物理性质变化？", ["报告容重下降，且多数试验小区的持水和团聚体等改善；不能省略多数小区限定。"], [
                 evidence(104, 104, "microbial activity led to the accumulation of C in the grass plots. It application can increase SOC and nutrient level, reduce soil ρ b and"),
                 evidence(104, 105, "long term. Continuous loss of C has been observed in this LTE in the past aggregates for most plots investigated, regardless of soil texture. Con-")],
                 ["正文左右栏交错；参考仅确定来源报告的方向，不把夹杂左栏其他讨论拼成新结论。", "气体传输和Ksat不能从持水改善推定。"]),
             part("U3.conditions", "土壤及作物是否造成不同结果？", ["气体传输、孔隙和Ksat随土壤与作物类型不同；粉壤土大麦小区存在下降。"], [
                 evidence(104, 106, "crop system. Schjønning et al. (2002) found little difference in a com- effect of manure on soil gas transport, pore network and Ksat varied with"),
                 evidence(104, 106, "parison between crop systems with or without grass/ley. The effect of soil type and crop type. In the clayey soil, manure increased gas diffusion"),
                 evidence(104, 106, "dent on the duration of grass/clover in the field. Riley et al. (2008) also decreased gas transport and Ksat in the barley plots, while in the maize")],
                 ["不可把所有土类/作物统一为改善。", "同文献多个地点、作物和处理不合并为同一研究条件。"]),
         ]},
        {"id": "U4", "kind": "primary", "query": "紫云英、稻草和石灰联合使用，对土壤有效镉和稻米镉有哪些影响？",
         "reference_document_ids": [1141], "subquestions": [
             part("U4.soil", "土壤有效镉如何变化？", ["结论报告MRF/MRFL相对于F降低有效镉，石灰进一步增强该效应。"], [
                 evidence(1141, 59, "ThecombinedutilizationofMRFreducedthebioavailabilityofCdinsoil,andthe\nadditionofLfurtherstrengthenedthiseffect."),
                 evidence(1141, 59, "ment,theMRFandMRFLtreatmentsreducedsoilavailableCdconcentrations,resultingin")],
                 ["MRFL包括化肥，不能删去F；土壤有效镉不等于总镉。", "本用例不采用受污染页4数字作为有效镉精确数值参考。"]),
             part("U4.grain", "早稻和晚稻的稻米镉如何变化？", ["相对于F，MRFL早稻降低65.2%、晚稻降低43.3%；保持季别及对照。"], [
                 evidence(1141, 55, "cantlydecreasedricegrainCdconcentrationby65.2%(Earlyrice)and43.3%(Laterice),\ncomparedwithFtreatment.")],
                 ["不能混成一个总降幅，也不能将MRF数值冒充MRFL。"]),
             part("U4.condition", "来源报告的处理、地点和初始条件是什么？", ["长沙微区，初始pH5.90；MRFL含紫云英、稻草、化肥、石灰。"], [
                 evidence(1141, 9, "ThemicroplotexperimentwasconductedinChangsha,HunanProvince,China."),
                 evidence(1141, 10, "fertilization(CK);(2)chemicalfertilizer(F);(3)milkvetch,ricestraw,andF(MRF);and\n(4)M,R,F,andlime(MRFL)."),
                 evidence(1141, 55, "at900kgha−1,andtheinitialsoilpHwas5.90.")],
                 ["原文明确条件与缺失条件分别列出；不得写成所有稻田的通用效应。"]),
         ]},
        {"id": "U5", "kind": "primary", "query": "珠江三角洲土壤镉的空间分布与分区管控，有哪些文献和原文依据？",
         "reference_document_ids": [1032], "subquestions": [
             part("U5.space", "高值区主要在哪里？", ["来源描述高值区主要分布在水系密集的北江、西江冲积平原等。"], [
                 evidence(1032, 59, "Cd高含量\n区分布特征明显,主要分布于水系密集的北江、西江冲积平原区,而东江流域 Cd的含量\n相对较低。")],
                 ["保留空间范围与研究年份，不外推全国。", "空间关联不能自动推导干预因果。"]),
             part("U5.management", "文献如何建议按地质区域管控？", ["研究建议区分第四系区与花岗岩/碎屑岩区，并按风险分类管理。"], [
                 evidence(1032, 100, "考虑珠江三角洲独特的地质环境,对\n珠江三角洲的不同地质类型区域提出不同管控建议,在第四系岩区,利用前文研究的土壤\n安全阈值作为土壤Cd 污染风险筛选值,结合 GB 15618 中的风险管制值,来进行风险管控\n和分类管理,严防土壤酸化。"),
                 evidence(1032, 98, "根据国发[2016]31 号《土壤污染防治计划》要求采取风险管控的思想,将农田分为优\n先保护类、安全利用类和严格管控类 3个类。")],
                 ["这是文献内的研究建议，不认证现行法规/阈值。", "分区规则、监测建议与具体措施有效性不可互相替代。"]),
         ]},
    ]

    def variant(parent: str, ident: str, query: str, kind: str, checks: list[str]) -> dict:
        return {"id": ident, "kind": kind, "parent": parent, "query": query,
                "inherits_subquestions": parent if kind == "synonym" else None,
                "reference_document_ids": next(c["reference_document_ids"] for c in cases if c["id"] == parent),
                "expected_checks": checks}

    cases.extend([
        variant("U1", "U1.EN", "How does long-term biochar addition affect SOC, and how do annual and single applications differ over time?",
                "synonym", ["与U1使用相同支持要求，不能因中英文变化丢失已核实来源。"]),
        variant("U2", "U2.PREMISE", "这篇石灰试验证明水稻显著增产了多少？", "false_premise",
                ["调用时以完整论文题名消除这篇指代，题名取449/1149等来源清单中的1149。", "应找到U2.yield反证，指出产量影响不显著；不得输出显著增产幅度。"]),
        variant("U4", "U4.CONDITION", "这项紫云英稻草石灰试验能否证明初始pH8.5的稻田也有同样降镉效果？", "condition_mismatch",
                ["调用时使用1141完整论文题名消除指代。", "U4.condition为初始pH5.90，不能作为pH8.5的直接支持。", "保留背景相关，不将没有匹配条件解释为该措施在碱性土无效。"]),
        variant("U4", "U4.UNSUPPORTED", "这项紫云英稻草石灰试验在2050年的具体稻米镉降幅是多少？", "insufficient_source_evidence",
                ["调用时使用1141完整论文题名消除指代。", "文献报告不能给出2050年实测结果，不能把已有季别结果外推到未来。", "原文证据不足与检索没找到分别记录；不得以图缺边判无效。"]),
    ])

    # Expand deictic variants deterministically, without placing source IDs in queries.
    for case in cases:
        if case["kind"] in {"false_premise", "condition_mismatch", "insufficient_source_evidence"}:
            doc = case["reference_document_ids"][0]
            title = corpora[doc]["title"]
            case["query"] = f"关于论文《{title}》：" + case["query"]
    return {
        "schema_version": "retrieval-quality-r0-cases-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "state": "frozen_before_first_quality_run",
        "scope": "five_user_confirmed_tasks_and_four_small_variants_not_corpus_benchmark",
        "source_scope": "current_qualified_academic_papers_default_runtime_revalidation_required",
        "reference_scope": "original_ten_M1_papers_frozen_chunks_not_exhaustive_reference",
        "reviewer": "Codex_AI_source_reading", "expert_certification": False,
        "model_api_calls": 0, "product_queries_executed": 0,
        "prohibited_leakage": "Only query and user scope may be passed to retrieval. Reference IDs, answer points, quotes and positions are evaluator-only.",
        "support_judgment": "Exact span is location proof only; support, condition fit and publication identity are independent. Unreviewed findings remain pending.",
        "gates": {"distinct_paper_rank_max": 10, "support_rank_max": 5,
                  "per_answerable_subquestion_required": True, "aggregate_cannot_hide_failure": True},
        "unanswerable_scoring": "Counterevidence and source insufficiency must be distinguished from retrieval failure; lack of graph edge is never evidence of nonexistence.",
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    target = args.output_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    output = target / "query-cases.json"
    if output.exists():
        raise SystemExit("Refusing to overwrite frozen cases; choose a new output directory.")
    result = build_cases()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    references = sum(len(p["reference_evidence"]) for c in result["cases"] for p in c.get("subquestions", []))
    print(json.dumps({"cases": len(result["cases"]), "reference_spans": references,
                      "output": output.relative_to(ROOT).as_posix(), "sha256": sha256(output)}))


if __name__ == "__main__":
    main()
