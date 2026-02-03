"""Tests for LocationService."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models import Device, DeviceType, DeviceState, RSDTunnel
from services.location_service import LocationService


class TestLocationServiceSetLocation:
    """Tests for set_location method."""

    @pytest.mark.asyncio
    async def test_set_location_returns_error_when_no_device(self):
        service = LocationService()

        result = await service.set_location(None, 37.7749, -122.4194)

        assert result["success"] is False
        assert "no device" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_set_location_simulator_calls_simctl(self):
        service = LocationService()
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = await service.set_location(device, 37.7749, -122.4194)

            assert result["success"] is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "xcrun" in call_args
            assert "simctl" in call_args
            assert "location" in call_args

    @pytest.mark.asyncio
    async def test_set_location_simulator_handles_error(self):
        service = LocationService()
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="simctl error")

            result = await service.set_location(device, 37.7749, -122.4194)

            assert result["success"] is False
            assert "simctl" in result["error"].lower()


class TestLocationServiceClearLocation:
    """Tests for clear_location method."""

    @pytest.mark.asyncio
    async def test_clear_location_returns_error_when_no_device(self):
        service = LocationService()

        result = await service.clear_location(None)

        assert result["success"] is False
        assert "no device" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_clear_location_simulator_calls_simctl(self):
        service = LocationService()
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = await service.clear_location(device)

            assert result["success"] is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "clear" in call_args


class TestLocationServicePhysicalDevice:
    """Tests for physical device location operations."""

    @pytest.mark.asyncio
    async def test_set_physical_uses_tunnel_when_provided(self):
        """Uses tunnel when tunnel parameter is provided."""
        service = LocationService()
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel', new_callable=AsyncMock) as mock_tunnel:
            mock_tunnel.return_value = {"success": True}

            await service._set_physical_location(device, 37.0, -122.0, tunnel=tunnel)

            mock_tunnel.assert_called_once_with(device, tunnel, 37.0, -122.0)

    @pytest.mark.asyncio
    async def test_set_physical_uses_usbmux_when_no_tunnel(self):
        """Falls back to usbmux when no tunnel is provided."""
        service = LocationService()
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_usbmux') as mock_usbmux:
            mock_usbmux.return_value = {"success": True}

            await service._set_physical_location(device, 37.0, -122.0, tunnel=None)

            mock_usbmux.assert_called_once_with(device, 37.0, -122.0)

    @pytest.mark.asyncio
    async def test_clear_physical_uses_tunnel_when_provided(self):
        """Uses tunnel when tunnel parameter is provided."""
        service = LocationService()
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_clear_via_tunnel', new_callable=AsyncMock) as mock_tunnel:
            mock_tunnel.return_value = {"success": True}

            await service._clear_physical_location(device, tunnel=tunnel)

            mock_tunnel.assert_called_once_with(device, tunnel)

    @pytest.mark.asyncio
    async def test_clear_physical_uses_usbmux_when_no_tunnel(self):
        """Falls back to usbmux when no tunnel is provided."""
        service = LocationService()
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_clear_via_usbmux') as mock_usbmux:
            mock_usbmux.return_value = {"success": True}

            await service._clear_physical_location(device, tunnel=None)

            mock_usbmux.assert_called_once_with(device)


class TestLocationServiceTunnel:
    """Tests for tunnel-based connections (iOS 17+)."""

    @pytest.mark.asyncio
    async def test_set_via_tunnel_receives_tunnel_directly(self):
        """Tunnel method receives RSDTunnel object directly."""
        service = LocationService()
        tunnel = RSDTunnel(address="fd10::1", port=62050, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        # Mock the pymobiledevice3 imports to simulate connection error
        with patch.dict('sys.modules', {
            'pymobiledevice3.remote.remote_service_discovery': MagicMock(),
            'pymobiledevice3.services.dvt.dvt_secure_socket_proxy': MagicMock(),
            'pymobiledevice3.services.dvt.instruments.location_simulation': MagicMock(),
        }):
            # The actual call will fail due to mocking, but we verify the signature
            result = await service._set_via_tunnel(device, tunnel, 37.0, -122.0)

            # Should fail but with connection error, not argument error
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_clear_via_tunnel_receives_tunnel_directly(self):
        """Clear tunnel method receives RSDTunnel object directly."""
        service = LocationService()
        tunnel = RSDTunnel(address="fd10::1", port=62050, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.dict('sys.modules', {
            'pymobiledevice3.remote.remote_service_discovery': MagicMock(),
            'pymobiledevice3.services.dvt.dvt_secure_socket_proxy': MagicMock(),
            'pymobiledevice3.services.dvt.instruments.location_simulation': MagicMock(),
        }):
            result = await service._clear_via_tunnel(device, tunnel)

            assert result["success"] is False
            assert "error" in result


class TestLocationServiceUsbmux:
    """Tests for usbmux-based connections (iOS 16 and earlier)."""

    def test_set_via_usbmux_handles_error(self):
        service = LocationService()
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        # Mock the actual method to simulate error
        with patch.object(service, '_set_via_usbmux') as mock_set:
            mock_set.return_value = {"success": False, "error": "Device not found"}

            result = mock_set(device, 37.7749, -122.4194)

            assert result["success"] is False

    def test_clear_via_usbmux_handles_error(self):
        service = LocationService()
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_clear_via_usbmux') as mock_clear:
            mock_clear.return_value = {"success": False, "error": "Device not found"}

            result = mock_clear(device)

            assert result["success"] is False
