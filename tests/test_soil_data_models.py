import unittest

from flask import Flask
from sqlalchemy import inspect, String

from framework.models.user import db


class SoilDataModelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        cls.app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(cls.app)
        import framework.models.soil_data  # noqa: F401 触发模型注册
        with cls.app.app_context():
            db.create_all()

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.remove()
        self.ctx.pop()

    def test_all_eight_tables_created(self):
        from framework.models import soil_data
        expected_tables = {
            soil_data.ThirdSurveyTopsoil.__tablename__,
            soil_data.ThirdSurveyProfile.__tablename__,
            soil_data.ThirdSurveySiteCondition.__tablename__,
            soil_data.ThirdSurveyBulkDensity.__tablename__,
            soil_data.SecondSurveyPoint.__tablename__,
            soil_data.FormulaFertilization.__tablename__,
            soil_data.AgriChemicalization.__tablename__,
            soil_data.GrainYield.__tablename__,
        }
        actual_tables = set(inspect(db.engine).get_table_names())
        self.assertTrue(expected_tables.issubset(actual_tables), expected_tables - actual_tables)

    def test_bulk_density_datetime_fields_are_string(self):
        from framework.models.soil_data import ThirdSurveyBulkDensity
        cols = ThirdSurveyBulkDensity.__table__.columns
        self.assertIsInstance(cols["sample_time"].type, String)
        self.assertIsInstance(cols["report_time"].type, String)

    def test_topsoil_ni_field_exists_and_nullable(self):
        from framework.models.soil_data import ThirdSurveyTopsoil
        col = ThirdSurveyTopsoil.__table__.columns["ni"]
        self.assertTrue(col.nullable)

    def test_can_insert_and_query_topsoil(self):
        from framework.models.soil_data import ThirdSurveyTopsoil
        rec = ThirdSurveyTopsoil(sample_id="S001", ph=5.5, som=15.2, ni=12.3)
        db.session.add(rec)
        db.session.commit()
        got = ThirdSurveyTopsoil.query.filter_by(sample_id="S001").first()
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got.ph, 5.5)
        self.assertAlmostEqual(got.ni, 12.3)


if __name__ == "__main__":
    unittest.main()
