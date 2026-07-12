from __future__ import annotations
from typing import Dict, Any

def calculate_lime_demand(
    assessment: Dict[str, Any],
    target_ph: float = 6.0,
    soil_depth: float = 20.0,
    bulk_density: float = 1.2,
    safety_factor: float = 1.3,
) -> Dict[str, Any]:
    current_ph = assessment.get('ph', 5.5)
    cec = assessment.get('cec', 15.0)
    exchangeable_acidity = assessment.get('exchangeable_acidity', 2.0)

    if current_ph >= target_ph:
        return {
            "lime_demand": 0.0,
            "message": "当前土壤pH已达到或超过目标pH，无需施用石灰",
            "current_ph": current_ph,
            "target_ph": target_ph,
        }

    ph_difference = target_ph - current_ph

    lime_equivalent = ph_difference * cec * 0.001

    soil_volume = 10000 * (soil_depth / 100)
    soil_mass = soil_volume * bulk_density

    lime_demand_kg_per_ha = lime_equivalent * soil_mass * 1000

    lime_demand_with_safety = lime_demand_kg_per_ha * safety_factor

    return {
        "current_ph": current_ph,
        "target_ph": target_ph,
        "ph_difference": round(ph_difference, 2),
        "lime_demand_kg_per_ha": round(lime_demand_kg_per_ha, 2),
        "lime_demand_with_safety_kg_per_ha": round(lime_demand_with_safety, 2),
        "safety_factor": safety_factor,
        "soil_depth_cm": soil_depth,
        "bulk_density_g_cm3": bulk_density,
        "recommendation": f"建议施用石灰 {round(lime_demand_with_safety, 0)} kg/ha（含{int((safety_factor - 1) * 100)}%安全系数）",
    }