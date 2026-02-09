"""Tests for cruise mode functionality."""

import time
import pytest
from unittest.mock import MagicMock

from services.coordinate_utils import move_location, bearing_to, distance_between
from services.cruise_service import CruiseService, CruiseState


# =============================================================================
# Coordinate Utils Tests
# =============================================================================

class TestCoordinateUtils:
    """Tests for coordinate calculation utilities."""

    def test_distance_between_same_point(self):
        """Distance between same point should be 0."""
        dist = distance_between(25.0, 121.5, 25.0, 121.5)
        assert dist == pytest.approx(0, abs=1e-10)

    def test_distance_between_known_points(self):
        """Test distance calculation with known values."""
        # Taipei 101 to Taipei Main Station - approximately 2.5km
        taipei_101 = (25.0339, 121.5645)
        taipei_station = (25.0478, 121.5170)
        dist = distance_between(*taipei_101, *taipei_station)
        assert 4.5 < dist < 5.5  # Roughly 5km

    def test_bearing_north(self):
        """Bearing due north should be 0 degrees."""
        bearing = bearing_to(25.0, 121.5, 26.0, 121.5)
        assert bearing == pytest.approx(0, abs=1)

    def test_bearing_east(self):
        """Bearing due east should be 90 degrees."""
        bearing = bearing_to(25.0, 121.5, 25.0, 122.5)
        assert bearing == pytest.approx(90, abs=1)

    def test_bearing_south(self):
        """Bearing due south should be 180 degrees."""
        bearing = bearing_to(25.0, 121.5, 24.0, 121.5)
        assert bearing == pytest.approx(180, abs=1)

    def test_bearing_west(self):
        """Bearing due west should be 270 degrees."""
        bearing = bearing_to(25.0, 121.5, 25.0, 120.5)
        assert bearing == pytest.approx(270, abs=1)

    def test_move_location_north(self):
        """Moving north should increase latitude."""
        lat, lon = move_location(25.0, 121.5, 0, 10, 1)  # 10 km/h for 1 second
        assert lat > 25.0
        assert lon == pytest.approx(121.5, abs=1e-6)

    def test_move_location_east(self):
        """Moving east should increase longitude."""
        lat, lon = move_location(25.0, 121.5, 90, 10, 1)  # 10 km/h for 1 second
        assert lat == pytest.approx(25.0, abs=1e-5)
        assert lon > 121.5

    def test_move_location_distance(self):
        """Verify movement covers expected distance."""
        # Move at 36 km/h for 100 seconds = 1 km
        new_lat, new_lon = move_location(25.0, 121.5, 0, 36, 100)
        dist = distance_between(25.0, 121.5, new_lat, new_lon)
        assert dist == pytest.approx(1.0, abs=0.01)

    def test_move_location_zero_duration(self):
        """Zero duration should not move."""
        lat, lon = move_location(25.0, 121.5, 45, 50, 0)
        assert lat == pytest.approx(25.0, abs=1e-10)
        assert lon == pytest.approx(121.5, abs=1e-10)


# =============================================================================
# Cruise Service Tests
# =============================================================================

