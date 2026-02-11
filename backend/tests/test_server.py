"""Tests for LocationSimulatorServer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from main import LocationSimulatorServer
from models import Device, DeviceType, DeviceState, RSDTunnel


@pytest.fixture
def server():
    """Create a server instance with mocked services."""
    with patch("main.DeviceManager") as MockDeviceManager, \
         patch("main.LocationService") as MockLocationService, \
         patch("main.TunnelManager") as MockTunnelManager, \
         patch("main.FavoritesService") as MockFavoritesService, \
         patch("main.CruiseService") as MockCruiseService, \
         patch("main.LastLocationService") as MockLastLocationService, \
         patch("main.PortForwardService") as MockPortForwardService, \
         patch("main.BrouterService") as MockBrouterService, \
         patch("main.RouteService") as MockRouteService:

        server = LocationSimulatorServer()

        # Setup mock instances
        server.devices = MockDeviceManager.return_value
        server.location = MockLocationService.return_value
        server.tunnel = MockTunnelManager.return_value
        server.favorites = MockFavoritesService.return_value
        server.cruise = MockCruiseService.return_value
        server.last_locations = MockLastLocationService.return_value
        server.port_forward = MockPortForwardService.return_value
        server.brouter = MockBrouterService.return_value
        server.route = MockRouteService.return_value

        yield server


class TestHandleRequest:
    """Tests for JSON-RPC request handling."""

    async def test_unknown_method_returns_error(self, server):
        request = {"id": "1", "method": "unknownMethod", "params": {}}

        response = await server.handle_request(request)

        assert response["id"] == "1"
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "unknownMethod" in response["error"]["message"]

    async def test_method_exception_returns_error(self, server):
        server.devices.list_devices = MagicMock(side_effect=Exception("Test error"))
        request = {"id": "2", "method": "listDevices", "params": {}}

        response = await server.handle_request(request)

        assert response["id"] == "2"
        assert "error" in response
        assert response["error"]["code"] == -1
        assert "Test error" in response["error"]["message"]


class TestListDevices:
    """Tests for listDevices RPC method."""

    async def test_list_devices_success(self, server):
        mock_device = Device(
            id="sim-123",
            name="iPhone 15",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )
        server.devices.list_devices = MagicMock(return_value=[mock_device])

        request = {"id": "1", "method": "listDevices", "params": {}}
        response = await server.handle_request(request)

        assert "result" in response
        assert "devices" in response["result"]
        assert len(response["result"]["devices"]) == 1
        assert response["result"]["devices"][0]["id"] == "sim-123"

    async def test_list_devices_empty(self, server):
        server.devices.list_devices = MagicMock(return_value=[])

        request = {"id": "1", "method": "listDevices", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["devices"] == []


class TestSelectDeviceRemoved:
    """Tests that selectDevice RPC method has been removed."""

    async def test_select_device_method_not_found(self, server):
        request = {"id": "1", "method": "selectDevice", "params": {"deviceId": "device-123"}}
        response = await server.handle_request(request)

        assert "error" in response
        assert response["error"]["code"] == -32601


class TestGetDeviceState:
    """Tests for getDeviceState RPC method."""

    async def test_get_device_state_idle(self, server):
        """Idle device returns null for cruise/route, location from LastLocationService."""
        server.location._last_locations = {}
        server.last_locations.get = MagicMock(return_value={"lat": 25.033, "lon": 121.565})
        server.cruise.get_cruise_status = MagicMock(return_value={"state": "idle", "deviceId": "dev-1"})
        server.route.get_route = MagicMock(return_value=None)
        server.route.get_route_session = MagicMock(return_value=None)
        server.devices.get_device = MagicMock(return_value=None)
        server.location._refresh_tasks = {}

        request = {"id": "1", "method": "getDeviceState", "params": {"deviceId": "dev-1"}}
        response = await server.handle_request(request)

        result = response["result"]
        assert result["location"]["latitude"] == 25.033
        assert result["cruise"] is None
        assert result["route"] is None
        assert result["routeCruise"] is None
        assert result["isRefreshing"] is False

    async def test_get_device_state_with_cruise(self, server):
        """Device with active cruise returns cruise data."""
        cruise_data = {"state": "running", "deviceId": "dev-1", "speedKmh": 80}
        server.location._last_locations = {"dev-1": {"lat": 25.0, "lon": 121.0}}
        server.last_locations.get = MagicMock(return_value=None)
        server.cruise.get_cruise_status = MagicMock(return_value=cruise_data)
        server.route.get_route = MagicMock(return_value=None)
        server.route.get_route_session = MagicMock(return_value=None)
        server.devices.get_device = MagicMock(return_value=None)
        server.location._refresh_tasks = {"dev-1": {}}

        request = {"id": "1", "method": "getDeviceState", "params": {"deviceId": "dev-1"}}
        response = await server.handle_request(request)

        result = response["result"]
        assert result["cruise"]["state"] == "running"
        assert result["cruise"]["speedKmh"] == 80
        assert result["isRefreshing"] is True

    async def test_get_device_state_missing_device_id(self, server):
        request = {"id": "1", "method": "getDeviceState", "params": {}}
        response = await server.handle_request(request)

        assert "deviceId required" in response["result"]["error"]

    async def test_get_device_state_no_state(self, server):
        """Device with no state at all returns all nulls."""
        server.location._last_locations = {}
        server.last_locations.get = MagicMock(return_value=None)
        server.cruise.get_cruise_status = MagicMock(return_value={"state": "idle", "deviceId": "dev-1"})
        server.route.get_route = MagicMock(return_value=None)
        server.route.get_route_session = MagicMock(return_value=None)
        server.devices.get_device = MagicMock(return_value=None)
        server.location._refresh_tasks = {}

        request = {"id": "1", "method": "getDeviceState", "params": {"deviceId": "dev-1"}}
        response = await server.handle_request(request)

        result = response["result"]
        assert result["location"] is None
        assert result["cruise"] is None


class TestGetAllDeviceStates:
    """Tests for getAllDeviceStates RPC method."""

    async def test_empty_states(self, server):
        """No active devices returns empty dict."""
        server.cruise._sessions = {}
        server.cruise._sessions_lock = MagicMock()
        server.cruise._sessions_lock.__enter__ = MagicMock()
        server.cruise._sessions_lock.__exit__ = MagicMock(return_value=False)
        server.route._sessions = {}

        request = {"id": "1", "method": "getAllDeviceStates", "params": {}}
        response = await server.handle_request(request)

        assert response["result"] == {}

    async def test_with_active_sessions(self, server):
        """Active cruise and route sessions return badge data."""
        from unittest.mock import PropertyMock
        import threading

        # Mock cruise session
        cruise_session = MagicMock()
        cruise_session.state = MagicMock()
        cruise_session.state.value = "running"
        server.cruise._sessions = {"dev-a": cruise_session}
        server.cruise._sessions_lock = threading.Lock()

        # Mock route session
        route_session = MagicMock()
        route_session.state = MagicMock()
        route_session.state.value = "running"
        route_session.current_segment_index = 2
        route_session.route.segments = [1, 2, 3, 4, 5]  # 5 segments
        server.route._sessions = {"dev-b": route_session}

        request = {"id": "1", "method": "getAllDeviceStates", "params": {}}
        response = await server.handle_request(request)

        result = response["result"]
        assert result["dev-a"]["cruising"] is True
        assert result["dev-b"]["routeCruising"] is True
        assert result["dev-b"]["routeProgress"] == "2/5"


class TestSetLocation:
    """Tests for setLocation RPC method."""

    async def test_set_location_success(self, server):
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server.devices.get_device = MagicMock(return_value=mock_device)
        server.location.set_location = MagicMock(return_value={"success": True})
        server.last_locations.update = MagicMock()

        request = {
            "id": "1",
            "method": "setLocation",
            "params": {"deviceId": "device-123", "latitude": 25.033, "longitude": 121.565}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.location.set_location.assert_called_once_with(
            mock_device, 25.033, 121.565,
        )

    async def test_set_location_no_device_id(self, server):
        request = {
            "id": "1",
            "method": "setLocation",
            "params": {"latitude": 25.033, "longitude": 121.565}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "deviceId required" in response["result"]["error"]

    async def test_set_location_missing_coordinates(self, server):
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server.devices.get_device = MagicMock(return_value=mock_device)

        request = {"id": "1", "method": "setLocation", "params": {"deviceId": "device-123", "latitude": 25.033}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "latitude and longitude required" in response["result"]["error"]


class TestClearLocation:
    """Tests for clearLocation RPC method."""

    async def test_clear_location_success(self, server):
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server.devices.get_device = MagicMock(return_value=mock_device)
        server.location.clear_location = MagicMock(return_value={"success": True})

        request = {"id": "1", "method": "clearLocation", "params": {"deviceId": "device-123"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.location.clear_location.assert_called_once_with(mock_device)

    async def test_clear_location_no_device_id(self, server):
        request = {"id": "1", "method": "clearLocation", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "deviceId required" in response["result"]["error"]


class TestTunnelOperations:
    """Tests for tunnel-related RPC methods."""

    async def test_retry_tunneld(self, server):
        """retryTunneld calls ensure_tunneld and returns state."""
        server.tunnel.ensure_tunneld = MagicMock(return_value="ready")

        request = {"id": "1", "method": "retryTunneld", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        assert response["result"]["state"] == "ready"
        server.tunnel.ensure_tunneld.assert_called_once()

    async def test_retry_tunneld_failure(self, server):
        """retryTunneld returns failure when tunneld can't start."""
        server.tunnel.ensure_tunneld = MagicMock(return_value="error")

        request = {"id": "1", "method": "retryTunneld", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert response["result"]["state"] == "error"

    async def test_old_tunnel_methods_removed(self, server):
        """startTunnel, stopTunnel, getTunnelStatus, selectDevice are no longer available."""
        for method in ["startTunnel", "stopTunnel", "getTunnelStatus", "selectDevice"]:
            request = {"id": "1", "method": method, "params": {}}
            response = await server.handle_request(request)
            assert "error" in response
            assert response["error"]["code"] == -32601

    async def test_disconnect_device(self, server):
        """disconnectDevice clears active tasks for the device."""
        server.cruise.stop_cruise = MagicMock(return_value={"success": True})
        server.route.stop_route_cruise = MagicMock(return_value={"success": True})
        server.location.close_connection = MagicMock()

        request = {"id": "1", "method": "disconnectDevice", "params": {"deviceId": "device-123"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.cruise.stop_cruise.assert_called_once_with("device-123")
        server.route.stop_route_cruise.assert_called_once_with("device-123")
        server.location.close_connection.assert_called_once_with("device-123")


class TestFavoritesOperations:
    """Tests for favorites-related RPC methods."""

    async def test_get_favorites(self, server):
        mock_favorite = MagicMock()
        mock_favorite.to_dict.return_value = {
            "latitude": 25.033,
            "longitude": 121.565,
            "name": "Taipei 101",
        }
        server.favorites.get_all = MagicMock(return_value=[mock_favorite])

        request = {"id": "1", "method": "getFavorites", "params": {}}
        response = await server.handle_request(request)

        assert "favorites" in response["result"]
        assert len(response["result"]["favorites"]) == 1
        assert response["result"]["favorites"][0]["name"] == "Taipei 101"

    async def test_get_favorites_empty(self, server):
        server.favorites.get_all = MagicMock(return_value=[])

        request = {"id": "1", "method": "getFavorites", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["favorites"] == []

    async def test_add_favorite_success(self, server):
        server.favorites.add = MagicMock(return_value={
            "success": True,
            "favorite": {"latitude": 25.033, "longitude": 121.565, "name": "Taipei"},
        })

        request = {
            "id": "1",
            "method": "addFavorite",
            "params": {"latitude": 25.033, "longitude": 121.565, "name": "Taipei"}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.favorites.add.assert_called_once_with(25.033, 121.565, "Taipei")

    async def test_add_favorite_missing_coords(self, server):
        request = {"id": "1", "method": "addFavorite", "params": {"name": "Test"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "latitude" in response["result"]["error"]

    async def test_update_favorite_success(self, server):
        server.favorites.update = MagicMock(return_value={
            "success": True,
            "favorite": {"latitude": 25.033, "longitude": 121.565, "name": "New Name"},
        })

        request = {
            "id": "1",
            "method": "updateFavorite",
            "params": {"index": 0, "name": "New Name"}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.favorites.update.assert_called_once_with(0, "New Name")

    async def test_update_favorite_missing_index(self, server):
        request = {"id": "1", "method": "updateFavorite", "params": {"name": "Test"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "index" in response["result"]["error"]

    async def test_update_favorite_missing_name(self, server):
        request = {"id": "1", "method": "updateFavorite", "params": {"index": 0}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "name" in response["result"]["error"]

    async def test_delete_favorite_success(self, server):
        server.favorites.delete = MagicMock(return_value={"success": True})

        request = {"id": "1", "method": "deleteFavorite", "params": {"index": 0}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.favorites.delete.assert_called_once_with(0)

    async def test_delete_favorite_missing_index(self, server):
        request = {"id": "1", "method": "deleteFavorite", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "index" in response["result"]["error"]

    async def test_import_favorites_success(self, server):
        server.favorites.import_from_file = MagicMock(return_value={
            "success": True,
            "imported": 5,
        })

        request = {
            "id": "1",
            "method": "importFavorites",
            "params": {"filePath": "/path/to/file.txt"}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        assert response["result"]["imported"] == 5

    async def test_import_favorites_missing_path(self, server):
        request = {"id": "1", "method": "importFavorites", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "filePath" in response["result"]["error"]
