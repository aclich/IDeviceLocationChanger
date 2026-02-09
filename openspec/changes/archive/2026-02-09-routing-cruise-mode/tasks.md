# Tasks: Routing Cruise Mode Implementation

## Phase 1: Backend Foundation & Pathfinding

### 1. Create BrouterService

- [x] 1.1 Create `python-backend/services/brouter_service.py`
- [x] 1.2 Implement `get_route(start: tuple, end: tuple) → list[tuple]` method
- [x] 1.3 Add Brouter API call with profile="hiking"
- [x] 1.4 Implement retry logic (3 retries, exponential backoff)
- [x] 1.5 Add timeout handling (10 seconds)
- [x] 1.6 Implement straight-line fallback on failure
- [x] 1.7 Add logging for all requests and failures
- [x] 1.8 Add configuration: BROUTER_API_URL environment variable

### 2. Create RouteService

- [x] 2.1 Create `python-backend/services/route_service.py`
- [x] 2.2 Define `Route`, `RouteSegment`, `Waypoint` dataclasses and `RouteState` enum
- [x] 2.3a Define standalone `RouteSession` dataclass (does NOT inherit CruiseSession; has its own state, position, speed, and route progression fields)
- [x] 2.3 Implement `add_waypoint(device_id, lat, lng)` to call Brouter and store segment
- [x] 2.4 Add arrival callback support to CruiseService: allow registering a per-device callback that fires on cruiseArrived (before session deletion). This lets RouteService intercept arrivals and feed the next point pair. When a callback is registered, CruiseService should NOT delete the session on arrival (RouteService manages lifecycle)
- [x] 2.5a Accept CruiseService as dependency in RouteService.__init__()
- [x] 2.5 Implement `start_route_cruise(device_id, speed_kmh)` — register arrival callback on CruiseService, feed first point pair
- [x] 2.6 Implement `_start_next_point_pair(session)` — read current step from polyline, call cruise_service.start_cruise() with point pair
- [x] 2.7 Implement `_on_point_arrival(device_id, cruise_status)` — advance step, track distance, feed next point pair or advance segment
- [x] 2.8 Implement segment advancement: when polyline exhausted, increment segment index, emit routeSegmentComplete
- [x] 2.9 Implement loop logic: when all segments done, reset indices if loop_mode, emit routeLoopComplete; otherwise emit routeArrived
- [x] 2.10 Implement pause/resume/stop by proxying to CruiseService + updating RouteSession state
- [x] 2.11 Implement set_route_speed() — update session.speed_kmh + proxy to cruise_service.set_cruise_speed()
- [x] 2.12 Add route-level event emission (routeStarted, routeUpdate, routeArrived, routeSegmentComplete, routeLoopComplete, routeError)

### 3. Register JSON-RPC Methods in main.py

- [x] 3.1 Add `addRouteWaypoint` method (deviceId, lat, lng) → returns route state with new segment
- [x] 3.2 Add `undoRouteWaypoint` method (deviceId) → removes last waypoint + its segment; if loop ON, removes old closure and recalculates new closure via Brouter; returns updated route state
- [x] 3.3 Add `startRouteCruise` method (deviceId, speedKmh) → starts route cruise session
- [x] 3.4 Add `getRouteStatus` method (deviceId) → returns current route and cruise state
- [x] 3.5 Add `pauseRouteCruise` method (deviceId)
- [x] 3.6 Add `resumeRouteCruise` method (deviceId)
- [x] 3.7 Add `stopRouteCruise` method (deviceId)
- [x] 3.8 Add `setRouteCruiseSpeed` method (deviceId, speedKmh)
- [x] 3.9 Add `clearRoute` method (deviceId) → clears all waypoints and segments
- [x] 3.10 Add `setRouteLoopMode` method (deviceId, enabled) → toggles loop mode
- [x] 3.11 Register all methods in `self._methods` dict in main.py (following existing camelCase convention)

### 4. Backend Tests

- [x] 4.1 Create `python-backend/test_route_service.py`
- [x] 4.2 Test waypoint addition and segment calculation
- [x] 4.3 Test route cruise movement loop (mock device)
- [x] 4.4 Test waypoint arrival detection and segment transitions
- [x] 4.5 Test loop closure and restart
- [x] 4.6 Test pause/resume functionality
- [x] 4.7 Test Brouter fallback on failure
- [x] 4.8 Run all tests: `npm run test:backend`

---

## Phase 2: Frontend Route Management

### 5. Create useRouteCruise Hook

- [x] 5.1 Create `src/hooks/useRouteCruise.js`
- [x] 5.2 Define route state: `{ waypoints, segments, loopMode, currentSegment, ... }`
- [x] 5.3 Implement `addWaypoint(lat, lng)` - calls backend, updates state
- [x] 5.4 Implement `undoWaypoint()` - removes last waypoint, recalculates distance. If loop mode is ON, backend must also remove old closure segment and recalculate new closure (last remaining waypoint → START) via Brouter
- [x] 5.5 Implement `toggleLoopMode()` - enables/disables auto-closure
- [x] 5.6 Implement `startRoute(speed)` - calls backend start endpoint
- [x] 5.7 Implement `pauseRoute()` / `resumeRoute()` / `stopRoute()`
- [x] 5.8 Implement `setRouteSpeed(speed)` - real-time speed updates
- [x] 5.9 Implement `clearRoute()` - resets to empty route
- [x] 5.10 Add event listeners for routeUpdate, routeArrived, routeError
- [x] 5.11 Export hook API for React components

