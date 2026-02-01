"""RSD tunnel management for iOS 17+ devices."""

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from typing import Optional

from models import RSDTunnel

logger = logging.getLogger(__name__)

# Default tunneld port
TUNNELD_DEFAULT_PORT = 49151


class TunnelManager:
    """Manages pymobiledevice3 lockdown tunnel for iOS 17+ devices."""

    def __init__(self):
        self._tunnel_info: Optional[RSDTunnel] = None
        self._is_running = False
        self._status_message = "Not started"
        self._last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def tunnel_info(self) -> Optional[RSDTunnel]:
        return self._tunnel_info

    def get_status(self) -> dict:
        """Get current tunnel status."""
        return {
            "running": self._is_running,
            "address": self._tunnel_info.address if self._tunnel_info else None,
            "port": self._tunnel_info.port if self._tunnel_info else None,
            "udid": self._tunnel_info.udid if self._tunnel_info else None,
            "message": self._status_message
        }

    async def start_tunnel(self, udid: Optional[str] = None) -> dict:
        """Start the lockdown tunnel."""
        logger.info("=" * 50)
        logger.info(f"Starting tunnel...{f' (UDID: {udid})' if udid else ''}")
        logger.info("=" * 50)

        # Return existing tunnel if running
        if self._is_running and self._tunnel_info:
            logger.info(f"Tunnel already running: {self._tunnel_info.address}:{self._tunnel_info.port}")
            return {
                "success": True,
                "address": self._tunnel_info.address,
                "port": self._tunnel_info.port,
                "udid": self._tunnel_info.udid
            }

        self._status_message = "Starting tunnel..."
        self._last_error = None

        # Step 1: Check for existing tunnel
        logger.info("Checking for existing tunnel...")
        tunnel = self._find_existing_tunnel(udid)
        if tunnel:
            logger.info(f"Found existing tunnel: {tunnel.address}:{tunnel.port}")
            return {
                "success": True,
                "address": tunnel.address,
                "port": tunnel.port,
                "udid": tunnel.udid
            }

        # Step 2: Start new tunnel
        logger.info("No existing tunnel found, starting new tunnel...")
        if sys.platform == "darwin":
            tunnel = self._start_tunnel_macos(udid)
        elif sys.platform == "linux":
            tunnel = self._start_tunnel_linux(udid)
        else:
            self._last_error = f"Unsupported platform: {sys.platform}"
            return {"success": False, "error": self._last_error}

        if tunnel:
            logger.info(f"SUCCESS: Tunnel started: {tunnel.address}:{tunnel.port}")
            return {
                "success": True,
                "address": tunnel.address,
                "port": tunnel.port,
                "udid": tunnel.udid
            }
        else:
            logger.error(f"FAILED: {self._last_error}")
            return {"success": False, "error": self._last_error or "Unknown error"}

    async def stop_tunnel(self) -> dict:
        """Stop the running tunnel."""
        logger.info("Stopping tunnel...")

        if sys.platform == "darwin":
            self._stop_tunnel_macos()
        elif sys.platform == "linux":
            self._stop_tunnel_linux()

        self._is_running = False
        self._tunnel_info = None
        self._status_message = "Stopped"
        logger.info("Tunnel stopped")

        return {"success": True}

    # =========================================================================
    # Tunnel Discovery
    # =========================================================================

    def _find_existing_tunnel(self, udid: Optional[str] = None) -> Optional[RSDTunnel]:
        """Check if a tunnel already exists."""
        tunnel = self._query_tunneld_http(udid)
        if tunnel:
            return tunnel

        tunnel = self._query_tunneld_api(udid)
        if tunnel:
            return tunnel

        return None

    def _query_tunneld_http(self, udid: Optional[str] = None) -> Optional[RSDTunnel]:
        """Query tunneld via HTTP API."""
        try:
            url = f"http://127.0.0.1:{TUNNELD_DEFAULT_PORT}/"
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')

            with urllib.request.urlopen(req, timeout=2) as response:
                response_text = response.read().decode('utf-8')

            data = json.loads(response_text)

            if not isinstance(data, dict) or len(data) == 0:
                logger.debug("Tunneld running but no devices")
                return None

            # Find matching device
            if udid and udid in data:
                return self._extract_tunnel_info(data[udid], udid)

            # Return first available
            for device_udid, device_info in data.items():
                if udid and device_udid != udid:
                    continue
                tunnel = self._extract_tunnel_info(device_info, device_udid)
                if tunnel:
                    return tunnel

            return None

        except Exception as e:
            logger.debug(f"Tunneld HTTP not available: {e}")
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
            tunnel = RSDTunnel(address=str(address), port=int(port), udid=udid)
            self._tunnel_info = tunnel
            self._is_running = True
            self._status_message = f"Running: {tunnel.address}:{tunnel.port}"
            logger.info(f"Found tunnel: {tunnel.address}:{tunnel.port} (UDID: {udid})")
            return tunnel

        return None

    def _query_tunneld_api(self, udid: Optional[str] = None) -> Optional[RSDTunnel]:
        """Query tunneld via pymobiledevice3 API."""
        try:
            from pymobiledevice3.tunneld import async_get_tunneld_devices

            # Run the async function in a new event loop
            # (we might be called from sync context)
            try:
                loop = asyncio.get_running_loop()
                # Already in async context - skip this method, HTTP API should work
                logger.debug("Skipping tunneld API (already in async context)")
                return None
            except RuntimeError:
                # No running loop - safe to use asyncio.run()
                devices = asyncio.run(async_get_tunneld_devices())

            if not devices:
                return None

            for device in devices:
                device_udid = getattr(device, 'udid', None)
                if udid and device_udid != udid:
                    continue

                tunnel = RSDTunnel(
                    address=str(device.address),
                    port=device.port,
                    udid=device_udid or udid
                )
                self._tunnel_info = tunnel
                self._is_running = True
                self._status_message = f"Running: {tunnel.address}:{tunnel.port}"
                return tunnel

            return None

        except ImportError:
            logger.debug("tunneld API not available")
            return None
        except Exception as e:
            logger.debug(f"tunneld API error: {e}")
            return None

    # =========================================================================
    # macOS Tunnel Start/Stop
    # =========================================================================

    def _start_tunnel_macos(self, udid: Optional[str] = None) -> Optional[RSDTunnel]:
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

    def _is_tunneld_running(self) -> bool:
        """Check if tunneld HTTP API is responding."""
        try:
            url = f"http://127.0.0.1:{TUNNELD_DEFAULT_PORT}/"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=1) as response:
                return True
        except Exception:
            return False

    def _start_tunneld_macos(self, python_path: str, udid: Optional[str] = None) -> Optional[RSDTunnel]:
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

    def _start_lockdown_tunnel_macos(self, python_path: str, udid: Optional[str] = None) -> Optional[RSDTunnel]:
        """Start direct lockdown tunnel on macOS."""
        udid_arg = f" --udid {udid}" if udid else ""
        script = f'''
        do shell script "{python_path} -m pymobiledevice3 lockdown start-tunnel{udid_arg} > /tmp/tunnel.log 2>&1 &" with administrator privileges
        '''

        try:
            logger.info(f"Requesting admin privileges for lockdown tunnel...{f' (UDID: {udid})' if udid else ''}")
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

    # =========================================================================
    # Linux Tunnel Start/Stop
    # =========================================================================

    def _start_tunnel_linux(self, udid: Optional[str] = None) -> Optional[RSDTunnel]:
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

    def _wait_for_tunnel(self, max_wait: int = 10, udid: Optional[str] = None) -> Optional[RSDTunnel]:
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

    def _parse_tunnel_from_log(self, log_path: str, udid: Optional[str] = None) -> Optional[RSDTunnel]:
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
                tunnel = RSDTunnel(
                    address=match.group(1),
                    port=int(match.group(2)),
                    udid=udid
                )
                self._tunnel_info = tunnel
                self._is_running = True
                self._status_message = f"Running: {tunnel.address}:{tunnel.port}"
                return tunnel

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
