## 1. EventBus Thread-Safe Publishing

- [x] 1.1 Add `set_loop(loop)` method to `EventBus` that stores a reference to the main asyncio event loop
- [x] 1.2 Rewrite `publish_sync()` to use `loop.call_soon_threadsafe(loop.create_task, self.publish(event))` instead of `asyncio.get_running_loop()`
- [x] 1.3 Call `event_bus.set_loop(asyncio.get_running_loop())` in `main.py` `run_http()` after the event loop is running

## 2. TunnelManager — Remove Async

- [x] 2.1 Convert `get_tunnel()` from `async def` to `def` — remove `async` keyword (internals already sync via urllib)
- [x] 2.2 Convert `start_tunnel()` from `async def` to `def` — remove `async` keyword and `await` on `_start_new_tunnel`
- [x] 2.3 Convert `stop_tunnel()` from `async def` to `def` — remove `async` keyword
- [x] 2.4 Convert `_start_new_tunnel()` from `async def` to `def` — remove `async` keyword

## 3. DeviceManager — Remove Async

- [x] 3.1 Convert `list_devices()` from `async def` to `def` — remove `async` keyword (internals already sync via subprocess)

## 4. LocationService — Convert to Threading

- [x] 4.1 Add `threading.Lock` (`_conn_lock`) to protect `_tunnel_connections` and `_usbmux_connections` dicts
- [x] 4.2 Add `_sync_rsd_connect(rsd)` and `_sync_rsd_close(rsd)` helper methods that wrap async pymobiledevice3 calls with `asyncio.run()`
- [x] 4.3 Convert `_create_tunnel_connection()` from async to sync — use `_sync_rsd_connect` instead of `await rsd.connect()`
- [x] 4.4 Convert `_get_or_create_tunnel_connection()` from async to sync — wrap `_tunnel_connections` access with `_conn_lock`
- [x] 4.5 Convert `_set_via_tunnel_with_retry()` from async to sync — replace `asyncio.sleep` with `time.sleep`, call sync `_tunnel_provider`
- [x] 4.6 Convert `_create_usbmux_connection()` and `_get_or_create_usbmux_connection()` from async to sync — wrap with `_conn_lock`
- [x] 4.7 Convert `_set_via_usbmux_with_retry()` from async to sync — replace `asyncio.sleep` with `time.sleep`
- [x] 4.8 Convert `set_location()` and `clear_location()` from async to sync — remove `async`/`await`
- [x] 4.9 Convert `_set_physical_location()` and `_clear_physical_location()` from async to sync
- [x] 4.10 Convert `close_connection()` and `close_all_connections()` from async to sync — use `_sync_rsd_close`, wrap with `_conn_lock`
- [x] 4.11 Convert `_clear_via_tunnel()` and `_clear_via_usbmux()` from async to sync
- [x] 4.12 Replace refresh task system: convert `_start_refresh_task()` and `_stop_refresh_task()` from asyncio.Task to threading.Thread with threading.Event for stop signaling
- [x] 4.13 Change `_tunnel_provider` type from `Callable[..., Awaitable[...]]` to `Callable[..., Optional[RSDTunnel]]` (sync)

## 5. CruiseService — Convert to Threading

- [x] 5.1 Add `threading.Lock` (`_sessions_lock`) to protect `_sessions` dict
- [x] 5.2 Add `_stop_event: threading.Event` and `_thread: threading.Thread` fields to `CruiseSession` dataclass (replace `_task: asyncio.Task`)
- [x] 5.3 Change `_set_location` callback type from `Callable[..., Awaitable[dict]]` to `Callable[..., dict]` (sync)
- [x] 5.4 Convert `_cruise_loop()` from async to sync — replace `asyncio.sleep` with `stop_event.wait(interval)`, call `_set_location` directly (no await), handle stop via `stop_event.is_set()` instead of `asyncio.CancelledError`
- [x] 5.5 Convert `start_cruise()` from async to sync — create `threading.Thread(target=_cruise_loop, daemon=True)` instead of `asyncio.create_task`, wrap `_sessions` access with lock
- [x] 5.6 Convert `stop_cruise()` from async to sync — set `stop_event`, call `thread.join(timeout=2)`, wrap `_sessions` access with lock
- [x] 5.7 Convert `pause_cruise()` and `resume_cruise()` from async to sync — wrap `_sessions` access with lock
- [x] 5.8 Convert `stop_all()` from async to sync
- [x] 5.9 Wrap `get_cruise_status()` and `set_cruise_speed()` with `_sessions_lock`

## 6. RouteService — Hybrid Sync/Async

