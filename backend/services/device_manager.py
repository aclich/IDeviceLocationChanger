"""Device discovery and management."""

import json
import logging
import os
import subprocess
import sys
from typing import List, Optional

from models import Device, DeviceType, DeviceState, ConnectionType, RSDTunnel

logger = logging.getLogger(__name__)


class DeviceManager:
    """Discovers and manages iOS devices (simulators and physical)."""

    def __init__(self):
        self._devices: List[Device] = []
        self._env = self._get_environment()

    @property
    def devices(self) -> List[Device]:
        """Get cached device list."""
        return self._devices

    def _get_environment(self) -> dict:
        """Get environment with proper PATH for external tools."""
        env = os.environ.copy()
        home = os.path.expanduser("~")
        additional_paths = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            f"{home}/.asdf/shims",
            f"{home}/.pyenv/shims",
            f"{home}/.local/bin",
            "/usr/bin",
            "/bin",
        ]
        env["PATH"] = ":".join(additional_paths) + ":" + env.get("PATH", "")
        return env

    def list_devices(self) -> List[Device]:
        """Discover all connected devices (simulators and physical)."""
        logger.info("Discovering devices...")

        simulators = self._discover_simulators()
        physical = self._discover_physical_devices()

        self._devices = simulators + physical
        logger.info(f"Found {len(self._devices)} device(s): {len(simulators)} simulators, {len(physical)} physical")

        return self._devices

    def _discover_simulators(self) -> List[Device]:
        """Find booted iOS simulators."""
        devices = []
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "-j"],
                capture_output=True,
                text=True,
                env=self._env
            )

            if result.returncode == 0:
                data = json.loads(result.stdout)
                for runtime, device_list in data.get("devices", {}).items():
                    if "iOS" not in runtime:
                        continue
                    for device in device_list:
                        if device.get("state") == "Booted":
                            devices.append(Device(
                                id=device["udid"],
                                name=device["name"],
                                type=DeviceType.SIMULATOR,
                                state=DeviceState.CONNECTED
                            ))
        except Exception as e:
            logger.error(f"Simulator discovery error: {e}")
        return devices

    def _discover_physical_devices(self) -> List[Device]:
        """Find physical iOS devices."""
        # Try native API first, fallback to CLI
        devices = self._discover_with_pymobiledevice3_native()
        if devices:
            return devices
        return self._discover_with_pymobiledevice3_cli()

    def _discover_with_pymobiledevice3_native(self) -> List[Device]:
        """Discover using pymobiledevice3 library directly."""
        devices = []
        try:
            from pymobiledevice3.usbmux import list_devices
            from pymobiledevice3.lockdown import create_using_usbmux

            usbmux_devices = list_devices()

            for usbmux_device in usbmux_devices:
                try:
                    lockdown = create_using_usbmux(serial=usbmux_device.serial)
                    conn_type = ConnectionType.USB
                    if hasattr(usbmux_device, 'connection_type'):
                        ct = str(usbmux_device.connection_type).upper()
                        if 'WIFI' in ct or 'NETWORK' in ct:
                            conn_type = ConnectionType.WIFI

                    device = Device(
                        id=usbmux_device.serial,
                        name=lockdown.display_name or "iPhone",
                        type=DeviceType.PHYSICAL,
                        state=DeviceState.CONNECTED,
                        product_type=lockdown.product_type,
                        connection_type=conn_type
                    )
                    devices.append(device)
                except Exception as e:
                    logger.debug(f"Device info error for {usbmux_device.serial}: {e}")
        except ImportError:
            logger.debug("pymobiledevice3 not available for native discovery")
        except Exception as e:
            logger.debug(f"pymobiledevice3 native discovery error: {e}")
        return devices

    def _discover_with_pymobiledevice3_cli(self) -> List[Device]:
        """Fallback to CLI-based discovery."""
        devices = []
        try:
            result = subprocess.run(
                ["pymobiledevice3", "usbmux", "list", "--no-color"],
                capture_output=True,
                text=True,
                env=self._env
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                for info in data:
                    udid = info.get("Identifier") or info.get("UniqueDeviceID") or info.get("UDID", "")
                    if not udid:
                        continue
                    devices.append(Device(
                        id=udid,
                        name=info.get("DeviceName", "iPhone"),
                        type=DeviceType.PHYSICAL,
                        state=DeviceState.CONNECTED,
                        product_type=info.get("ProductType"),
                        connection_type=ConnectionType.USB
                    ))
        except Exception as e:
            logger.debug(f"CLI discovery error: {e}")
        return devices

    def get_device(self, device_id: str) -> Optional[Device]:
        """Get device by ID from cached list."""
        for device in self._devices:
            if device.id == device_id:
                return device
        return None

    def update_tunnel(self, device_id: str, tunnel: RSDTunnel) -> bool:
        """Update device with tunnel info."""
        device = self.get_device(device_id)
        if device:
            device.rsd_tunnel = tunnel
            return True
        return False
