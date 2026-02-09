"""Tests for route cruise speed behavior and dynamic arrival threshold.

Covers:
- arrival_threshold_km function: purely speed-based, no static floor
- Integration scenarios run in parallel:
  - Walking pace: 5 km/h over ~4m
  - Highway speed: 120 km/h over ~100m
  - Slow + short: 1 km/h over ~1m (traveled, not skipped)
  - Multi-point: 5 km/h, 4 points ~1m apart
  - Fine-grained: 10 km/h, 10 points ~0.5m apart

All integration scenarios target ~3s cruise time and run concurrently
in threads, so total wall time ≈ max(scenarios) ≈ 4-5s instead of sum.
"""

import asyncio
import threading
import time

import pytest
from unittest.mock import AsyncMock, MagicMock

from services.cruise_service import (
    CruiseService,
    ARRIVAL_THRESHOLD_KM,
    arrival_threshold_km,
)
from services.route_service import RouteService
from services.coordinate_utils import distance_between


# =============================================================================
# Unit tests: arrival_threshold_km
# =============================================================================

class TestArrivalThreshold:
    """Unit tests for the dynamic arrival threshold function."""

    def test_threshold_scales_with_speed(self):
        """Threshold = speed_kmh / 720_000 for all positive speeds."""
        assert arrival_threshold_km(5.0) == pytest.approx(5.0 / 720_000)
        assert arrival_threshold_km(100.0) == pytest.approx(100.0 / 720_000)
        assert arrival_threshold_km(3600) == pytest.approx(0.005)
        assert arrival_threshold_km(7200) == pytest.approx(0.01)
        assert arrival_threshold_km(36000) == pytest.approx(0.05)

    def test_slow_speed_tiny_threshold(self):
        """At slow speeds, threshold is very small (not clamped to 5m)."""
        # 0.1 km/h → 0.1 / 720000 ≈ 1.39e-7 km ≈ 0.14mm
        thresh = arrival_threshold_km(0.1)
        assert thresh < 0.000001  # less than 1mm
        assert thresh > 0

    def test_zero_speed_returns_minimum(self):
        """Zero speed returns 1mm floor, does not crash."""
        assert arrival_threshold_km(0) == 0.000001

    def test_negative_speed_returns_minimum(self):
        """Negative speed returns 1mm floor."""
        assert arrival_threshold_km(-10) == 0.000001

    def test_traversal_time_always_5ms(self):
        """For any positive speed, time to cross the threshold is exactly 5ms."""
        speeds = [0.1, 1, 5, 10, 50, 100, 500, 1000, 3600, 7200, 36000, 360000]
        for speed in speeds:
            threshold = arrival_threshold_km(speed)
            time_hours = threshold / speed
            time_ms = time_hours * 3_600_000
            assert time_ms == pytest.approx(5.0, rel=1e-9), (
                f"speed={speed} km/h: traversal time {time_ms:.4f}ms != 5ms"
            )

    def test_legacy_constant_still_exported(self):
        """ARRIVAL_THRESHOLD_KM constant is still available (5m)."""
        assert ARRIVAL_THRESHOLD_KM == 0.005


# =============================================================================
# Integration helpers
# =============================================================================

def _build_route(route_service, mock_brouter, device_id, points):
    """Build a route where each consecutive pair is a separate segment."""
    for i, pt in enumerate(points):
        if i == 0:
            asyncio.run(route_service.add_waypoint(device_id, pt[0], pt[1]))
        else:
            prev = points[i - 1]
            path = [prev, pt]
            dist = distance_between(prev[0], prev[1], pt[0], pt[1])
            mock_brouter.get_route = AsyncMock(return_value={
                "path": path,
                "distance_km": dist,
                "is_fallback": True,
            })
            asyncio.run(route_service.add_waypoint(device_id, pt[0], pt[1]))


