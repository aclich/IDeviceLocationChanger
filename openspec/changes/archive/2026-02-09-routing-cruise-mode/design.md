# Design: Routing Cruise Mode

## Context

The app currently supports single-target cruise mode using straight-line movement. Users need multi-waypoint pathfinding-based routing to simulate realistic journeys along roads/trails. We'll extend the existing cruise architecture to handle sequential waypoint-based movement while reusing the core movement loop logic.

## Goals

- Enable users to create multi-waypoint hiking routes via map clicks
- Integrate Brouter pathfinding service to calculate realistic paths
- Support infinite looping for endurance training simulation
- Reuse existing pause/resume and speed control logic
- Gracefully fall back to straight lines if pathfinding fails
- Maintain performance with real-time updates

## Non-Goals

- Support multiple routing profiles (hiking only, fixed)
- Optimize pathfinding for shortest vs. fastest routes (use Brouter defaults)
- Prevent C→B→A backtracking optimization (defer to future)
- Edit waypoints mid-cruise (must stop/pause first)
- Import GPX files (file I/O not in scope)

---

## Architecture

### Frontend Architecture

```
App.jsx
├── RoutePanel (NEW)
│   ├── Route creation UI (toggle, waypoints, buttons)
│   ├── useRouteCruise hook integration
│   └── Route visualization display
├── MapWidget
│   ├── Handle route mode map clicks → addWaypoint
│   ├── Draw polylines and waypoint markers (route)
│   └── Keep existing direct location clicks (direct mode)
├── ControlPanel
│   ├── Add "Route Mode" toggle
│   ├── Keep existing direct/joystick/cruise controls
│   └── Show/hide route-specific UI based on mode
└── useRouteCruise hook (NEW)
    ├── Route state: waypoints, segments, loopMode, currentSegment
    ├── API calls: addWaypoint, undoWaypoint, startRoute, etc.
    └── Event listeners: routeUpdate, routeArrived, routeError
```

### Backend Architecture

```
main.py
├── Register RouteService and BrouterService
└── Initialize callbacks

RouteService (NEW) — sequencer, no movement loop
├── Per-device route sessions (waypoints, segments, progression state)
├── Delegates point-pair movement to CruiseService
├── Listens for CruiseService arrival → advances to next point pair
├── Pause/resume/stop/speed → proxied to CruiseService
└── Emits route-level events (routeStarted, routeUpdate, routeArrived, etc.)

BrouterService (NEW)
├── Call Brouter REST API
├── Handle retries and timeouts
├── Fallback to straight-line on failure
└── Distance calculation
```

### Data Flow

```
User clicks map
  → MapWidget detects route mode
  → Frontend calls sendRequest('addRouteWaypoint', { deviceId, lat, lng })
    → BrouterService.get_route(start, end, profile="hiking")
    → Returns path: [[lat,lng], ...]
    → RouteService updates route object
    → Backend emits event: routeWaypointAdded
  → Frontend receives event
  → React updates route state
  → MapWidget re-renders polyline and markers

User clicks "Start Route"
  → Frontend calls sendRequest('startRouteCruise', { deviceId, speedKmh })
  → RouteService creates route cruise session
  → Starts async movement loop
  → Every tick:
    - Calculate bearing to current step in path
    - Move device location using move_location()
    - Check if arrived at next waypoint
    - If yes, advance to next segment
    - Emit routeUpdate event
  → Frontend receives updates, refreshes UI
```

---

## Key Design Decisions

### 1. CruiseSession as Movement Engine (Point-Pair Delegation)

**Decision:** RouteService does NOT have its own movement loop. Instead, it delegates movement to CruiseService by feeding consecutive point pairs from the Brouter polyline. CruiseSession is the low-level "move from A to B" engine; RouteService is the sequencer that decides what A and B are.

**Architecture:**
```
RouteService (sequencer/orchestrator)
  └── breaks each segment's polyline into consecutive point pairs
  └── calls CruiseService.start_cruise(current_point, next_point) internally
  └── listens for cruise arrival → advances to next point pair
  └── when segment's polyline exhausted → advances to next segment
  └── when all segments done → loops or stops
```

**Example flow:**
```
Brouter segment: P0 ---800m--- P1 ---1.2km--- P2 ---200m--- P3
RouteService:    cruise(P0→P1) → arrival → cruise(P1→P2) → arrival → cruise(P2→P3) → segment done
```

**Rationale:**
- CruiseSession already handles speed, pause/resume, arrival detection per tick
- Dynamic speed changes apply instantly (CruiseSession reads speed_kmh each tick)
- Zero code duplication — RouteService is pure orchestration logic
- A regular single-target cruise is just a degenerate route (1 segment, 2 points)
- Consistent movement physics across both cruise modes

