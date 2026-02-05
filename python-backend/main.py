#!/usr/bin/env python3
"""
Location Simulator Backend

A JSON-RPC server for iOS location simulation.
Runs as HTTP server with SSE support for real-time events.

Endpoints:
  - POST /rpc     - JSON-RPC requests
  - GET  /events  - Server-Sent Events stream
  - GET  /health  - Health check

All coordinate calculations are handled by the frontend.
"""

import sys
import json
import asyncio
import logging
import argparse
from datetime import datetime
from typing import Optional

from models import Device, DeviceType
from services import DeviceManager, LocationService, TunnelManager, FavoritesService, CruiseService, LastLocationService, event_bus

# Configure logging to stderr
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
    Events are published via SSE for real-time updates to all connected clients.
    """

    def __init__(self):
        # Services
        self.devices = DeviceManager()
        self.tunnel = TunnelManager()
        self.location = LocationService()
        self.favorites = FavoritesService()
        self.cruise = CruiseService()
        self.last_locations = LastLocationService()

        # Wire up tunnel provider for retry mechanism
        # This allows LocationService to get fresh tunnel info on connection errors
        self.location.set_tunnel_provider(self._get_tunnel_for_device)

        # Wire up cruise service callbacks
        self.cruise.set_location_callback(self._set_location_for_cruise)
        self.cruise.set_event_emitter(self._emit_event)

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
            # Favorites
            "getFavorites": self._get_favorites,
            "addFavorite": self._add_favorite,
            "updateFavorite": self._update_favorite,
            "deleteFavorite": self._delete_favorite,
            "importFavorites": self._import_favorites,
            # Cruise
            "startCruise": self._start_cruise,
            "stopCruise": self._stop_cruise,
            "pauseCruise": self._pause_cruise,
            "resumeCruise": self._resume_cruise,
            "setCruiseSpeed": self._set_cruise_speed,
            "getCruiseStatus": self._get_cruise_status,
            # Last Location
            "getLastLocation": self._get_last_location,
        }

        logger.info("Location Simulator Backend initialized")

    async def _get_tunnel_for_device(self, udid: str):
        """Tunnel provider callback for LocationService retry mechanism.

        Queries tunneld for fresh tunnel info.
        """
        return await self.tunnel.get_tunnel(udid)

    def _emit_event(self, event: dict) -> None:
        """Emit an event to all SSE subscribers.

        Events are JSON objects with 'event' and 'data' keys.
        Used by CruiseService to send position updates.
        """
        event_bus.publish_sync(event)

    async def _set_location_for_cruise(
        self,
        device_id: str,
        latitude: float,
        longitude: float
    ) -> dict:
        """Set location callback for CruiseService.

        This is called by the cruise loop to update device location.
        """
        device = self.devices.get_device(device_id)
        if not device:
            device = self._selected_device
        if not device:
            return {"success": False, "error": "Device not found"}

        # For physical devices, get tunnel from TunnelManager
        tunnel = None
        if device.type == DeviceType.PHYSICAL:
            tunnel = await self.tunnel.get_tunnel(device.id)

        result = await self.location.set_location(
            device,
            latitude,
            longitude,
            tunnel=tunnel
        )

        # If tunnel was used but failed, invalidate it for refresh on next try
        if tunnel and not result.get("success"):
            self.tunnel.invalidate(device.id)

        # Persist last location on success
        if result.get("success"):
            self.last_locations.update(device.id, latitude, longitude)

        return result

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
        """Set location on selected device.

        Accepts either deviceId parameter or uses selected device.
        """
        # Get device from params or fallback to selected device
        device_id = params.get("deviceId")
        if device_id:
            device = self.devices.get_device(device_id)
            if not device:
                return {"success": False, "error": f"Device not found: {device_id}"}
        elif self._selected_device:
            device = self.devices.get_device(self._selected_device.id)
            if not device:
                device = self._selected_device
        else:
            return {"success": False, "error": "No device selected"}

        latitude = params.get("latitude")
        longitude = params.get("longitude")

        if latitude is None or longitude is None:
            return {"success": False, "error": "latitude and longitude required"}

        # For physical devices, get tunnel from TunnelManager
        tunnel = None
        if device.type == DeviceType.PHYSICAL:
            tunnel = await self.tunnel.get_tunnel(device.id)

        result = await self.location.set_location(
            device,
            float(latitude),
            float(longitude),
            tunnel=tunnel
        )

        # If tunnel was used but failed, invalidate it for refresh on next try
        if tunnel and not result.get("success"):
            self.tunnel.invalidate(device.id)

        # Persist last location on success
        if result.get("success"):
            self.last_locations.update(device.id, float(latitude), float(longitude))

        return result

    async def _clear_location(self, params: dict) -> dict:
        """Clear simulated location on selected device.

        Accepts either deviceId parameter or uses selected device.
        """
        # Get device from params or fallback to selected device
        device_id = params.get("deviceId")
        if device_id:
            device = self.devices.get_device(device_id)
            if not device:
                return {"success": False, "error": f"Device not found: {device_id}"}
        elif self._selected_device:
            device = self.devices.get_device(self._selected_device.id)
            if not device:
                device = self._selected_device
        else:
            return {"success": False, "error": "No device selected"}

        # For physical devices, get tunnel from TunnelManager
        tunnel = None
        if device.type == DeviceType.PHYSICAL:
            tunnel = await self.tunnel.get_tunnel(device.id)

        result = await self.location.clear_location(device, tunnel=tunnel)

        # If tunnel was used but failed, invalidate it for refresh on next try
        if tunnel and not result.get("success"):
            self.tunnel.invalidate(device.id)

        return result

    async def _start_tunnel(self, params: dict) -> dict:
        """Start RSD tunnel for iOS 17+ devices."""
        # Get UDID from params or selected device
        udid = params.get("udid")
        if not udid and self._selected_device:
            udid = self._selected_device.id

        if not udid:
            return {"success": False, "error": "No device specified. Select a device first."}

        result = await self.tunnel.start_tunnel(udid)

        # Update device with tunnel info on success
        if result.get("success") and result.get("address"):
            from models import RSDTunnel
            tunnel = RSDTunnel(
                address=result["address"],
                port=result["port"],
                udid=udid
            )
            self.devices.update_tunnel(udid, tunnel)
            # Also update selected device if it's the same one
            if self._selected_device and self._selected_device.id == udid:
                self._selected_device.rsd_tunnel = tunnel
                logger.info(f"Updated selected device with tunnel: {tunnel.address}:{tunnel.port}")

        return result

    async def _stop_tunnel(self, params: dict) -> dict:
        """Stop RSD tunnel for device or all tunnels."""
        udid = params.get("udid")
        # If no UDID specified and we have a selected device, use that
        if not udid and self._selected_device:
            udid = self._selected_device.id
        return await self.tunnel.stop_tunnel(udid)

    async def _get_tunnel_status(self, params: dict) -> dict:
        """Get current tunnel status."""
        udid = params.get("udid")
        # If no UDID specified and we have a selected device, use that
        if not udid and self._selected_device:
            udid = self._selected_device.id
        return self.tunnel.get_status(udid)

    # =========================================================================
    # Favorites Operations
    # =========================================================================

    async def _get_favorites(self, params: dict) -> dict:
        """Get all favorite locations."""
        favorites = self.favorites.get_all()
        return {"favorites": [f.to_dict() for f in favorites]}

    async def _add_favorite(self, params: dict) -> dict:
        """Add a new favorite location."""
        latitude = params.get("latitude")
        longitude = params.get("longitude")
        name = params.get("name", "")

        if latitude is None or longitude is None:
            return {"success": False, "error": "latitude and longitude required"}

        return self.favorites.add(float(latitude), float(longitude), name)

    async def _update_favorite(self, params: dict) -> dict:
        """Update (rename) a favorite location."""
        index = params.get("index")
        name = params.get("name")

        if index is None:
            return {"success": False, "error": "index required"}
        if name is None:
            return {"success": False, "error": "name required"}

        return self.favorites.update(int(index), name)

    async def _delete_favorite(self, params: dict) -> dict:
        """Delete a favorite location."""
        index = params.get("index")

        if index is None:
            return {"success": False, "error": "index required"}

        return self.favorites.delete(int(index))

    async def _import_favorites(self, params: dict) -> dict:
        """Import favorites from a file."""
        file_path = params.get("filePath")

        if not file_path:
            return {"success": False, "error": "filePath required"}

        return self.favorites.import_from_file(file_path)

    # =========================================================================
    # Cruise Operations
    # =========================================================================

    async def _start_cruise(self, params: dict) -> dict:
        """Start cruise mode towards a target location."""
        # Get device ID from params or selected device
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        # Get coordinates
        start_lat = params.get("startLatitude")
        start_lon = params.get("startLongitude")
        target_lat = params.get("targetLatitude")
        target_lon = params.get("targetLongitude")
        speed = params.get("speedKmh", 5.0)

        if None in (start_lat, start_lon, target_lat, target_lon):
            return {"success": False, "error": "Start and target coordinates required"}

        return await self.cruise.start_cruise(
            device_id=device_id,
            start_lat=float(start_lat),
            start_lon=float(start_lon),
            target_lat=float(target_lat),
            target_lon=float(target_lon),
            speed_kmh=float(speed)
        )

    async def _stop_cruise(self, params: dict) -> dict:
        """Stop cruise mode."""
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        return await self.cruise.stop_cruise(device_id)

    async def _pause_cruise(self, params: dict) -> dict:
        """Pause cruise mode."""
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        return await self.cruise.pause_cruise(device_id)

    async def _resume_cruise(self, params: dict) -> dict:
        """Resume paused cruise mode."""
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        return await self.cruise.resume_cruise(device_id)

    async def _set_cruise_speed(self, params: dict) -> dict:
        """Set cruise speed."""
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        speed = params.get("speedKmh")
        if speed is None:
            return {"success": False, "error": "speedKmh required"}

        return self.cruise.set_cruise_speed(device_id, float(speed))

    async def _get_cruise_status(self, params: dict) -> dict:
        """Get cruise status for a device."""
        device_id = params.get("deviceId")
        if not device_id and self._selected_device:
            device_id = self._selected_device.id

        if not device_id:
            return {"success": False, "error": "No device specified"}

        return self.cruise.get_cruise_status(device_id)

    # =========================================================================
    # Last Location Operations
    # =========================================================================

    async def _get_last_location(self, params: dict) -> dict:
        """Get the last set location for a device."""
        device_id = params.get("deviceId")
        if not device_id:
            return {"success": False, "error": "deviceId required"}

        location = self.last_locations.get(device_id)
        if location:
            return {
                "success": True,
                "latitude": location["lat"],
                "longitude": location["lon"],
            }
        return {"success": False, "error": "No last location for this device"}

    # =========================================================================
    # HTTP Server
    # =========================================================================

    async def run_http(self, host: str = "127.0.0.1", port: int = 8765):
        """Run HTTP server with SSE support.
        
        Endpoints:
          - POST /rpc     - JSON-RPC requests
          - GET  /events  - Server-Sent Events stream
          - GET  /health  - Health check
        """
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

        async def handle_events(request: web.Request) -> web.StreamResponse:
            """Handle Server-Sent Events (SSE) for real-time updates.
            
            Clients connect here to receive events like:
              - cruiseUpdate
              - cruiseStarted
              - cruiseStopped
              - cruiseArrived
              - cruisePaused
              - cruiseResumed
              - cruiseError
            """
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'text/event-stream',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Access-Control-Allow-Origin': '*',
                }
            )
            await response.prepare(request)
            
            logger.info("SSE client connecting...")
            
            try:
                # Send initial connection event
                await response.write(
                    f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n".encode()
                )
                
                # Subscribe to event bus and stream events
                async for event in event_bus.subscribe():
                    if event is None:
                        # Shutdown signal
                        break
                    
                    # Format as SSE: event: <name>\ndata: <json>\n\n
                    event_name = event.get("event", "message")
                    event_data = json.dumps(event)
                    sse_message = f"event: {event_name}\ndata: {event_data}\n\n"
                    
                    await response.write(sse_message.encode())
                    
            except asyncio.CancelledError:
                logger.debug("SSE connection cancelled")
            except ConnectionResetError:
                logger.debug("SSE client disconnected")
            except Exception as e:
                logger.error(f"SSE error: {e}")
            
            return response

        async def handle_health(request: web.Request) -> web.Response:
            """Health check endpoint."""
            return web.json_response({
                "status": "ok",
                "mode": "http",
                "subscribers": event_bus.subscriber_count
            })

        # Create app with CORS middleware
        app = web.Application(middlewares=[cors_middleware])
        app.router.add_route("POST", "/rpc", handle_rpc)
        app.router.add_route("OPTIONS", "/rpc", handle_rpc)  # CORS preflight
        app.router.add_route("GET", "/events", handle_events)
        app.router.add_route("GET", "/health", handle_health)
        app.router.add_route("OPTIONS", "/health", handle_health)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)

        logger.info("=" * 60)
        logger.info(f"Backend started (HTTP mode with SSE)")
        logger.info(f"Server running at http://{host}:{port}")
        logger.info(f"Endpoints:")
        logger.info(f"  POST /rpc     - JSON-RPC requests")
        logger.info(f"  GET  /events  - Server-Sent Events stream")
        logger.info(f"  GET  /health  - Health check")
        logger.info("=" * 60)

        await site.start()

        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await event_bus.close()
            await self.cruise.stop_all()
            await self.location.close_all_connections()
            await runner.cleanup()
            logger.info("HTTP server shutdown")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description="Location Simulator Backend")
    parser.add_argument(
        "--http",
        action="store_true",
        default=True,  # HTTP is now the default
        help="Run as HTTP server (default)"
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
        asyncio.run(server.run_http(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
