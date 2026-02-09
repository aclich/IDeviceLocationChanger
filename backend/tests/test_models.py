"""Tests for data models."""

import pytest
from models import (
    Device,
    DeviceType,
    DeviceState,
    ConnectionType,
    RSDTunnel,
    TunnelStatus,
    TunnelState,
    PRODUCT_NAME_MAP,
)


class TestRSDTunnel:
    """Tests for RSDTunnel dataclass."""

    def test_is_configured_with_valid_address_and_port(self):
        tunnel = RSDTunnel(address="127.0.0.1", port=12345)
        assert tunnel.is_configured is True

    def test_is_configured_with_empty_address(self):
        tunnel = RSDTunnel(address="", port=12345)
        assert tunnel.is_configured is False

    def test_is_configured_with_zero_port(self):
        tunnel = RSDTunnel(address="127.0.0.1", port=0)
        assert tunnel.is_configured is False

    def test_is_configured_with_negative_port(self):
        tunnel = RSDTunnel(address="127.0.0.1", port=-1)
        assert tunnel.is_configured is False

    def test_to_dict(self):
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="abc123")
        result = tunnel.to_dict()

        assert result == {
            "address": "192.168.1.1",
            "port": 8080,
            "udid": "abc123",
        }

    def test_to_dict_without_udid(self):
        tunnel = RSDTunnel(address="localhost", port=5000)
        result = tunnel.to_dict()

        assert result["udid"] is None


class TestDevice:
    """Tests for Device dataclass."""

    def test_create_simulator_device(self):
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        assert device.id == "sim-123"
        assert device.name == "iPhone 15 Pro"
        assert device.type == DeviceType.SIMULATOR
        assert device.state == DeviceState.CONNECTED
        assert device.rsd_tunnel is None

    def test_create_physical_device_with_tunnel(self):
        tunnel = RSDTunnel(address="10.0.0.1", port=9999, udid="device-udid")
        device = Device(
            id="phys-456",
            name="My iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
            rsd_tunnel=tunnel,
            product_type="iPhone17,1",
            connection_type=ConnectionType.USB,
        )

        assert device.rsd_tunnel is not None
        assert device.rsd_tunnel.address == "10.0.0.1"
        assert device.product_type == "iPhone17,1"
        assert device.connection_type == ConnectionType.USB

    def test_product_name_with_known_product_type(self):
        device = Device(
            id="test",
            name="Unknown",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
            product_type="iPhone17,1",
        )

        assert device.product_name == "iPhone 16 Pro"

    def test_product_name_with_unknown_product_type(self):
        device = Device(
            id="test",
            name="Unknown",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
            product_type="iPhone99,9",
        )

        # Falls back to product_type when not in map
        assert device.product_name == "iPhone99,9"

    def test_product_name_without_product_type(self):
        device = Device(
            id="test",
            name="My Device",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )

        # Falls back to name when no product_type
        assert device.product_name == "My Device"

    def test_to_dict_simulator(self):
        device = Device(
            id="sim-123",
            name="iPhone 15 Pro",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )

        result = device.to_dict()

        assert result == {
            "id": "sim-123",
            "name": "iPhone 15 Pro",
            "type": "simulator",
            "state": "connected",
            "productType": None,
            "productName": "iPhone 15 Pro",
            "connectionType": "Unknown",
            "rsdTunnel": None,
        }

    def test_to_dict_physical_with_tunnel(self):
        tunnel = RSDTunnel(address="10.0.0.1", port=9999, udid="device-udid")
        device = Device(
            id="phys-456",
            name="My iPhone",
            type=DeviceType.PHYSICAL,
            state=DeviceState.DISCONNECTED,
            rsd_tunnel=tunnel,
            product_type="iPhone16,1",
            connection_type=ConnectionType.WIFI,
        )

        result = device.to_dict()

        assert result["id"] == "phys-456"
        assert result["type"] == "physical"
        assert result["state"] == "disconnected"
        assert result["productType"] == "iPhone16,1"
        assert result["productName"] == "iPhone 15 Pro"
        assert result["connectionType"] == "WiFi"
        assert result["rsdTunnel"] == {
            "address": "10.0.0.1",
            "port": 9999,
            "udid": "device-udid",
        }


