## Why

The backend is fully asyncio-based but almost none of the services perform actual async I/O. The cruise loop (`CruiseService._cruise_loop`) runs as an `asyncio.Task` and on every tick (5-10x/sec) awaits `_set_location_for_cruise`, which awaits `tunnel.get_tunnel()` (a sync `urllib` HTTP call wrapped in async) and `location.set_location()` (sync pymobiledevice3 calls wrapped in async). When the tunneld HTTP query times out (2s), it blocks the entire asyncio event loop, freezing cruise movement and all other request handling. The asyncio overhead adds complexity without benefit — services like `TunnelManager`, `LocationService`, `CruiseService`, `RouteService`, `DeviceManager`, `FavoritesService`, and `LastLocationService` are all fundamentally synchronous.

## What Changes

- **BREAKING** Convert `CruiseService` from `asyncio.Task` to `threading.Thread` for the cruise loop. Sleep and location calls become direct synchronous calls, eliminating event loop blocking.
- **BREAKING** Convert `RouteService` to use threading-compatible calls instead of async/await. It remains a sequencer that delegates to `CruiseService`.
- **BREAKING** Convert `LocationService` from asyncio-based connection management to threading-based. Replace `asyncio.Task` refresh loops with `threading.Thread`. Use `threading.Lock` for connection dict access.
- **BREAKING** Convert `TunnelManager` from async to fully synchronous. It already uses sync `urllib` — just remove the `async` wrappers.
- **BREAKING** Convert `DeviceManager.list_devices()` from async to sync. It uses `subprocess.run` which is already blocking.
- Cache tunnel info in `_set_location_for_cruise` instead of querying tunneld on every cruise tick. Only re-query on connection error.
- Debounce `LastLocationService` saves — write to disk at most once every 5 seconds instead of on every cruise tick.
- Keep asyncio **only** where external packages require it: `aiohttp` web server (HTTP + SSE), `aiohttp.ClientSession` in `BrouterService`, `asyncio.start_server` in `PortForwardService`.
- Bridge async↔sync at the `main.py` boundary: aiohttp handlers call sync service methods via `loop.run_in_executor()` for potentially blocking operations, or directly for fast operations.
- Remove async from RPC handler methods that never actually await anything (favorites, status getters, etc.).

## Capabilities

### New Capabilities
- `threading-services`: Core service layer using threads instead of asyncio — covers CruiseService, RouteService, LocationService, TunnelManager, DeviceManager threading model, synchronization primitives, and thread lifecycle management.
- `tunnel-caching`: Tunnel info caching in the cruise hot path — cache last-good tunnel per device, skip redundant tunneld queries during active cruise, invalidate on connection error.
- `debounced-persistence`: Debounced disk writes for LastLocationService — dirty flag + periodic flush instead of write-per-tick.

### Modified Capabilities
_(No existing specs to modify — this is the first set of specs.)_

## Impact

- **Backend services** (`python-backend/services/`): All 9 service files change. `cruise_service.py`, `route_service.py`, `location_service.py`, `tunnel_manager.py`, `device_manager.py` lose async/await. `event_bus.py`, `brouter_service.py`, `port_forward_service.py` keep asyncio.
- **Server entry point** (`python-backend/main.py`): RPC handlers become sync where possible, with `run_in_executor` bridge for blocking calls. `_set_location_for_cruise` callback becomes sync with tunnel caching.
- **Tests** (`python-backend/tests/`, `python-backend/test_*.py`): All async test methods need conversion to sync or updated mocks. `pytest-asyncio` usage reduced.
- **No frontend changes** — the JSON-RPC/SSE interface is unchanged.
- **No dependency changes** — `aiohttp` stays for the web server; no new packages needed.
- **Thread safety** — services that were previously safe by asyncio's single-threaded model now need explicit locks for shared state (`_sessions`, `_tunnel_connections`, etc.).
