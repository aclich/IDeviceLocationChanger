"""Tests for route cruise service functionality.

Tests cover:
- BrouterService: HTTP route fetching, retries, fallback
- RouteService: waypoint management, segment calculation
- Route cruise: movement delegation, arrival callbacks, loop mode
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.brouter_service import BrouterService
from services.route_service import (
    RouteService,
    RouteState,
    Waypoint,
    RouteSegment,
    Route,
    RouteSession,
)
from services.cruise_service import CruiseService, CruiseState
from services.coordinate_utils import distance_between


# =============================================================================
# BrouterService Tests
# =============================================================================

class TestBrouterService:
    """Tests for BrouterService HTTP route fetching."""

    @pytest.fixture
    def brouter_service(self):
        """Create a BrouterService instance."""
        return BrouterService()

    @pytest.mark.asyncio
    async def test_get_route_success(self, brouter_service):
        """Test successful route fetching from Brouter API."""
        # Mock successful HTTP response
        mock_response_data = {
            "features": [{
                "geometry": {
                    "coordinates": [
                        [121.5, 25.0],      # [lng, lat]
                        [121.505, 25.005],
                        [121.51, 25.01],
                    ]
                }
            }]
        }

        # Create mock response object
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        # Create mock session
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch.object(brouter_service, '_get_session', return_value=mock_session):
            result = await brouter_service.get_route((25.0, 121.5), (25.01, 121.51))

        assert result["is_fallback"] is False
        assert len(result["path"]) == 3
        # Verify lat/lng conversion (Brouter returns [lng, lat], we want [lat, lng])
        assert result["path"][0] == [25.0, 121.5]
        assert result["path"][1] == [25.005, 121.505]
        assert result["distance_km"] > 0

    @pytest.mark.asyncio
    async def test_get_route_http_error_fallback(self, brouter_service):
        """Test fallback to straight line on HTTP 500 error."""
        # Create mock response object
        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        # Create mock session
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch.object(brouter_service, '_get_session', return_value=mock_session):
            result = await brouter_service.get_route((25.0, 121.5), (25.01, 121.51))

        # Should fallback to straight line
        assert result["is_fallback"] is True
        assert len(result["path"]) == 2
        assert result["path"][0] == [25.0, 121.5]
        assert result["path"][1] == [25.01, 121.51]
        # Distance should be Haversine distance
        expected_dist = distance_between(25.0, 121.5, 25.01, 121.51)
        assert result["distance_km"] == pytest.approx(expected_dist, abs=0.001)

    @pytest.mark.asyncio
    async def test_get_route_timeout_fallback(self, brouter_service):
        """Test fallback on request timeout."""
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch.object(brouter_service, '_get_session', return_value=mock_session):
            result = await brouter_service.get_route((25.0, 121.5), (25.01, 121.51))

        # Should fallback to straight line after retries
        assert result["is_fallback"] is True
        assert len(result["path"]) == 2

    @pytest.mark.asyncio
    async def test_get_route_empty_coordinates_fallback(self, brouter_service):
        """Test fallback when Brouter returns empty coordinates."""
        mock_response_data = {
            "features": [{
                "geometry": {
                    "coordinates": []
                }
            }]
        }

        # Create mock response object
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response_data)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        # Create mock session
        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_resp)

        with patch.object(brouter_service, '_get_session', return_value=mock_session):
            result = await brouter_service.get_route((25.0, 121.5), (25.01, 121.51))

        assert result["is_fallback"] is True
        assert len(result["path"]) == 2

    @pytest.mark.asyncio
    async def test_get_route_retry_then_success(self, brouter_service):
        """Test retry logic - fails twice then succeeds."""
        call_count = 0

        def mock_get_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = AsyncMock()
            if call_count < 3:
                mock_resp.status = 503  # Service unavailable
                mock_resp.text = AsyncMock(return_value="Service Unavailable")
            else:
                mock_resp.status = 200
                mock_resp.json = AsyncMock(return_value={
                    "features": [{
                        "geometry": {
                            "coordinates": [[121.5, 25.0], [121.51, 25.01]]
                        }
                    }]
                })
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            return mock_resp

        mock_session = AsyncMock()
        mock_session.get = MagicMock(side_effect=mock_get_with_retry)

        with patch.object(brouter_service, '_get_session', return_value=mock_session):
            # Speed up retries by mocking sleep
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await brouter_service.get_route((25.0, 121.5), (25.01, 121.51))

        # Should succeed after retries
        assert result["is_fallback"] is False
        assert call_count == 3

    def test_calculate_path_distance(self, brouter_service):
        """Test path distance calculation."""
        # Simple straight north path
        path = [[25.0, 121.5], [25.01, 121.5], [25.02, 121.5]]
        distance = brouter_service._calculate_path_distance(path)

        # Each step is ~1.11 km (0.01 degrees latitude)
        assert distance == pytest.approx(2.22, abs=0.05)

    @pytest.mark.asyncio
    async def test_close_session(self, brouter_service):
        """Test closing the HTTP session."""
        mock_session = AsyncMock()
        mock_session.closed = False
        brouter_service._session = mock_session

        await brouter_service.close()

        mock_session.close.assert_called_once()


# =============================================================================
# RouteService - Route Building Tests
# =============================================================================

class TestRouteServiceBuilding:
    """Tests for RouteService waypoint and segment management."""

    @pytest.fixture
    def mock_brouter(self):
        """Create a mock BrouterService."""
        mock = AsyncMock()
        # Default: return simple 3-point path
        mock.get_route = AsyncMock(return_value={
            "path": [[25.0, 121.5], [25.005, 121.505], [25.01, 121.51]],
            "distance_km": 1.5,
            "is_fallback": False,
        })
        return mock

    @pytest.fixture
    def mock_cruise_service(self):
        """Create a mock CruiseService."""
        mock = MagicMock(spec=CruiseService)
        mock.start_cruise = MagicMock(return_value={"success": True})
        mock.stop_cruise = MagicMock(return_value={"success": True})
        mock.pause_cruise = MagicMock(return_value={"success": True})
        mock.resume_cruise = MagicMock(return_value={"success": True})
        mock.set_cruise_speed = MagicMock(return_value={"success": True})
        mock.on_arrival = MagicMock()
        mock.remove_arrival_callback = MagicMock()
        mock.cleanup_session = MagicMock()
        return mock

    @pytest.fixture
    def route_service(self, mock_cruise_service, mock_brouter):
        """Create a RouteService with mocked dependencies."""
        service = RouteService(mock_cruise_service, mock_brouter)
        service._emit_event = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_add_first_waypoint_start(self, route_service):
        """Test adding first waypoint sets START position."""
        result = await route_service.add_waypoint("device-1", 25.0, 121.5)

        assert result["success"] is True
        route = result["route"]
        assert len(route["waypoints"]) == 1
        assert route["waypoints"][0]["name"] == "START"
        assert route["waypoints"][0]["lat"] == 25.0
        assert route["waypoints"][0]["lng"] == 121.5
        assert len(route["segments"]) == 0  # No segments yet

    @pytest.mark.asyncio
    async def test_add_second_waypoint_creates_segment(self, route_service, mock_brouter):
        """Test adding second waypoint creates first segment."""
        # Add START
        await route_service.add_waypoint("device-1", 25.0, 121.5)

        # Add waypoint 1
        result = await route_service.add_waypoint("device-1", 25.01, 121.51)

        assert result["success"] is True
        route = result["route"]
        assert len(route["waypoints"]) == 2
        assert route["waypoints"][1]["name"] == "1"
        assert len(route["segments"]) == 1

        # Verify segment
        segment = route["segments"][0]
        assert segment["fromWaypoint"] == 0
        assert segment["toWaypoint"] == 1
        assert segment["distanceKm"] == 1.5
        assert segment["isFallback"] is False

        # Verify brouter was called
        mock_brouter.get_route.assert_called_once_with(
            (25.0, 121.5), (25.01, 121.51)
        )

    @pytest.mark.asyncio
    async def test_add_multiple_waypoints(self, route_service):
        """Test adding multiple waypoints builds route progressively."""
        # Add START and 3 waypoints
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)
        result = await route_service.add_waypoint("device-1", 25.03, 121.53)

        route = result["route"]
        assert len(route["waypoints"]) == 4
        assert len(route["segments"]) == 3
        assert route["waypoints"][0]["name"] == "START"
        assert route["waypoints"][1]["name"] == "1"
        assert route["waypoints"][2]["name"] == "2"
        assert route["waypoints"][3]["name"] == "3"

    @pytest.mark.asyncio
    async def test_set_loop_mode_adds_closure(self, route_service):
        """Test enabling loop mode adds closure segment."""
        # Build route: START -> 1 -> 2
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)

        # Enable loop mode
        result = await route_service.set_loop_mode("device-1", enabled=True)

        assert result["success"] is True
        route = result["route"]
        assert route["loopMode"] is True
        assert len(route["segments"]) == 3  # 2 normal + 1 closure

        # Last segment should be closure (waypoint 2 -> START)
        closure = route["segments"][-1]
        assert closure["isClosure"] is True
        assert closure["fromWaypoint"] == 2
        assert closure["toWaypoint"] == 0

    @pytest.mark.asyncio
    async def test_set_loop_mode_removes_closure(self, route_service):
        """Test disabling loop mode removes closure segment."""
        # Build route with loop
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)
        await route_service.set_loop_mode("device-1", enabled=True)

        # Disable loop mode
        result = await route_service.set_loop_mode("device-1", enabled=False)

        assert result["success"] is True
        route = result["route"]
        assert route["loopMode"] is False
        assert len(route["segments"]) == 2  # Only normal segments
        # No closure segment
        assert not any(s["isClosure"] for s in route["segments"])

    @pytest.mark.asyncio
    async def test_add_waypoint_with_loop_recalculates_closure(self, route_service):
        """Test adding waypoint in loop mode recalculates closure."""
        # Build route with loop
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.set_loop_mode("device-1", enabled=True)

        # Add another waypoint (should remove old closure, add new one)
        result = await route_service.add_waypoint("device-1", 25.02, 121.52)

        route = result["route"]
        assert len(route["segments"]) == 3  # START->1, 1->2, 2->START
        closure = route["segments"][-1]
        assert closure["isClosure"] is True
        assert closure["fromWaypoint"] == 2  # From new waypoint
        assert closure["toWaypoint"] == 0    # To START

    @pytest.mark.asyncio
    async def test_undo_waypoint(self, route_service):
        """Test removing last waypoint."""
        # Build route with 3 waypoints
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)

        # Undo last waypoint
        result = await route_service.undo_waypoint("device-1")

        assert result["success"] is True
        route = result["route"]
        assert len(route["waypoints"]) == 2  # START and 1
        assert len(route["segments"]) == 1   # Only START->1

    @pytest.mark.asyncio
    async def test_undo_waypoint_with_loop_recalculates_closure(self, route_service):
        """Test undo in loop mode recalculates closure."""
        # Build route with loop
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)
        await route_service.set_loop_mode("device-1", enabled=True)

        # Undo last waypoint
        result = await route_service.undo_waypoint("device-1")

        route = result["route"]
        assert len(route["waypoints"]) == 2
        assert len(route["segments"]) == 2  # START->1, 1->START
        closure = route["segments"][-1]
        assert closure["isClosure"] is True
        assert closure["fromWaypoint"] == 1
        assert closure["toWaypoint"] == 0

    @pytest.mark.asyncio
    async def test_undo_waypoint_cannot_undo_while_cruising(self, route_service):
        """Test cannot undo waypoint while route cruise is active."""
        # Build route
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        await route_service.add_waypoint("device-1", 25.02, 121.52)

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Try to undo
        result = await route_service.undo_waypoint("device-1")

        assert result["success"] is False
        assert "Cannot modify route while cruising" in result["error"]

        # Clean up
        route_service.stop_route_cruise("device-1")

    @pytest.mark.asyncio
    async def test_undo_waypoint_no_waypoints_to_undo(self, route_service):
        """Test undo with no waypoints returns error."""
        result = await route_service.undo_waypoint("device-1")

        assert result["success"] is False
        assert "No waypoint to undo" in result["error"]

    @pytest.mark.asyncio
    async def test_undo_waypoint_only_start_clears_route(self, route_service):
        """Test undoing START when it's the only waypoint clears the route."""
        await route_service.add_waypoint("device-1", 25.0, 121.5)

        result = await route_service.undo_waypoint("device-1")

        assert result["success"] is True
        assert result["route"]["waypoints"] == []
        assert result["route"]["segments"] == []

    def test_clear_route(self, route_service):
        """Test clearing route removes all waypoints."""
        # Add route using event loop
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )

        result = route_service.clear_route("device-1")

        assert result["success"] is True
        # Verify route is empty
        status = route_service.get_route_status("device-1")
        assert len(status["route"]["waypoints"]) == 0

    def test_clear_route_cannot_clear_while_cruising(self, route_service):
        """Test cannot clear route while cruise is active."""
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        # start_route_cruise is sync
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        result = route_service.clear_route("device-1")

        assert result["success"] is False
        assert "Stop route cruise before clearing" in result["error"]

        # Clean up (sync)
        route_service.stop_route_cruise("device-1")

    def test_get_route_status_no_route(self, route_service):
        """Test getting status when no route exists."""
        status = route_service.get_route_status("device-1")

        assert len(status["route"]["waypoints"]) == 0
        assert status["cruiseState"]["state"] == "idle"

    @pytest.mark.asyncio
    async def test_total_distance_calculation(self, route_service):
        """Test route total distance is sum of segments."""
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)
        result = await route_service.add_waypoint("device-1", 25.02, 121.52)

        # Total should be sum of both segments (each 1.5 km from mock)
        assert result["route"]["totalDistanceKm"] == pytest.approx(3.0, abs=0.01)


