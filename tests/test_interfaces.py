import unittest

from ai_culti_demo import (
    build_report_summary,
    diagnose_county,
    get_county_overview,
    verify_standalone_runtime,
)


class InterfaceTests(unittest.TestCase):
    def test_overview_returns_layers(self):
        result = get_county_overview()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["area"]["code"], "lechang")
        self.assertGreaterEqual(len(result["layers"]), 3)
        self.assertIn("lineage", result)

    def test_diagnosis_returns_machine_readable_payload(self):
        result = diagnose_county(
            {
                "topic": "acidification",
                "area_code": "lechang",
                "longitude": 113.35,
                "latitude": 25.13,
            }
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["result_kind"], "advisory_only")
        self.assertEqual(result["topic"]["id"], "acidification")
        self.assertIn("recommended_layers", result)
        self.assertTrue(result["fallback"]["used"])
        self.assertFalse(result["reliability"]["predictive"])
        self.assertFalse(result["reliability"]["quantitative_available"])

    def test_diagnosis_marks_missing_location_fallback(self):
        result = diagnose_county({"topic": "quality", "area_code": "lechang"})

        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["fallback"]["used"])
        self.assertIn("longitude", result["fallback"]["fields"])

    def test_invalid_topic_returns_error_code(self):
        result = diagnose_county({"topic": "bad-topic"})

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "INVALID_TOPIC")

    def test_report_summary_uses_diagnosis(self):
        diagnosis = diagnose_county({"topic": "improvement", "area_code": "lechang"})
        result = build_report_summary(diagnosis)

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["result_kind"], "advisory_only")
        self.assertEqual(result["diagnosis_id"], diagnosis["diagnosis_id"])
        self.assertIn("findings", result)
        self.assertIn("actions", result)
        self.assertFalse(result["reliability"]["quantitative_available"])

    def test_runtime_check_has_no_external_runtime_dependency(self):
        result = verify_standalone_runtime()

        self.assertEqual(result["status"], "ok")
        self.assertTrue(
            all(not item["runtime_dependency"] for item in result["reference_projects"])
        )


if __name__ == "__main__":
    unittest.main()
