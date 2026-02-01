"""Location simulation service - sends coordinates to devices."""

import asyncio
import logging
import subprocess
from typing import Any, Optional

from models import Device, DeviceType

logger = logging.getLogger(__name__)


class LocationService:
    """
    Simple location service that sends coordinates to iOS devices.

    All coordinate calculations (joystick, cruise mode) are handled by the frontend.
    This service only receives coordinates and injects them to the device.
    """

    def __init__(self):
        # Connection cache for physical devices
        self._connections: dict[str, dict] = {}  # device_id -> {dvt, location_service}

    async def set_location(self, device: Device, latitude: float, longitude: float) -> dict:
        """Set location on device."""
        if not device:
            return {"success": False, "error": "No device provided"}

        try:
            if device.type == DeviceType.SIMULATOR:
                return self._set_simulator_location(device, latitude, longitude)
            else:
                return await self._set_physical_location(device, latitude, longitude)
        except Exception as e:
            logger.error(f"Set location error: {e}")
            self._clear_connection(device.id)
            return {"success": False, "error": str(e)}

    async def clear_location(self, device: Device) -> dict:
        """Clear simulated location on device."""
        if not device:
            return {"success": False, "error": "No device provided"}

        try:
            if device.type == DeviceType.SIMULATOR:
                return self._clear_simulator_location(device)
            else:
                return await self._clear_physical_location(device)
        except Exception as e:
            logger.error(f"Clear location error: {e}")
            self._clear_connection(device.id)
            return {"success": False, "error": str(e)}

    def _set_simulator_location(self, device: Device, lat: float, lon: float) -> dict:
        """Set location on iOS Simulator."""
        result = subprocess.run(
            ["xcrun", "simctl", "location", device.id, "set", f"{lat},{lon}"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return {"success": True}
        return {"success": False, "error": result.stderr or "simctl failed"}

    def _clear_simulator_location(self, device: Device) -> dict:
        """Clear location on iOS Simulator."""
        result = subprocess.run(
            ["xcrun", "simctl", "location", device.id, "clear"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return {"success": True}
        return {"success": False, "error": result.stderr or "simctl failed"}

    async def _set_physical_location(self, device: Device, lat: float, lon: float) -> dict:
        """Set location on physical iOS device."""
        location_service = await self._get_location_service(device)
        if not location_service:
            return {"success": False, "error": "Failed to connect to device"}

        location_service.set(lat, lon)
        return {"success": True}

    async def _clear_physical_location(self, device: Device) -> dict:
        """Clear location on physical iOS device."""
        location_service = await self._get_location_service(device)
        if not location_service:
            return {"success": False, "error": "Failed to connect to device"}

        location_service.clear()
        return {"success": True}

    async def _get_location_service(self, device: Device) -> Optional[Any]:
        """Get or create location service connection for physical device."""
        if device.id in self._connections:
            return self._connections[device.id].get("location_service")

        try:
            if device.rsd_tunnel and device.rsd_tunnel.is_configured:
                return await self._connect_via_tunnel(device)
            else:
                return self._connect_via_usbmux(device)
        except Exception as e:
            logger.error(f"Connection error for {device.id}: {e}")
            return None

    async def _connect_via_tunnel(self, device: Device) -> Optional[Any]:
        """Connect to device via RSD tunnel (iOS 17+)."""
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        # RSD connect() is truly async
        rsd = RemoteServiceDiscoveryService((device.rsd_tunnel.address, device.rsd_tunnel.port))
        await rsd.connect()

        # DVT creation is sync
        dvt = DvtSecureSocketProxyService(lockdown=rsd)
        dvt.__enter__()
        location_service = LocationSimulation(dvt)

        self._connections[device.id] = {
            "rsd": rsd,
            "dvt": dvt,
            "location_service": location_service
        }
        logger.info(f"Connected to {device.id} via tunnel")
        return location_service

    def _connect_via_usbmux(self, device: Device) -> Optional[Any]:
        """Connect to device via usbmux (iOS 16 and earlier)."""
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        lockdown = create_using_usbmux(serial=device.id)
        dvt = DvtSecureSocketProxyService(lockdown=lockdown)
        dvt.__enter__()
        location_service = LocationSimulation(dvt)

        self._connections[device.id] = {
            "dvt": dvt,
            "location_service": location_service
        }
        logger.info(f"Connected to {device.id} via usbmux")
        return location_service

    def _clear_connection(self, device_id: str) -> None:
        """Clear cached connection for device."""
        if device_id not in self._connections:
            return

        conn = self._connections.pop(device_id)
        dvt = conn.get("dvt")
        rsd = conn.get("rsd")

        if dvt:
            try:
                dvt.__exit__(None, None, None)
            except Exception:
                pass

        # rsd.close() is async - schedule it if there's a running loop
        if rsd:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(rsd.close())
            except RuntimeError:
                # No running loop - just skip, cleanup on process exit
                pass

        logger.debug(f"Cleared connection for {device_id}")

    def disconnect_all(self) -> None:
        """Disconnect from all devices."""
        for device_id in list(self._connections.keys()):
            self._clear_connection(device_id)
