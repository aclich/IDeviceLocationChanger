## ADDED Requirements

### Requirement: CruiseService runs cruise loops in daemon threads
CruiseService SHALL run each per-device cruise loop in a `threading.Thread` (daemon=True) instead of an `asyncio.Task`. The thread SHALL use `threading.Event.wait(interval)` for sleep and `threading.Event` for stop signaling.

#### Scenario: Cruise loop runs independently of asyncio event loop
- **WHEN** a cruise is started for a device
- **THEN** a daemon `threading.Thread` is created and started for that device's cruise loop
- **AND** the thread uses `threading.Event.wait(interval)` instead of `asyncio.sleep`

#### Scenario: Cruise stop signals the thread via Event
- **WHEN** `stop_cruise` is called for a device
- **THEN** the session's `threading.Event` is set
- **AND** `thread.join(timeout=2)` is called to wait for thread exit
- **AND** the session is removed from `_sessions`

#### Scenario: Cruise pause skips ticks without stopping thread
- **WHEN** a cruise is paused
- **THEN** the cruise thread continues running but skips location updates when `session.state == PAUSED`
- **AND** the thread resumes updates when `session.state` returns to `RUNNING`

#### Scenario: Blocking tunneld timeout does not freeze other services
- **WHEN** the tunneld HTTP query times out (2 seconds) during a cruise tick
- **THEN** only the cruise thread for that device is blocked
- **AND** the aiohttp event loop continues to serve RPC requests and SSE events without delay

### Requirement: CruiseService set_location callback is synchronous
CruiseService SHALL accept a synchronous location setter callback with signature `Callable[[str, float, float], dict]`. The callback SHALL NOT be async/awaitable.

#### Scenario: Sync callback type
- **WHEN** `set_location_callback` is called during initialization
- **THEN** the callback stored SHALL have the type `Callable[[str, float, float], dict]` (not `Awaitable`)

#### Scenario: Cruise loop calls callback directly
- **WHEN** the cruise loop computes a new position
- **THEN** it calls `self._set_location(device_id, lat, lon)` directly as a synchronous function call
- **AND** no `await` or executor is used

### Requirement: CruiseService protects shared state with threading.Lock
CruiseService SHALL use a `threading.Lock` to protect the `_sessions` dictionary, since cruise threads write session state while RPC handlers read status or stop sessions concurrently.

#### Scenario: Concurrent session read from RPC handler
- **WHEN** an RPC handler calls `get_cruise_status` while a cruise thread is updating session state
- **THEN** access to `_sessions` is serialized via lock and no race condition occurs

#### Scenario: Concurrent stop from RPC handler
- **WHEN** an RPC handler calls `stop_cruise` while the cruise thread is mid-tick
- **THEN** the lock ensures the session is not deleted while the cruise thread is reading it

### Requirement: LocationService uses threading for connection management
LocationService SHALL use `threading.Lock` to protect `_tunnel_connections` and `_usbmux_connections` dictionaries. Refresh loops SHALL run in daemon `threading.Thread` instances instead of `asyncio.Task`.

#### Scenario: Connection dict protected by lock
- **WHEN** a cruise thread calls `set_location` (which accesses `_tunnel_connections`) simultaneously with an RPC handler calling `close_connection`
- **THEN** the `threading.Lock` serializes access and prevents corruption

#### Scenario: Refresh loop runs in thread
- **WHEN** a refresh loop is started for a device
- **THEN** it runs as a daemon `threading.Thread` using `threading.Event.wait(REFRESH_INTERVAL)` for sleep
- **AND** it is stoppable via `threading.Event.set()`

#### Scenario: RSD connect wrapped in asyncio.run
- **WHEN** a new tunnel connection is created from a non-asyncio thread
- **THEN** `RemoteServiceDiscoveryService.connect()` is called via `asyncio.run()` which creates a temporary event loop
- **AND** `RSD.close()` is similarly wrapped when closing connections

### Requirement: LocationService set_location and clear_location are synchronous
LocationService `set_location` and `clear_location` SHALL be synchronous methods (not async). The `_tunnel_provider` callback SHALL be synchronous.

#### Scenario: set_location is sync
- **WHEN** `set_location(device, lat, lon, tunnel)` is called
- **THEN** it executes synchronously without `await`
- **AND** returns a dict with `success` key

#### Scenario: Retry delay uses time.sleep
- **WHEN** a connection error triggers a retry in `_set_via_tunnel_with_retry`
- **THEN** `time.sleep(RETRY_DELAY_SECONDS)` is used instead of `asyncio.sleep`

### Requirement: TunnelManager is fully synchronous
TunnelManager SHALL have no async methods. All methods (`get_tunnel`, `start_tunnel`, `stop_tunnel`, `get_status`, `invalidate`) SHALL be regular synchronous functions.

