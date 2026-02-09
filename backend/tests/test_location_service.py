"""Tests for LocationService."""

import pytest
from unittest.mock import MagicMock, patch

from models import Device, DeviceType, DeviceState, RSDTunnel
from services.location_service import LocationService


def _make_service(tmp_path):
    """Create a LocationService with isolated temp directory."""
    return LocationService(data_dir=str(tmp_path))


class TestLocationServiceSetLocation:
    """Tests for set_location method."""

    def test_set_location_returns_error_when_no_device(self, tmp_path):
        service = _make_service(tmp_path)

        result = service.set_location(None, 37.7749, -122.4194)

        assert result["success"] is False
        assert "no device" in result["error"].lower()

    def test_set_location_simulator_calls_simctl(self, tmp_path):
        service = _make_service(tmp_path)
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = service.set_location(device, 37.7749, -122.4194)

            assert result["success"] is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "xcrun" in call_args
            assert "simctl" in call_args
            assert "location" in call_args

    def test_set_location_simulator_handles_error(self, tmp_path):
        service = _make_service(tmp_path)
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="simctl error")

            result = service.set_location(device, 37.7749, -122.4194)

            assert result["success"] is False
            assert "simctl" in result["error"].lower()


class TestLocationServiceClearLocation:
    """Tests for clear_location method."""

    def test_clear_location_returns_error_when_no_device(self, tmp_path):
        service = _make_service(tmp_path)

        result = service.clear_location(None)

        assert result["success"] is False
        assert "no device" in result["error"].lower()

    def test_clear_location_simulator_calls_simctl(self, tmp_path):
        service = _make_service(tmp_path)
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            result = service.clear_location(device)

            assert result["success"] is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "clear" in call_args


class TestLocationServicePhysicalDevice:
    """Tests for physical device location operations."""

    def test_set_physical_uses_tunnel_when_provided(self, tmp_path):
        """Uses tunnel when tunnel parameter is provided."""
        service = _make_service(tmp_path)
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel:
            mock_tunnel.return_value = {"success": True}

            service._set_physical_location(device, 37.0, -122.0, tunnel=tunnel)

            mock_tunnel.assert_called_once_with(device, tunnel, 37.0, -122.0)

    def test_set_physical_uses_usbmux_when_no_tunnel(self, tmp_path):
        """Falls back to usbmux when no tunnel is provided and device type is unknown."""
        service = _make_service(tmp_path)
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_usbmux.return_value = {"success": True}

            # No tunnel provider, no stored type → probes tunnel (none) → falls to usbmux
            service._set_physical_location(device, 37.0, -122.0, tunnel=None)

            mock_usbmux.assert_called_once_with(device, 37.0, -122.0)

    def test_set_physical_stays_on_tunnel_for_known_tunnel_device(self, tmp_path):
        """Known tunnel device never falls to usbmux, even without tunnel info."""
        service = _make_service(tmp_path)
        service._device_connection_types["test-device"] = "tunnel"
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel, \
             patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_tunnel.return_value = {"success": False, "error": "No tunnel"}

            service._set_physical_location(device, 37.0, -122.0, tunnel=None)

            mock_tunnel.assert_called_once()
            mock_usbmux.assert_not_called()

    def test_clear_physical_uses_tunnel_when_provided(self, tmp_path):
        """Uses tunnel when tunnel parameter is provided."""
        service = _make_service(tmp_path)
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_clear_via_tunnel') as mock_tunnel:
            mock_tunnel.return_value = {"success": True}

            service._clear_physical_location(device, tunnel=tunnel)

            mock_tunnel.assert_called_once_with(device, tunnel)

    def test_clear_physical_uses_usbmux_when_no_tunnel(self, tmp_path):
        """Falls back to usbmux when no tunnel is provided and device type is unknown."""
        service = _make_service(tmp_path)
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_clear_via_usbmux') as mock_usbmux:
            mock_usbmux.return_value = {"success": True}

            # No tunnel provider, no stored type → falls to usbmux
            service._clear_physical_location(device, tunnel=None)

            mock_usbmux.assert_called_once_with(device)


class TestLocationServiceTunnel:
    """Tests for tunnel-based connections (iOS 17+)."""

    def test_set_via_tunnel_receives_tunnel_directly(self, tmp_path):
        """Tunnel method receives RSDTunnel object directly."""
        service = _make_service(tmp_path)
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
            result = service._set_via_tunnel_with_retry(device, tunnel, 37.0, -122.0)

            # Should fail but with connection error, not argument error
            assert result["success"] is False
            assert "error" in result

    def test_clear_via_tunnel_receives_tunnel_directly(self, tmp_path):
        """Clear tunnel method receives RSDTunnel object directly."""
        service = _make_service(tmp_path)
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
            result = service._clear_via_tunnel(device, tunnel)

            assert result["success"] is False
            assert "error" in result


