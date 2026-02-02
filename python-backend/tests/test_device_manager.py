"""Tests for DeviceManager service."""

import json
import pytest
from unittest.mock import patch, MagicMock

from services.device_manager import DeviceManager
from models import Device, DeviceType, DeviceState, ConnectionType, RSDTunnel


class TestDeviceManager:
    """Tests for DeviceManager class."""

    def test_init_creates_empty_device_list(self):
        dm = DeviceManager()
        assert dm.devices == []

    def test_get_device_returns_none_when_not_found(self):
        dm = DeviceManager()
        assert dm.get_device("nonexistent") is None

    def test_get_device_returns_device_when_found(self):
        dm = DeviceManager()
        device = Device(
            id="test-123",
            name="Test Device",
            type=DeviceType.SIMULATOR,
            state=DeviceState.CONNECTED,
        )
        dm._devices = [device]

        result = dm.get_device("test-123")

        assert result is device

    def test_update_tunnel_success(self):
        dm = DeviceManager()
        device = Device(
            id="test-123",
            name="Test Device",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        dm._devices = [device]

        tunnel = RSDTunnel(address="127.0.0.1", port=8080, udid="test-123")
        result = dm.update_tunnel("test-123", tunnel)

        assert result is True
        assert device.rsd_tunnel == tunnel

    def test_update_tunnel_device_not_found(self):
        dm = DeviceManager()

        tunnel = RSDTunnel(address="127.0.0.1", port=8080)
        result = dm.update_tunnel("nonexistent", tunnel)

        assert result is False


class TestSimulatorDiscovery:
    """Tests for simulator discovery."""

    @patch("services.device_manager.subprocess.run")
    async def test_discover_simulators_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "devices": {
                    "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
                        {
                            "udid": "sim-123",
                            "name": "iPhone 15 Pro",
                            "state": "Booted",
                        },
                        {
                            "udid": "sim-456",
                            "name": "iPhone 15",
                            "state": "Shutdown",
                        },
                    ],
                    "com.apple.CoreSimulator.SimRuntime.watchOS-10-0": [
                        {
                            "udid": "watch-123",
                            "name": "Apple Watch",
                            "state": "Booted",
                        },
                    ],
                }
            })
        )

        dm = DeviceManager()
        devices = await dm.list_devices()

        # Should only return booted iOS simulators
        simulators = [d for d in devices if d.type == DeviceType.SIMULATOR]
        assert len(simulators) == 1
        assert simulators[0].id == "sim-123"
        assert simulators[0].name == "iPhone 15 Pro"
        assert simulators[0].state == DeviceState.CONNECTED

    @patch("services.device_manager.subprocess.run")
    async def test_discover_simulators_no_booted(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "devices": {
                    "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
                        {
                            "udid": "sim-123",
                            "name": "iPhone 15 Pro",
                            "state": "Shutdown",
                        },
                    ],
                }
            })
        )

        dm = DeviceManager()
        devices = await dm.list_devices()

        simulators = [d for d in devices if d.type == DeviceType.SIMULATOR]
        assert len(simulators) == 0

    @patch("services.device_manager.subprocess.run")
    async def test_discover_simulators_xcrun_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        dm = DeviceManager()
        devices = await dm.list_devices()

        simulators = [d for d in devices if d.type == DeviceType.SIMULATOR]
        assert len(simulators) == 0

    @patch("services.device_manager.subprocess.run")
    async def test_discover_simulators_exception(self, mock_run):
        mock_run.side_effect = Exception("xcrun not found")

        dm = DeviceManager()
        devices = await dm.list_devices()

        # Should handle exception gracefully
        simulators = [d for d in devices if d.type == DeviceType.SIMULATOR]
        assert len(simulators) == 0


class TestPhysicalDeviceDiscovery:
    """Tests for physical device discovery."""

    @patch.object(DeviceManager, "_discover_with_pymobiledevice3_native")
    @patch.object(DeviceManager, "_discover_with_pymobiledevice3_cli")
    @patch("services.device_manager.subprocess.run")
    async def test_prefers_native_discovery(self, mock_run, mock_cli, mock_native):
        # Simulator discovery returns empty
        mock_run.return_value = MagicMock(returncode=0, stdout='{"devices": {}}')

        native_device = Device(
            id="native-123",
            name="Native Device",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        mock_native.return_value = [native_device]
        mock_cli.return_value = []

        dm = DeviceManager()
        devices = await dm.list_devices()

        physical = [d for d in devices if d.type == DeviceType.PHYSICAL]
        assert len(physical) == 1
        assert physical[0].id == "native-123"
        mock_cli.assert_not_called()

    @patch.object(DeviceManager, "_discover_with_pymobiledevice3_native")
    @patch.object(DeviceManager, "_discover_with_pymobiledevice3_cli")
    @patch("services.device_manager.subprocess.run")
    async def test_falls_back_to_cli(self, mock_run, mock_cli, mock_native):
        # Simulator discovery returns empty
        mock_run.return_value = MagicMock(returncode=0, stdout='{"devices": {}}')

        mock_native.return_value = []

        cli_device = Device(
            id="cli-456",
            name="CLI Device",
            type=DeviceType.PHYSICAL,
            state=DeviceState.CONNECTED,
        )
        mock_cli.return_value = [cli_device]

        dm = DeviceManager()
        devices = await dm.list_devices()

        physical = [d for d in devices if d.type == DeviceType.PHYSICAL]
        assert len(physical) == 1
        assert physical[0].id == "cli-456"


class TestCLIDiscovery:
    """Tests for CLI-based physical device discovery."""

    @patch("services.device_manager.subprocess.run")
    def test_cli_discovery_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {
                    "Identifier": "device-udid-123",
                    "DeviceName": "My iPhone",
                    "ProductType": "iPhone17,1",
                },
            ])
        )

        dm = DeviceManager()
        devices = dm._discover_with_pymobiledevice3_cli()

        assert len(devices) == 1
        assert devices[0].id == "device-udid-123"
        assert devices[0].name == "My iPhone"
        assert devices[0].product_type == "iPhone17,1"
        assert devices[0].connection_type == ConnectionType.USB

    @patch("services.device_manager.subprocess.run")
    def test_cli_discovery_uses_alternative_id_fields(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {
                    "UniqueDeviceID": "unique-id-456",
                    "DeviceName": "iPhone",
                },
            ])
        )

        dm = DeviceManager()
        devices = dm._discover_with_pymobiledevice3_cli()

        assert len(devices) == 1
        assert devices[0].id == "unique-id-456"

    @patch("services.device_manager.subprocess.run")
    def test_cli_discovery_skips_devices_without_id(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"DeviceName": "No ID Device"},
            ])
        )

        dm = DeviceManager()
        devices = dm._discover_with_pymobiledevice3_cli()

        assert len(devices) == 0

    @patch("services.device_manager.subprocess.run")
    def test_cli_discovery_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

        dm = DeviceManager()
        devices = dm._discover_with_pymobiledevice3_cli()

        assert len(devices) == 0
