# Spec: Route Cruise Movement

## Feature: Device Follows Multi-Waypoint Route

Once a route is created, the device can cruise along the entire path, moving through all segments in sequence, with support for pause/resume and speed control.

### Requirement: Start Route Cruise

User initiates movement along the calculated route path.

#### Scenario: Start Route with Single Waypoint

- **WHEN** route has START and waypoint 1 only
- **AND** user clicks "Start Route" button
- **THEN** backend creates a route cruise session
- **AND** device begins moving from START toward waypoint 1
- **AND** UI shows "Route Cruise: Running, Segment 1/1"
- **AND** progress shows "1.2 km to Waypoint 1"

#### Scenario: Start Route with Multiple Waypoints

- **WHEN** route has START, 1, 2, 3 waypoints
- **AND** user clicks "Start Route"
- **THEN** device moves: START → 1 → 2 → 3 (then stops)
- **AND** UI shows "Route Cruise: Running, Segment 1/3"
- **AND** progress updates in real-time as device moves

#### Scenario: Start Route with Loop Enabled

- **WHEN** route has START, 1, 2 waypoints
- **AND** loop mode is ON (so route is START → 1 → 2 → START)
- **AND** user clicks "Start Route"
- **THEN** device moves in loop: START → 1 → 2 → START → 1 → 2 → ... (indefinitely)
- **AND** UI shows "Route Cruise: Running, Segment 1/3 (Loop enabled)"
- **AND** loop counter shows "Loop 1/∞"

---

## Requirement: Multi-Segment Movement

Device correctly follows each segment of the route in sequence, detecting arrival at intermediate waypoints.

#### Scenario: Progress Through Segments

- **WHEN** device is cruising on a 3-segment route
- **AND** reaches waypoint 1 (end of segment 1)
- **THEN** device automatically transitions to segment 2
- **AND** begins moving toward waypoint 2
- **AND** UI updates: "Segment 2/3, 3.2 km to Waypoint 2"
- **AND** event "waypointReached" is emitted: { waypoint: 1, distanceTraveledSoFar: 5.2 }

#### Scenario: Arrival at Final Waypoint (No Loop)

- **WHEN** device reaches the final waypoint and loop mode is OFF
- **THEN** device stops moving
- **AND** UI shows "Route Cruise: Arrived"
- **AND** event "routeArrived" is emitted with total distance and duration
- **AND** "Start Route" button is re-enabled (to restart)

#### Scenario: Loop Return to Start

- **WHEN** device reaches final waypoint with loop mode ON
- **AND** there is an active loop closure segment
- **THEN** device moves along the return path (final waypoint → START)
- **AND** upon reaching START, automatically begins loop iteration again
- **AND** loop counter increments: "Loop 1/∞" → "Loop 2/∞"
- **AND** UI shows "Segment 1/3" (restarted)

---

## Requirement: Pause and Resume

User can pause the route cruise at any point and resume from the exact location.

#### Scenario: Pause Route Cruise

- **WHEN** device is actively moving on segment 2 of 3
- **AND** user clicks "Pause" button
- **THEN** device stops moving (location is frozen)
- **AND** UI shows "Route Cruise: Paused"
- **AND** internal state remembers: segment 2, step in segment, current coordinates
- **AND** "Resume" button becomes enabled
- **AND** "Start Route" button changes to "Clear Route"

#### Scenario: Resume From Pause

- **WHEN** route cruise is paused at some location
- **AND** user clicks "Resume"
- **THEN** device continues moving toward the next waypoint in sequence
- **AND** (does NOT recalculate path; continues with stored route)
- **AND** UI shows "Route Cruise: Running, Segment 2/3"
- **AND** movement continues smoothly from pause location

#### Scenario: Resume After Manual Location Change

- **WHEN** route cruise is paused at Waypoint 1
- **AND** user switches to "Direct Mode" and manually moves device to a different location
- **AND** then clicks "Resume" while still in route mode
- **THEN** device continues moving toward Waypoint 2
- **AND** (does NOT snap back to pause location; continues from new location)
- **AND** distance remaining recalculates based on new position to Waypoint 2

#### Scenario: Cannot Pause During Loop (Optional)