**Implementation:**
```python
# RouteService orchestrates CruiseService internally
async def _advance_to_next_point(self, session: RouteSession):
    segment = session.route.segments[session.current_segment_index]
    path = segment.path

    if session.current_step_in_segment >= len(path) - 1:
        # Segment complete, advance to next segment
        session.current_segment_index += 1
        session.current_step_in_segment = 0
        emit_event("routeSegmentComplete", ...)
        # Check if route complete or loop
        ...
    else:
        # Feed next point pair to CruiseService
        current = path[session.current_step_in_segment]
        next_pt = path[session.current_step_in_segment + 1]
        session.current_step_in_segment += 1
        await self.cruise_service.start_cruise(
            device_id, current[0], current[1], next_pt[0], next_pt[1], session.speed_kmh
        )
```

> **Considered alternative: gpx-grinder densification (~/Developer/gpx-grinder)**
>
> An alternative approach was discussed: run Brouter polylines through `gpx_grinder.grind_track()`
> to produce evenly-spaced micro-points (e.g., every 0.1s of travel time at ~0.14m spacing for
> walking speed), then play them back as a pre-computed array of set_location() calls.
>
> **Pros of gpx-grinder approach:**
> - Perfectly smooth movement regardless of Brouter point spacing
> - Elevation interpolation built-in
> - Opens the door to GPX file import (future enhancement)
> - Battle-tested with 625+ lines of tests
>
> **Why we chose point-pair delegation instead (for now):**
> - Dynamic speed changes require re-grinding the remaining path (expensive)
> - Replaces CruiseSession's movement loop rather than reusing it
> - Memory cost: 10km route at 0.1s intervals = ~71,000 points
> - Added dependency (gpxpy)
> - Point-pair delegation is simpler and handles dynamic speed natively
>
> **Revisit if:** Movement between Brouter points appears jerky in practice (sparse
> polylines with large gaps). In that case, gpx-grinder densification as a preprocessing
> step before point-pair delegation (hybrid approach) would give both smoothness and
> dynamic speed support.

### 2. Segment-Based Route Representation

**Decision:** Route is stored as waypoints + segments (where each segment is a polyline from Brouter).

**Structure:**
```python
@dataclass
class Route:
    waypoints: list[Waypoint]  # [START, 1, 2, 3, ...]
    segments: list[RouteSegment]  # [START→1, 1→2, 2→3, ...]
    loop_mode: bool
    total_distance: float
```

**Loop segment handling:** When `loop_mode` is enabled, the closure segment (last waypoint → START) is **appended to `segments`** as the final entry. This means:
- Loop OFF with 3 waypoints: `segments = [START→1, 1→2, 2→3]` (3 segments)
- Loop ON with 3 waypoints: `segments = [START→1, 1→2, 2→3, 3→START]` (4 segments)

When loop mode is toggled ON, the closure segment is calculated and appended. When toggled OFF, it's removed. When a new waypoint is added with loop ON, the old closure is removed, new forward segment is added, and a new closure is recalculated and appended.

**Rationale:**
- Each segment is independently calculated by Brouter
- Movement loop simply iterates `segments` linearly — no special-case for loop closure
- Easy to visualize each leg
- Supports dynamic loop closure recalculation
- Clear waypoint tracking

### 3. Brouter for Pathfinding

**Decision:** Use Brouter REST API (same as gpx.studio).

**Configuration:**
- API endpoint: environment variable `BROUTER_API_URL` (default: public instance)
- Profile: hardcoded to "hiking"
- Timeout: 10 seconds per request

**Rationale:**
- Open-source, battle-tested
- Hiking profile supports trails
- Proven in production (gpx.studio)
- Fallback to straight line simple and reliable

### 4. Fallback Strategy

**Decision:** If Brouter fails, use straight-line path (Haversine distance).

**Logic:**
```python
try:
    path = brouter_service.get_route(start, end)
except Exception as e:
    logger.warning(f"Brouter failed: {e}, using straight line")
    path = [start, end]  # Straight line fallback
    emit_event("routeSegmentFallback", { "segment": ... })
```

**Rationale:**
- Cruise can still proceed
- User is warned (event emitted)
- No data loss
- User can retry or continue

### 5. Loop Mode: Auto-Close, No Reversal

**Decision:** When loop is ON, auto-calculate return path from final waypoint to START. Do NOT reorder waypoints.

**Example:**
```
User adds: 1, 2, 3
Route becomes: START → 1 → 2 → 3 → START (not 3 → 2 → 1 → START)
```

