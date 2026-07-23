from __future__ import annotations
import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _query_to_dataframe(model_class) -> pd.DataFrame:
    """将 SQLAlchemy 模型查询结果转为 DataFrame，列名为模型字段名。

    遍历 ``mapper.column_attrs`` 取 ``attr.key``（Python 属性名），而非
    ``Column.name``（DB 列名），以正确处理保留字字段（如 ``as_`` 映射到列 ``as``、
    ``yield_`` 映射到列 ``yield``）——此环境下 ``Column.key`` 默认等于 ``name``，
    无法区分，必须走 mapper。
    """
    columns = [attr.key for attr in model_class.__mapper__.column_attrs]
    rows = [
        {col: getattr(instance, col) for col in columns}
        for instance in model_class.query.all()
    ]
    return pd.DataFrame(rows, columns=columns)


def load_soil_data(area_code: str = "lechang") -> Dict[str, Any]:
    """从数据库读取土壤数据，DB 为空或查询失败时降级 mock。

    返回结构保持不变：{"third_survey": DataFrame, "formula_fertilization": DataFrame}

    .. deprecated:: area_code
        ``area_code`` 已废弃——当前实现直接查询全表，DB 不按区域过滤，参数保留
        仅为签名兼容，将在未来接线时移除。调用方不应依赖此参数产生任何过滤效果。
    """
    try:
        from framework.models.soil_data import ThirdSurveyTopsoil, FormulaFertilization

        third_survey_df = _query_to_dataframe(ThirdSurveyTopsoil)
        formula_df = _query_to_dataframe(FormulaFertilization)

        if third_survey_df.empty and formula_df.empty:
            logger.warning("DB 土壤数据表为空，降级到 mock 数据")
            return _generate_mock_data()
        return {"third_survey": third_survey_df, "formula_fertilization": formula_df}
    except Exception as e:
        logger.warning("从 DB 读取土壤数据失败，降级到 mock: %s", e)
        return _generate_mock_data()


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
