from scripts.benchmark_kg_relational_indexes import run_benchmark


def test_10k_intermediate_dataset_uses_all_expected_partial_indexes():
    report = run_benchmark()

    assert report["synthetic_only"] is True
    assert report["rows"] == {
        "kg_extraction_job": 10_000,
        "kg_relation_candidate": 10_000,
        "kg_outbox_event": 10_000,
    }
    assert report["passed"] is True
    assert all(
        query["used_expected_index"] for query in report["queries"].values()
    )
