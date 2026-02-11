"""RSD tunnel management for iOS 17+ devices.

TunnelManager queries tunneld for tunnel connections.
It does NOT cache tunnel info - each get_tunnel() call queries tunneld fresh.
"""

import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from typing import Callable, Optional

from models import RSDTunnel, TunnelState, TunnelStatus

logger = logging.getLogger(__name__)

# Default tunneld port
TUNNELD_DEFAULT_PORT = 49151
TUNNELD_QUERY_TIMEOUT = 10  # seconds


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
        # Tunneld daemon state: "starting", "ready", or "error"
        self._tunneld_state: str = "starting"
        self._tunneld_error: Optional[str] = None
        # Event emitter callback for SSE (set by main.py)
        self._event_emitter: Optional[Callable[[dict], None]] = None

    def set_event_emitter(self, emitter: Callable[[dict], None]) -> None:
        """Set the event emitter callback for SSE events."""
        self._event_emitter = emitter

    def _emit_tunneld_status(self, state: str, error: str = None) -> None:
        """Emit tunneldStatus SSE event."""
        self._tunneld_state = state
        self._tunneld_error = error
        if self._event_emitter:
            event = {"event": "tunneldStatus", "data": {"state": state}}
            if error:
                event["data"]["error"] = error
            self._event_emitter(event)

    def ensure_tunneld(self) -> str:
        """Check if tunneld is running, start it if not.

        Returns the final state: "ready" or "error".
        Emits tunneldStatus SSE events for state transitions.
        """
        self._emit_tunneld_status("starting")

        if self._is_tunneld_running():
            logger.info("tunneld is already running")
            self._emit_tunneld_status("ready")
            return "ready"

        logger.info("tunneld is not running, attempting to start...")
        python_path = self._find_python_with_pymobiledevice3()

        if sys.platform == "darwin":
            result = self._start_tunneld_daemon_macos(python_path)
        elif sys.platform == "linux":
            result = self._start_tunneld_daemon_linux(python_path)
        elif sys.platform == "win32":
            result = self._start_tunneld_daemon_windows(python_path)
        else:
            self._emit_tunneld_status("error", f"Unsupported platform: {sys.platform}")
            return "error"

        if result:
            self._emit_tunneld_status("ready")
            return "ready"
        else:
            error_msg = self._last_error or "Failed to start tunneld"
            self._emit_tunneld_status("error", error_msg)
            return "error"

    def _start_tunneld_daemon_macos(self, python_path: str) -> bool:
        """Start tunneld daemon on macOS. Returns True on success."""
        script = f'''
        do shell script "{python_path} -m pymobiledevice3 remote tunneld -d > /tmp/tunneld.log 2>&1 &" with administrator privileges
        '''
        try:
            logger.info("Requesting admin privileges for tunneld...")
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                stderr = result.stderr or result.stdout
                if "User canceled" in stderr:
                    self._last_error = "Admin authentication cancelled"
                    return False
                logger.warning(f"tunneld returned: {stderr}")

            # Wait for tunneld to become responsive
            time.sleep(2)
            for _ in range(26):  # ~13 seconds
                if self._is_tunneld_running():
                    return True
                time.sleep(0.5)
            self._last_error = "Tunnel did not become available"
            return False
        except subprocess.TimeoutExpired:
            self._last_error = "Timeout waiting for admin authentication"
            return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def _start_tunneld_daemon_linux(self, python_path: str) -> bool:
        """Start tunneld daemon on Linux. Returns True on success."""
        try:
            subprocess.Popen(
                ["pkexec", python_path, "-m", "pymobiledevice3", "remote", "tunneld", "-d"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(2)
            for _ in range(16):  # ~8 seconds
                if self._is_tunneld_running():
                    return True
                time.sleep(0.5)
            self._last_error = "Tunnel did not become available"
            return False
        except Exception as e:
            self._last_error = str(e)
            return False

    def _start_tunneld_daemon_windows(self, python_path: str) -> bool:
        """Start tunneld daemon on Windows. Returns True on success.

        Attempts to launch with UAC elevation via ShellExecuteW (runas).
        Falls back to direct launch if already running as admin.
        """
        import ctypes

        tunneld_log = os.path.join(os.environ.get("TEMP", "."), "tunneld.log")
        args = f"-m pymobiledevice3 remote tunneld -d"

        try:
            # Check if already running as admin
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()

            if is_admin:
                # Already admin — launch directly
                logger.info("Running as admin, starting tunneld directly...")
                subprocess.Popen(
                    [python_path, "-m", "pymobiledevice3", "remote", "tunneld", "-d"],
                    stdout=open(tunneld_log, "w"),
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Request UAC elevation
                logger.info("Requesting admin privileges for tunneld via UAC...")
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", python_path, args, None, 0  # SW_HIDE
                )
                if ret <= 32:
                    self._last_error = "UAC elevation was denied or failed"
                    return False

            # Wait for tunneld to become responsive
            time.sleep(2)
            for _ in range(26):  # ~13 seconds
                if self._is_tunneld_running():
                    return True
                time.sleep(0.5)
            self._last_error = "Tunnel did not become available"
            return False
        except Exception as e:
            self._last_error = str(e)
            return False

    # =========================================================================
    # Public API
    # =========================================================================

    def get_tunnel(self, udid: str) -> Optional[RSDTunnel]:
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

            with urllib.request.urlopen(req, timeout=TUNNELD_QUERY_TIMEOUT) as response:
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
        # Handle list format: [{"tunnel-address": ..., "tunnel-port": ...}]``
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
        """Check if tunneld process is running.

        First tries querying the tunneld HTTP API (cross-platform).
        Falls back to platform-specific process checks.
        """
        # Fast path: try HTTP API (works on all platforms)
        try:
            url = f"http://127.0.0.1:{TUNNELD_DEFAULT_PORT}/"
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=TUNNELD_QUERY_TIMEOUT) as response:
                response.read()
            return True
        except Exception:
            pass

        # Fallback: platform-specific process check
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return "tunneld" in result.stdout
            else:
                result = subprocess.run(
                    ["pgrep", "-f", "pymobiledevice3.*tunneld"],
                    capture_output=True, text=True, timeout=5
                )
                return result.returncode == 0
        except Exception:
            return False

    # =========================================================================
    # Helpers
    # =========================================================================

    def _find_python_with_pymobiledevice3(self) -> str:
        """Find Python installation with pymobiledevice3."""
        home = os.path.expanduser("~")

        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            candidates = [
                sys.executable,
                os.path.join(local_app_data, "Programs", "Python", "Python313", "python.exe"),
                os.path.join(local_app_data, "Programs", "Python", "Python312", "python.exe"),
                os.path.join(local_app_data, "Programs", "Python", "Python311", "python.exe"),
                f"{home}\\.pyenv\\pyenv-win\\shims\\python",
                "python",
            ]
            fallback = "python"
        else:
            candidates = [
                sys.executable,
                f"{home}/.asdf/shims/python3",
                f"{home}/.pyenv/shims/python3",
                "/opt/homebrew/bin/python3",
                "/usr/local/bin/python3",
                "python3",
            ]
            fallback = "python3"

        for path in candidates:
            if not path:
                continue
            if path not in (fallback,) and not os.path.exists(path):
                continue
            try:
                kwargs = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                result = subprocess.run(
                    [path, "-c", "import pymobiledevice3; print('ok')"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    **kwargs
                )
                if result.returncode == 0 and 'ok' in result.stdout:
                    return path
            except Exception:
                continue

        return fallback