- [x] 6.1 Convert cruise orchestration methods to sync: `start_route_cruise()`, `stop_route_cruise()`, `pause_route_cruise()`, `resume_route_cruise()` — remove `async`/`await`, call sync CruiseService methods
- [x] 6.2 Convert `_start_next_point_pair()` from async to sync — calls sync `CruiseService.start_cruise()`
- [x] 6.3 Convert `_on_point_arrival()` from async to sync — called from cruise thread, calls sync `_start_next_point_pair`
- [x] 6.4 Convert `stop_all()` from async to sync
- [x] 6.5 Keep route-building methods async: `add_waypoint()`, `undo_waypoint()`, `set_loop_mode()`, `reroute_and_resume()`, `_add_closure_segment()` — these await `BrouterService.get_route()`

## 7. Tunnel Caching in Cruise Callback

- [x] 7.1 Add `_tunnel_cache: dict[str, tuple[Optional[RSDTunnel], float]]` and `TUNNEL_CACHE_TTL = 30` to `LocationSimulatorServer`
- [x] 7.2 Rewrite `_set_location_for_cruise()` as sync: check cache first, query `tunnel.get_tunnel()` only on miss/expiry, store result in cache
- [x] 7.3 Add cache invalidation on `set_location` failure — remove cache entry, call `tunnel.invalidate(device_id)`
- [x] 7.4 Clear tunnel cache entry when cruise stops (in `_stop_cruise` and on arrival)
- [x] 7.5 Convert `_get_tunnel_for_device()` from async to sync (it calls sync `tunnel.get_tunnel()`)

## 8. Debounced Persistence

- [x] 8.1 Add `_dirty` flag, `_stop_event: threading.Event`, `_flush_thread: threading.Thread` to `LastLocationService.__init__`
- [x] 8.2 Start daemon flush thread in `__init__` that runs `_flush_loop()` — checks dirty flag every 5 seconds, writes to disk if dirty
- [x] 8.3 Change `update()` to set `_dirty = True` and update in-memory dict only — remove the `self._save()` call
- [x] 8.4 Add `flush()` public method for immediate write if dirty
- [x] 8.5 Add `close()` method — set stop event, join thread, final flush
- [x] 8.6 Call `self.last_locations.close()` in `main.py` shutdown sequence

## 9. main.py — RPC Handler Bridge

- [x] 9.1 Convert fast sync RPC methods — remove `async` keyword from: `_select_device`, `_get_favorites`, `_add_favorite`, `_update_favorite`, `_delete_favorite`, `_import_favorites`, `_get_tunnel_status`, `_get_cruise_status`, `_get_last_location`, `_list_interfaces`, `_list_port_forwards`, `_get_route_status`, `_set_cruise_speed`, `_set_route_cruise_speed`, `_clear_route`
- [x] 9.2 Convert blocking sync RPC methods — remove `async`, wrap call in `handle_request` with `run_in_executor` for: `_list_devices`, `_set_location`, `_clear_location`, `_start_tunnel`, `_stop_tunnel`, `_start_cruise`, `_stop_cruise`, `_pause_cruise`, `_resume_cruise`, `_start_route_cruise`, `_stop_route_cruise`, `_pause_route_cruise`, `_resume_route_cruise`
- [x] 9.3 Keep async RPC methods that call async services: `_add_route_waypoint`, `_undo_route_waypoint`, `_set_route_loop_mode`, `_reroute_route_cruise`, `_start_port_forward`, `_stop_port_forward`
- [x] 9.4 Update `handle_request` dispatch to detect sync vs async methods and call appropriately (direct call for sync, await for async, run_in_executor for blocking sync)
- [x] 9.5 Update shutdown sequence in `run_http()`: call sync `route.stop_all()`, `cruise.stop_all()`, sync `location.close_all_connections()`, `last_locations.close()`; keep `await` for async services (`event_bus.close()`, `port_forward.stop_all()`, `brouter.close()`)

## 10. Test Migration

- [x] 10.1 Update `tests/test_tunnel_manager.py` — convert async tests to sync, remove `pytest-asyncio` markers
- [x] 10.2 Update `tests/test_location_service.py` — convert async tests to sync, mock threading primitives
- [x] 10.3 Update `test_cruise.py` — convert async tests to sync, mock `threading.Thread` and `threading.Event`, remove `asyncio.sleep` waits
- [x] 10.4 Update `test_route_service.py` — convert async cruise tests to sync, keep async tests for route-building methods
- [x] 10.5 Update `tests/test_server.py` — adapt to new sync/async classification of RPC methods
- [x] 10.6 Update `tests/test_device_manager.py` — convert async tests to sync
- [x] 10.7 Run full test suite (`npm run test:backend`) and fix any remaining failures
