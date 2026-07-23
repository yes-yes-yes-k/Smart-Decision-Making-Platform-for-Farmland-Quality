import unittest
from unittest import mock

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


class ImportPrepareTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_column_map_strips_and_renames(self):
        from scripts.import_lechang_data import _prepare_dataframe, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyTopsoil
        # 源列名含前导/尾随空格（如 " Ni"、"TK "）
        df = pd.DataFrame(
            {" Ni": [12.0], "TK ": [18.0], "pH": [5.5], "未映射列": [99]}
        )
        out = _prepare_dataframe(df, COLUMN_MAPS["third_survey_topsoil"], ThirdSurveyTopsoil)
        self.assertIn("ni", out.columns)
        self.assertIn("tk", out.columns)
        self.assertIn("ph", out.columns)
        self.assertNotIn("未映射列", out.columns)  # 非模型字段被丢弃
        self.assertEqual(len(out), 1)

    def test_datetime_converted_to_iso_string(self):
        from scripts.import_lechang_data import _prepare_dataframe, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyBulkDensity
        df = pd.DataFrame(
            {"接样时间": pd.to_datetime(["2024-01-02 03:04:05"]), "土壤容重1": [1.2]}
        )
        out = _prepare_dataframe(df, COLUMN_MAPS["third_survey_bulk_density"], ThirdSurveyBulkDensity)
        self.assertEqual(out["sample_time"].iloc[0], "2024-01-02 03:04:05")
        self.assertEqual(out["bulk_density_1"].iloc[0], 1.2)


class ImportIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_idempotent_import_deletes_then_inserts(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import ThirdSurveyTopsoil
        # 预置旧数据
        db.session.add(ThirdSurveyTopsoil(sample_id="OLD", ph=9.9))
        db.session.commit()

        df1 = pd.DataFrame({"ID": ["A"], "pH": [5.0]})
        df2 = pd.DataFrame({"ID": ["A"], "pH": [5.0]})

        with mock.patch("scripts.import_lechang_data._read_excel", return_value=df1):
            n1 = import_one_source(ThirdSurveyTopsoil, COLUMN_MAPS["third_survey_topsoil"], ["x.xlsx"])
        with mock.patch("scripts.import_lechang_data._read_excel", return_value=df2):
            n2 = import_one_source(ThirdSurveyTopsoil, COLUMN_MAPS["third_survey_topsoil"], ["x.xlsx"])

        self.assertEqual(n1, 1)
        self.assertEqual(n2, 1)
        rows = ThirdSurveyTopsoil.query.all()
        self.assertEqual(len(rows), 1)  # 旧数据被删，无重复
        self.assertEqual(rows[0].sample_id, "A")
        self.assertIsNone(ThirdSurveyTopsoil.query.filter_by(sample_id="OLD").first())


class ImportEncryptedSkipTests(unittest.TestCase):
    def setUp(self):
        self.app = _make_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_encrypted_file_skipped_with_zero_rows(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import AgriChemicalization

        def _raise(*args, **kwargs):
            raise Exception("Workbook is encrypted")

        with mock.patch("scripts.import_lechang_data._read_excel", side_effect=_raise):
            n = import_one_source(AgriChemicalization, COLUMN_MAPS["agri_chemicalization"], ["enc.xls"])

        self.assertEqual(n, 0)

    def test_missing_file_returns_zero(self):
        from scripts.import_lechang_data import import_one_source, COLUMN_MAPS
        from framework.models.soil_data import GrainYield
        n = import_one_source(GrainYield, COLUMN_MAPS["grain_yield"], ["nonexistent.xls"])
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
