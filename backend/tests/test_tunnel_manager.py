"""Tests for TunnelManager service."""

import pytest
from unittest.mock import MagicMock, patch

from models import RSDTunnel, TunnelState, TunnelStatus
from services.tunnel_manager import TunnelManager


class TestTunnelManagerInit:
    """Tests for TunnelManager initialization."""

    def test_init_creates_empty_status_dict(self):
        manager = TunnelManager()
        assert manager._last_status == {}

    def test_init_has_no_last_error(self):
        manager = TunnelManager()
        assert manager._last_error is None


class TestTunnelManagerGetTunnel:
    """Tests for get_tunnel method."""

    def test_get_tunnel_queries_tunneld_fresh(self):
        """get_tunnel should always query tunneld fresh, no caching."""
        manager = TunnelManager()
        mock_tunnel = RSDTunnel(address="fd10::1", port=62050, udid="test-udid")

        with patch.object(manager, '_query_tunneld_http', return_value=mock_tunnel) as mock_query:
            result = manager.get_tunnel("test-udid")

            mock_query.assert_called_once_with("test-udid")
            assert result is not None
            assert result.address == "fd10::1"
            assert result.port == 62050

    def test_get_tunnel_returns_none_when_no_tunnel(self):
        """get_tunnel returns None when tunneld has no tunnel for device."""
        manager = TunnelManager()

        with patch.object(manager, '_query_tunneld_http', return_value=None):
            result = manager.get_tunnel("unknown-device")

            assert result is None

    def test_get_tunnel_updates_status_on_success(self):
        """get_tunnel updates last status when tunnel found."""
        manager = TunnelManager()
        mock_tunnel = RSDTunnel(address="fd10::1", port=62050, udid="test-udid")

        with patch.object(manager, '_query_tunneld_http', return_value=mock_tunnel):
            manager.get_tunnel("test-udid")

            assert "test-udid" in manager._last_status
            assert manager._last_status["test-udid"].status == TunnelStatus.CONNECTED

    def test_get_tunnel_returns_none_for_empty_udid(self):
        """get_tunnel returns None when called without UDID."""
        manager = TunnelManager()

        result = manager.get_tunnel("")
        assert result is None

        result = manager.get_tunnel(None)
        assert result is None


class TestTunnelManagerGetStatus:
    """Tests for get_status method."""

    def test_get_status_with_no_tunnels(self):
        manager = TunnelManager()
        status = manager.get_status()

        assert status["running"] is False
        assert status["address"] is None
        assert status["port"] is None
        assert status["udid"] is None
        assert status["status"] == "no_tunnel"

    def test_get_status_for_specific_device_not_found(self):
        manager = TunnelManager()
        status = manager.get_status(udid="unknown-device")

        assert status["udid"] == "unknown-device"
        assert status["status"] == "no_tunnel"

    def test_get_status_for_connected_device(self):
        manager = TunnelManager()
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        state = TunnelState(
            udid="test-udid",
            status=TunnelStatus.CONNECTED,
            tunnel_info=tunnel,
        )
        manager._last_status["test-udid"] = state

        status = manager.get_status(udid="test-udid")

        assert status["status"] == "connected"
        assert status["tunnelInfo"]["address"] == "192.168.1.1"

    def test_get_status_legacy_format_with_connected_tunnel(self):
        """Legacy format returns first connected tunnel when no UDID specified."""
        manager = TunnelManager()
        tunnel = RSDTunnel(address="10.0.0.1", port=9999, udid="device-1")
        state = TunnelState(
            udid="device-1",
            status=TunnelStatus.CONNECTED,
            tunnel_info=tunnel,
        )
        manager._last_status["device-1"] = state

        status = manager.get_status()

        assert status["running"] is True
        assert status["address"] == "10.0.0.1"
        assert status["port"] == 9999


class TestTunnelManagerInvalidate:
    """Tests for invalidate method."""

    def test_invalidate_existing_tunnel(self):
        manager = TunnelManager()
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        state = TunnelState(
            udid="test-udid",
            status=TunnelStatus.CONNECTED,
            tunnel_info=tunnel,
        )
        manager._last_status["test-udid"] = state

        manager.invalidate("test-udid")

        assert manager._last_status["test-udid"].status == TunnelStatus.DISCONNECTED
        assert "failed" in manager._last_status["test-udid"].error.lower()

    def test_invalidate_nonexistent_tunnel_no_error(self):
        manager = TunnelManager()
        # Should not raise
        manager.invalidate("unknown-device")