#### Scenario: get_tunnel is sync
- **WHEN** `get_tunnel(udid)` is called
- **THEN** it executes the HTTP query to tunneld synchronously via `urllib.request`
- **AND** returns `Optional[RSDTunnel]` without `await`

#### Scenario: start_tunnel is sync
- **WHEN** `start_tunnel(udid)` is called
- **THEN** it runs the admin tunnel start process synchronously
- **AND** returns a result dict without `await`

### Requirement: DeviceManager.list_devices is synchronous
`DeviceManager.list_devices()` SHALL be a synchronous method. It already uses `subprocess.run` internally.

#### Scenario: list_devices is sync
- **WHEN** `list_devices()` is called
- **THEN** it runs `subprocess.run` and pymobiledevice3 discovery synchronously
- **AND** returns `List[Device]` without `await`

### Requirement: RouteService cruise methods are synchronous
RouteService cruise orchestration methods (`start_route_cruise`, `stop_route_cruise`, `pause_route_cruise`, `resume_route_cruise`, `_start_next_point_pair`, `_on_point_arrival`) SHALL be synchronous. Route building methods that call BrouterService (`add_waypoint`, `undo_waypoint`, `set_loop_mode`, `reroute_and_resume`) SHALL remain async.

#### Scenario: start_route_cruise is sync
- **WHEN** `start_route_cruise(device_id, speed_kmh)` is called
- **THEN** it calls sync `CruiseService.start_cruise()` and returns without `await`

#### Scenario: _on_point_arrival is sync (called from cruise thread)
- **WHEN** the cruise thread arrives at a target point and invokes the arrival callback
- **THEN** `_on_point_arrival` executes synchronously in the cruise thread context
- **AND** it calls sync `_start_next_point_pair` which calls sync `CruiseService.start_cruise`

#### Scenario: add_waypoint remains async
- **WHEN** `add_waypoint(device_id, lat, lng)` is called from an RPC handler
- **THEN** it awaits `BrouterService.get_route()` to calculate the path
- **AND** the method is declared `async def`

### Requirement: main.py bridges async and sync at the RPC boundary
The aiohttp RPC handler SHALL dispatch to service methods using the appropriate bridge pattern: direct call for fast sync methods, `run_in_executor` for blocking sync methods, and `await` for async methods.

#### Scenario: Fast sync RPC methods called directly
- **WHEN** an RPC request arrives for a fast sync method (e.g., `getFavorites`, `getCruiseStatus`, `getTunnelStatus`)
- **THEN** the handler calls the sync service method directly without `run_in_executor`
- **AND** the method is not declared `async`

#### Scenario: Blocking sync RPC methods use run_in_executor
- **WHEN** an RPC request arrives for a blocking sync method (e.g., `listDevices`, `setLocation`, `startCruise`)
- **THEN** the handler calls `await loop.run_in_executor(None, method, params)` to avoid blocking the event loop

#### Scenario: Async RPC methods await directly
- **WHEN** an RPC request arrives for an async method (e.g., `addRouteWaypoint`, `startPortForward`)
- **THEN** the handler awaits the method directly as it calls async services (BrouterService, PortForwardService)

### Requirement: _set_location_for_cruise is fully synchronous
The `_set_location_for_cruise` callback in main.py SHALL be a synchronous function. It SHALL NOT call any async methods or use `await`.

#### Scenario: Cruise callback runs in cruise thread
- **WHEN** the CruiseService cruise loop calls the location setter callback
- **THEN** `_set_location_for_cruise` executes synchronously in the cruise thread
- **AND** it calls sync `TunnelManager.get_tunnel()` and sync `LocationService.set_location()`

### Requirement: EventBus publish_sync is thread-safe
EventBus SHALL store a reference to the main asyncio event loop and use `loop.call_soon_threadsafe()` for publishing from non-asyncio threads.

#### Scenario: Publishing from a cruise thread
- **WHEN** a cruise thread calls `event_bus.publish_sync(event)`
- **THEN** the event is scheduled on the main asyncio event loop via `loop.call_soon_threadsafe(loop.create_task, self.publish(event))`
- **AND** the SSE subscribers receive the event

#### Scenario: Event loop reference set at startup
- **WHEN** the HTTP server starts
- **THEN** `event_bus.set_loop(asyncio.get_running_loop())` is called to store the loop reference

### Requirement: All daemon threads terminate on process exit
All background threads (cruise loops, refresh loops, flush loops) SHALL be created with `daemon=True` so they terminate automatically when the main process exits.

#### Scenario: Process shutdown kills daemon threads
- **WHEN** the main process receives a shutdown signal
- **THEN** all daemon threads terminate without explicit join
- **AND** services with `close()` methods perform a final flush/cleanup before exit

#### Scenario: Explicit stop cleans up threads
- **WHEN** `stop_cruise`, `close_connection`, or `close()` is called
- **THEN** the corresponding thread's stop event is set
- **AND** `thread.join(timeout=2)` is called for graceful shutdown