### 6. Create RoutePanel Component

- [x] 6.1 Create `src/components/RoutePanel.jsx`
- [x] 6.2 Add route mode toggle (ON/OFF)
- [x] 6.3 Add loop mode toggle
- [x] 6.4 Display route state: "N waypoints, X.X km"
- [x] 6.5 Add "Start Route" button (disabled if no route)
- [x] 6.6 Add "Pause" / "Resume" buttons (enabled based on state)
- [x] 6.7 Add "Stop Route" button
- [x] 6.8 Add "Clear Route" button
- [x] 6.9 Add "Undo" button (disabled if no waypoints to remove)
- [x] 6.10 Display progress: "Segment N/M, X.X km remaining"
- [x] 6.11 Display ETA based on remaining distance and speed
- [x] 6.12 Show loop counter if loop mode enabled
- [x] 6.13 Show error messages (fallback to straight line, Brouter unavailable, etc.)

### 7. Update MapWidget for Route Mode

- [x] 7.1 Add route mode prop from parent (App.jsx)
- [x] 7.2 Modify click handler: detect route mode, call addWaypoint() vs setLocation()
- [x] 7.3 Draw route polylines: Leaflet.polyline for each segment
- [x] 7.4 Draw waypoint markers: START (blue, large), 1/2/3 (orange, numbered)
- [x] 7.5 Update polylines/markers when route changes
- [x] 7.6 Color polylines: teal/green for forward, optional different color for loop closure
- [x] 7.7 Update current position marker to show on route
- [x] 7.8 Zoom/pan to fit route on first click or "fit to route" button

### 8. Update ControlPanel

- [x] 8.1 Add "Route Mode" toggle to existing controls
- [x] 8.2 Hide/show route-specific controls based on mode
- [x] 8.3 Disable joystick when route mode is ON
- [x] 8.4 Show/hide RoutePanel based on route mode

### 9. Update App.jsx

- [x] 9.1 Import useRouteCruise hook
- [x] 9.2 Add route mode state and setter
- [x] 9.3 Pass route mode to MapWidget, ControlPanel, RoutePanel
- [x] 9.4 Handle device selection: clear route when switching devices (optional)
- [x] 9.5 Integrate RoutePanel into layout

### 10. Update useBackend.js Hook

- [x] 10.1 Add JSON-RPC calls via sendRequest() for route methods (addRouteWaypoint, startRouteCruise, pauseRouteCruise, resumeRouteCruise, stopRouteCruise, setRouteCruiseSpeed, clearRoute, undoRouteWaypoint, setRouteLoopMode, getRouteStatus)
- [x] 10.2 Add route event handlers to existing SSE event listener (routeUpdate, routeArrived, routeError, routeWaypointAdded, routeWaypointReached, routeSegmentComplete, routeLoopComplete)
- [x] 10.3 Add routeStatus state (similar to cruiseStatus) updated from SSE events
- [x] 10.4 Add routeState state for waypoints, segments, loop mode (updated from events)

---

## Phase 3: Integration & Testing

### 11. Frontend Integration Tests

- [x] 11.1 Create `src/hooks/useRouteCruise.test.js`
- [x] 11.2 Test addWaypoint and segment calculation (mock backend)
- [x] 11.3 Test loop mode toggle
- [x] 11.4 Test pause/resume
- [x] 11.5 Test speed updates
- [x] 11.6 Test event listeners
- [x] 11.7 Run: `npm run test:run`

### 12. Manual E2E Testing

- [x] 12.1 Start app in dev mode (manual)
- [x] 12.2 Toggle route mode and add 3 waypoints on map (manual)
- [x] 12.3 Verify polylines and markers render correctly (manual)
- [x] 12.4 Verify distance calculation matches Brouter (manual)
- [x] 12.5 Enable loop mode and verify auto-closure (manual)
- [x] 12.6 Start route cruise and verify device moves along path (manual)
- [x] 12.7 Test pause/resume mid-route (manual)
- [x] 12.8 Test speed slider updates in real-time (manual)
- [x] 12.9 Test undo waypoint (manual)
- [x] 12.10 Test loop iteration (device reaches START and repeats) (manual)
- [x] 12.11 Test fallback (disable internet, verify straight-line fallback) (manual)

### 13. Documentation

- [x] 13.1 Update CLAUDE.md with new route mode commands
- [x] 13.2 Add JSDoc comments to useRouteCruise hook
- [x] 13.3 Add JSDoc comments to RoutePanel component
- [x] 13.4 Document BrouterService configuration (BROUTER_API_URL)
- [x] 13.5 Add example: "How to create and run a route"

---

## Summary

**Total Tasks:** 13 main sections, ~80 subtasks
**Estimated Effort:**
- Backend: ~8-10 hours (services, endpoints, tests)
- Frontend: ~6-8 hours (hooks, components, integration)
- Testing & Polish: ~2-3 hours

**Dependencies:** None (can work in parallel after backend foundation laid)

**Definition of Done:**
- All tasks checked off
- E2E tests passing
- No console errors
- Manual testing complete
- Code reviewed and merged
