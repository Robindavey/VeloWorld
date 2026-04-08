"""Performance budgets for core pipeline math paths.

These tests act as regression gates so critical ingestion computations remain
within known runtime envelopes over time.
"""

from time import perf_counter

from stages.ingestion import haversine_distance, calculate_total_distance
from veloverse_pipeline import RoutePoint


def _build_points(count: int) -> list[RoutePoint]:
    base_lat = 45.8
    base_lon = 6.8
    return [
        RoutePoint(lat=base_lat + i * 0.00001, lon=base_lon + i * 0.00001)
        for i in range(count)
    ]


def test_haversine_distance_budget():
    loops = 50_000
    start = perf_counter()
    acc = 0.0
    for i in range(loops):
        acc += haversine_distance(
            45.8 + i * 0.000001,
            6.8 + i * 0.000001,
            45.8005 + i * 0.000001,
            6.8005 + i * 0.000001,
        )
    elapsed = perf_counter() - start

    # Keeps this strict but stable across typical CI runners.
    assert elapsed < 0.55, f"haversine budget exceeded: {elapsed:.3f}s for {loops} calls"
    assert acc > 0


def test_total_distance_budget():
    points = _build_points(2_000)
    start = perf_counter()
    distance = calculate_total_distance(points)
    elapsed = perf_counter() - start

    assert elapsed < 0.08, f"total_distance budget exceeded: {elapsed:.4f}s for 2,000 points"
    assert distance > 0