**Rationale:**
- Simple and predictable
- User can manually add waypoints in reverse if desired
- Reordering is deferred to future (complex optimization)
- Matches gpx.studio approach

### 6. Resume Behavior After Location Change

**Decision:** Resume continues to next waypoint from current location (no snap-back).

**Example:**
```
1. Cruise paused at waypoint 1
2. User switches to direct mode, moves device to new location
3. User resumes → Device heads to waypoint 2 from new location
```

**Rationale:**
- Flexible for real-world adjustments
- No sudden position jumps
- User maintains control

### 7. Real-Time Speed Updates

**Decision:** Speed slider updates apply immediately to next movement tick.

**Implementation:**
```python
# In _movement_loop:
if session.state == RouteState.RUNNING:
    new_lat, new_lon = move_location(
        ...,
        session.speed_kmh,  # Read from session (may have changed)
        duration_sec
    )
```

**Rationale:**
- Responsive UI
- Consistent with cruise mode
- No buffering or lag

### 8. Event-Driven Architecture

**Decision:** Use existing event system (backend emits, frontend listens) for all updates.

**Events:**
- `routeStarted` - Cruise initiated
- `routeUpdate` - Position, segment, progress
- `routeWaypointReached` - Intermediate waypoint hit
- `routeSegmentComplete` - Segment finished (optional)
- `routeLoopComplete` - Full loop finished (if loop mode)
- `routeArrived` - Final arrival or indefinite loop
- `routeError` - Pathfinding or device error
- `routeWaypointAdded` - UI feedback on waypoint addition

**Rationale:**
- Decouples frontend from backend
- Extensible for future features
- Matches existing cruise architecture

---

## Data Structures

### Frontend Route Object
```javascript
{
  waypoints: [
    { lat: 37.7749, lng: -122.4194, name: "START" },
    { lat: 37.7850, lng: -122.4300, name: "1" },
    { lat: 37.7950, lng: -122.4200, name: "2" },
  ],
  segments: [
    // Forward segments always present
    {
      from_waypoint: 0,
      to_waypoint: 1,
      path: [[37.7749, -122.4194], ...],  // Brouter polyline
      distance_km: 5.2,
      is_closure: false,
    },
    {
      from_waypoint: 1,
      to_waypoint: 2,
      path: [[37.7850, -122.4300], ...],
      distance_km: 3.1,
      is_closure: false,
    },
    // Closure segment appended when loop_mode is true
    {
      from_waypoint: 2,
      to_waypoint: 0,
      path: [[37.7950, -122.4200], ...],
      distance_km: 4.5,
      is_closure: true,  // Marks this as the loop closure segment
    },
  ],
  loop_mode: true,
  total_distance_km: 12.8,
  profile: "hiking",
}
// Note: When loop_mode is false, the closure segment is not present in segments array.
// The movement loop simply iterates segments[0..N-1] then either stops or wraps to 0.
```

### Backend Route Session
```python
class RouteState(str, Enum):
    """Route cruise session state (mirrors CruiseState pattern)."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ARRIVED = "arrived"
    STOPPED = "stopped"

@dataclass
class RouteSession:
    """Per-device route cruise session state.

    RouteService is a sequencer — it tracks which point pair to feed to CruiseService
    next. CruiseService owns the movement loop and async task. RouteSession only holds
    route progression state.
    """
    device_id: str
    route: Route
    speed_kmh: float
    state: RouteState = RouteState.IDLE

    # Route progression (which point pair CruiseService is currently executing)
    current_segment_index: int = 0
    current_step_in_segment: int = 0  # Index within segment polyline
    segments_completed: int = 0
    loops_completed: int = 0

    # Tracking
    start_time: float = field(default_factory=time.time)
    distance_traveled_km: float = 0.0
```

---

## Pathfinding Integration Details

### Brouter API Call
```python
# GET https://brouter.de/brouter?format=geojson&profile=hiking&lon1=X&lat1=Y&lon2=X2&lat2=Y2
response = {
    "features": [{
        "geometry": {
            "coordinates": [[lng, lat], ...]  # Note: Brouter returns [lng, lat]
        }
    }]
}
# Convert to [lat, lng] for internal use
```

### Retry Logic
```python
def get_route(start, end, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(..., timeout=10)
            return response.geometry.coordinates  # [lat, lng]
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
            else:
                return None  # Caller uses fallback
```

---

## Route Sequencer Pseudocode

RouteService does NOT run its own movement loop. It delegates movement to CruiseService
and listens for arrival events to advance the route progression.

