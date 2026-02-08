"""Location simulation service - sends coordinates to devices.

LocationService manages persistent connections to iOS devices and decides
whether to use RSD tunnel (iOS 17+) or usbmux (iOS 16 and earlier).

Connection type decision flow:
1. Reuse existing connection if available (no tunneld query)
2. Use stored device connection type from disk (persisted on first success)
3. Probe on first connection: query tunneld, fall back to usbmux if no tunnel

Once a device is recorded as "tunnel", it NEVER falls back to usbmux.
Tunneld is only queried on retry after connection failure, not on every call.

Features:
- Persistent connections: Reuse connections across set_location calls
- Auto-refresh: Periodically re-send last location to keep connection alive
- Retry with reconnection: On error, retry with fresh tunnel info (up to 5 times)
- Device type persistence: Remember tunnel vs usbmux per device across restarts
"""

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from models import Device, DeviceType, RSDTunnel

logger = logging.getLogger(__name__)

# Configuration
REFRESH_INTERVAL_SECONDS = 3  # Re-send location every X seconds if no updates
MAX_RETRY_ATTEMPTS = 5  # Maximum retry attempts on connection error
RETRY_DELAY_SECONDS = 0.5  # Delay between retries
HEALTH_CHECK_INTERVAL_SECONDS = 10  # Run DVT health check after this many seconds of reuse

# Device connection type persistence
DEVICE_TYPES_FILENAME = "device_connection_types.json"


