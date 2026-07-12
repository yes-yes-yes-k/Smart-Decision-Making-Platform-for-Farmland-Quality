from __future__ import annotations
from typing import Dict, Any, List

def assess_acidification(soil_data: Dict[str, Any]) -> Dict[str, Any]:
    ph = soil_data.get('ph', 5.5)
    exchangeable_acidity = soil_data.get('exchangeable_acidity', 2.0)
    cec = soil_data.get('cec', 15.0)

    if ph < 4.5:
        grade = "强酸性"
        level = 4
    elif ph < 5.0:
        grade = "酸性"
        level = 3
    elif ph < 5.5:
        grade = "微酸性"
        level = 2
    elif ph < 6.0:
        grade = "偏弱酸性"
        level = 1
    else:
        grade = "中性或碱性"
        level = 0

    acidification_degree = (1 - ph / 7.0) * 100 if ph < 7.0 else 0

    return {
        "ph": ph,
        "exchangeable_acidity": exchangeable_acidity,
        "cec": cec,
        "grade": grade,
        "level": level,
        "acidification_degree": round(acidification_degree, 2),
        "assessment": f"土壤pH值为{ph}，属于{grade}等级",
    }

def simulate_nitrogen_impact(
    assessment: Dict[str, Any],
    current_ph: float = 5.5,
    nitrogen_rates: List[float] = [0, 50, 100, 150, 200],
) -> Dict[str, Any]:
    ph_values = []
    for rate in nitrogen_rates:
        ph_decrease = 0.02 * (rate / 100)
        new_ph = max(3.0, current_ph - ph_decrease)
        ph_values.append(round(new_ph, 2))

    return {
        "current_ph": current_ph,
        "nitrogen_rates": nitrogen_rates,
        "ph_after_application": ph_values,
        "ph_decrease": [round(0.02 * (r / 100), 3) for r in nitrogen_rates],
        "simulation": {
            "description": "不同施氮量对土壤pH的影响模拟",
            "unit": "kg/ha",
        },
    }