class TestTunnelManagerQueryTunneldHttp:
    """Tests for _query_tunneld_http method."""

    @patch('urllib.request.urlopen')
    def test_returns_tunnel_when_found(self, mock_urlopen):
        manager = TunnelManager()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"test-udid": [{"tunnel-address": "fd10::1", "tunnel-port": 62050}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = manager._query_tunneld_http("test-udid")

        assert result is not None
        assert result.address == "fd10::1"
        assert result.port == 62050
        assert result.udid == "test-udid"

    @patch('urllib.request.urlopen')
    def test_returns_none_when_device_not_found(self, mock_urlopen):
        manager = TunnelManager()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"other-device": [{"tunnel-address": "fd10::1", "tunnel-port": 62050}]}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = manager._query_tunneld_http("test-udid")

        assert result is None

    @patch('urllib.request.urlopen')
    def test_returns_none_when_tunneld_not_available(self, mock_urlopen):
        manager = TunnelManager()
        mock_urlopen.side_effect = Exception("Connection refused")

        result = manager._query_tunneld_http("test-udid")

        assert result is None

    @patch('urllib.request.urlopen')
    def test_handles_empty_response(self, mock_urlopen):
        manager = TunnelManager()
        mock_response = MagicMock()
        mock_response.read.return_value = b'{}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = manager._query_tunneld_http("test-udid")

        assert result is None


class TestTunnelManagerExtractTunnelInfo:
    """Tests for _extract_tunnel_info method."""

    def test_extracts_from_list_format(self):
        manager = TunnelManager()
        device_info = [{"tunnel-address": "fd10::1", "tunnel-port": 62050}]

        result = manager._extract_tunnel_info(device_info, "test-udid")

        assert result is not None
        assert result.address == "fd10::1"
        assert result.port == 62050

    def test_extracts_from_dict_format(self):
        manager = TunnelManager()
        device_info = {"address": "192.168.1.1", "port": 8080}

        result = manager._extract_tunnel_info(device_info, "test-udid")

        assert result is not None
        assert result.address == "192.168.1.1"
        assert result.port == 8080

    def test_handles_alternative_key_names(self):
        manager = TunnelManager()
        device_info = {"tunnel_address": "10.0.0.1", "tunnel_port": 9999}

        result = manager._extract_tunnel_info(device_info, "test-udid")

        assert result is not None
        assert result.address == "10.0.0.1"
        assert result.port == 9999

    def test_returns_none_for_empty_list(self):
        manager = TunnelManager()
        device_info = []

        result = manager._extract_tunnel_info(device_info, "test-udid")

        assert result is None

    def test_returns_none_for_missing_address(self):
        manager = TunnelManager()
        device_info = {"port": 8080}

        result = manager._extract_tunnel_info(device_info, "test-udid")

        assert result is None


class TestTunnelManagerIsTunneldRunning:
    """Tests for _is_tunneld_running method."""

    @patch('urllib.request.urlopen')
    def test_returns_true_when_tunneld_responds(self, mock_urlopen):
        manager = TunnelManager()
        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = manager._is_tunneld_running()

        assert result is True

    @patch('urllib.request.urlopen')
    def test_returns_false_when_tunneld_not_running(self, mock_urlopen):
        manager = TunnelManager()
        mock_urlopen.side_effect = Exception("Connection refused")

        result = manager._is_tunneld_running()

        assert result is False


class TestTunnelManagerPerDeviceIsolation:
    """Tests to ensure per-device state isolation."""

    def test_different_devices_have_independent_state(self):
        manager = TunnelManager()

        # Update status for two devices
        manager._update_status(
            "device-1",
            TunnelStatus.CONNECTED,
            RSDTunnel(address="10.0.0.1", port=1111, udid="device-1")
        )
        manager._update_status(
            "device-2",
            TunnelStatus.DISCONNECTED,
            None,
            "Test error"
        )

        # Verify isolation
        assert manager._last_status["device-1"].status == TunnelStatus.CONNECTED
        assert manager._last_status["device-2"].status == TunnelStatus.DISCONNECTED
        assert manager._last_status["device-1"].tunnel_info is not None
        assert manager._last_status["device-2"].tunnel_info is None

    def test_invalidate_one_device_does_not_affect_others(self):
        manager = TunnelManager()

        manager._update_status("device-1", TunnelStatus.CONNECTED, None)
        manager._update_status("device-2", TunnelStatus.CONNECTED, None)

        manager.invalidate("device-1")

        assert manager._last_status["device-1"].status == TunnelStatus.DISCONNECTED
        assert manager._last_status["device-2"].status == TunnelStatus.CONNECTED
