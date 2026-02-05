"""Location simulation service - sends coordinates to devices.

LocationService is responsible only for sending coordinates to devices.
It receives tunnel info from the caller (main.py) for iOS 17+ devices,
or uses direct usbmux connections for iOS 16 and earlier.

The caller (main.py/LocationSimulatorServer) is responsible for:
- Getting validated tunnel from TunnelManager
- Deciding whether to use tunnel or usbmux
- Passing the appropriate connection info to LocationService

Connections are kept persistent to prevent location jumping back to real GPS.
Each device maintains its own independent connection that persists until
explicitly cleared or app exits.

Features:
- Persistent connections: Reuse connections across set_location calls
- Auto-refresh: Periodically re-send last location to keep connection alive
- Retry with reconnection: On error, retry with fresh tunnel info (up to 5 times)
"""

import asyncio
import logging
import subprocess;
import time
from typing import Callable, Optional, Awaitable

from models import Device, DeviceType, RSDTunnel

logger = logging.getLogger(__name__)

# Configuration
REFRESH_INTERVAL_SECONDS = 3  # Re-send location every X seconds if no updates
MAX_RETRY_ATTEMPTS = 5  # Maximum retry attempts on connection error
RETRY_DELAY_SECONDS = 0.5  # Delay between retries


class LocationService:
    """
    Location service that sends coordinates to iOS devices.

    Features:
    - Persistent connections to prevent location jumping back
    - Auto-refresh to keep location active
    - Retry with full reconnection on errors

    Connection strategy is determined by the caller:
    - If tunnel is provided, use it (iOS 17+)
    - If no tunnel, use usbmux (iOS 16 and earlier)
    """

    def __init__(self):
        # Persistent connections per device: {device_id: {"rsd": ..., "dvt": ..., "location": ...}}
        # For tunnel connections (iOS 17+)
        self._tunnel_connections: dict[str, dict] = {}
        # For usbmux connections (iOS 16 and earlier)
        self._usbmux_connections: dict[str, dict] = {}

        # Last known location per device for refresh: {device_id: {"lat": ..., "lon": ..., "time": ...}}
        self._last_locations: dict[str, dict] = {}

        # Refresh tasks per device: {device_id: asyncio.Task}
        self._refresh_tasks: dict[str, asyncio.Task] = {}

        # Tunnel provider callback for retry mechanism
        # Set by main.py: async def provider(udid) -> Optional[RSDTunnel]
        self._tunnel_provider: Optional[Callable[[str], Awaitable[Optional[RSDTunnel]]]] = None

    def set_tunnel_provider(self, provider: Callable[[str], Awaitable[Optional[RSDTunnel]]]) -> None:
        """Set the tunnel provider callback for retry mechanism.

        The provider should query tunneld for fresh tunnel info.
        Called by main.py during initialization.
        """
        self._tunnel_provider = provider

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
    # Connection Management
    # =========================================================================

    async def close_connection(self, device_id: str) -> None:
        """Close persistent connection for a specific device.

        Called when clearing location or on connection failure.
        Also stops the refresh task for this device.
        """
        # Stop refresh task
        await self._stop_refresh_task(device_id)

        # Clear last location
        self._last_locations.pop(device_id, None)

        # Close tunnel connection if exists
        if device_id in self._tunnel_connections:
            conn = self._tunnel_connections.pop(device_id)
            logger.info(f"[{device_id[:8]}] Closing persistent tunnel connection")
            try:
                if conn.get("dvt"):
                    conn["dvt"].__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"[{device_id[:8]}] Error closing DVT: {e}")
            try:
                if conn.get("rsd"):
                    await conn["rsd"].close()
            except Exception as e:
                logger.debug(f"[{device_id[:8]}] Error closing RSD: {e}")

        # Close usbmux connection if exists
        if device_id in self._usbmux_connections:
            conn = self._usbmux_connections.pop(device_id)
            logger.info(f"[{device_id[:8]}] Closing persistent usbmux connection")
            try:
                if conn.get("dvt"):
                    conn["dvt"].__exit__(None, None, None)
            except Exception as e:
                logger.debug(f"[{device_id[:8]}] Error closing DVT: {e}")

    async def close_all_connections(self) -> None:
        """Close all persistent connections. Called on shutdown."""
        logger.info("Closing all persistent location connections...")

        # Stop all refresh tasks first
        for device_id in list(self._refresh_tasks.keys()):
            await self._stop_refresh_task(device_id)

        # Close all connections
        for device_id in list(self._tunnel_connections.keys()):
            await self.close_connection(device_id)
        for device_id in list(self._usbmux_connections.keys()):
            await self.close_connection(device_id)

    # =========================================================================
    # Refresh Mechanism
    # =========================================================================

    def _update_last_location(self, device_id: str, lat: float, lon: float) -> None:
        """Update last known location for a device."""
        self._last_locations[device_id] = {
            "lat": lat,
            "lon": lon,
            "time": time.time()
        }

    async def _start_refresh_task(self, device: Device) -> None:
        """Start the refresh task for a device if not already running."""
        if device.id in self._refresh_tasks:
            return  # Already running

        async def refresh_loop():
            """Periodically re-send the last location to keep connection alive."""
            while True:
                try:
                    await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

                    # Check if we have a last location
                    last = self._last_locations.get(device.id)
                    if not last:
                        continue

                    # Check if enough time has passed since last update
                    elapsed = time.time() - last["time"]
                    if elapsed < REFRESH_INTERVAL_SECONDS:
                        continue  # Recent update, skip refresh

                    # Re-send the last location
                    logger.debug(f"[{device.id[:8]}] Refreshing location ({elapsed:.1f}s since last update)")

                    if device.id in self._tunnel_connections:
                        conn = self._tunnel_connections[device.id]
                        if conn.get("location"):
                            conn["location"].set(last["lat"], last["lon"])
                            self._last_locations[device.id]["time"] = time.time()
                    elif device.id in self._usbmux_connections:
                        conn = self._usbmux_connections[device.id]
                        if conn.get("location"):
                            conn["location"].set(last["lat"], last["lon"])
                            self._last_locations[device.id]["time"] = time.time()

                except asyncio.CancelledError:
                    logger.debug(f"[{device.id[:8]}] Refresh task cancelled")
                    break
                except Exception as e:
                    logger.warning(f"[{device.id[:8]}] Refresh failed: {e}")
                    # On refresh error, try to reconnect on next set_location
                    # Don't close connection here - let the next set_location handle it

        task = asyncio.create_task(refresh_loop())
        self._refresh_tasks[device.id] = task
        logger.debug(f"[{device.id[:8]}] Started refresh task (interval: {REFRESH_INTERVAL_SECONDS}s)")

    async def _stop_refresh_task(self, device_id: str) -> None:
        """Stop the refresh task for a device."""
        if device_id in self._refresh_tasks:
            task = self._refresh_tasks.pop(device_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.debug(f"[{device_id[:8]}] Stopped refresh task")

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
            return await self._set_via_tunnel_with_retry(device, tunnel, lat, lon)
        # No tunnel - use usbmux (works for iOS 16 and earlier)
        return await self._set_via_usbmux_with_retry(device, lat, lon)

    async def _clear_physical_location(
        self,
        device: Device,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Clear location on physical iOS device."""
        if tunnel:
            return await self._clear_via_tunnel(device, tunnel)
        return await self._clear_via_usbmux(device)

    # =========================================================================
    # Tunnel-based Connection (iOS 17+) - With Retry
    # =========================================================================

    async def _create_tunnel_connection(self, device: Device, tunnel: RSDTunnel) -> tuple:
        """Create a new tunnel connection.

        Returns:
            Tuple of (rsd, dvt, location_service)
        """
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
        await rsd.connect()

        dvt = DvtSecureSocketProxyService(lockdown=rsd)
        dvt.__enter__()

        location_service = LocationSimulation(dvt)

        # Store for reuse
        self._tunnel_connections[device.id] = {
            "rsd": rsd,
            "dvt": dvt,
            "location": location_service,
            "tunnel": tunnel  # Store tunnel info for reference
        }

        return rsd, dvt, location_service

    async def _get_or_create_tunnel_connection(
        self,
        device: Device,
        tunnel: RSDTunnel
    ) -> tuple:
        """Get existing tunnel connection or create new persistent one.

        Returns:
            Tuple of (rsd, dvt, location_service)
        """
        # Check for existing connection
        if device.id in self._tunnel_connections:
            conn = self._tunnel_connections[device.id]
            if conn.get("dvt") and conn.get("location"):
                logger.debug(f"[{device.id[:8]}] Reusing existing tunnel connection")
                return conn["rsd"], conn["dvt"], conn["location"]
            # Invalid connection, clean up
            logger.debug(f"[{device.id[:8]}] Existing connection invalid, recreating")
            await self.close_connection(device.id)

        # Create new connection
        logger.info(f"[{device.id[:8]}] Creating new persistent tunnel connection")
        return await self._create_tunnel_connection(device, tunnel)

    async def _set_via_tunnel_with_retry(
        self,
        device: Device,
        tunnel: RSDTunnel,
        lat: float,
        lon: float
    ) -> dict:
        """Set location via RSD tunnel with retry on connection errors.

        On error, retries up to MAX_RETRY_ATTEMPTS times:
        1. Close existing connection
        2. Get fresh tunnel info from tunnel provider
        3. Create new DVT connection
        4. Retry set_location
        """
        last_error = None
        current_tunnel = tunnel

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                _, _, location_service = await self._get_or_create_tunnel_connection(device, current_tunnel)
                location_service.set(lat, lon)

                # Success - update last location and start refresh task
                self._update_last_location(device.id, lat, lon)
                await self._start_refresh_task(device)

                if attempt > 0:
                    logger.info(f"[{device.id[:8]}] Set location succeeded on attempt {attempt + 1}")
                return {"success": True}

            except Exception as e:
                last_error = e
                logger.warning(f"[{device.id[:8]}] Set location failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")

                # Close the failed connection
                await self.close_connection(device.id)

                # If we have more attempts, try to get fresh tunnel info
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

                    # Try to get fresh tunnel info
                    if self._tunnel_provider:
                        logger.info(f"[{device.id[:8]}] Requesting fresh tunnel info for retry...")
                        fresh_tunnel = await self._tunnel_provider(device.id)
                        if fresh_tunnel:
                            current_tunnel = fresh_tunnel
                            logger.info(f"[{device.id[:8]}] Got fresh tunnel: {fresh_tunnel.address}:{fresh_tunnel.port}")
                        else:
                            logger.warning(f"[{device.id[:8]}] No tunnel available, retrying with existing info")

        # All retries failed
        logger.error(f"[{device.id[:8]}] Set location via tunnel failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}")
        return {"success": False, "error": f"Tunnel connection failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"}

    async def _clear_via_tunnel(self, device: Device, tunnel: RSDTunnel) -> dict:
        """Clear location via RSD tunnel (iOS 17+).

        Uses existing connection if available, then closes it.
        """
        try:
            # Use existing connection if available
            if device.id in self._tunnel_connections:
                conn = self._tunnel_connections[device.id]
                conn["location"].clear()
            else:
                # No existing connection - create one just to clear
                # (edge case: clearing without prior set)
                _, _, location_service = await self._get_or_create_tunnel_connection(device, tunnel)
                location_service.clear()

            # Close connection after clearing (simulation ended)
            await self.close_connection(device.id)
            return {"success": True}
        except Exception as e:
            await self.close_connection(device.id)
            logger.error(f"[{device.id[:8]}] Clear location via tunnel failed: {e}")
            return {"success": False, "error": f"Tunnel connection failed: {e}"}

    # =========================================================================
    # USBMux-based Connection (iOS 16 and earlier) - With Retry
    # =========================================================================

    async def _create_usbmux_connection(self, device: Device) -> tuple:
        """Create a new usbmux connection.

        Returns:
            Tuple of (lockdown, dvt, location_service)
        """
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        lockdown = create_using_usbmux(serial=device.id)
        dvt = DvtSecureSocketProxyService(lockdown=lockdown)
        dvt.__enter__()

        location_service = LocationSimulation(dvt)

        # Store for reuse
        self._usbmux_connections[device.id] = {
            "lockdown": lockdown,
            "dvt": dvt,
            "location": location_service
        }

        return lockdown, dvt, location_service

    async def _get_or_create_usbmux_connection(self, device: Device) -> tuple:
        """Get existing usbmux connection or create new persistent one.

        Returns:
            Tuple of (lockdown, dvt, location_service)
        """
        # Check for existing connection
        if device.id in self._usbmux_connections:
            conn = self._usbmux_connections[device.id]
            if conn.get("dvt") and conn.get("location"):
                logger.debug(f"[{device.id[:8]}] Reusing existing usbmux connection")
                return conn["lockdown"], conn["dvt"], conn["location"]
            # Invalid connection, clean up
            logger.debug(f"[{device.id[:8]}] Existing connection invalid, recreating")
            await self.close_connection(device.id)

        # Create new connection
        logger.info(f"[{device.id[:8]}] Creating new persistent usbmux connection")
        return await self._create_usbmux_connection(device)

    async def _set_via_usbmux_with_retry(self, device: Device, lat: float, lon: float) -> dict:
        """Set location via usbmux with retry on connection errors.

        On error, retries up to MAX_RETRY_ATTEMPTS times:
        1. Close existing connection
        2. Create new lockdown connection
        3. Retry set_location
        """
        last_error = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                _, _, location_service = await self._get_or_create_usbmux_connection(device)
                location_service.set(lat, lon)

                # Success - update last location and start refresh task
                self._update_last_location(device.id, lat, lon)
                await self._start_refresh_task(device)

                if attempt > 0:
                    logger.info(f"[{device.id[:8]}] Set location succeeded on attempt {attempt + 1}")
                return {"success": True}

            except Exception as e:
                last_error = e
                logger.warning(f"[{device.id[:8]}] Set location failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")

                # Close the failed connection
                await self.close_connection(device.id)

                # Wait before retry
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        # All retries failed
        logger.error(f"[{device.id[:8]}] Set location via usbmux failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}")
        return {"success": False, "error": f"Connection failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"}

    async def _clear_via_usbmux(self, device: Device) -> dict:
        """Clear location via usbmux (iOS 16 and earlier).

        Uses existing connection if available, then closes it.
        """
        try:
            # Use existing connection if available
            if device.id in self._usbmux_connections:
                conn = self._usbmux_connections[device.id]
                conn["location"].clear()
            else:
                # No existing connection - create one just to clear
                _, _, location_service = await self._get_or_create_usbmux_connection(device)
                location_service.clear()

            # Close connection after clearing (simulation ended)
            await self.close_connection(device.id)
            return {"success": True}
        except Exception as e:
            await self.close_connection(device.id)
            logger.error(f"[{device.id[:8]}] Clear location via usbmux failed: {e}")
            return {"success": False, "error": str(e)}