class LocationService:
    """
    Location service that sends coordinates to iOS devices.

    Features:
    - Persistent connections to prevent location jumping back
    - Auto-refresh to keep location active
    - Retry with full reconnection on errors
    - Device connection type persistence (tunnel vs usbmux)

    Connection strategy is determined internally based on existing
    connections, persisted device type, or first-time probing.
    Callers do not need to provide tunnel info.
    """

    def __init__(self, data_dir: Optional[str] = None):
        # Persistent connections per device: {device_id: {"rsd": ..., "dvt": ..., "location": ...}}
        # For tunnel connections (iOS 17+)
        self._tunnel_connections: dict[str, dict] = {}
        # For usbmux connections (iOS 16 and earlier)
        self._usbmux_connections: dict[str, dict] = {}

        # Lock to protect _tunnel_connections and _usbmux_connections access
        self._conn_lock = threading.Lock()

        # Last known location per device for refresh: {device_id: {"lat": ..., "lon": ..., "time": ...}}
        self._last_locations: dict[str, dict] = {}

        # Refresh threads per device: {device_id: {"thread": Thread, "stop_event": Event}}
        self._refresh_tasks: dict[str, dict] = {}

        # Tunnel provider callback for retry mechanism
        # Set by main.py: def provider(udid) -> Optional[RSDTunnel]
        self._tunnel_provider: Optional[Callable[[str], Optional[RSDTunnel]]] = None

        # Device connection type persistence: {device_id: "tunnel" | "usbmux"}
        # Prevents falling from tunnel to usbmux on transient tunneld timeouts
        self._device_connection_types: dict[str, str] = {}
        self._types_dir = Path(data_dir) if data_dir else Path.home() / ".location-simulator"
        self._types_file = self._types_dir / DEVICE_TYPES_FILENAME
        self._load_connection_types()

    def set_tunnel_provider(self, provider: Callable[[str], Optional[RSDTunnel]]) -> None:
        """Set the tunnel provider callback for retry mechanism.

        The provider should query tunneld for fresh tunnel info.
        Called by main.py during initialization.
        """
        self._tunnel_provider = provider

    # =========================================================================
    # Device Connection Type Persistence
    # =========================================================================

    def _load_connection_types(self) -> None:
        """Load device connection types from disk."""
        try:
            if self._types_file.exists():
                with open(self._types_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for device_id, conn_type in data.items():
                        if conn_type in ("tunnel", "usbmux"):
                            self._device_connection_types[device_id] = conn_type
                logger.info(f"Loaded connection types for {len(self._device_connection_types)} devices")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load device connection types: {e}")

    def _save_connection_types(self) -> None:
        """Save device connection types to disk."""
        try:
            self._types_dir.mkdir(parents=True, exist_ok=True)
            with open(self._types_file, "w", encoding="utf-8") as f:
                json.dump(self._device_connection_types, f, indent=2)
            logger.debug(f"Saved connection types for {len(self._device_connection_types)} devices")
        except OSError as e:
            logger.error(f"Failed to save device connection types: {e}")

    def _record_device_type(self, device_id: str, conn_type: str) -> None:
        """Record and persist device connection type on first successful connection."""
        if self._device_connection_types.get(device_id) != conn_type:
            self._device_connection_types[device_id] = conn_type
            self._save_connection_types()
            logger.info(f"[{device_id[:8]}] Recorded connection type: {conn_type}")

    def get_device_connection_type(self, device_id: str) -> Optional[str]:
        """Get stored connection type for a device. Returns 'tunnel', 'usbmux', or None."""
        return self._device_connection_types.get(device_id)

    # =========================================================================
    # Async-to-Sync Helpers for pymobiledevice3
    # =========================================================================

    @staticmethod
    def _sync_rsd_connect(rsd) -> None:
        """Connect an RSD service synchronously.

        RemoteServiceDiscoveryService.connect() is async in pymobiledevice3,
        so we wrap it with asyncio.run().
        """
        import asyncio
        asyncio.run(rsd.connect())

    @staticmethod
    def _sync_rsd_close(rsd) -> None:
        """Close an RSD service synchronously.

        rsd.close() is async in pymobiledevice3,
        so we wrap it with asyncio.run().
        """
        import asyncio
        asyncio.run(rsd.close())

    def set_location(
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
                return self._set_physical_location(device, latitude, longitude, tunnel)
        except Exception as e:
            logger.error(f"Set location error: {e}")
            return {"success": False, "error": str(e)}

    def clear_location(self, device: Device, tunnel: Optional[RSDTunnel] = None) -> dict:
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
                return self._clear_physical_location(device, tunnel)
        except Exception as e:
            logger.error(f"Clear location error: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Connection Management
    # =========================================================================

    def close_connection(self, device_id: str) -> None:
        """Close persistent connection for a specific device.

        Called when clearing location or on connection failure.
        Also stops the refresh task for this device.
        """
        # Stop refresh task
        self._stop_refresh_task(device_id)

        # Clear last location
        self._last_locations.pop(device_id, None)

        with self._conn_lock:
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
                        self._sync_rsd_close(conn["rsd"])
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

    def close_all_connections(self) -> None:
        """Close all persistent connections. Called on shutdown."""
        logger.info("Closing all persistent location connections...")

        # Stop all refresh tasks first
        for device_id in list(self._refresh_tasks.keys()):
            self._stop_refresh_task(device_id)

        # Close all connections
        with self._conn_lock:
            device_ids = list(self._tunnel_connections.keys()) + list(self._usbmux_connections.keys())

        for device_id in device_ids:
            self.close_connection(device_id)

    # =========================================================================
    # DVT Health Check
    # =========================================================================

    def _check_dvt_health(self, device_id: str, dvt) -> bool:
        """Check if DVT connection is alive by listing root directory.

        Creates a DeviceInfo channel on the existing DVT and tries ls("/").
        If the DVT transport is dead, this will raise or return empty.
        """
        try:
            from pymobiledevice3.services.dvt.instruments.device_info import DeviceInfo
            result = DeviceInfo(dvt).ls("/")
            return result is not None and len(result) > 0
        except Exception as e:
            logger.warning(f"[{device_id[:8]}] DVT health check failed: {e}")
            return False

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

    def _start_refresh_task(self, device: Device) -> None:
        """Start the refresh thread for a device if not already running."""
        if device.id in self._refresh_tasks:
            return  # Already running

        stop_event = threading.Event()

        def refresh_loop():
            """Periodically re-send the last location to keep connection alive."""
            while not stop_event.is_set():
                # Wait for the interval or until stopped
                if stop_event.wait(timeout=REFRESH_INTERVAL_SECONDS):
                    break  # Stop event was set

                try:
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

                    with self._conn_lock:
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

                except Exception as e:
                    logger.warning(f"[{device.id[:8]}] Refresh failed: {e}")
                    # On refresh error, try to reconnect on next set_location
                    # Don't close connection here - let the next set_location handle it

            logger.debug(f"[{device.id[:8]}] Refresh thread exiting")

        thread = threading.Thread(target=refresh_loop, daemon=True, name=f"refresh-{device.id[:8]}")
        thread.start()
        self._refresh_tasks[device.id] = {"thread": thread, "stop_event": stop_event}
        logger.debug(f"[{device.id[:8]}] Started refresh thread (interval: {REFRESH_INTERVAL_SECONDS}s)")

    def _stop_refresh_task(self, device_id: str) -> None:
        """Stop the refresh thread for a device."""
        if device_id in self._refresh_tasks:
            task_info = self._refresh_tasks.pop(device_id)
            task_info["stop_event"].set()
            task_info["thread"].join(timeout=5)
            logger.debug(f"[{device_id[:8]}] Stopped refresh thread")

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

    def _set_physical_location(
        self,
        device: Device,
        lat: float,
        lon: float,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Set location on physical iOS device.

        Routes to tunnel or usbmux based on:
        1. Existing connection (reuse without querying tunneld)
        2. Stored device connection type (from disk)
        3. Probing (first-time only: try tunneld, then usbmux)

        Never falls from tunnel to usbmux — once a device is known to use
        tunnel, it always uses tunnel even if tunneld times out.
        """
        # 1. Check existing connections (fastest path — no tunneld query)
        with self._conn_lock:
            has_tunnel_conn = device.id in self._tunnel_connections
            has_usbmux_conn = device.id in self._usbmux_connections

        if has_tunnel_conn:
            return self._set_via_tunnel_with_retry(device, tunnel, lat, lon)

        if has_usbmux_conn:
            return self._set_via_usbmux_with_retry(device, lat, lon)

        # 2. Check stored device type (no existing connection but we know what it needs)
        known_type = self._device_connection_types.get(device.id)

        if known_type == "tunnel":
            # Tunnel device — get tunnel info from provider, never try usbmux
            if not tunnel and self._tunnel_provider:
                tunnel = self._tunnel_provider(device.id)
            return self._set_via_tunnel_with_retry(device, tunnel, lat, lon)

        if known_type == "usbmux":
            return self._set_via_usbmux_with_retry(device, lat, lon)

        # 3. Unknown device — probe (first connection only)
        # Try tunnel first if caller provided one or provider can find one
        if not tunnel and self._tunnel_provider:
            tunnel = self._tunnel_provider(device.id)

        if tunnel:
            result = self._set_via_tunnel_with_retry(device, tunnel, lat, lon)
            if result.get("success"):
                self._record_device_type(device.id, "tunnel")
            return result

        # No tunnel available — try usbmux
        result = self._set_via_usbmux_with_retry(device, lat, lon)
        if result.get("success"):
            self._record_device_type(device.id, "usbmux")
        return result

    def _clear_physical_location(
        self,
        device: Device,
        tunnel: Optional[RSDTunnel] = None
    ) -> dict:
        """Clear location on physical iOS device.

        Uses existing connection or stored device type to determine path.
        Only queries tunneld if needed for a tunnel device with no connection.
        """
        # Check existing connections
        with self._conn_lock:
            has_tunnel_conn = device.id in self._tunnel_connections
            has_usbmux_conn = device.id in self._usbmux_connections

        if has_tunnel_conn:
            return self._clear_via_tunnel(device, tunnel)

        if has_usbmux_conn:
            return self._clear_via_usbmux(device)

        # No existing connection — use stored type
        known_type = self._device_connection_types.get(device.id)

        if known_type == "tunnel":
            if not tunnel and self._tunnel_provider:
                tunnel = self._tunnel_provider(device.id)
            return self._clear_via_tunnel(device, tunnel)

        if known_type == "usbmux":
            return self._clear_via_usbmux(device)

        # Unknown — try tunnel if available, else usbmux
        if tunnel:
            return self._clear_via_tunnel(device, tunnel)
        if self._tunnel_provider:
            tunnel = self._tunnel_provider(device.id)
            if tunnel:
                return self._clear_via_tunnel(device, tunnel)
        return self._clear_via_usbmux(device)

    # =========================================================================
    # Tunnel-based Connection (iOS 17+) - With Retry
    # =========================================================================

    def _create_tunnel_connection(self, device: Device, tunnel: RSDTunnel) -> tuple:
        """Create a new tunnel connection.

        Returns:
            Tuple of (rsd, dvt, location_service)
        """
        from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
        from pymobiledevice3.services.dvt.dvt_secure_socket_proxy import DvtSecureSocketProxyService
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        rsd = RemoteServiceDiscoveryService((tunnel.address, tunnel.port))
        self._sync_rsd_connect(rsd)

        dvt = DvtSecureSocketProxyService(lockdown=rsd)
        dvt.__enter__()

        location_service = LocationSimulation(dvt)

        # Store for reuse (caller holds _conn_lock)
        self._tunnel_connections[device.id] = {
            "rsd": rsd,
            "dvt": dvt,
            "location": location_service,
            "tunnel": tunnel,
            "created_at": time.time(),
        }

        return rsd, dvt, location_service

    def _get_or_create_tunnel_connection(
        self,
        device: Device,
        tunnel: RSDTunnel
    ) -> tuple:
        """Get existing tunnel connection or create new persistent one.

        Returns:
            Tuple of (rsd, dvt, location_service)
        """
        with self._conn_lock:
            # Check for existing connection
            if device.id in self._tunnel_connections:
                conn = self._tunnel_connections[device.id]
                if conn.get("dvt") and conn.get("location"):
                    age = time.time() - conn.get("created_at", 0)
                    if age > HEALTH_CHECK_INTERVAL_SECONDS:
                        if self._check_dvt_health(device.id, conn["dvt"]):
                            logger.debug(f"[{device.id[:8]}] Health check passed, resetting age")
                            conn["created_at"] = time.time()
                            return conn["rsd"], conn["dvt"], conn["location"]
                        else:
                            logger.warning(f"[{device.id[:8]}] Health check failed ({age:.0f}s old), reconnecting")
                            # Release lock before close_connection (which also acquires it)
                else:
                    logger.debug(f"[{device.id[:8]}] Existing connection invalid, recreating")
                    # Release lock before close_connection
            else:
                # No existing connection - create new one
                logger.info(f"[{device.id[:8]}] Creating new persistent tunnel connection")
                return self._create_tunnel_connection(device, tunnel)

            # If we reach here with an existing connection that needs reconnecting,
            # we need to check which case we're in
            if device.id in self._tunnel_connections:
                conn = self._tunnel_connections[device.id]
                if conn.get("dvt") and conn.get("location"):
                    age = time.time() - conn.get("created_at", 0)
                    if age <= HEALTH_CHECK_INTERVAL_SECONDS:
                        logger.debug(f"[{device.id[:8]}] Reusing existing tunnel connection")
                        return conn["rsd"], conn["dvt"], conn["location"]

        # Close outside the lock (close_connection acquires _conn_lock internally)
        self.close_connection(device.id)

        # Create new connection
        with self._conn_lock:
            logger.info(f"[{device.id[:8]}] Creating new persistent tunnel connection")
            return self._create_tunnel_connection(device, tunnel)

    def _set_via_tunnel_with_retry(
        self,
        device: Device,
        tunnel: Optional[RSDTunnel],
        lat: float,
        lon: float
    ) -> dict:
        """Set location via RSD tunnel with retry on connection errors.

        Reuses existing DVT connection when possible (no tunneld query).
        Only queries tunneld for fresh tunnel info on retry after failure.

        On error, retries up to MAX_RETRY_ATTEMPTS times:
        1. Close existing connection
        2. Get fresh tunnel info from tunnel provider (tunneld query)
        3. Create new DVT connection
        4. Retry set_location

        Never falls back to usbmux.
        """
        last_error = None
        current_tunnel = tunnel

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                # For new connection creation, we need tunnel info
                with self._conn_lock:
                    has_existing = device.id in self._tunnel_connections

                if not has_existing and current_tunnel is None:
                    # No existing connection and no tunnel info — query provider
                    if self._tunnel_provider:
                        logger.info(f"[{device.id[:8]}] Requesting tunnel info for new connection...")
                        current_tunnel = self._tunnel_provider(device.id)

                    if current_tunnel is None:
                        last_error = Exception("No tunnel available")
                        logger.warning(f"[{device.id[:8]}] No tunnel available (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS})")
                        if attempt < MAX_RETRY_ATTEMPTS - 1:
                            time.sleep(RETRY_DELAY_SECONDS)
                            continue
                        break

                _, _, location_service = self._get_or_create_tunnel_connection(device, current_tunnel)
                location_service.set(lat, lon)

                # Success — record device type and update last location
                self._record_device_type(device.id, "tunnel")
                self._update_last_location(device.id, lat, lon)
                self._start_refresh_task(device)

                if attempt > 0:
                    logger.info(f"[{device.id[:8]}] Set location succeeded on attempt {attempt + 1}")
                return {"success": True}

            except Exception as e:
                last_error = e
                logger.warning(f"[{device.id[:8]}] Set location failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")

                # Close the failed connection
                self.close_connection(device.id)
                current_tunnel = None  # Force fresh query on next attempt

                # If we have more attempts, get fresh tunnel info from provider
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY_SECONDS)

                    if self._tunnel_provider:
                        logger.info(f"[{device.id[:8]}] Requesting fresh tunnel info for retry...")
                        fresh_tunnel = self._tunnel_provider(device.id)
                        if fresh_tunnel:
                            current_tunnel = fresh_tunnel
                            logger.info(f"[{device.id[:8]}] Got fresh tunnel: {fresh_tunnel.address}:{fresh_tunnel.port}")
                        else:
                            logger.warning(f"[{device.id[:8]}] No tunnel available from provider")

        # All retries failed
        logger.error(f"[{device.id[:8]}] Set location via tunnel failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}")
        return {"success": False, "error": f"Tunnel connection failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"}

    def _clear_via_tunnel(self, device: Device, tunnel: RSDTunnel) -> dict:
        """Clear location via RSD tunnel (iOS 17+).

        Uses existing connection if available, then closes it.
        """
        try:
            # Use existing connection if available
            with self._conn_lock:
                if device.id in self._tunnel_connections:
                    conn = self._tunnel_connections[device.id]
                    conn["location"].clear()
                else:
                    # No existing connection - create one just to clear
                    # (edge case: clearing without prior set)
                    _, _, location_service = self._create_tunnel_connection(device, tunnel)
                    location_service.clear()

            # Close connection after clearing (simulation ended)
            self.close_connection(device.id)
            return {"success": True}
        except Exception as e:
            self.close_connection(device.id)
            logger.error(f"[{device.id[:8]}] Clear location via tunnel failed: {e}")
            return {"success": False, "error": f"Tunnel connection failed: {e}"}

    # =========================================================================
    # USBMux-based Connection (iOS 16 and earlier) - With Retry
    # =========================================================================

    def _create_usbmux_connection(self, device: Device) -> tuple:
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

        # Store for reuse (caller holds _conn_lock)
        self._usbmux_connections[device.id] = {
            "lockdown": lockdown,
            "dvt": dvt,
            "location": location_service,
            "created_at": time.time(),
        }

        return lockdown, dvt, location_service

    def _get_or_create_usbmux_connection(self, device: Device) -> tuple:
        """Get existing usbmux connection or create new persistent one.

        Returns:
            Tuple of (lockdown, dvt, location_service)
        """
        with self._conn_lock:
            # Check for existing connection
            if device.id in self._usbmux_connections:
                conn = self._usbmux_connections[device.id]
                if conn.get("dvt") and conn.get("location"):
                    age = time.time() - conn.get("created_at", 0)
                    if age > HEALTH_CHECK_INTERVAL_SECONDS:
                        if self._check_dvt_health(device.id, conn["dvt"]):
                            logger.debug(f"[{device.id[:8]}] Health check passed, resetting age")
                            conn["created_at"] = time.time()
                            return conn["lockdown"], conn["dvt"], conn["location"]
                        else:
                            logger.warning(f"[{device.id[:8]}] Health check failed ({age:.0f}s old), reconnecting")
                    else:
                        logger.debug(f"[{device.id[:8]}] Reusing existing usbmux connection")
                        return conn["lockdown"], conn["dvt"], conn["location"]
                else:
                    logger.debug(f"[{device.id[:8]}] Existing connection invalid, recreating")
            else:
                # No existing connection - create new one
                logger.info(f"[{device.id[:8]}] Creating new persistent usbmux connection")
                return self._create_usbmux_connection(device)

        # Close outside the lock (close_connection acquires _conn_lock internally)
        self.close_connection(device.id)

        # Create new connection
        with self._conn_lock:
            logger.info(f"[{device.id[:8]}] Creating new persistent usbmux connection")
            return self._create_usbmux_connection(device)

    def _set_via_usbmux_with_retry(self, device: Device, lat: float, lon: float) -> dict:
        """Set location via usbmux with retry on connection errors.

        On error, retries up to MAX_RETRY_ATTEMPTS times:
        1. Close existing connection
        2. Create new lockdown connection
        3. Retry set_location
        """
        last_error = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                _, _, location_service = self._get_or_create_usbmux_connection(device)
                location_service.set(lat, lon)

                # Success - update last location and start refresh task
                self._update_last_location(device.id, lat, lon)
                self._start_refresh_task(device)

                if attempt > 0:
                    logger.info(f"[{device.id[:8]}] Set location succeeded on attempt {attempt + 1}")
                return {"success": True}

            except Exception as e:
                last_error = e
                logger.warning(f"[{device.id[:8]}] Set location failed (attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}): {e}")

                # Close the failed connection
                self.close_connection(device.id)

                # Wait before retry
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY_SECONDS)

        # All retries failed
        logger.error(f"[{device.id[:8]}] Set location via usbmux failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}")
        return {"success": False, "error": f"Connection failed after {MAX_RETRY_ATTEMPTS} attempts: {last_error}"}

    def _clear_via_usbmux(self, device: Device) -> dict:
        """Clear location via usbmux (iOS 16 and earlier).

        Uses existing connection if available, then closes it.
        """
        try:
            # Use existing connection if available
            with self._conn_lock:
                if device.id in self._usbmux_connections:
                    conn = self._usbmux_connections[device.id]
                    conn["location"].clear()
                else:
                    # No existing connection - create one just to clear
                    _, _, location_service = self._create_usbmux_connection(device)
                    location_service.clear()

            # Close connection after clearing (simulation ended)
            self.close_connection(device.id)
            return {"success": True}
        except Exception as e:
            self.close_connection(device.id)
            logger.error(f"[{device.id[:8]}] Clear location via usbmux failed: {e}")
            return {"success": False, "error": str(e)}