def _build_route_multipoint_segment(route_service, mock_brouter, device_id, points):
    """Build a route as a single segment with a multi-point polyline."""
    asyncio.run(route_service.add_waypoint(device_id, points[0][0], points[0][1]))
    total_dist = sum(
        distance_between(
            points[i][0], points[i][1],
            points[i + 1][0], points[i + 1][1],
        )
        for i in range(len(points) - 1)
    )
    mock_brouter.get_route = AsyncMock(return_value={
        "path": points,
        "distance_km": total_dist,
        "is_fallback": True,
    })
    asyncio.run(route_service.add_waypoint(device_id, points[-1][0], points[-1][1]))


def _wait_for_route_arrival(route_service):
    """Intercept events to detect routeArrived. Returns (event, data_holder)."""
    arrived = threading.Event()
    arrival_data = {}
    original_mock = route_service._emit_event  # MagicMock

    def capture(event_data):
        original_mock(event_data)
        if event_data.get("event") == "routeArrived":
            arrival_data.update(event_data.get("data", {}))
            arrived.set()

    route_service._emit_event = capture
    return arrived, arrival_data


def _make_services():
    """Create a real CruiseService + RouteService with mock dependencies."""
    cruise = CruiseService()
    cruise.set_location_callback(MagicMock(return_value={"success": True}))
    cruise.set_event_emitter(MagicMock())
    brouter = AsyncMock()
    route = RouteService(cruise, brouter)
    route._emit_event = MagicMock()
    return cruise, brouter, route


# =============================================================================
# Scenario definitions
# =============================================================================

def _scenario_walking():
    """5 km/h over ~4m, single segment. (~3s)"""
    return {
        "name": "walking",
        "speed_kmh": 5.0,
        "points": [[25.0, 121.5], [25.000036, 121.5]],
        "multipoint": False,
        "check_speed": True,
        "time_abs": 2.0,
    }


def _scenario_highway():
    """120 km/h over ~100m, single segment. (~3s)"""
    return {
        "name": "highway",
        "speed_kmh": 120.0,
        "points": [[25.0, 121.5], [25.0009, 121.5]],
        "multipoint": False,
        "check_speed": True,
        "time_abs": 2.0,
    }


def _scenario_slow_short():
    """1 km/h over ~1m — traveled, not skipped. (~3.6s)"""
    return {
        "name": "slow-short",
        "speed_kmh": 1.0,
        "points": [[25.0, 121.5], [25.000009, 121.5]],
        "multipoint": False,
        "check_speed": False,  # single tick overhead is large fraction
        "time_abs": 2.0,
    }


def _scenario_multi_step():
    """5 km/h, 4 points ~1m apart, all traveled. (~3s)"""
    return {
        "name": "multi-step",
        "speed_kmh": 5.0,
        "points": [[25.0 + i * 0.000009, 121.5] for i in range(4)],
        "multipoint": True,
        "check_speed": False,  # transition overhead
        "time_abs": 2.0,
    }


def _scenario_fine_grained():
    """10 km/h, 10 points ~0.5m apart. (~3s + transition overhead)"""
    return {
        "name": "fine-grained",
        "speed_kmh": 10.0,
        "points": [[25.0 + i * 0.0000045, 121.5] for i in range(10)],
        "multipoint": True,
        "check_speed": False,  # 9 transitions dominate
        "time_abs": 3.7,       # 1.0 + 9 * 0.3
    }


ALL_SCENARIOS = [
    _scenario_walking,
    _scenario_highway,
    _scenario_slow_short,
    _scenario_multi_step,
    _scenario_fine_grained,
]


# =============================================================================
# Single-scenario runner (used by threads)
# =============================================================================

