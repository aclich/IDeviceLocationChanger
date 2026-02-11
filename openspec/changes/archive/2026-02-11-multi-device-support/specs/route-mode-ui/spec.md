## MODIFIED Requirements

### Requirement: Mode Conflict Resolution

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

## ADDED Requirements

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
