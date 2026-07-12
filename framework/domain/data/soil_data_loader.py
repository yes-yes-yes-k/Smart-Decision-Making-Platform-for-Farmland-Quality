from __future__ import annotations
import os
from typing import Any, Dict
import pandas as pd
import numpy as np

def load_soil_data(area_code: str = "lechang") -> Dict[str, Any]:
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", area_code)
    if not os.path.exists(data_dir):
        return _generate_mock_data()
    try:
        third_survey_data = _load_third_survey_data(data_dir)
        formula_data = _generate_formula_mock()
        return {"third_survey": third_survey_data, "formula_fertilization": formula_data}
    except Exception:
        return _generate_mock_data()

def _load_third_survey_data(data_dir: str) -> pd.DataFrame:
    topsoil_path = os.path.join(data_dir, "01_乐昌市土壤三普表层土点位数据_fake.xlsx")
    if os.path.exists(topsoil_path):
        return pd.read_excel(topsoil_path)
    return pd.DataFrame()

def _generate_mock_data() -> Dict[str, Any]:
    return {"third_survey": _generate_third_survey_mock(), "formula_fertilization": _generate_formula_mock()}

def _generate_third_survey_mock() -> pd.DataFrame:
    np.random.seed(42)
    n_points = 623
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })

def _generate_formula_mock() -> pd.DataFrame:
    np.random.seed(123)
    n_points = 1256
    ph_values = np.random.uniform(4.0, 7.0, n_points)
    return pd.DataFrame({
        "pH": ph_values.round(2),
        "交换性酸": np.random.uniform(0.5, 3.0, n_points).round(2),
        "交换性Al": np.random.uniform(0.1, 2.5, n_points).round(2),
        "交换性H": np.random.uniform(0.05, 0.8, n_points).round(2),
        "CEC": np.random.uniform(8.0, 25.0, n_points).round(2),
        "容重": np.random.uniform(1.0, 1.4, n_points).round(2),
        "有机质": np.random.uniform(10.0, 30.0, n_points).round(2),
    })