def _run_scenario(scenario: dict) -> dict:
    """Run one integration scenario. Returns result dict with measurements.

    Runs in its own thread with fully independent services.
    Never raises — captures errors into result["error"].
    """
    result = {"name": scenario["name"], "error": None}

    try:
        cruise, brouter, route_svc = _make_services()
        device_id = scenario["name"]
        speed_kmh = scenario["speed_kmh"]
        points = scenario["points"]

        # Calculate expected route distance
        route_dist = sum(
            distance_between(
                points[i][0], points[i][1],
                points[i + 1][0], points[i + 1][1],
            )
            for i in range(len(points) - 1)
        )

        # Build route
        if scenario["multipoint"]:
            _build_route_multipoint_segment(route_svc, brouter, device_id, points)
        else:
            _build_route(route_svc, brouter, device_id, points)

        arrived, arrival_data = _wait_for_route_arrival(route_svc)

        # Run cruise
        wall_start = time.time()
        route_svc.start_route_cruise(device_id, speed_kmh=speed_kmh)

        if not arrived.wait(timeout=15):
            result["error"] = f"[{scenario['name']}] Route did not arrive within 15s"
            route_svc.stop_all()
            cruise.stop_all()
            return result

        wall_elapsed = time.time() - wall_start

        # Collect measurements
        result["route_dist"] = route_dist
        result["traveled"] = arrival_data["distanceTraveledKm"]
        result["wall_elapsed"] = wall_elapsed
        result["expected_time"] = route_dist / speed_kmh * 3600
        result["speed_kmh"] = speed_kmh
        result["check_speed"] = scenario["check_speed"]
        result["time_abs"] = scenario["time_abs"]

        route_svc.stop_all()
        cruise.stop_all()

    except Exception as e:
        result["error"] = f"[{scenario['name']}] Exception: {e}"

    return result


# =============================================================================
# Integration: all scenarios run concurrently
# =============================================================================

class TestIntegrationParallel:
    """Run all speed/distance scenarios concurrently, assert after all finish."""

    def test_all_scenarios_concurrent(self):
        """Launch 5 independent route cruises in parallel threads.

        Each scenario creates its own CruiseService + RouteService.
        Total wall time ≈ max(~3-4s) instead of sum(~15s).
        """
        scenarios = [fn() for fn in ALL_SCENARIOS]
        results: list[dict] = [None] * len(scenarios)

        def run(index, scenario):
            results[index] = _run_scenario(scenario)

        threads = [
            threading.Thread(target=run, args=(i, s), name=f"test-{s['name']}")
            for i, s in enumerate(scenarios)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        # Collect all assertion failures, report together
        failures = []

        for r in results:
            if r is None:
                failures.append("A scenario thread did not complete")
                continue
            if r["error"]:
                failures.append(r["error"])
                continue

            name = r["name"]
            traveled = r["traveled"]
            route_dist = r["route_dist"]
            wall_elapsed = r["wall_elapsed"]
            expected_time = r["expected_time"]
            speed_kmh = r["speed_kmh"]

            # Distance: traveled ≈ route distance
            if abs(traveled - route_dist) / route_dist > 0.05:
                failures.append(
                    f"[{name}] Distance: traveled {traveled:.5f} km "
                    f"vs route {route_dist:.5f} km (>5% off)"
                )

            # Time: wall clock ≈ expected time
            if abs(wall_elapsed - expected_time) > r["time_abs"]:
                failures.append(
                    f"[{name}] Time: {wall_elapsed:.2f}s "
                    f"vs expected {expected_time:.2f}s "
                    f"(tolerance {r['time_abs']:.1f}s)"
                )

            # Speed (only for single-segment scenarios without transition overhead)
            if r["check_speed"] and wall_elapsed > 0:
                actual_speed = traveled / wall_elapsed * 3600
                if abs(actual_speed - speed_kmh) / speed_kmh > 0.25:
                    failures.append(
                        f"[{name}] Speed: actual {actual_speed:.2f} "
                        f"vs set {speed_kmh} km/h (>25% off)"
                    )

        assert not failures, "Scenario failures:\n" + "\n".join(failures)
