## Context

The backend runs on a single asyncio event loop (aiohttp web server). All services are declared `async` even though most perform only blocking synchronous work (subprocess calls, urllib HTTP, pymobiledevice3 DVT operations). The cruise loop runs as an `asyncio.Task` that ticks 5-10x/sec. Each tick awaits a chain of calls — tunnel query (sync urllib wrapped in async, 2s timeout), location set (sync pymobiledevice3 wrapped in async) — blocking the entire event loop when any of these stall.

Three services genuinely use async I/O via external packages: `BrouterService` (aiohttp client), `PortForwardService` (asyncio TCP server), and `EventBus` (asyncio.Queue for SSE). Everything else is sync work wearing an async costume.

## Goals / Non-Goals

**Goals:**
- Eliminate event loop blocking during cruise mode — a tunneld timeout must not freeze the UI or other requests
- Remove unnecessary async/await from services that perform only synchronous operations
- Use `threading.Thread` for background loops (cruise, location refresh) so they run independently of the event loop
- Cache tunnel info during active cruise to stop redundant tunneld HTTP queries (currently 5-10/sec)
- Debounce `LastLocationService` disk writes (currently 5-10 writes/sec during cruise)
- Keep the JSON-RPC/SSE external API unchanged — no frontend changes

**Non-Goals:**
- Replacing aiohttp with a sync web framework — aiohttp stays for HTTP + SSE
- Converting BrouterService or PortForwardService away from asyncio — they legitimately use async I/O
- Adding multiprocessing or process pools
- Changing the communication protocol or API contract
- Performance optimization of pymobiledevice3 DVT calls themselves

## Decisions

### 1. Service classification: sync vs. async

**Fully sync (remove all async/await):**
| Service | Reason |
|---------|--------|
| `TunnelManager` | Already uses sync `urllib.request`; `async` keyword is cosmetic |
| `DeviceManager` | Already uses sync `subprocess.run` |
| `CruiseService` | Cruise loop moves to `threading.Thread`; `_set_location` callback becomes sync |
| `LocationService` | DVT/pymobiledevice3 calls are blocking; refresh loop moves to thread. One exception: `RemoteServiceDiscoveryService.connect()` is async — wrap with `asyncio.run()` in thread context (infrequent, only on connection creation) |
| `RouteService` | Cruise orchestration methods become sync. Only route-building methods that call BrouterService stay async (see below) |
| `FavoritesService` | Already sync |
| `LastLocationService` | Already sync; add debounce thread |

**Keep async (external async packages):**
| Service | Reason |
|---------|--------|
| `BrouterService` | Uses `aiohttp.ClientSession` for HTTP |
| `PortForwardService` | Uses `asyncio.start_server` and streams |
| `EventBus` | Uses `asyncio.Queue` for SSE delivery; already has `publish_sync()` bridge |

**Hybrid — RouteService detail:**
RouteService has two categories of methods:
- **Route building** (user-initiated, infrequent): `add_waypoint`, `undo_waypoint`, `set_loop_mode`, `reroute_and_resume`, `_add_closure_segment` — these call `BrouterService.get_route()` which is async. **Keep these async.** They're called from aiohttp RPC handlers.
- **Route cruising** (hot path): `start_route_cruise`, `stop_route_cruise`, `pause_route_cruise`, `resume_route_cruise`, `_start_next_point_pair`, `_on_point_arrival` — these delegate to sync `CruiseService`. **Make these sync.** `_on_point_arrival` is called from the cruise thread.

### 2. CruiseService threading model

**Current:** `asyncio.create_task(_cruise_loop)` → `await asyncio.sleep()` → `await _set_location()`

**New:**
```
session._thread = threading.Thread(target=_cruise_loop, daemon=True)
session._stop_event = threading.Event()
```

- **Sleep**: `stop_event.wait(interval)` — returns immediately when stop is signaled, otherwise waits the interval. Replaces `asyncio.sleep`.
- **Pause**: Check `session.state` at top of loop (same as current). No extra event needed — the loop just skips the tick.
- **Stop**: `stop_event.set()` then `thread.join(timeout=2)`. Replaces `task.cancel()` + `await task`.
- **Callback**: `_set_location` callback type changes from `Callable[[str, float, float], Awaitable[dict]]` to `Callable[[str, float, float], dict]` (sync).
- **Event emission**: `self._emit()` calls `event_bus.publish_sync()` (already thread-safe after fix, see Decision 5).
- **Session dict lock**: `threading.Lock` protects `self._sessions` for concurrent access (cruise thread writes state, RPC thread reads status/stops).

### 3. LocationService threading model

**Connection dicts** (`_tunnel_connections`, `_usbmux_connections`) protected by `threading.Lock` since cruise threads and RPC handlers access them concurrently.

**Refresh loop**: `threading.Thread` with `threading.Event.wait(REFRESH_INTERVAL)` instead of `asyncio.Task` with `asyncio.sleep`. Stop via event signal.

**pymobiledevice3 async bridge**: `RemoteServiceDiscoveryService.connect()` and `.close()` are the only truly async calls. Wrap with `asyncio.run()` in the thread context:
```python
def _sync_rsd_connect(self, rsd):
    asyncio.run(rsd.connect())
```
This is safe because each thread has no running event loop, so `asyncio.run()` creates a temporary one. Called only during connection creation/teardown (rare, not per-tick).

