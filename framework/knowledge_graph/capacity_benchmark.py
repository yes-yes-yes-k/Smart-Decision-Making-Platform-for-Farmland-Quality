"""Runtime measurements used by the full Apache AGE capacity acceptance."""
from __future__ import annotations

import math
from statistics import median
from time import perf_counter
from typing import Any, Callable, Sequence

from .contracts import GraphQuery
from .stores import AgeGraphStore


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("at least one latency sample is required")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def benchmark_age_queries(
    store: AgeGraphStore,
    entity_ids: Sequence[str],
    *,
    rounds: int = 10,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, Any]:
    if rounds <= 0 or not entity_ids:
        raise ValueError("positive rounds and representative entity_ids are required")
    samples = []
    by_hop: dict[str, list[float]] = {"1": [], "2": []}
    for _ in range(rounds):
        for entity_id in entity_ids:
            for hops in (1, 2):
                started = clock()
                store.neighbors(GraphQuery(
                    (entity_id,), max_hops=hops, top_k=100,
                    timeout_ms=1_000, max_result_bytes=1_048_576,
                ))
                elapsed_ms = (clock() - started) * 1_000
                samples.append(elapsed_ms)
                by_hop[str(hops)].append(elapsed_ms)
    plan = store.entity_lookup_plan(str(entity_ids[0]))
    return {
        "status": "completed",
        "max_hops": 2,
        "top_k": 100,
        "timeout_ms": 1_000,
        "rounds": rounds,
        "representative_entity_count": len(entity_ids),
        "sample_count": len(samples),
        "p50_ms": round(median(samples), 6),
        "p95_ms": round(_percentile(samples, 0.95), 6),
        "max_ms": round(max(samples), 6),
        "by_hop": {
            hops: {
                "sample_count": len(values),
                "p95_ms": round(_percentile(values, 0.95), 6),
                "max_ms": round(max(values), 6),
            }
            for hops, values in by_hop.items()
        },
        "single_document_full_graph_scan": bool(plan["full_graph_scan"]),
        "entity_lookup_plan": plan,
    }


def benchmark_release_switch(
    store: AgeGraphStore,
    *,
    target_release: str,
    rollback_release: str,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, Any]:
    if not target_release or not rollback_release or target_release == rollback_release:
        raise ValueError("distinct target and rollback releases are required")
    initial = store.active_release()
    started = clock()
    store.activate_release(target_release)
    activate_seconds = clock() - started
    if store.active_release() != target_release:
        raise RuntimeError("target release did not become active")
    started = clock()
    store.activate_release(rollback_release)
    rollback_seconds = clock() - started
    if store.active_release() != rollback_release:
        raise RuntimeError("rollback release did not become active")
    return {
        "status": "completed",
        "initial_release": initial,
        "target_release": target_release,
        "rollback_release": rollback_release,
        "activate_seconds": round(activate_seconds, 6),
        "rollback_seconds": round(rollback_seconds, 6),
        "final_release": rollback_release,
    }
