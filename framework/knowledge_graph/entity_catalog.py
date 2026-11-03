"""Canonical entity catalog and surface alias table for entity resolution.

R3 follow-up: resolve 31 pending entity candidates to canonical entities.
The catalog is conservative — only merges surfaces that unambiguously
refer to the same concept. Cross-document canonicalization is applied
where surfaces clearly denote the same measurable entity.

Within-document deduplications (3 pairs in doc 1015):
  - "不同种植时间" ≡ "种植时间在80 d 左右" → planting_time
  - "根部组织中的铅" ≡ "根组织中的铅浓度" → root_tissue_pb
  - "吸收和累积量" ≡ "植物对铅的累积" → pb_accumulation

Cross-document: no matches — the 5 papers study different topics
(Pb uptake, Cd spatial distribution, potato yield, CEC, heavy metal
adsorption). Canonical IDs are assigned so future extractions can match.
"""
from __future__ import annotations

# Canonical entity definitions: canonical_id → (canonical_name, entity_type)
CANONICAL_ENTITIES: dict[str, tuple[str, str]] = {
    # --- measures ---
    "planting_time": ("planting time", "measure"),
    "total_lead": ("total lead", "measure"),
    "inter_row_subsoiling": ("inter-row subsoiling", "measure"),
    "dissolved_organic_carbon": ("dissolved organic carbon", "measure"),
    "calcium": ("calcium", "measure"),
    "elevation": ("elevation", "measure"),
    "manganese": ("manganese", "measure"),
    "milk_vetch_rice_straw_application": ("milk vetch + rice straw application", "measure"),
    "milk_vetch_rice_straw_lime_combined": ("milk vetch + rice straw + lime combined", "measure"),
    # --- indicators ---
    "root_surface_pb_concentration": ("root surface Pb concentration", "indicator"),
    "root_tissue_pb": ("root tissue Pb", "indicator"),
    "root_xylem_pb": ("root xylem Pb", "indicator"),
    "pb_accumulation": ("Pb accumulation", "indicator"),
    "phosphorus_use_efficiency": ("phosphorus use efficiency", "indicator"),
    "potato_yield": ("potato yield", "indicator"),
    "heavy_metal_adsorption_ratio": ("heavy metal adsorption ratio", "indicator"),
    "soil_solution_heavy_metal_concentration": ("soil solution heavy metal ion concentration", "indicator"),
    "plant_cd_uptake": ("plant Cd uptake", "indicator"),
    "soil_cd_mobility": ("soil Cd mobility", "indicator"),
    "rice_cd_concentration": ("rice Cd concentration", "indicator"),
    "soil_total_cd": ("soil total Cd", "indicator"),
    "adsorption_capacity": ("adsorption capacity", "indicator"),
    "cation_exchange_capacity": ("cation exchange capacity", "indicator"),
    # --- soil ---
    "pb_contaminated_sediment": ("Pb-contaminated sediment", "soil"),
    # --- crop ---
    "maize": ("maize", "crop"),
    # --- condition ---
    "greenhouse_cultivation": ("greenhouse cultivation", "condition"),
    "replication_count_6": ("6 replicates", "condition"),
    "flooded_incubation": ("flooded incubation", "condition"),
}

# Surface → canonical_id mapping. Multiple surfaces may map to the same canonical.
SURFACE_ALIASES: dict[str, str] = {
    # measures
    "不同种植时间": "planting_time",
    "种植时间在80 d 左右": "planting_time",
    "重 金 属 铅 总 量": "total_lead",
    "Inter-rowsubsoiling": "inter_row_subsoiling",
    "DOC 含量": "dissolved_organic_carbon",
    "钙(Ca)": "calcium",
    "高程": "elevation",
    "锰(Mn)": "manganese",
    "applicationofMandR": "milk_vetch_rice_straw_application",
    "CombinedutilizationofM,R,andL": "milk_vetch_rice_straw_lime_combined",
    # indicators
    "根表面的浓度": "root_surface_pb_concentration",
    "根部组织中的铅": "root_tissue_pb",
    "根组织中的铅浓度": "root_tissue_pb",
    "根木质部导管中的铅": "root_xylem_pb",
    "吸收和累积量": "pb_accumulation",
    "植物对铅的累积": "pb_accumulation",
    "phosphorususeefficiency": "phosphorus_use_efficiency",
    "starchpotatoyield": "potato_yield",
    "各组分吸附重金属的量的相对比例": "heavy_metal_adsorption_ratio",
    "土壤溶液中的重金\n属离子浓度": "soil_solution_heavy_metal_concentration",
    "Cd 被植物吸收": "plant_cd_uptake",
    "Cd在土壤中的迁移率或环境利用率": "soil_cd_mobility",
    "水稻Cd浓度": "rice_cd_concentration",
    "土壤总Cd含量": "soil_total_cd",
    "吸附量": "adsorption_capacity",
    "CECcontentofthesoil": "cation_exchange_capacity",
    # soil
    "受铅污染的沉积物": "pb_contaminated_sediment",
    # crop
    "玉米种子": "maize",
    # condition
    "温室栽培": "greenhouse_cultivation",
    "6 个重复": "replication_count_6",
    "淹水培养": "flooded_incubation",
}


def resolve_surface(surface: str) -> tuple[str | None, str | None, str]:
    """Resolve a surface text to its canonical entity.

    Returns (canonical_id, canonical_name, resolution_status).
    status is 'resolved' if a match is found, 'unresolved' otherwise.
    """
    canonical_id = SURFACE_ALIASES.get(surface)
    if canonical_id is None:
        return None, None, "unresolved"
    canonical_name, entity_type = CANONICAL_ENTITIES[canonical_id]
    return canonical_id, canonical_name, "resolved"


def cross_document_canonical_matches() -> dict[str, list[int]]:
    """Return canonical_id → list of document_ids that share that canonical.

    Currently empty (no cross-document matches), but the structure is
    here for when future extractions add matching entities.
    """
    return {}