**Retry mechanism**: `_tunnel_provider` callback becomes sync (calls sync `TunnelManager.get_tunnel`). `time.sleep()` replaces `asyncio.sleep()` for retry delays.

### 4. main.py async↔sync bridge

The aiohttp handler is async. Service methods are mostly sync. Bridge strategy:

**`handle_request` stays async** — it's the RPC dispatch entry point called from aiohttp.

**Individual RPC methods classified:**
- **Fast sync methods** (< 1ms, no I/O): `_get_favorites`, `_get_tunnel_status`, `_get_cruise_status`, `_get_route_status`, `_list_port_forwards`, `_get_last_location`, `_select_device`, `_set_cruise_speed`, `_set_route_cruise_speed`, `_clear_route` — call sync service methods directly, no executor needed. Remove `async` keyword.
- **Blocking sync methods** (subprocess/network I/O): `_list_devices`, `_set_location`, `_clear_location`, `_start_tunnel`, `_stop_tunnel`, `_start_cruise`, `_stop_cruise`, `_pause_cruise`, `_resume_cruise`, `_start_route_cruise`, `_stop_route_cruise`, `_pause_route_cruise`, `_resume_route_cruise` — wrap in `await loop.run_in_executor(None, method, params)` to avoid blocking the event loop.
- **Async methods** (call async services): `_add_route_waypoint`, `_undo_route_waypoint`, `_set_route_loop_mode`, `_reroute_route_cruise`, `_start_port_forward`, `_stop_port_forward` — keep `async` as they call `BrouterService` or `PortForwardService`.

**`_set_location_for_cruise` becomes fully sync** — it's the callback from the cruise thread. No executor needed; it runs in the cruise thread context directly.

### 5. EventBus thread-safe publishing

Current `publish_sync()` calls `asyncio.get_running_loop()` which fails from non-asyncio threads.

**Fix**: Store a reference to the main asyncio event loop at startup. Use `loop.call_soon_threadsafe()` from threads:
```python
def set_loop(self, loop: asyncio.AbstractEventLoop):
    self._loop = loop

def publish_sync(self, event: dict):
    if self._loop and self._loop.is_running():
        self._loop.call_soon_threadsafe(self._loop.create_task, self.publish(event))
```
Called from `main.py` during initialization: `event_bus.set_loop(asyncio.get_running_loop())`.

### 6. Tunnel caching in cruise hot path

**Location**: `main.py._set_location_for_cruise()` (the cruise callback).

**Cache structure**:
```python
self._tunnel_cache: dict[str, tuple[RSDTunnel, float]] = {}  # {device_id: (tunnel, timestamp)}
TUNNEL_CACHE_TTL = 30  # seconds
```

**Logic per cruise tick**:
1. Check cache: if cached tunnel exists and age < TTL → use it, skip tunneld query
2. Cache miss or expired → query `tunnel.get_tunnel()` once, store result in cache
3. On location set failure → invalidate cache entry, retry with fresh query
4. On cruise stop → remove cache entry for device

This reduces tunneld queries from 5-10/sec to ~1 every 30 seconds during normal operation.

### 7. Debounced persistence for LastLocationService

**Mechanism**: Dirty flag + background flush thread.

```python
class LastLocationService:
    _dirty: bool = False
    _flush_interval: float = 5.0  # seconds
    _flush_thread: threading.Thread  # daemon, runs _flush_loop
    _stop_event: threading.Event
```

- `update()`: Sets `_dirty = True`, updates in-memory dict. No disk write.
- `_flush_loop()`: Every 5s, checks `_dirty`; if True, writes JSON, resets flag.
- `flush()`: Public method for immediate write. Called on shutdown.
- `close()`: Signals stop event, joins flush thread, final flush.

Reduces disk writes from 5-10/sec to at most 1 every 5 seconds.

## Risks / Trade-offs

**[Thread safety bugs]** → Services previously safe by asyncio's single-threaded model now need explicit locks. Mitigate by: keeping lock scopes minimal (protect dict access only, not long operations), using daemon threads that die with the process, and adding `threading.Lock` to `CruiseService._sessions`, `LocationService._tunnel_connections/_usbmux_connections`.

**[asyncio.run() in threads for RSD connect]** → Creates a temporary event loop per connection setup. This is infrequent (once per connection, not per tick) and well-supported in Python 3.13+. If pymobiledevice3 adds sync connect in the future, we can switch.

**[EventBus cross-thread delivery]** → `call_soon_threadsafe` + `create_task` adds a small delay vs direct queue push. Acceptable since SSE events are already buffered and don't need sub-millisecond delivery.

**[Tunnel cache staleness]** → 30s TTL means we might use stale tunnel info for up to 30s after tunnel dies. Mitigated by: LocationService's retry mechanism (on DVT error, it requests fresh tunnel from provider, which bypasses the cache), and the cache is invalidated on any set_location failure.

**[Test migration effort]** → All `async def test_*` methods in cruise/route/location/tunnel tests need conversion to sync. `pytest-asyncio` fixtures replaced with regular fixtures. This is mechanical but touches many test files.
