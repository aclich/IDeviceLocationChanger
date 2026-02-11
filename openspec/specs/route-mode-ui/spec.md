# Spec: Route Mode UI

## Feature: Enable/Disable Route Mode Toggle

Allow users to switch between direct location setting mode and waypoint-based route mode.

### Requirement: Route Mode Toggle

The app displays a toggle control in ControlPanel to enable/disable route mode. When enabled, subsequent map clicks add waypoints instead of setting location directly. When disabled, map clicks set location normally.

#### Scenario: Toggle Route Mode On

- **WHEN** the user clicks "Route Mode" toggle in ControlPanel
- **THEN** the toggle shows as "ON" with visual indicator
- **AND** text displays "Route Mode: ON, Click map to add waypoints"
- **AND** subsequent map clicks add waypoints instead of setting location
- **AND** the existing route (if any) is preserved

#### Scenario: Toggle Route Mode Off

- **WHEN** the user clicks "Route Mode" toggle while in route mode
- **THEN** the toggle shows as "OFF"
- **AND** text displays "Route Mode: OFF, Click map to set location"
- **AND** subsequent map clicks set device location directly (existing behavior)
- **AND** the route visualization remains on map (doesn't disappear)

#### Scenario: Start Fresh Route (Device Has Location)

- **WHEN** the user toggles route mode ON after clearing a previous route
- **AND** the device already has a location set
- **THEN** the route is empty but START will auto-set to device's current location on first click
- **AND** first map click adds waypoint 1 (START is auto-derived from device position)
- **AND** subsequent clicks add waypoints (2, 3, ...)

#### Scenario: Start Fresh Route (No Device Location)

- **WHEN** the user toggles route mode ON after clearing a previous route
- **AND** the device does NOT have a location set
- **THEN** the route is empty
- **AND** the first click on map sets the starting position (marked as "START")
- **AND** subsequent clicks add waypoints (1, 2, 3, ...)

---

## Requirement: Route Mode Persistence

Route mode state persists while toggled on, allowing the user to make multiple clicks before starting cruise.

#### Scenario: Add Multiple Waypoints While Route Mode On

- **WHEN** route mode is ON
- **AND** user clicks waypoint 1, then waypoint 2, then waypoint 3
- **THEN** route displays all three waypoints on map with polylines connecting them
- **AND** UI shows "Route: 3 waypoints, 0 km" (before pathfinding)
- **AND** user can continue clicking to add more waypoints

#### Scenario: Route Clears When Starting Cruise

- **WHEN** the user has 3 waypoints in the route
- **AND** clicks "Start Route" button to begin cruise
- **THEN** the route starts being followed
- **AND** after stopping the cruise, the route can be restarted
- **AND** to create a new route, user clicks "Clear Route" first

---

## Requirement: Visual Feedback for Route Mode State

The UI clearly indicates whether route mode is active and the current route state.

#### Scenario: Route Mode Indicator

- **WHEN** route mode is ON
- **THEN** ControlPanel shows toggle as "ON" with distinct color (e.g., blue/highlighted)
- **AND** status text shows "Route Mode: ON"
- **AND** if a route exists, shows "Route: 3 waypoints, 12.8 km" (with distance after pathfinding)

#### Scenario: No Waypoints State

- **WHEN** route mode is ON but no waypoints have been added
- **THEN** UI shows "Route: 0 waypoints, Ready to click map"
- **AND** the "Start Route" button is disabled (no route to start)

#### Scenario: Route Ready State

- **WHEN** route mode is ON and user has added at least one waypoint
- **THEN** UI shows "Route: N waypoints, X.X km"
- **AND** the "Start Route" button is enabled
- **AND** the "Undo" button is enabled (can remove last waypoint)

---

## Requirement: Mode Conflict Resolution

Only one cruise type (regular or route) can be active at a time. Switching between modes is handled gracefully.

#### Scenario: Start Route Cruise While Regular Cruise Is Running

- **WHEN** a regular (single-target) cruise is actively running
- **AND** user starts a route cruise
- **THEN** the regular cruise is automatically stopped
- **AND** route cruise begins normally
- **AND** no error or confirmation dialog is shown (seamless transition)

#### Scenario: Start Regular Cruise While Route Cruise Is Running

- **WHEN** a route cruise is actively running
- **AND** user starts a regular (single-target) cruise
- **THEN** the route cruise is automatically stopped
- **AND** regular cruise begins normally
- **AND** the route visualization remains on the map (route is not cleared)

#### Scenario: Switch to Joystick Mode During Route Cruise

- **WHEN** route cruise is actively running
- **AND** user switches to joystick mode
- **THEN** route cruise is automatically paused (not stopped)
- **AND** UI shows "Route Cruise: Paused"
- **AND** user can control device position manually via joystick
- **AND** user can resume route cruise later (device continues from its new position toward next waypoint)

#### Scenario: Switch to Direct Mode During Route Cruise

- **WHEN** route cruise is actively running
- **AND** user switches to direct mode (clicks map to set location)
- **THEN** route cruise is automatically paused (not stopped)
- **AND** user can set device location manually
- **AND** route visualization remains on map
- **AND** user can resume route cruise later from the new location

#### Scenario: Switch Device While Route Cruise Is Running

- **WHEN** route cruise is running on device A
- **AND** user switches to device B in the UI
- **THEN** route cruise continues running on device A in the backend (not paused or stopped)
- **AND** UI reflects device B's state from `getDeviceState` query
- **AND** switching back to device A restores the route cruise UI state via `getDeviceState`
- **AND** SSE events for device A's route cruise update badge state (not full UI state) while device B is selected

---

### Requirement: Route mode auto-activates on device switch
When switching to a device that has route state (definition or active cruise), the UI SHALL automatically enter Route mode.

#### Scenario: Switch to device with route definition
- **WHEN** the user switches to a device that has a route definition with waypoints
- **AND** the device is NOT actively route cruising
- **THEN** the UI SHALL switch to Route mode
- **AND** the route waypoints and polylines SHALL be displayed on the map

#### Scenario: Switch to device with active route cruise
- **WHEN** the user switches to a device that has an active route cruise
- **THEN** the UI SHALL switch to Route mode
- **AND** the route cruise progress SHALL be displayed

#### Scenario: Switch to device with no route
- **WHEN** the user switches to a device that has no route definition
- **THEN** the route mode toggle SHALL NOT be changed (keep current mode)
