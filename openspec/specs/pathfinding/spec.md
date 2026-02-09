# Spec: Pathfinding via Brouter

## Feature: Calculate Hiking Routes Using Brouter

The app calls Brouter pathfinding service to calculate optimal hiking routes between waypoints instead of using straight lines.

### Requirement: Brouter Integration

The backend calls Brouter API to calculate hiking routes and returns the path to the frontend.

#### Scenario: Successful Pathfinding

- **WHEN** user adds waypoint 2 after having waypoint 1
- **THEN** backend calls Brouter API with:
  - Start: waypoint 1 coordinates
  - End: waypoint 2 coordinates
  - Profile: "hiking"
- **AND** Brouter returns an ordered array of lat/lng points representing the hiking path
- **AND** frontend receives the path array and draws polyline on map
- **AND** total distance is calculated from the path
- **AND** UI updates to show "Route: X waypoints, Y.Y km"

#### Scenario: Brouter API Unavailable

- **WHEN** Brouter API is unreachable or times out
- **THEN** backend retries up to 3 times with exponential backoff
- **AND** if all retries fail, falls back to straight-line path
- **AND** frontend displays warning message: "Path calculation failed, using straight line"
- **AND** waypoint is still added to the route (with straight-line segment)
- **AND** user can continue adding waypoints or undo and re-add after connectivity recovers

#### Scenario: No Route Found

- **WHEN** Brouter cannot find a hiking route (e.g., waypoints are on separate islands)
- **THEN** backend returns error: "No hiking route found between waypoints"
- **AND** frontend shows error dialog: "Cannot connect these waypoints. Try different locations."
- **AND** waypoint is NOT added to route
- **AND** user can click "Undo" or try a different location

---

## Requirement: Profile Configuration

Pathfinding always uses the "hiking" profile as specified.

#### Scenario: Hiking Profile

- **WHEN** any pathfinding request is made
- **THEN** the Brouter request always includes profile="hiking"
- **AND** no user selection or configuration of profiles is exposed
- **AND** the hiking profile avoids motorways and prefers trails/paths

---

## Requirement: Distance Calculation

Total route distance is calculated from the pathfinding results.

#### Scenario: Calculate Total Distance

- **WHEN** route has 3 segments (START→1, 1→2, 2→START with loop)
- **THEN** each segment's distance is calculated from Brouter's polyline
- **AND** distances are summed: segment1 + segment2 + segment3 = total
- **AND** total distance is displayed in UI: "Route: 2 waypoints, 12.8 km"
- **AND** distance is updated each time a waypoint is added or removed

#### Scenario: Distance Precision

- **WHEN** calculating segment distance
- **THEN** distance uses Haversine formula (same as existing cruise_service)
- **AND** distance is rounded to 1 decimal place for display
- **AND** internal calculations use full precision for accuracy

---

## Requirement: Loop Closure Pathfinding

When loop mode is enabled, Brouter calculates the return path from final waypoint to start.

#### Scenario: Auto-Closing Route

- **WHEN** user enables loop mode on a route with waypoints (START, 1, 2)
- **THEN** backend automatically calls Brouter to find path from waypoint 2 back to START
- **AND** polyline is drawn from 2 → START on the map
- **AND** total distance includes the closure segment
- **AND** UI shows "Route: 2 waypoints, X.X km, Loop: ON"

#### Scenario: Adding Waypoint with Loop On

- **WHEN** loop mode is already ON
- **AND** user adds a new waypoint (3) to route with (START, 1, 2)
- **THEN** backend calculates:
  - Path from 2 → 3 (new segment)
  - Path from 3 → START (new closure, replaces 2→START)
- **AND** total distance is recalculated: START→1 + 1→2 + 2→3 + 3→START
- **AND** old closure segment (2→START) is removed from map
- **AND** new polylines are drawn

---

## Requirement: Fallback Behavior

If pathfinding fails, the system gracefully falls back to straight lines.

#### Scenario: Fallback to Straight Line

- **WHEN** Brouter fails after 3 retries
- **THEN** backend creates a "fake path" consisting of:
  - Start point
  - End point
  - Calculated direct distance
- **AND** frontend draws a straight polyline (not curved)
- **AND** warning is shown: "Using straight-line path (routing unavailable)"
- **AND** route can still be cruised normally
- **AND** distance is based on Haversine calculation

#### Scenario: User Aware of Fallback

- **WHEN** a segment falls back to straight line
- **THEN** UI shows a warning badge or different color for that segment (optional)
- **AND** hover text displays: "Straight-line path (routing unavailable)"
- **NOTE:** Retry pathfinding for failed segments is a future enhancement. For MVP, user can undo the waypoint and re-add it after connectivity recovers
