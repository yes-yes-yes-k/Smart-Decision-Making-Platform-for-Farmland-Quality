import unittest

from ai_culti_demo import list_thematic_models, run_thematic_model


class ThematicModelTests(unittest.TestCase):
    def setUp(self):
        """提供 Flask app context，使 Agent 持久化正常工作（避免 status=degraded）。"""
        from framework.api.app import create_app
        from framework.models.user import db
        self.app = create_app("sqlite")
        self.app.config["TESTING"] = True
        self._ctx = self.app.app_context()
        self._ctx.push()
        db.create_all()

    def tearDown(self):
        from framework.models.user import db
        db.session.remove()
        self._ctx.pop()

    def test_list_thematic_models_returns_five_professional_models(self):
        result = list_thematic_models()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["models"]), 6)
        self.assertEqual(
            result["models"][0]["model_id"],
            "stability-risk-evaluation",
        )

    def test_list_thematic_models_can_include_non_professional_capabilities(self):
        result = list_thematic_models(include_non_professional=True)
        self.assertEqual(len(result["models"]), 9)
        categories = {model["model_id"]: model.get("category") for model in result["models"]}
        self.assertEqual(categories["spatial-structure-analysis"], "auxiliary")
        self.assertEqual(categories["multi-factor-collaborative-improvement"], "experimental")

    def test_run_single_thematic_model_returns_uniform_payload(self):
        result = run_thematic_model(
            {
                "model_id": "acidification-governance",
                "area_code": "lechang",
                "longitude": 113.35,
                "latitude": 25.13,
            }
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["model_id"], "acidification-remediation")
        self.assertEqual(
            set(result),
            {"model_id", "status", "subject", "result", "meta", "issues"},
        )
        deprecated = next(issue for issue in result["issues"] if issue["code"] == "DEPRECATED_MODEL_ID")
        self.assertEqual(deprecated["details"]["deprecated_model_id"], "acidification-governance")
        self.assertEqual(deprecated["details"]["canonical_model_id"], "acidification-remediation")
        self.assertIsNotNone(result["result"]["soil_conditioner_dosage"])
        self.assertTrue(result["meta"]["simulated"])
        self.assertTrue(result["issues"])

    def test_run_indicator_model_marks_missing_indicator_fallback(self):
        result = run_thematic_model(
            {
                "model_id": "soil-indicator-analysis",
                "area_code": "lechang",
            }
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["fallback"]["used"])
        self.assertIn("indicators", result["fallback"]["fields"])

    def test_run_collaborative_model_returns_dependencies(self):
        result = run_thematic_model(
            {
                "model_id": "multi-factor-collaborative-improvement",
                "area_code": "lechang",
            }
        )

        self.assertEqual(result["status"], "ok")
        self.assertIn("dependent_models", result)
        self.assertGreaterEqual(len(result["dependent_models"]), 2)
        self.assertIn("zoning_recommendations", result)

    def test_invalid_model_returns_error_code(self):
        result = run_thematic_model({"model_id": "bad-model"})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_MODEL_ID")

    def test_thematic_models_return_canonical_envelope_without_external_runtime(self):
        result = run_thematic_model({"model_id": "organic-matter-improvement"})

        self.assertEqual(result["model_id"], "organic-matter-improvement")
        self.assertEqual(
            set(result),
            {"model_id", "status", "subject", "result", "meta", "issues"},
        )
        self.assertIn(result["status"], ("degraded", "rejected", "unavailable"))
        self.assertTrue(result["issues"])

    def test_run_real_diagnosis_model_uses_standard_fields(self):
        """验证真实诊断路径返回标准码字段（ZALX/ZYZAYS/CYZAYS/GDZLDJ），不回退默认值"""
        import tempfile
        import os
        from ai_culti_demo.farmland_diagnosis import bulk_evaluate, diagnose

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, 'test.csv')
            with open(csv_path, 'w', encoding='utf-8') as f:
                f.write('''YJNYQ,EJNYQ,SJD,YJZ,YXL,SXJ,TRRZ,GCZD,GGNL,PSNL,DXBW,ZDGX,YXTCHD,GCHD
华南区,闽南粤中农林水产区,4.5,10,5,50,1.8,黏土,基本满足,基本满足,丘陵上部,夹层型,60,15
''')
            db_path = os.path.join(tmpdir, 'test.db')
            bulk_evaluate(csv_path, db_path)
            diagnose(db_path)

            result = run_thematic_model({
                "model_id": "obstacle-diagnosis",
                "parcel_id": "0",
                "db_path": db_path,
            })

            self.assertEqual(result["status"], "ok")
            diagnosis = result["result"]
            self.assertNotEqual(diagnosis["obstacle_type"], "无明显障碍")
            self.assertTrue(diagnosis["primary_factors"])
            self.assertEqual(
                set(diagnosis),
                {"obstacle_type", "primary_factors", "secondary_factors", "obstacle_degrees", "obstacle_levels", "obstacle_combination"},
            )


if __name__ == "__main__":
    unittest.main()
