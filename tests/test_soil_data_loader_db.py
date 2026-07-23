import unittest

import pandas as pd
from flask import Flask

from framework.models.user import db
import framework.models.soil_data  # noqa: F401


def _make_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
    return app


class SoilDataLoaderDbTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_returns_real_data_when_db_populated(self):
        from framework.models.soil_data import ThirdSurveyTopsoil, FormulaFertilization
        db.session.add(ThirdSurveyTopsoil(sample_id="R1", ph=4.2, som=11.0))
        db.session.add(FormulaFertilization(sample_id="F1", ph=5.0, organic_matter=20.0))
        db.session.commit()

        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()

        self.assertIn("third_survey", result)
        self.assertIn("formula_fertilization", result)
        self.assertGreaterEqual(len(result["third_survey"]), 1)
        self.assertGreaterEqual(len(result["formula_fertilization"]), 1)
        # 非空 DB 不应返回 mock 的 623 行规模
        self.assertNotEqual(len(result["third_survey"]), 623)

    def test_falls_back_to_mock_when_db_empty(self):
        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()
        self.assertIn("third_survey", result)
        self.assertIn("formula_fertilization", result)
        # mock 第三普固定 623 行
        self.assertEqual(len(result["third_survey"]), 623)

    def test_returns_structure_has_expected_keys(self):
        from framework.domain.data.soil_data_loader import load_soil_data
        result = load_soil_data()
        self.assertEqual(set(result.keys()), {"third_survey", "formula_fertilization"})
        self.assertIsInstance(result["third_survey"], pd.DataFrame)
        self.assertIsInstance(result["formula_fertilization"], pd.DataFrame)


if __name__ == "__main__":
    unittest.main()