- **WHEN** loop mode is enabled
- **AND** user tries to pause (optional restriction)
- **THEN** either: pause is allowed and resume works normally, OR pause is disabled with message "Cannot pause infinite loop"
- **NOTE:** First implementation allows pause; future refinement can restrict if needed

---

## Requirement: Dynamic Speed Control

User can adjust cruise speed in real-time while the device is moving.

#### Scenario: Change Speed While Cruising

- **WHEN** device is moving at 5 km/h
- **AND** user adjusts speed slider to 10 km/h
- **THEN** next movement step uses 10 km/h
- **AND** distance remaining recalculates based on new speed
- **AND** UI updates ETA immediately
- **AND** movement is smooth (no stuttering or resetting)

#### Scenario: Speed Persists Across Segments

- **WHEN** user sets speed to 8 km/h on segment 1
- **AND** device transitions to segment 2
- **THEN** segment 2 is also cruised at 8 km/h
- **AND** speed does not reset between segments

#### Scenario: Speed Persists Across Loops

- **WHEN** loop mode is enabled and user sets speed to 6 km/h
- **AND** device completes one full loop and restarts
- **THEN** next loop iteration also uses 6 km/h
- **AND** user can change speed at any point in the loop

#### Scenario: Speed Range

- **WHEN** user adjusts speed slider
- **THEN** speed is clamped to 1-50 km/h range
- **AND** attempting to set 0 km/h results in 1 km/h
- **AND** attempting to set 100 km/h results in 50 km/h

---

## Requirement: Progress Tracking and UI Updates

UI displays current route progress, distance remaining, and ETA.

#### Scenario: Current Segment Display

- **WHEN** device is on segment 2 of 3
- **THEN** UI shows "Segment 2/3" or "Waypoint 1 → Waypoint 2"
- **AND** displays distance traveled so far: "5.2 km traveled"
- **AND** displays distance remaining: "7.6 km to destination"

#### Scenario: ETA Calculation

- **WHEN** device is moving at 5 km/h with 7.6 km remaining
- **THEN** ETA is calculated: 7.6 km ÷ 5 km/h = 91.2 minutes
- **AND** UI shows "ETA: 1h 31m" or similar
- **AND** ETA updates in real-time as speed or position changes
- **AND** ETA recalculates each movement step

#### Scenario: Loop Progress

- **WHEN** loop mode is enabled
- **THEN** UI shows current loop: "Loop 1/∞" (or "Loop 1 (infinite)")
- **AND** segment number resets per loop: "Segment 1/3, Loop 1"
- **AND** total distance traveled (across all loops) is tracked separately

#### Scenario: Real-Time Updates

- **WHEN** device is actively cruising
- **THEN** position, progress, and ETA update every 100-200ms (matching movement tick rate)
- **AND** updates are emitted via event system (routeUpdate)
- **AND** frontend receives updates and refreshes UI

---

## Requirement: Stop Route Cruise

User can stop the route cruise, clearing the route state and returning to idle.

#### Scenario: Stop Route Cruise

- **WHEN** route cruise is running or paused
- **AND** user clicks "Stop Route" button
- **THEN** device stops moving
- **AND** backend clears the route session
- **AND** UI returns to initial state: "Route: [previous route configuration]"
- **AND** "Start Route" button is re-enabled
- **AND** map still shows the route for potential restart

#### Scenario: Clear Route

- **WHEN** user wants to start a completely new route
- **AND** clicks "Clear Route" button
- **THEN** the previous route is deleted
- **AND** all waypoints are removed from map
- **AND** route state resets to empty
- **AND** UI shows "Route: 0 waypoints, Ready to click map"

---

## Requirement: Error Handling During Cruise

If errors occur during cruise (e.g., device unreachable), the system handles gracefully.

#### Scenario: Device Unreachable During Cruise

- **WHEN** device is moving and suddenly becomes unreachable
- **THEN** backend logs the error and pauses the cruise
- **AND** UI shows error: "Device unreachable. Cruise paused."
- **AND** user can click "Resume" to retry once device is back
- **AND** or click "Stop" to end the cruise

#### Scenario: Pathfinding Error on Loop Closure

- **WHEN** user has loop mode ON with 2 waypoints
- **AND** pathfinding fails for the loop closure segment
- **THEN** backend falls back to straight-line closure
- **AND** cruise can proceed normally
- **AND** warning is shown: "Loop return path is straight-line (routing unavailable)"