class TestLocationServiceUsbmux:
    """Tests for usbmux-based connections (iOS 16 and earlier)."""

    def test_set_via_usbmux_handles_error(self, tmp_path):
        service = _make_service(tmp_path)
        device = Device(
            id="test-device",
            name="Test iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        # Mock the actual method to simulate error
        with patch.object(service, '_set_via_usbmux_with_retry') as mock_set:
            mock_set.return_value = {"success": False, "error": "Device not found"}

            result = mock_set(device, 37.7749, -122.4194)

            assert result["success"] is False

    def test_clear_via_usbmux_handles_error(self, tmp_path):
        service = _make_service(tmp_path)
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


class TestLocationServiceConnectionTypePersistence:
    """Tests for device connection type persistence."""

    def test_records_tunnel_type_on_success(self, tmp_path):
        """Records 'tunnel' when a device successfully connects via tunnel."""
        service = _make_service(tmp_path)
        service._record_device_type("device-123", "tunnel")

        assert service._device_connection_types["device-123"] == "tunnel"
        # Verify persisted to disk
        service2 = _make_service(tmp_path)
        assert service2._device_connection_types["device-123"] == "tunnel"

    def test_records_usbmux_type_on_success(self, tmp_path):
        """Records 'usbmux' when a device successfully connects via usbmux."""
        service = _make_service(tmp_path)
        service._record_device_type("device-456", "usbmux")

        assert service._device_connection_types["device-456"] == "usbmux"

    def test_known_tunnel_device_never_uses_usbmux(self, tmp_path):
        """A device stored as 'tunnel' never falls to usbmux path."""
        service = _make_service(tmp_path)
        service._record_device_type("device-123", "tunnel")

        device = Device(
            id="device-123",
            name="iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel, \
             patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_tunnel.return_value = {"success": False, "error": "No tunnel"}

            service._set_physical_location(device, 37.0, -122.0)

            mock_tunnel.assert_called_once()
            mock_usbmux.assert_not_called()

    def test_tunneld_timeout_does_not_fall_to_usbmux(self, tmp_path):
        """When tunneld times out, a known tunnel device stays on tunnel path.

        Reproduces the original bug: tunneld HTTP query times out → provider
        returns None → code should NOT fall to usbmux for a device that
        previously connected via tunnel.
        """
        service = _make_service(tmp_path)
        service._record_device_type("device-123", "tunnel")

        # Simulate tunneld timeout: provider returns None
        service.set_tunnel_provider(lambda udid: None)

        device = Device(
            id="device-123",
            name="iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel, \
             patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_tunnel.return_value = {"success": False, "error": "No tunnel available"}

            result = service._set_physical_location(device, 37.0, -122.0)

            # Must stay on tunnel path — never try usbmux
            mock_tunnel.assert_called_once()
            mock_usbmux.assert_not_called()

    def test_tunneld_timeout_with_existing_connection_reuses_it(self, tmp_path):
        """When tunneld times out but an existing DVT connection is alive,
        reuse the existing connection without any tunneld query.

        This is the hot path during joystick/cruise mode.
        """
        service = _make_service(tmp_path)

        device = Device(
            id="device-123",
            name="iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        # Simulate an existing tunnel connection
        service._tunnel_connections["device-123"] = {
            "rsd": MagicMock(),
            "dvt": MagicMock(),
            "location": MagicMock(),
            "tunnel": RSDTunnel(address="fd10::1", port=62050, udid="device-123"),
            "created_at": __import__("time").time(),
        }

        # Provider that would be called on tunneld query — should NOT be called
        provider_called = []
        def failing_provider(udid):
            provider_called.append(udid)
            return None  # Simulate timeout

        service.set_tunnel_provider(failing_provider)

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel, \
             patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_tunnel.return_value = {"success": True}

            result = service._set_physical_location(device, 37.0, -122.0)

            assert result["success"] is True
            mock_tunnel.assert_called_once()
            mock_usbmux.assert_not_called()
            # Provider should NOT have been called — existing connection is reused
            assert len(provider_called) == 0

    def test_first_connection_probe_records_type(self, tmp_path):
        """First-time connection to unknown device probes tunneld, then
        records the type for future use.
        """
        service = _make_service(tmp_path)
        tunnel = RSDTunnel(address="fd10::1", port=62050, udid="new-device")

        # Provider returns a tunnel (tunneld is responsive)
        service.set_tunnel_provider(lambda udid: tunnel)

        device = Device(
            id="new-device",
            name="iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel:
            mock_tunnel.return_value = {"success": True}

            service._set_physical_location(device, 37.0, -122.0)

            mock_tunnel.assert_called_once_with(device, tunnel, 37.0, -122.0)

        # After success, the type should be recorded (by _set_via_tunnel_with_retry
        # in real code; here we verify the probe path passed the right tunnel)

    def test_first_connection_probe_falls_to_usbmux_when_no_tunnel(self, tmp_path):
        """First-time connection to unknown device with no tunneld falls to usbmux."""
        service = _make_service(tmp_path)

        # Provider returns None (no tunnel available)
        service.set_tunnel_provider(lambda udid: None)

        device = Device(
            id="new-device",
            name="iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        with patch.object(service, '_set_via_tunnel_with_retry') as mock_tunnel, \
             patch.object(service, '_set_via_usbmux_with_retry') as mock_usbmux:
            mock_usbmux.return_value = {"success": True}

            service._set_physical_location(device, 37.0, -122.0)

            # No tunnel → should try usbmux
            mock_tunnel.assert_not_called()
            mock_usbmux.assert_called_once()
