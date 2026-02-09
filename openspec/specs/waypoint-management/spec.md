# Spec: Waypoint Management

## Feature: Add Waypoints by Clicking Map

Users click on the map in route mode to add waypoints. Each click triggers pathfinding from the last waypoint to the new one.

### Requirement: Add Waypoint on Map Click

When route mode is enabled and user clicks the map, a new waypoint is added and the path from the previous waypoint is calculated.

#### Scenario: Add First Waypoint (Device Has Location)

- **WHEN** route mode is ON and no waypoints exist
- **AND** the device already has a location set (e.g., 37.7749, -122.4194)
- **AND** user clicks on the map at coordinates (37.7850, -122.4300)
- **THEN** START is auto-set to the device's current location (37.7749, -122.4194)
- **AND** a "START" marker appears at the device's current location
- **AND** waypoint "1" appears at the clicked location (37.7850, -122.4300)
- **AND** pathfinding is triggered from START to waypoint 1
- **AND** UI shows "Route: 1 waypoint, [distance] km" once pathfinding completes
- **AND** "Start Route" button is now enabled

#### Scenario: Add First Waypoint (No Device Location)

- **WHEN** route mode is ON and no waypoints exist
- **AND** the device does NOT have a location set yet
- **AND** user clicks on the map at coordinates (37.7749, -122.4194)
- **THEN** a starting position marker appears labeled "START" at the clicked location
- **AND** the route state shows "Route: 0 waypoints (starting position only)"
- **AND** "Start Route" button is still disabled (need at least one waypoint beyond START)

#### Scenario: Add Second Waypoint (After Manual START)

- **WHEN** route has only a START position (set via first click, no device location)
- **AND** user clicks the map at a new location (37.7850, -122.4300)
- **THEN** a numbered waypoint "1" appears on the map
- **AND** a polyline is drawn from START to waypoint 1
- **AND** pathfinding is triggered to calculate the hiking route between the two points
- **AND** the UI shows "Route: 1 waypoint, [distance] km" once pathfinding completes
- **AND** "Start Route" button is now enabled

#### Scenario: Add Third Waypoint (With Loop Off)

- **WHEN** route has 2 waypoints (START and 1)
- **AND** loop mode is OFF
- **AND** user clicks the map at a new location
- **THEN** waypoint "2" appears on the map
- **AND** polylines connect: START → 1 → 2
- **AND** pathfinding calculates route from waypoint 1 to waypoint 2
- **AND** UI shows "Route: 2 waypoints, [new total distance] km"

#### Scenario: Add Waypoint With Loop Mode On

- **WHEN** route has 2 waypoints (START and 1)
- **AND** loop mode is ON
- **AND** user clicks the map to add waypoint 2
- **THEN** waypoint "2" appears
- **AND** polylines connect: START → 1 → 2 → START (auto-closure)
- **AND** pathfinding calculates:
  - Route from 1 to 2
  - Route from 2 back to START (loop closure)
- **AND** UI shows total distance including return path

---

## Requirement: Undo Waypoint

User can remove the last added waypoint without affecting previous ones.

#### Scenario: Undo Removes Last Waypoint (Loop Off)

- **WHEN** route has 3 waypoints (START, 1, 2, 3) and loop mode is OFF
- **AND** user clicks "Undo" button
- **THEN** waypoint 3 and its incoming segment (2→3) are removed
- **AND** route now shows START → 1 → 2
- **AND** polylines update to show new endpoint at waypoint 2
- **AND** UI shows "Route: 2 waypoints, [recalculated distance] km"

#### Scenario: Undo Removes Last Waypoint (Loop On)

- **WHEN** route has 3 waypoints (START, 1, 2, 3) and loop mode is ON
- **AND** segments are [START→1, 1→2, 2→3, 3→START(closure)]
- **AND** user clicks "Undo" button
- **THEN** waypoint 3, its incoming segment (2→3), and the old closure (3→START) are all removed
- **AND** backend calls Brouter to calculate new closure from waypoint 2 → START
- **AND** segments become [START→1, 1→2, 2→START(new closure)]
- **AND** polylines update to show new closure path
- **AND** total distance recalculates including new closure
- **AND** if new closure pathfinding fails, falls back to straight line (same as add waypoint fallback)

#### Scenario: Undo Cannot Remove Start Position

- **WHEN** route has only 1 waypoint (START)
- **THEN** the "Undo" button is disabled (grayed out)
- **AND** clicking undo has no effect

#### Scenario: Undo While Cruise Running

- **WHEN** route cruise is running
- **AND** user clicks "Undo"
- **THEN** the undo is ignored or shows error "Cannot modify route while cruising"
- **AND** user must pause/stop cruise first to modify route

---

## Requirement: Visual Waypoint Markers

Waypoints are visually distinct and clearly labeled on the map.

#### Scenario: Start Position Marker

- **WHEN** first waypoint (starting position) is added
- **THEN** a large blue circle appears on the map
- **AND** "START" label is displayed at or near the marker
- **AND** marker is slightly larger than numbered waypoints

#### Scenario: Numbered Waypoint Markers

- **WHEN** user adds waypoints 1, 2, 3
- **THEN** each appears as a numbered marker (orange/yellow dot)
- **AND** each displays its number (1, 2, 3, ...)
- **AND** markers are distinctly smaller than START marker
- **AND** polyline passes through all markers in order

#### Scenario: Waypoint Clustering

- **WHEN** user zooms in on a cluster of waypoints
- **THEN** all waypoint markers remain visible
- **AND** labels do not overlap (or are stacked vertically if close)
- **AND** polylines remain visible connecting them

---

## Requirement: Route Polyline Visualization

The calculated route path is drawn on the map with visual distinction for segments.

#### Scenario: Route Polyline Display

- **WHEN** pathfinding completes for a segment
- **THEN** a polyline is drawn on the map from previous waypoint to current
- **AND** color is consistent (e.g., teal/green)
- **AND** line width is 3-4 pixels for visibility
- **AND** polyline follows the calculated hiking path (not straight line)

#### Scenario: Multiple Segments

- **WHEN** route has 3 waypoints (START, 1, 2)
- **THEN** two polylines are visible:
  - START → 1 (first segment)
  - 1 → 2 (second segment)
- **AND** both segments appear connected at waypoint markers
- **AND** color and style are consistent

#### Scenario: Loop Closure Visualization

- **WHEN** loop mode is enabled with 2 waypoints (START, 1)
- **THEN** polylines show: START → 1 → START (loop closed)
- **AND** return segment from 1 to START is visible on map
- **AND** color/style may be slightly different or same as forward segments
