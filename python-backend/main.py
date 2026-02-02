#!/usr/bin/env python3
"""
Location Simulator Backend

A JSON-RPC server for iOS location simulation.
Supports two modes:
  - stdio mode (default): JSON-RPC over stdin/stdout for Electron
  - HTTP mode (--http): HTTP server for browser access

All coordinate calculations are handled by the frontend.
"""

import sys
import json
import asyncio
import logging
import argparse
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

        # Get fresh device state from DeviceManager (includes tunnel info)
        device = self.devices.get_device(self._selected_device.id)
        if not device:
            device = self._selected_device

        result = await self.location.set_location(
            device,
            float(latitude),
            float(longitude)
        )
        return result

    async def _clear_location(self, params: dict) -> dict:
        """Clear simulated location on selected device."""
        if not self._selected_device:
            return {"success": False, "error": "No device selected"}

        # Get fresh device state from DeviceManager (includes tunnel info)
        device = self.devices.get_device(self._selected_device.id)
        if not device:
            device = self._selected_device

        result = await self.location.clear_location(device)
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
            target_id = udid or (
                self._selected_device.id if self._selected_device else None)
            if target_id:
                self.devices.update_tunnel(target_id, tunnel)
                # Also update selected device if it's the same one
                if self._selected_device and self._selected_device.id == target_id:
                    self._selected_device.rsd_tunnel = tunnel
                    logger.info(
                        f"Updated selected device with tunnel: {tunnel.address}:{tunnel.port}")

        return result

    async def _stop_tunnel(self, params: dict) -> dict:
        """Stop RSD tunnel."""
        return await self.tunnel.stop_tunnel()

    async def _get_tunnel_status(self, params: dict) -> dict:
        """Get current tunnel status."""
        return self.tunnel.get_status()

    # =========================================================================
    # Main Loop (stdio mode)
    # =========================================================================

    async def run_stdio(self):
        """Main loop for stdio mode - read from stdin, process, write to stdout."""
        logger.info("=" * 60)
        logger.info("Backend started (stdio mode) - waiting for requests")
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
                logger.info(
                    f"[{self._request_count}] << {method} (id={request_id})")
                logger.debug(f"    Params: {request.get('params', {})}")

                # Process
                start = datetime.now()
                response = await self.handle_request(request)
                elapsed = (datetime.now() - start).total_seconds() * 1000

                # Log response
                if "error" in response:
                    logger.error(
                        f"[{self._request_count}] >> ERROR ({elapsed:.1f}ms): {response['error']}")
                else:
                    logger.info(
                        f"[{self._request_count}] >> OK ({elapsed:.1f}ms)")

                # Send response
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                logger.exception(f"Error: {e}")

        logger.info("Backend shutdown")

    # =========================================================================
    # HTTP Server Mode
    # =========================================================================

    async def run_http(self, host: str = "127.0.0.1", port: int = 8765):
        """Run as HTTP server for browser mode."""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            sys.exit(1)

        # CORS headers for all responses
        CORS_HEADERS = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Accept",
            "Access-Control-Max-Age": "3600",
        }

        @web.middleware
        async def cors_middleware(request: web.Request, handler):
            """Add CORS headers to all responses."""
            # Handle preflight requests
            if request.method == "OPTIONS":
                return web.Response(headers=CORS_HEADERS)

            # Handle actual requests
            try:
                response = await handler(request)
                response.headers.update(CORS_HEADERS)
                return response
            except web.HTTPException as e:
                e.headers.update(CORS_HEADERS)
                raise

        async def handle_rpc(request: web.Request) -> web.Response:
            """Handle JSON-RPC requests over HTTP POST."""
            try:
                body = await request.json()
                self._request_count += 1
                request_id = body.get("id", "?")
                method = body.get("method", "?")

                logger.info(
                    f"[{self._request_count}] << {method} (id={request_id})")
                logger.debug(f"    Params: {body.get('params', {})}")

                start = datetime.now()
                response = await self.handle_request(body)
                elapsed = (datetime.now() - start).total_seconds() * 1000

                if "error" in response:
                    logger.error(
                        f"[{self._request_count}] >> ERROR ({elapsed:.1f}ms): {response['error']}")
                else:
                    logger.info(
                        f"[{self._request_count}] >> OK ({elapsed:.1f}ms)")

                return web.json_response(response)
            except json.JSONDecodeError:
                return web.json_response(
                    {"error": {"code": -32700, "message": "Parse error"}},
                    status=400
                )
            except Exception as e:
                logger.exception(f"HTTP handler error: {e}")
                return web.json_response(
                    {"error": {"code": -1, "message": str(e)}},
                    status=500
                )

        async def handle_health(request: web.Request) -> web.Response:
            """Health check endpoint."""
            return web.json_response({"status": "ok", "mode": "http"})

        # Create app with CORS middleware
        app = web.Application(middlewares=[cors_middleware])
        app.router.add_route("*", "/rpc", handle_rpc)
        app.router.add_route("*", "/health", handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)

        logger.info("=" * 60)
        logger.info(f"Backend started (HTTP mode)")
        logger.info(f"Server running at http://{host}:{port}")
        logger.info(f"RPC endpoint: http://{host}:{port}/rpc")
        logger.info("=" * 60)

        await site.start()

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()
            logger.info("HTTP server shutdown")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description="Location Simulator Backend")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run as HTTP server (for browser mode)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP server host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP server port (default: 8765)"
    )
    args = parser.parse_args()

    server = LocationSimulatorServer()
    try:
        if args.http:
            asyncio.run(server.run_http(args.host, args.port))
        else:
            asyncio.run(server.run_stdio())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