# =============================================================================
# RouteService - Route Cruise Tests
# =============================================================================

class TestRouteServiceCruise:
    """Tests for RouteService cruise movement and delegation."""

    @pytest.fixture
    def mock_brouter(self):
        """Create a mock BrouterService with simple paths."""
        mock = AsyncMock()
        # Return simple 3-point paths
        mock.get_route = AsyncMock(return_value={
            "path": [[25.0, 121.5], [25.005, 121.505], [25.01, 121.51]],
            "distance_km": 1.5,
            "is_fallback": False,
        })
        return mock

    @pytest.fixture
    def mock_cruise_service(self):
        """Create a mock CruiseService."""
        mock = MagicMock(spec=CruiseService)
        mock.start_cruise = MagicMock(return_value={"success": True})
        mock.stop_cruise = MagicMock(return_value={"success": True})
        mock.pause_cruise = MagicMock(return_value={"success": True})
        mock.resume_cruise = MagicMock(return_value={"success": True})
        mock.set_cruise_speed = MagicMock(return_value={"success": True})
        mock.on_arrival = MagicMock()
        mock.remove_arrival_callback = MagicMock()
        mock.cleanup_session = MagicMock()
        return mock

    @pytest.fixture
    def route_service(self, mock_cruise_service, mock_brouter):
        """Create a RouteService with mocked dependencies."""
        service = RouteService(mock_cruise_service, mock_brouter)
        service._emit_event = MagicMock()
        return service

    def test_start_route_cruise_success(self, route_service, mock_cruise_service):
        """Test starting route cruise delegates to CruiseService."""
        # Build route (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )

        # Start cruise (sync)
        result = route_service.start_route_cruise("device-1", speed_kmh=10.0)

        assert result["success"] is True
        assert result["session"]["state"] == "running"

        # Verify arrival callback registered
        mock_cruise_service.on_arrival.assert_called_once_with(
            "device-1", route_service._on_point_arrival
        )

        # Verify CruiseService.start_cruise called for first point pair
        mock_cruise_service.start_cruise.assert_called_once()
        call_args = mock_cruise_service.start_cruise.call_args[1]
        assert call_args["device_id"] == "device-1"
        assert call_args["speed_kmh"] == 10.0
        # First point pair: path[0] -> path[1]
        assert call_args["start_lat"] == 25.0
        assert call_args["start_lon"] == 121.5

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_start_route_cruise_insufficient_waypoints(self, route_service):
        """Test cannot start route cruise with less than 2 waypoints."""
        # Only START
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )

        result = route_service.start_route_cruise("device-1", speed_kmh=10.0)

        assert result["success"] is False
        assert "needs at least 2 points" in result["error"]

    def test_start_route_cruise_stops_existing_regular_cruise(
        self, route_service, mock_cruise_service
    ):
        """Test starting route cruise stops any existing regular cruise."""
        # Build route (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )

        # Start route cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Verify stop_cruise was called
        mock_cruise_service.stop_cruise.assert_called_with("device-1")

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_point_arrival_advances_to_next_point(
        self, route_service, mock_cruise_service
    ):
        """Test arrival callback advances to next point in segment."""
        # Build route with 3-point path per segment (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Simulate arrival at first point
        session = route_service._sessions["device-1"]
        assert session.current_step_in_segment == 0

        # Call arrival callback (sync)
        arrival_data = {
            "deviceId": "device-1",
            "location": {"latitude": 25.005, "longitude": 121.505},
            "distanceTraveledKm": 0.75,
            "durationSeconds": 270,
        }
        route_service._on_point_arrival("device-1", arrival_data)

        # Should advance to next step
        session = route_service._sessions["device-1"]
        assert session.current_step_in_segment == 1
        assert session.distance_traveled_km == 0.75

        # CruiseService.start_cruise should be called again for next point pair
        assert mock_cruise_service.start_cruise.call_count == 2

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_segment_completion_advances_to_next_segment(
        self, route_service, mock_cruise_service
    ):
        """Test completing segment's polyline advances to next segment."""
        # Build route with 2 segments (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.02, 121.52)
        )

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        session = route_service._sessions["device-1"]
        assert session.current_segment_index == 0
        assert session.current_step_in_segment == 0

        # Simulate arrivals for all points in first segment
        # Path has 3 points: [0]->[1], [1]->[2]
        # After 2 arrivals, segment should complete
        route_service._on_point_arrival("device-1", {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270})
        route_service._on_point_arrival("device-1", {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270})

        # Should advance to segment 1
        session = route_service._sessions["device-1"]
        assert session.current_segment_index == 1
        assert session.current_step_in_segment == 0
        assert session.segments_completed == 1

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_route_completion_non_loop(self, route_service, mock_cruise_service):
        """Test route completes and session removed in non-loop mode."""
        # Build simple route (2 segments with 3 points each) (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.02, 121.52)
        )

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Simulate completing all segments
        # 2 segments * 2 point pairs + 1 bridge between segments = 5 arrivals
        for _ in range(5):
            if "device-1" in route_service._sessions:
                route_service._on_point_arrival(
                    "device-1",
                    {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270}
                )

        # Session should be removed (route arrived)
        assert "device-1" not in route_service._sessions

        # Verify arrival callback removed and cruise session cleaned up
        mock_cruise_service.remove_arrival_callback.assert_called_with("device-1")
        mock_cruise_service.cleanup_session.assert_called_with("device-1")

    def test_route_completion_loop_mode(self, route_service, mock_cruise_service):
        """Test route loops back in loop mode."""
        # Build route with loop (3 segments including closure) (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.02, 121.52)
        )
        asyncio.run(
            route_service.set_loop_mode("device-1", enabled=True)
        )

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Simulate completing all 3 segments + bridge cruises between them
        # 3 segments * 2 point pairs + 2 bridges between segs + 1 bridge for loop restart = 9 arrivals
        for _ in range(9):
            if "device-1" in route_service._sessions:
                route_service._on_point_arrival(
                    "device-1",
                    {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270}
                )

        # Session should still exist and loop back to segment 0
        assert "device-1" in route_service._sessions
        session = route_service._sessions["device-1"]
        assert session.current_segment_index == 0
        assert session.loops_completed == 1

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_pause_route_cruise(self, route_service, mock_cruise_service):
        """Test pausing route cruise."""
        # Build and start route (async for build, sync for cruise)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Pause (sync)
        result = route_service.pause_route_cruise("device-1")

        assert result["success"] is True
        assert result["session"]["state"] == "paused"
        mock_cruise_service.pause_cruise.assert_called_once_with("device-1")

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_resume_route_cruise(self, route_service, mock_cruise_service):
        """Test resuming paused route cruise."""
        # Build, start, and pause route
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)
        route_service.pause_route_cruise("device-1")

        # Resume (sync)
        result = route_service.resume_route_cruise("device-1")

        assert result["success"] is True
        assert result["session"]["state"] == "running"
        mock_cruise_service.resume_cruise.assert_called_once_with("device-1")

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_pause_no_active_cruise(self, route_service):
        """Test pausing when no active cruise."""
        result = route_service.pause_route_cruise("device-1")

        assert result["success"] is False
        assert "No active route cruise" in result["error"]

    def test_resume_not_paused(self, route_service):
        """Test resuming when not paused."""
        # Build and start route (running state)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Try to resume (should fail, sync)
        result = route_service.resume_route_cruise("device-1")

        assert result["success"] is False
        assert "Cannot resume" in result["error"]

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_stop_route_cruise(self, route_service, mock_cruise_service):
        """Test stopping route cruise."""
        # Build and start route
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Stop (sync)
        result = route_service.stop_route_cruise("device-1")

        assert result["success"] is True
        assert "device-1" not in route_service._sessions

        # Verify callbacks
        mock_cruise_service.remove_arrival_callback.assert_called_with("device-1")
        mock_cruise_service.stop_cruise.assert_called()

    def test_set_route_speed(self, route_service, mock_cruise_service):
        """Test adjusting route cruise speed."""
        # Build and start route
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Change speed
        result = route_service.set_route_speed("device-1", 20.0)

        assert result["success"] is True
        assert result["speedKmh"] == 20.0
        mock_cruise_service.set_cruise_speed.assert_called_with("device-1", 20.0)

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_set_route_speed_minimum_clamp(self, route_service):
        """Test route speed has minimum clamp."""
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Try to set very low speed
        result = route_service.set_route_speed("device-1", 0.05)

        # Should be clamped to 0.1
        assert result["speedKmh"] == 0.1

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_set_route_speed_no_active_cruise(self, route_service):
        """Test setting speed when no active cruise."""
        result = route_service.set_route_speed("device-1", 20.0)

        assert result["success"] is False
        assert "No active route cruise" in result["error"]

    def test_stop_all(self, route_service):
        """Test stopping all route cruise sessions."""
        # Start multiple route cruises
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        asyncio.run(
            route_service.add_waypoint("device-2", 26.0, 122.0)
        )
        asyncio.run(
            route_service.add_waypoint("device-2", 26.01, 122.01)
        )
        route_service.start_route_cruise("device-2", speed_kmh=15.0)

        # Stop all (sync)
        route_service.stop_all()

        # Both should be stopped
        assert "device-1" not in route_service._sessions
        assert "device-2" not in route_service._sessions

    def test_remaining_distance_calculation(self, route_service):
        """Test remaining distance calculation during cruise."""
        # Build route (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.02, 121.52)
        )

        # Start cruise (sync)
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        session = route_service._sessions["device-1"]
        initial_remaining = session.remaining_distance_km()

        # Should be total of all segments
        assert initial_remaining == pytest.approx(3.0, abs=0.1)

        # Advance one point (sync)
        route_service._on_point_arrival(
            "device-1",
            {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270}
        )

        # Remaining should decrease
        session = route_service._sessions["device-1"]
        new_remaining = session.remaining_distance_km()
        assert new_remaining < initial_remaining

        # Clean up
        route_service.stop_route_cruise("device-1")


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================

class TestRouteServiceEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.fixture
    def mock_brouter(self):
        """Create a mock BrouterService."""
        mock = AsyncMock()
        mock.get_route = AsyncMock(return_value={
            "path": [[25.0, 121.5], [25.005, 121.505], [25.01, 121.51]],
            "distance_km": 1.5,
            "is_fallback": False,
        })
        return mock

    @pytest.fixture
    def mock_cruise_service(self):
        """Create a mock CruiseService."""
        mock = MagicMock(spec=CruiseService)
        mock.start_cruise = MagicMock(return_value={"success": True})
        mock.stop_cruise = MagicMock(return_value={"success": True})
        mock.pause_cruise = MagicMock(return_value={"success": True})
        mock.resume_cruise = MagicMock(return_value={"success": True})
        mock.set_cruise_speed = MagicMock(return_value={"success": True})
        mock.on_arrival = MagicMock()
        mock.remove_arrival_callback = MagicMock()
        mock.cleanup_session = MagicMock()
        return mock

    @pytest.fixture
    def route_service(self, mock_cruise_service, mock_brouter):
        """Create a RouteService with mocked dependencies."""
        service = RouteService(mock_cruise_service, mock_brouter)
        service._emit_event = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_brouter_fallback_marked_in_segment(self, route_service, mock_brouter):
        """Test segment is marked as fallback when Brouter fails."""
        # Make brouter return fallback
        mock_brouter.get_route = AsyncMock(return_value={
            "path": [[25.0, 121.5], [25.01, 121.51]],
            "distance_km": 1.2,
            "is_fallback": True,
        })

        # Build route
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        result = await route_service.add_waypoint("device-1", 25.01, 121.51)

        # Segment should be marked as fallback
        segment = result["route"]["segments"][0]
        assert segment["isFallback"] is True

    @pytest.mark.asyncio
    async def test_multi_device_routes(self, route_service):
        """Test multiple devices can have independent routes."""
        # Build routes for two devices
        await route_service.add_waypoint("device-1", 25.0, 121.5)
        await route_service.add_waypoint("device-1", 25.01, 121.51)

        await route_service.add_waypoint("device-2", 26.0, 122.0)
        await route_service.add_waypoint("device-2", 26.01, 122.01)

        # Both should have routes
        status1 = route_service.get_route_status("device-1")
        status2 = route_service.get_route_status("device-2")

        assert len(status1["route"]["waypoints"]) == 2
        assert len(status2["route"]["waypoints"]) == 2
        assert status1["route"]["waypoints"][0]["lat"] == 25.0
        assert status2["route"]["waypoints"][0]["lat"] == 26.0

    def test_arrival_callback_ignores_paused_state(self, route_service):
        """Test arrival callback does nothing when route is paused."""
        # Build and start route
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Pause (sync)
        route_service.pause_route_cruise("device-1")

        session = route_service._sessions["device-1"]
        initial_step = session.current_step_in_segment

        # Call arrival callback while paused (sync)
        route_service._on_point_arrival(
            "device-1",
            {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270}
        )

        # Should not advance
        session = route_service._sessions["device-1"]
        assert session.current_step_in_segment == initial_step

        # Clean up
        route_service.stop_route_cruise("device-1")

    @pytest.mark.asyncio
    async def test_event_emission_on_waypoint_add(self, route_service):
        """Test events are emitted when waypoints are added."""
        await route_service.add_waypoint("device-1", 25.0, 121.5)

        # Check event was emitted
        calls = route_service._emit_event.call_args_list
        events = [c[0][0] for c in calls]
        assert any(e.get("event") == "routeWaypointAdded" for e in events)

    def test_event_emission_on_route_start(self, route_service):
        """Test events are emitted when route cruise starts."""
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Check routeStarted event
        calls = route_service._emit_event.call_args_list
        events = [c[0][0] for c in calls]
        assert any(e.get("event") == "routeStarted" for e in events)

        # Clean up
        route_service.stop_route_cruise("device-1")

    def test_event_emission_on_loop_complete(self, route_service, mock_cruise_service):
        """Test routeLoopComplete event emitted when loop completes."""
        # Build loop route (async)
        asyncio.run(
            route_service.add_waypoint("device-1", 25.0, 121.5)
        )
        asyncio.run(
            route_service.add_waypoint("device-1", 25.01, 121.51)
        )
        asyncio.run(
            route_service.set_loop_mode("device-1", enabled=True)
        )
        route_service.start_route_cruise("device-1", speed_kmh=10.0)

        # Complete all segments + bridge cruises
        # 2 segments * 2 point pairs + 1 bridge + loop restart triggers on 5th arrival
        for _ in range(5):
            if "device-1" in route_service._sessions:
                route_service._on_point_arrival(
                    "device-1",
                    {"deviceId": "device-1", "location": {}, "distanceTraveledKm": 0.75, "durationSeconds": 270}
                )

        # Check routeLoopComplete event
        calls = route_service._emit_event.call_args_list
        events = [c[0][0] for c in calls]
        assert any(e.get("event") == "routeLoopComplete" for e in events)

        # Clean up
        route_service.stop_route_cruise("device-1")
