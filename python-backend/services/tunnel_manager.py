"""RSD tunnel management for iOS 17+ devices.

TunnelManager queries tunneld for tunnel connections.
It does NOT cache tunnel info - each get_tunnel() call queries tunneld fresh.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from typing import Optional

from models import RSDTunnel, TunnelState, TunnelStatus

logger = logging.getLogger(__name__)

# Default tunneld port
TUNNELD_DEFAULT_PORT = 49151


class TunnelManager:
    """
    Manages pymobiledevice3 lockdown tunnels for iOS 17+ devices.

    Each get_tunnel() call queries tunneld for fresh tunnel info.
    No caching - tunneld is the source of truth.
    """

    def __init__(self):
        # Track last known state for UI display
        self._last_status: dict[str, TunnelState] = {}
        # Track last error for UI display
        self._last_error: Optional[str] = None

    # =========================================================================
    # Public API
    # =========================================================================

    async def get_tunnel(self, udid: str) -> Optional[RSDTunnel]:
        """
        Get tunnel for device by querying tunneld.

        Always queries tunneld for fresh info - no caching.
        Returns tunnel info if found, None otherwise.

        This method does NOT require admin password - it only queries
        existing tunnels from tunneld daemon.
        """
        if not udid:
            logger.warning("get_tunnel called without UDID")
            return None

        # Query tunneld for current tunnel info
        tunnel = self._query_tunneld_http(udid)

        if tunnel:
            logger.debug(f"[{udid[:8]}] Tunnel found: {tunnel.address}:{tunnel.port}")
            # Update last known status
            self._update_status(udid, TunnelStatus.CONNECTED, tunnel)
        else:
            logger.debug(f"[{udid[:8]}] No tunnel found in tunneld")
            self._update_status(udid, TunnelStatus.NO_TUNNEL, None)

        return tunnel

    def get_status(self, udid: str = None) -> dict:
        """
        Get tunnel status for UI display.

        If udid provided: return status for specific device
        If udid is None: return status for all devices with legacy format
        """
        if udid:
            state = self._last_status.get(udid)
            if state:
                return state.to_dict()
            return TunnelState(udid=udid).to_dict()

        # Legacy format for backward compatibility
        # Return status of first connected tunnel or general status
        for state in self._last_status.values():
            if state.status == TunnelStatus.CONNECTED and state.tunnel_info:
                return {
                    "running": True,
                    "address": state.tunnel_info.address,
                    "port": state.tunnel_info.port,
                    "udid": state.udid,
                    "message": f"Connected: {state.tunnel_info.address}:{state.tunnel_info.port}",
                    "status": state.status.value,
                }

        # No connected tunnels
        return {
            "running": False,
            "address": None,
            "port": None,
            "udid": None,
            "message": self._last_error or "No active tunnels",
            "status": TunnelStatus.NO_TUNNEL.value,
        }

    def invalidate(self, udid: str) -> None:
        """
        Mark tunnel as disconnected after a connection failure.
        Called by main.py when location operation fails.

        Since we don't cache, this just updates the UI status.
        Next get_tunnel() will query tunneld fresh anyway.
        """
        if udid in self._last_status:
            state = self._last_status[udid]
            state.status = TunnelStatus.DISCONNECTED
            state.error = "Connection failed"
            logger.info(f"[{udid[:8]}] Tunnel marked as disconnected")

    async def start_tunnel(self, udid: str) -> dict:
        """
        Explicitly start tunnel for device. May require admin password.

        Called by UI "Start Tunnel" button when no tunnel exists.
        """
        if not udid:
            return {"success": False, "error": "UDID required"}

        logger.info("=" * 50)
        logger.info(f"Starting tunnel for {udid[:8]}...")
        logger.info("=" * 50)

        self._last_error = None

        # Step 1: Check for existing tunnel
        logger.info("Checking for existing tunnel...")
        tunnel = self._query_tunneld_http(udid)

        if tunnel:
            logger.info(f"[{udid[:8]}] Found existing tunnel: {tunnel.address}:{tunnel.port}")
            self._update_status(udid, TunnelStatus.CONNECTED, tunnel)
            return {
                "success": True,
                "address": tunnel.address,
                "port": tunnel.port,
                "udid": udid,
                "status": TunnelStatus.CONNECTED.value,
            }

        # Step 2: Start new tunnel (requires admin)
        logger.info("No tunnel found, starting new tunnel...")
        tunnel = await self._start_new_tunnel(udid)

        if tunnel:
            self._update_status(udid, TunnelStatus.CONNECTED, tunnel)
            logger.info(f"[{udid[:8]}] SUCCESS: Tunnel started: {tunnel.address}:{tunnel.port}")
            return {
                "success": True,
                "address": tunnel.address,
                "port": tunnel.port,
                "udid": udid,
                "status": TunnelStatus.CONNECTED.value,
            }
        else:
            self._update_status(udid, TunnelStatus.ERROR, None, self._last_error)
            logger.error(f"[{udid[:8]}] FAILED: {self._last_error}")
            return {"success": False, "error": self._last_error or "Unknown error"}

    async def stop_tunnel(self, udid: str = None) -> dict:
        """
        Stop tunnel for device or all tunnels.

        If udid provided: clear that device's status
        If udid is None: stop all tunnel processes (requires admin)
        """
        logger.info(f"Stopping tunnel...{f' (UDID: {udid[:8]})' if udid else ' (all)'}")

        if udid:
            # Just clear the specific device's status
            if udid in self._last_status:
                del self._last_status[udid]
            logger.info(f"[{udid[:8]}] Tunnel state cleared")
        else:
            # Stop all tunnel processes
            if sys.platform == "darwin":
                self._stop_tunnel_macos()
            elif sys.platform == "linux":
                self._stop_tunnel_linux()

            # Clear all states
            self._last_status.clear()
            logger.info("All tunnels stopped")

        return {"success": True}

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _update_status(
        self,
        udid: str,
        status: TunnelStatus,
        tunnel: Optional[RSDTunnel],
        error: str = None
    ) -> None:
        """Update last known status for UI display."""
        if udid not in self._last_status:
            self._last_status[udid] = TunnelState(udid=udid)

        state = self._last_status[udid]
        state.status = status
        state.tunnel_info = tunnel
        state.error = error
        if status == TunnelStatus.CONNECTED:
            state.last_validated = time.time()

    # =========================================================================
    # Tunnel Discovery (Query tunneld)
    # =========================================================================

    def _query_tunneld_http(self, udid: str) -> Optional[RSDTunnel]:
        """Query tunneld via HTTP API for specific device."""
        try:
            url = f"http://127.0.0.1:{TUNNELD_DEFAULT_PORT}/"
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=2) as response:
                response_text = response.read().decode('utf-8')

            data = json.loads(response_text)

            if not isinstance(data, dict) or len(data) == 0:
                return None

            # Find matching device
            if udid in data:
                return self._extract_tunnel_info(data[udid], udid)

            # Try partial match (some systems use different UDID formats)
            for device_udid, device_info in data.items():
                if udid in device_udid or device_udid in udid:
                    return self._extract_tunnel_info(device_info, udid)

            return None

        except Exception as e:
            logger.debug(f"Tunneld query failed: {e}")
            return None

    def _extract_tunnel_info(self, device_info, udid: str) -> Optional[RSDTunnel]:
        """Extract tunnel info from device data."""
        # Handle list format: [{"tunnel-address": ..., "tunnel-port": ...}]
        if isinstance(device_info, list):
            if not device_info:
                return None
            device_info = device_info[0]

        if not isinstance(device_info, dict):
            return None

        # Try various key names
        address = (device_info.get('tunnel-address') or
                   device_info.get('address') or
                   device_info.get('tunnel_address') or
                   device_info.get('rsd_address'))
        port = (device_info.get('tunnel-port') or
                device_info.get('port') or
                device_info.get('tunnel_port') or
                device_info.get('rsd_port'))

        if address and port:
            return RSDTunnel(address=str(address), port=int(port), udid=udid)

        return None

    def _is_tunneld_running(self) -> bool:
        """Check if tunneld HTTP API is responding."""
        try:
            url = f"http://127.0.0.1:{TUNNELD_DEFAULT_PORT}/"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=1):
                return True
        except Exception:
            return False

    # =========================================================================
    # Start New Tunnel (requires admin)
    # =========================================================================

    async def _start_new_tunnel(self, udid: str) -> Optional[RSDTunnel]:
        """Start new tunnel - platform specific, may require admin."""
        if sys.platform == "darwin":
            return self._start_tunnel_macos(udid)
        elif sys.platform == "linux":
            return self._start_tunnel_linux(udid)
        else:
            self._last_error = f"Unsupported platform: {sys.platform}"
            return None

    def _start_tunnel_macos(self, udid: str) -> Optional[RSDTunnel]:
        """Start tunnel on macOS."""
        python_path = self._find_python_with_pymobiledevice3()
        logger.info(f"Using Python: {python_path}")

        # Check if tunneld is already running
        if self._is_tunneld_running():
            # Tunneld running but device not found - try direct tunnel
            logger.info("Tunneld running, trying direct lockdown tunnel...")
            return self._start_lockdown_tunnel_macos(python_path, udid)
        else:
            # Start tunneld daemon
            logger.info("Starting tunneld daemon...")
            tunnel = self._start_tunneld_macos(python_path, udid)
            if tunnel:
                return tunnel

            # Fallback to direct tunnel
            logger.info("Tunneld failed, trying direct lockdown tunnel...")
            return self._start_lockdown_tunnel_macos(python_path, udid)

    def _start_tunneld_macos(self, python_path: str, udid: str) -> Optional[RSDTunnel]:
        """Start tunneld daemon on macOS with admin privileges."""
        script = f'''
        do shell script "{python_path} -m pymobiledevice3 remote tunneld -d > /tmp/tunneld.log 2>&1 &" with administrator privileges
        '''

        try:
            logger.info("Requesting admin privileges for tunneld...")
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                stderr = result.stderr or result.stdout
                if "User canceled" in stderr:
                    self._last_error = "Admin authentication cancelled"
                    return None
                logger.warning(f"tunneld returned: {stderr}")

            # Wait for tunnel
            time.sleep(2)
            return self._wait_for_tunnel(max_wait=15, udid=udid)

        except subprocess.TimeoutExpired:
            self._last_error = "Timeout waiting for admin authentication"
            return None
        except Exception as e:
            self._last_error = str(e)
            return None

    def _start_lockdown_tunnel_macos(self, python_path: str, udid: str) -> Optional[RSDTunnel]:
        """Start direct lockdown tunnel on macOS."""
        udid_arg = f" --udid {udid}" if udid else ""
        script = f'''
        do shell script "{python_path} -m pymobiledevice3 lockdown start-tunnel{udid_arg} > /tmp/tunnel.log 2>&1 &" with administrator privileges
        '''

        try:
            logger.info(f"Requesting admin privileges for lockdown tunnel... (UDID: {udid[:8]})")
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                stderr = result.stderr or result.stdout
                if "User canceled" in stderr:
                    self._last_error = "Admin authentication cancelled"
                    return None

            time.sleep(3)

            # Try to parse from log file
            tunnel = self._parse_tunnel_from_log("/tmp/tunnel.log", udid)
            if tunnel:
                return tunnel

            # Try tunneld query
            return self._wait_for_tunnel(max_wait=5, udid=udid)

        except subprocess.TimeoutExpired:
            self._last_error = "Timeout waiting for admin authentication"
            return None
        except Exception as e:
            self._last_error = str(e)
            return None

    def _start_tunnel_linux(self, udid: str) -> Optional[RSDTunnel]:
        """Start tunnel on Linux using pkexec."""
        python_path = self._find_python_with_pymobiledevice3()

        try:
            subprocess.Popen(
                ["pkexec", python_path, "-m", "pymobiledevice3", "remote", "tunneld", "-d"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return self._wait_for_tunnel(max_wait=10, udid=udid)

        except Exception as e:
            self._last_error = str(e)
            return None

    # =========================================================================
    # Stop Tunnel
    # =========================================================================

    def _stop_tunnel_macos(self) -> None:
        """Stop tunnel processes on macOS."""
        for pattern in ["pymobiledevice3.*start-tunnel", "pymobiledevice3.*tunneld"]:
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True)
            except Exception:
                pass

        # Try with admin privileges
        script = '''
        do shell script "pkill -f 'pymobiledevice3.*tunneld' ; pkill -f 'pymobiledevice3.*start-tunnel' ; exit 0" with administrator privileges
        '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        except Exception:
            pass

    def _stop_tunnel_linux(self) -> None:
        """Stop tunnel processes on Linux."""
        for pattern in ["pymobiledevice3.*start-tunnel", "pymobiledevice3.*tunneld"]:
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True)
            except Exception:
                pass

    # =========================================================================
    # Helpers
    # =========================================================================

    def _wait_for_tunnel(self, max_wait: int = 10, udid: str = None) -> Optional[RSDTunnel]:
        """Poll for tunnel to become available."""
        logger.info(f"Waiting for tunnel (max {max_wait}s)...")

        for i in range(max_wait * 2):  # Poll every 0.5s
            time.sleep(0.5)

            tunnel = self._query_tunneld_http(udid)
            if tunnel:
                logger.info(f"Tunnel found after {(i + 1) * 0.5:.1f}s")
                return tunnel

        self._last_error = "Tunnel did not become available"
        return None

    def _parse_tunnel_from_log(self, log_path: str, udid: str) -> Optional[RSDTunnel]:
        """Parse tunnel info from log file."""
        try:
            if not os.path.exists(log_path):
                return None

            with open(log_path, 'r') as f:
                content = f.read()

            if not content:
                return None

            # Pattern: --rsd <address> <port>
            match = re.search(r'--rsd\s+([a-fA-F0-9:]+)\s+(\d+)', content)
            if match:
                return RSDTunnel(
                    address=match.group(1),
                    port=int(match.group(2)),
                    udid=udid
                )

            return None
        except Exception:
            return None

    def _find_python_with_pymobiledevice3(self) -> str:
        """Find Python installation with pymobiledevice3."""
        home = os.path.expanduser("~")
        candidates = [
            sys.executable,
            f"{home}/.asdf/shims/python3",
            f"{home}/.pyenv/shims/python3",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "python3",
        ]

        for path in candidates:
            if not path:
                continue
            if path != "python3" and not os.path.exists(path):
                continue
            try:
                result = subprocess.run(
                    [path, "-c", "import pymobiledevice3; print('ok')"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0 and 'ok' in result.stdout:
                    return path
            except Exception:
                continue

        return "python3"
