#!/usr/bin/env python3
"""
Location Simulator Backend

A simple JSON-RPC server over stdin/stdout for iOS location simulation.
All coordinate calculations are handled by the frontend.
"""

import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Optional

from models import Device
from services import DeviceManager, LocationService, TunnelManager

# Configure logging to stderr (stdout is for JSON-RPC communication)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr
)

logger = logging.getLogger('Backend')


class LocationSimulatorServer:
    """
    JSON-RPC server for location simulation.

    Handles device discovery, tunnel management, and location injection.
    All coordinate calculations (joystick, cruise) are done by the frontend.
    """

    def __init__(self):
        # Services
        self.devices = DeviceManager()
        self.location = LocationService()
        self.tunnel = TunnelManager()

        # State
        self._selected_device: Optional[Device] = None
        self._request_count = 0

        # Method registry
        self._methods = {
            "listDevices": self._list_devices,
            "selectDevice": self._select_device,
            "setLocation": self._set_location,
            "clearLocation": self._clear_location,
            "startTunnel": self._start_tunnel,
            "stopTunnel": self._stop_tunnel,
            "getTunnelStatus": self._get_tunnel_status,
        }

        logger.info("Location Simulator Backend initialized")

    # =========================================================================
    # JSON-RPC Handler
    # =========================================================================

    async def handle_request(self, request: dict) -> dict:
        """Handle a single JSON-RPC request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method not in self._methods:
            return {
                "id": request_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        try:
            result = await self._methods[method](params)
            return {"id": request_id, "result": result}
        except Exception as e:
            logger.exception(f"Error handling {method}: {e}")
            return {
                "id": request_id,
                "error": {"code": -1, "message": str(e)}
            }

    # =========================================================================
    # RPC Methods
    # =========================================================================

    async def _list_devices(self, params: dict) -> dict:
        """List all connected devices."""
        devices = await self.devices.list_devices()
        return {"devices": [d.to_dict() for d in devices]}

    async def _select_device(self, params: dict) -> dict:
        """Select a device for location simulation."""
        device_id = params.get("deviceId")
        if not device_id:
            return {"success": False, "error": "deviceId required"}

        device = self.devices.get_device(device_id)
        if not device:
            return {"success": False, "error": f"Device not found: {device_id}"}

        self._selected_device = device
        return {"success": True, "device": device.to_dict()}

    async def _set_location(self, params: dict) -> dict:
        """Set location on selected device."""
        if not self._selected_device:
            return {"success": False, "error": "No device selected"}

        latitude = params.get("latitude")
        longitude = params.get("longitude")

        if latitude is None or longitude is None:
            return {"success": False, "error": "latitude and longitude required"}

        result = await self.location.set_location(
            self._selected_device,
            float(latitude),
            float(longitude)
        )
        return result

    async def _clear_location(self, params: dict) -> dict:
        """Clear simulated location on selected device."""
        if not self._selected_device:
            return {"success": False, "error": "No device selected"}

        result = await self.location.clear_location(self._selected_device)
        return result

    async def _start_tunnel(self, params: dict) -> dict:
        """Start RSD tunnel for iOS 17+ devices."""
        udid = params.get("udid")
        result = await self.tunnel.start_tunnel(udid)

        # Update device with tunnel info on success
        if result.get("success") and result.get("address"):
            from models import RSDTunnel
            tunnel = RSDTunnel(
                address=result["address"],
                port=result["port"],
                udid=result.get("udid")
            )
            # Update specified device or selected device
            target_id = udid or (self._selected_device.id if self._selected_device else None)
            if target_id:
                self.devices.update_tunnel(target_id, tunnel)

        return result

    async def _stop_tunnel(self, params: dict) -> dict:
        """Stop RSD tunnel."""
        return await self.tunnel.stop_tunnel()

    async def _get_tunnel_status(self, params: dict) -> dict:
        """Get current tunnel status."""
        return self.tunnel.get_status()

    # =========================================================================
    # Main Loop
    # =========================================================================

    async def run(self):
        """Main loop - read from stdin, process, write to stdout."""
        logger.info("=" * 60)
        logger.info("Backend started - waiting for requests")
        logger.info("=" * 60)

        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    logger.info("EOF received - frontend closed")
                    break

                line_str = line.decode().strip()
                if not line_str:
                    continue

                # Parse request
                request = json.loads(line_str)
                self._request_count += 1
                request_id = request.get("id", "?")
                method = request.get("method", "?")

                # Log request
                logger.info(f"[{self._request_count}] << {method} (id={request_id})")
                logger.debug(f"    Params: {request.get('params', {})}")

                # Process
                start = datetime.now()
                response = await self.handle_request(request)
                elapsed = (datetime.now() - start).total_seconds() * 1000

                # Log response
                if "error" in response:
                    logger.error(f"[{self._request_count}] >> ERROR ({elapsed:.1f}ms): {response['error']}")
                else:
                    logger.info(f"[{self._request_count}] >> OK ({elapsed:.1f}ms)")

                # Send response
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                logger.exception(f"Error: {e}")

        logger.info("Backend shutdown")


def main():
    """Entry point."""
    server = LocationSimulatorServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
