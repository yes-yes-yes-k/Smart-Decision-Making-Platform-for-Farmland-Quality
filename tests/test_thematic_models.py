import unittest

from ai_culti_demo import list_thematic_models, run_thematic_model


class ThematicModelTests(unittest.TestCase):
    def test_list_thematic_models_returns_eight_models(self):
        result = list_thematic_models()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["models"]), 8)
        self.assertEqual(
            result["models"][0]["model_id"],
            "spatial-structure-analysis",
        )

    def test_run_single_thematic_model_returns_uniform_payload(self):
        result = run_thematic_model(
            {
                "model_id": "acidification-governance",
                "area_code": "lechang",
                "longitude": 113.35,
                "latitude": 25.13,
            }
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model"]["model_id"], "acidification-governance")
        self.assertIn("findings", result)
        self.assertIn("recommended_layers", result)
        self.assertFalse(result["fallback"]["used"])
        self.assertEqual(result["reliability"]["level"], "demo_stub")

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

    def test_thematic_models_do_not_require_external_runtime(self):
        result = run_thematic_model({"model_id": "organic-matter-improvement"})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["lineage"]["runtime_dependency"], "none")


if __name__ == "__main__":
    unittest.main()
