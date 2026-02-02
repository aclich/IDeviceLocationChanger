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
         patch("main.TunnelManager") as MockTunnelManager:

        server = LocationSimulatorServer()

        # Setup mock instances
        server.devices = MockDeviceManager.return_value
        server.location = MockLocationService.return_value
        server.tunnel = MockTunnelManager.return_value

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
        server.devices.list_devices = AsyncMock(side_effect=Exception("Test error"))
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
        server.devices.list_devices = AsyncMock(return_value=[mock_device])

        request = {"id": "1", "method": "listDevices", "params": {}}
        response = await server.handle_request(request)

        assert "result" in response
        assert "devices" in response["result"]
        assert len(response["result"]["devices"]) == 1
        assert response["result"]["devices"][0]["id"] == "sim-123"

    async def test_list_devices_empty(self, server):
        server.devices.list_devices = AsyncMock(return_value=[])

        request = {"id": "1", "method": "listDevices", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["devices"] == []


class TestSelectDevice:
    """Tests for selectDevice RPC method."""

    async def test_select_device_success(self, server):
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server.devices.get_device = MagicMock(return_value=mock_device)

        request = {"id": "1", "method": "selectDevice", "params": {"deviceId": "device-123"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        assert response["result"]["device"]["id"] == "device-123"
        assert server._selected_device == mock_device

    async def test_select_device_missing_id(self, server):
        request = {"id": "1", "method": "selectDevice", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "deviceId required" in response["result"]["error"]

    async def test_select_device_not_found(self, server):
        server.devices.get_device = MagicMock(return_value=None)

        request = {"id": "1", "method": "selectDevice", "params": {"deviceId": "nonexistent"}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "not found" in response["result"]["error"]


class TestSetLocation:
    """Tests for setLocation RPC method."""

    async def test_set_location_success(self, server):
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server._selected_device = mock_device
        server.devices.get_device = MagicMock(return_value=mock_device)
        server.location.set_location = AsyncMock(return_value={"success": True})

        request = {
            "id": "1",
            "method": "setLocation",
            "params": {"latitude": 25.033, "longitude": 121.565}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.location.set_location.assert_called_once_with(mock_device, 25.033, 121.565)

    async def test_set_location_no_device_selected(self, server):
        server._selected_device = None

        request = {
            "id": "1",
            "method": "setLocation",
            "params": {"latitude": 25.033, "longitude": 121.565}
        }
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "No device selected" in response["result"]["error"]

    async def test_set_location_missing_coordinates(self, server):
        server._selected_device = MagicMock()

        request = {"id": "1", "method": "setLocation", "params": {"latitude": 25.033}}
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
        server._selected_device = mock_device
        server.devices.get_device = MagicMock(return_value=mock_device)
        server.location.clear_location = AsyncMock(return_value={"success": True})

        request = {"id": "1", "method": "clearLocation", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        server.location.clear_location.assert_called_once_with(mock_device)

    async def test_clear_location_no_device_selected(self, server):
        server._selected_device = None

        request = {"id": "1", "method": "clearLocation", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "No device selected" in response["result"]["error"]


class TestTunnelOperations:
    """Tests for tunnel-related RPC methods."""

    async def test_start_tunnel_success(self, server):
        server.tunnel.start_tunnel = AsyncMock(return_value={
            "success": True,
            "address": "127.0.0.1",
            "port": 12345,
            "udid": "device-123",
        })
        server.devices.update_tunnel = MagicMock(return_value=True)

        # Set up selected device
        mock_device = Device(
            id="device-123",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        server._selected_device = mock_device

        request = {"id": "1", "method": "startTunnel", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True
        assert response["result"]["address"] == "127.0.0.1"
        server.devices.update_tunnel.assert_called_once()

    async def test_start_tunnel_failure(self, server):
        server.tunnel.start_tunnel = AsyncMock(return_value={
            "success": False,
            "error": "No device connected",
        })

        request = {"id": "1", "method": "startTunnel", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is False
        assert "No device connected" in response["result"]["error"]

    async def test_stop_tunnel(self, server):
        server.tunnel.stop_tunnel = AsyncMock(return_value={"success": True})

        request = {"id": "1", "method": "stopTunnel", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["success"] is True

    async def test_get_tunnel_status(self, server):
        server.tunnel.get_status = MagicMock(return_value={
            "running": True,
            "address": "127.0.0.1",
            "port": 12345,
        })

        request = {"id": "1", "method": "getTunnelStatus", "params": {}}
        response = await server.handle_request(request)

        assert response["result"]["running"] is True
        assert response["result"]["address"] == "127.0.0.1"