class TestCruiseService:
    """Tests for CruiseService class."""

    @pytest.fixture
    def cruise_service(self):
        """Create a CruiseService with mocked callbacks."""
        service = CruiseService()
        service._set_location = MagicMock(return_value={"success": True})
        service._emit_event = MagicMock()
        return service

    def test_start_cruise_success(self, cruise_service):
        """Test starting cruise mode."""
        result = cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.01,
            target_lon=121.5,
            speed_kmh=10.0
        )

        assert result["success"] is True
        assert "session" in result
        assert result["session"]["state"] == "running"
        assert cruise_service.get_cruise_status("test-device")["state"] == "running"

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_start_cruise_already_at_target(self, cruise_service):
        """Test starting cruise when already at target location."""
        result = cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.0,
            target_lon=121.5,
            speed_kmh=10.0
        )

        assert result["success"] is False
        assert "Already at target" in result["error"]

    def test_stop_cruise(self, cruise_service):
        """Test stopping cruise mode."""
        # Start cruise first
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.1,
            target_lon=121.5,
            speed_kmh=10.0
        )

        # Stop it
        result = cruise_service.stop_cruise("test-device")

        assert result["success"] is True
        assert cruise_service.get_cruise_status("test-device")["state"] == "idle"

    def test_pause_resume_cruise(self, cruise_service):
        """Test pause and resume functionality."""
        # Start cruise
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.1,
            target_lon=121.5,
            speed_kmh=10.0
        )

        # Pause
        result = cruise_service.pause_cruise("test-device")
        assert result["success"] is True
        assert cruise_service.get_cruise_status("test-device")["state"] == "paused"

        # Resume
        result = cruise_service.resume_cruise("test-device")
        assert result["success"] is True
        assert cruise_service.get_cruise_status("test-device")["state"] == "running"

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_pause_when_not_running(self, cruise_service):
        """Test pausing when not in running state."""
        result = cruise_service.pause_cruise("test-device")
        assert result["success"] is False
        assert "No active cruise" in result["error"]

    def test_resume_when_not_paused(self, cruise_service):
        """Test resuming when not paused."""
        # Start cruise (running state)
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.1,
            target_lon=121.5,
            speed_kmh=10.0
        )

        # Try to resume (should fail - already running)
        result = cruise_service.resume_cruise("test-device")
        assert result["success"] is False

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_set_cruise_speed(self, cruise_service):
        """Test setting cruise speed."""
        # Need an active cruise first
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.1,
            target_lon=121.5,
            speed_kmh=10.0
        )

        result = cruise_service.set_cruise_speed("test-device", 20.0)
        assert result["success"] is True
        assert result["speedKmh"] == 20.0

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_set_cruise_speed_clamp(self, cruise_service):
        """Test speed clamping to valid range."""
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.1,
            target_lon=121.5,
            speed_kmh=10.0
        )

        # No upper clamp - high speeds pass through
        result = cruise_service.set_cruise_speed("test-device", 100.0)
        assert result["speedKmh"] == 100.0

        # Lower bound: minimum is 0.1 km/h to prevent stall
        result = cruise_service.set_cruise_speed("test-device", 0.05)
        assert result["speedKmh"] == 0.1

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_get_cruise_status_idle(self, cruise_service):
        """Test getting status when no cruise is active."""
        status = cruise_service.get_cruise_status("test-device")
        assert status["state"] == "idle"
        assert status["deviceId"] == "test-device"

    def test_cruise_movement_towards_target(self, cruise_service):
        """Test that cruise moves towards target."""
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.01,  # ~1km north
            target_lon=121.5,
            speed_kmh=36.0  # 10 m/s
        )

        # Let the background thread run for a short time
        time.sleep(0.5)

        status = cruise_service.get_cruise_status("test-device")
        # Should have moved north (latitude increased)
        assert status["location"]["latitude"] > 25.0

        # Clean up
        cruise_service.stop_cruise("test-device")

    def test_cruise_arrival(self, cruise_service):
        """Test cruise arrival at close target."""
        # Use a target about 10 meters north (just above threshold)
        # At 36 km/h = 10 m/s, should arrive in ~1 second
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0,
            start_lon=121.5,
            target_lat=25.0001,  # ~11 meters north
            target_lon=121.5,
            speed_kmh=36.0  # 10 m/s
        )

        # Wait for arrival (should take ~1-2 seconds)
        time.sleep(2.5)

        # Should have arrived and session removed
        status = cruise_service.get_cruise_status("test-device")
        assert status["state"] == "idle"

        # Check that arrival event was emitted
        calls = cruise_service._emit_event.call_args_list
        arrival_events = [c for c in calls if c[0][0].get("event") == "cruiseArrived"]
        assert len(arrival_events) > 0

    def test_stop_all(self, cruise_service):
        """Test stopping all cruise sessions."""
        # Start multiple cruises
        cruise_service.start_cruise(
            device_id="device-1",
            start_lat=25.0, start_lon=121.5,
            target_lat=25.1, target_lon=121.5,
            speed_kmh=10.0
        )
        cruise_service.start_cruise(
            device_id="device-2",
            start_lat=26.0, start_lon=121.5,
            target_lat=26.1, target_lon=121.5,
            speed_kmh=10.0
        )

        # Stop all
        cruise_service.stop_all()

        # Both should be idle
        assert cruise_service.get_cruise_status("device-1")["state"] == "idle"
        assert cruise_service.get_cruise_status("device-2")["state"] == "idle"

    def test_event_emission(self, cruise_service):
        """Test that events are emitted correctly."""
        cruise_service.start_cruise(
            device_id="test-device",
            start_lat=25.0, start_lon=121.5,
            target_lat=25.1, target_lon=121.5,
            speed_kmh=10.0
        )

        # Check cruiseStarted event
        calls = cruise_service._emit_event.call_args_list
        started_events = [c for c in calls if c[0][0].get("event") == "cruiseStarted"]
        assert len(started_events) == 1

        # Wait for update events from the background thread
        time.sleep(0.5)

        calls = cruise_service._emit_event.call_args_list
        update_events = [c for c in calls if c[0][0].get("event") == "cruiseUpdate"]
        assert len(update_events) > 0

        # Stop and check stopped event
        cruise_service.stop_cruise("test-device")

        calls = cruise_service._emit_event.call_args_list
        stopped_events = [c for c in calls if c[0][0].get("event") == "cruiseStopped"]
        assert len(stopped_events) == 1