class TestEnums:
    """Tests for enum values."""

    def test_device_type_values(self):
        assert DeviceType.SIMULATOR.value == "simulator"
        assert DeviceType.PHYSICAL.value == "physical"

    def test_device_state_values(self):
        assert DeviceState.CONNECTED.value == "connected"
        assert DeviceState.DISCONNECTED.value == "disconnected"

    def test_connection_type_values(self):
        assert ConnectionType.USB.value == "USB"
        assert ConnectionType.WIFI.value == "WiFi"
        assert ConnectionType.UNKNOWN.value == "Unknown"


class TestProductNameMap:
    """Tests for product name mapping."""

    def test_iphone_16_pro_mapping(self):
        assert PRODUCT_NAME_MAP["iPhone17,1"] == "iPhone 16 Pro"
        assert PRODUCT_NAME_MAP["iPhone17,2"] == "iPhone 16 Pro Max"

    def test_iphone_15_pro_mapping(self):
        assert PRODUCT_NAME_MAP["iPhone16,1"] == "iPhone 15 Pro"
        assert PRODUCT_NAME_MAP["iPhone16,2"] == "iPhone 15 Pro Max"


class TestTunnelStatus:
    """Tests for TunnelStatus enum."""

    def test_tunnel_status_values(self):
        assert TunnelStatus.NO_TUNNEL.value == "no_tunnel"
        assert TunnelStatus.DISCOVERING.value == "discovering"
        assert TunnelStatus.CONNECTED.value == "connected"
        assert TunnelStatus.STALE.value == "stale"
        assert TunnelStatus.DISCONNECTED.value == "disconnected"
        assert TunnelStatus.ERROR.value == "error"


class TestTunnelState:
    """Tests for TunnelState dataclass."""

    def test_default_values(self):
        state = TunnelState(udid="test-udid")

        assert state.udid == "test-udid"
        assert state.status == TunnelStatus.NO_TUNNEL
        assert state.tunnel_info is None
        assert state.last_validated == 0.0
        assert state.last_queried == 0.0
        assert state.error is None

    def test_with_tunnel_info(self):
        tunnel = RSDTunnel(address="192.168.1.1", port=8080, udid="test-udid")
        state = TunnelState(
            udid="test-udid",
            status=TunnelStatus.CONNECTED,
            tunnel_info=tunnel,
            last_validated=1234567890.0,
            last_queried=1234567880.0,
        )

        assert state.status == TunnelStatus.CONNECTED
        assert state.tunnel_info.address == "192.168.1.1"
        assert state.tunnel_info.port == 8080
        assert state.last_validated == 1234567890.0

    def test_with_error(self):
        state = TunnelState(
            udid="test-udid",
            status=TunnelStatus.DISCONNECTED,
            error="Connection refused",
        )

        assert state.status == TunnelStatus.DISCONNECTED
        assert state.error == "Connection refused"

    def test_to_dict_minimal(self):
        state = TunnelState(udid="test-udid")
        result = state.to_dict()

        assert result == {
            "udid": "test-udid",
            "status": "no_tunnel",
            "tunnelInfo": None,
            "lastValidated": 0.0,
            "lastQueried": 0.0,
            "error": None,
        }

    def test_to_dict_full(self):
        tunnel = RSDTunnel(address="10.0.0.1", port=9999, udid="test-udid")
        state = TunnelState(
            udid="test-udid",
            status=TunnelStatus.CONNECTED,
            tunnel_info=tunnel,
            last_validated=1000.0,
            last_queried=999.0,
            error=None,
        )
        result = state.to_dict()

        assert result["status"] == "connected"
        assert result["tunnelInfo"] == {
            "address": "10.0.0.1",
            "port": 9999,
            "udid": "test-udid",
        }
        assert result["lastValidated"] == 1000.0
