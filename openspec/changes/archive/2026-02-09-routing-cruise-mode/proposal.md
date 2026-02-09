# Proposal: Routing Cruise Mode with Pathfinding

## Why

Current cruise mode supports only straight-line movement to a single target. For realistic GPS simulation, users need to follow actual road/trail networks. Inspired by gpx.studio, we'll add pathfinding-based multi-waypoint routes with loop capability, allowing users to simulate realistic journeys along hiking or running paths.

## What Changes

- **Route Mode UI:** Toggle to switch from direct location setting to waypoint-based routing
- **Pathfinding Integration:** Brouter service calculates optimal paths between waypoints using hiking profile
- **Multi-Waypoint Routes:** Users click multiple points; device follows chained route segments
- **Loop Mode:** Optional auto-closure and infinite looping with intelligent waypoint ordering
- **Route Visualization:** Map displays route path with start position, numbered waypoints, and segments
- **Pause/Resume:** Reuse existing cruise pause/resume logic for routes
- **Dynamic Speed:** Real-time speed adjustment across entire route
- **Fallback Handling:** Falls back to straight line if pathfinding fails

## Capabilities

### New Capabilities

- `route-mode-toggle`: Enable/disable route mode on map (vs. direct location setting)
- `waypoint-management`: Click to add waypoints, undo to remove last waypoint
- `route-pathfinding`: Calculate optimal hiking paths between waypoints using Brouter
- `multi-segment-routing`: Follow chained route segments from start to all waypoints
- `loop-mode`: Auto-close route and repeat infinitely with loop toggle
- `route-visualization`: Display route path, waypoints, and current position on Leaflet map
- `route-cruise-movement`: Device follows route with pause, resume, and speed control
- `route-progress-tracking`: Show current segment, waypoint, distance remaining, ETA

### Modified Capabilities

- `cruise-mode`: Extended to support route-based multi-waypoint cruising (vs. single-target)
- `map-interaction`: Map clicks now add waypoints in route mode (vs. setting location directly)

## Impact

### Files to Create
- `src/components/RoutePanel.jsx` - Route creation and control UI
- `src/hooks/useRouteCruise.js` - Route state management and API
- `src/utils/brouter.js` - Brouter pathfinding client
- `python-backend/services/route_service.py` - Backend route cruise logic
- `python-backend/services/brouter_service.py` - Brouter integration

### Files to Modify
- `src/App.jsx` - Add route mode state, integrate RoutePanel
- `src/components/MapWidget.jsx` - Handle waypoint clicks vs. location clicks based on route mode
- `src/components/ControlPanel.jsx` - Add route mode toggle
- `src/utils/backendClient.js` - Add route-specific API calls and event handlers
- `python-backend/main.py` - Register route service and endpoints

### Architecture

```
Frontend:
  ControlPanel → Toggle "Route Mode"
  MapWidget → Clicks add waypoints (route mode) or set location (direct mode)
  RoutePanel → Display route, manage waypoints, show progress
  useRouteCruise → Manage route state, call backend APIs

Backend:
  route_service.py → Manage route cruise sessions (similar to cruise_service)
  brouter_service.py → Call Brouter API, handle fallback logic
  coordinate_utils.py → Reuse move_location, bearing_to, distance_between
```

## Success Criteria

1. ✓ User can toggle "Route Mode" and add waypoints by clicking map
2. ✓ Route path displayed on map with visual waypoint markers
3. ✓ Device follows chained pathfinding segments (START → 1 → 2 → 3)
4. ✓ Loop mode enabled: auto-closes route and repeats infinitely
5. ✓ Pause/resume works; resume continues to next waypoint
6. ✓ Speed slider adjusts real-time during route cruise
7. ✓ If pathfinding fails, falls back to straight line
8. ✓ Progress shown: "Segment 2/3, 5.2 km remaining"

---

**Ready to build out specs and design?**
