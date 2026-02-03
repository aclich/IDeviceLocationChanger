"""Location simulation service - sends coordinates to devices.

LocationService is responsible only for sending coordinates to devices.
It receives tunnel info from the caller (main.py) for iOS 17+ devices,
or uses direct usbmux connections for iOS 16 and earlier.

The caller (main.py/LocationSimulatorServer) is responsible for:
- Getting validated tunnel from TunnelManager
- Deciding whether to use tunnel or usbmux
- Passing the appropriate connection info to LocationService
"""

import logging
import subprocess
from typing import Optional

from models import Device, DeviceType, RSDTunnel

logger = logging.getLogger(__name__)


class LocationService:
    """
    Simple location service that sends coordinates to iOS devices.

    All coordinate calculations (joystick, cruise mode) are handled by the frontend.
    This service only receives coordinates and injects them to the device.

    Connection strategy is determined by the caller:
    - If tunnel is provided, use it (iOS 17+)
    - If no tunnel, use usbmux (iOS 16 and earlier)
    """

    async def set_location(
        self,
        device: Device,
        latitude: float,
        longitude: float,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Set location on device.

        Args:
            device: Target device
            latitude: GPS latitude
            longitude: GPS longitude
            tunnel: Optional RSD tunnel for iOS 17+ devices
        """
        if not device:
            return {"success": False, "error": "No device provided"}

        try:
            if device.type == DeviceType.SIMULATOR:
                return self._set_simulator_location(device, latitude, longitude)
            else:
                return await self._set_physical_location(device, latitude, longitude, tunnel)
        except Exception as e:
            logger.error(f"Set location error: {e}")
            return {"success": False, "error": str(e)}

    async def clear_location(self, device: Device, tunnel: Optional[RSDTunnel] = None) -> dict:
        """Clear simulated location on device.

        Args:
            device: Target device
            tunnel: Optional RSD tunnel for iOS 17+ devices
        """
        if not device:
            return {"success": False, "error": "No device provided"}

        try:
            if device.type == DeviceType.SIMULATOR:
                return self._clear_simulator_location(device)
            else:
                return await self._clear_physical_location(device, tunnel)
        except Exception as e:
            logger.error(f"Clear location error: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Simulator Location (via xcrun simctl)
    # =========================================================================

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

    # =========================================================================
    # Physical Device Location
    # =========================================================================

    async def _set_physical_location(
        self,
        device: Device,
        lat: float,
        lon: float,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Set location on physical iOS device.

        Args:
            device: Target device
            lat: GPS latitude
            lon: GPS longitude
            tunnel: Optional RSD tunnel (caller provides for iOS 17+)

        If tunnel is provided, use it. Otherwise fall back to usbmux.
        """
        if tunnel:
            return await self._set_via_tunnel(device, tunnel, lat, lon)
        # No tunnel - use usbmux (works for iOS 16 and earlier)
        return self._set_via_usbmux(device, lat, lon)

    async def _clear_physical_location(
        self,
        device: Device,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Clear location on physical iOS device."""
        if tunnel:
            return await self._clear_via_tunnel(device, tunnel)
        return self._clear_via_usbmux(device)

    # =========================================================================
    # Tunnel-based Connection (iOS 17+)
    # =========================================================================

    async def _set_via_tunnel(
        self,
        device: Device,
        tunnel: RSDTunnel,
        lat: float,
        lon: float
    ) -> dict:
        """Set location via RSD tunnel (iOS 17+).

        Args:
            device: Target device
            tunnel: Validated RSD tunnel connection info
            lat: GPS latitude
            lon: GPS longitude
        """
        try:
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

            # Connect via tunnel
            rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
            await rsd.connect()

            try:
                dvt = DvtSecureSocketProxyService(lockdown=rsd)
                dvt.__enter__()
                try:
                    location_service = LocationSimulation(dvt)
                    location_service.set(lat, lon)
                    return {"success": True}
                finally:
                    dvt.__exit__(None, None, None)
            finally:
                try:
                    await rsd.close()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[{device.id[:8]}] Set location via tunnel failed: {e}")
            return {"success": False, "error": f"Tunnel connection failed: {e}"}

    async def _clear_via_tunnel(self, device: Device, tunnel: RSDTunnel) -> dict:
        """Clear location via RSD tunnel (iOS 17+).

        Args:
            device: Target device
            tunnel: Validated RSD tunnel connection info
        """
        try:
            from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

            # Connect via tunnel
            rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
            await rsd.connect()

            try:
                dvt = DvtSecureSocketProxyService(lockdown=rsd)
                dvt.__enter__()
                try:
                    location_service = LocationSimulation(dvt)
                    location_service.clear()
                    return {"success": True}
                finally:
                    dvt.__exit__(None, None, None)
            finally:
                try:
                    await rsd.close()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[{device.id[:8]}] Clear location via tunnel failed: {e}")
            return {"success": False, "error": f"Tunnel connection failed: {e}"}

    # =========================================================================
    # USBMux-based Connection (iOS 16 and earlier)
    # =========================================================================

    def _set_via_usbmux(self, device: Device, lat: float, lon: float) -> dict:
        """Set location via usbmux (iOS 16 and earlier)."""
        #TODO: Check if device is iOS 16 or earlier?
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

            lockdown = create_using_usbmux(serial=device.id)
            dvt = DvtSecureSocketProxyService(lockdown=lockdown)
            dvt.__enter__()
            try:
                location_service = LocationSimulation(dvt)
                location_service.set(lat, lon)
                return {"success": True}
            finally:
                dvt.__exit__(None, None, None)

        except Exception as e:
            logger.error(f"[{device.id[:8]}] Set location via usbmux failed: {e}")
            return {"success": False, "error": str(e)}

    def _clear_via_usbmux(self, device: Device) -> dict:
        """Clear location via usbmux (iOS 16 and earlier)."""
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

            lockdown = create_using_usbmux(serial=device.id)
            dvt = DvtSecureSocketProxyService(lockdown=lockdown)
            dvt.__enter__()
            try:
                location_service = LocationSimulation(dvt)
                location_service.clear()
                return {"success": True}
            finally:
                dvt.__exit__(None, None, None)

        except Exception as e:
            logger.error(f"[{device.id[:8]}] Clear location via usbmux failed: {e}")
            return {"success": False, "error": str(e)}