```python
class RouteService:
    def __init__(self, cruise_service: CruiseService):
        self.cruise_service = cruise_service
        self._sessions: dict[str, RouteSession] = {}

    async def start_route_cruise(self, device_id: str, speed_kmh: float):
        session = self._sessions[device_id]
        session.state = RouteState.RUNNING
        session.speed_kmh = speed_kmh

        # Register callback: when CruiseService arrives at target, advance route
        self.cruise_service.on_arrival(device_id, self._on_point_arrival)

        # Start first point pair
        await self._start_next_point_pair(session)
        emit_event("routeStarted", session.to_dict())

    async def _start_next_point_pair(self, session: RouteSession):
        """Feed the next point pair from the polyline to CruiseService."""
        # Check if all segments are traversed
        if session.current_segment_index >= len(session.route.segments):
            if session.route.loop_mode:
                session.current_segment_index = 0
                session.current_step_in_segment = 0
                session.loops_completed += 1
                emit_event("routeLoopComplete", ...)
            else:
                session.state = RouteState.ARRIVED
                emit_event("routeArrived", ...)
                return

        segment = session.route.segments[session.current_segment_index]
        path = segment.path
        step = session.current_step_in_segment

        if step >= len(path) - 1:
            # Segment polyline exhausted, advance to next segment
            session.current_segment_index += 1
            session.current_step_in_segment = 0
            session.segments_completed += 1
            emit_event("routeSegmentComplete", ...)
            # Recurse to start next segment's first point pair
            await self._start_next_point_pair(session)
            return

        # Delegate movement to CruiseService: cruise from path[step] to path[step+1]
        current_pt = path[step]
        next_pt = path[step + 1]
        await self.cruise_service.start_cruise(
            session.device_id,
            current_pt[0], current_pt[1],  # start lat/lon
            next_pt[0], next_pt[1],        # target lat/lon
            session.speed_kmh
        )

    async def _on_point_arrival(self, device_id: str, cruise_status: dict):
        """Called by CruiseService when it arrives at the current target point."""
        session = self._sessions.get(device_id)
        if not session or session.state != RouteState.RUNNING:
            return

        # Track distance from this point pair
        session.distance_traveled_km += cruise_status.get("distance_traveled_km", 0)

        # Advance to next point in polyline
        session.current_step_in_segment += 1
        emit_event("routeUpdate", session.to_dict())

        # Feed next point pair to CruiseService
        await self._start_next_point_pair(session)

    async def pause_route(self, device_id: str):
        session = self._sessions[device_id]
        session.state = RouteState.PAUSED
        await self.cruise_service.pause_cruise(device_id)

    async def resume_route(self, device_id: str):
        session = self._sessions[device_id]
        session.state = RouteState.RUNNING
        await self.cruise_service.resume_cruise(device_id)

    async def set_route_speed(self, device_id: str, speed_kmh: float):
        session = self._sessions[device_id]
        session.speed_kmh = speed_kmh
        # Speed applies immediately — CruiseService reads it next tick
        await self.cruise_service.set_cruise_speed(device_id, speed_kmh)
```

**Key insight:** CruiseService handles the 100-200ms movement loop, bearing calculation,
arrival detection, pause/resume, and dynamic speed. RouteService is stateless with
respect to movement — it only tracks "which point pair are we on?" and advances on arrival.

---

## Testing Strategy

### Unit Tests
- BrouterService: Mock HTTP responses, test fallback
- RouteService: Waypoint progression, loop logic
- Coordinate calculations: Reuse existing tests

### Integration Tests
- E2E route creation: Click → Pathfinding → Visualization
- Pause/resume across segments
- Loop iteration and restart

### Manual Tests
- Real Brouter API call (if public instance available)
- Map visualization with real routes
- Device actual movement (on simulator)

---

## Performance Considerations

1. **Pathfinding calls:** One per waypoint addition, cached results stored
2. **Movement loop:** Same 100-200ms tick rate as cruise (no change)
3. **Polyline rendering:** Leaflet handles 1000+ points efficiently
4. **Storage:** Route segments stored in memory (not persisted on disk for MVP)

---

## Future Enhancements (Out of Scope)

1. Reverse/reorder waypoints to minimize backtracking
2. Alternative profiles (running, cycling, etc.) with UI selection
3. Persist routes to disk (`~/.location-simulator/routes.json`)
4. Import GPX files as pre-made routes
5. Snap waypoints to road network (Snap-to-Roads)
6. Turn-by-turn navigation display
7. Multi-profile comparison (fastest vs. shortest)
8. Per-device independent route management (each device manages its own route in the UI simultaneously)
