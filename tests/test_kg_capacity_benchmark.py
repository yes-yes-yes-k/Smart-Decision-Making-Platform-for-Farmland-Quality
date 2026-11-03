from __future__ import annotations

from framework.knowledge_graph.capacity_benchmark import (
    benchmark_age_queries, benchmark_release_switch,
)


class BenchmarkStore:
    def __init__(self):
        self.active = "release-old"
        self.queries = []

    def neighbors(self, query):
        self.queries.append(query)

    def entity_lookup_plan(self, entity_id):
        return {"entity_id": entity_id, "uses_index": True, "full_graph_scan": False}

    def active_release(self):
        return self.active

    def activate_release(self, release_id):
        self.active = release_id


def _clock(step=0.001):
    state = {"value": 0.0}

    def now():
        value = state["value"]
        state["value"] += step
        return value

    return now


def test_query_benchmark_measures_both_hops_top100_and_index_plan():
    store = BenchmarkStore()

    report = benchmark_age_queries(
        store, ["entity:1", "entity:2"], rounds=2, clock=_clock(),
    )

    assert report["sample_count"] == 8
    assert report["max_hops"] == 2 and report["top_k"] == 100
    assert report["p95_ms"] == 1.0
    assert report["single_document_full_graph_scan"] is False
    assert {query.max_hops for query in store.queries} == {1, 2}
    assert all(query.top_k == 100 and query.timeout_ms == 1_000 for query in store.queries)


def test_release_benchmark_finishes_on_rollback_release_and_records_times():
    store = BenchmarkStore()

    report = benchmark_release_switch(
        store, target_release="release-new", rollback_release="release-old",
        clock=_clock(step=0.25),
    )

    assert report["activate_seconds"] == 0.25
    assert report["rollback_seconds"] == 0.25
    assert report["initial_release"] == "release-old"
    assert report["final_release"] == "release-old"
    assert store.active == "release-old"
