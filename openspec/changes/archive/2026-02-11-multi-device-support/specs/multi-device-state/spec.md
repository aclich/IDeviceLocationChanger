## ADDED Requirements

### Requirement: getDeviceState RPC method
The backend SHALL expose a `getDeviceState` JSON-RPC method that accepts `{deviceId}` and returns an aggregated snapshot of all state for that device.

#### Scenario: Device with active cruise
- **WHEN** `getDeviceState` is called for a device that has an active cruise session
- **THEN** the response SHALL include `cruise` with the full cruise session state (deviceId, targetLat, targetLng, speed, currentLat, currentLng, isPaused, bearing, remainingDistance)
- **AND** `location` SHALL reflect the cruise's current position

#### Scenario: Device with active route cruise
- **WHEN** `getDeviceState` is called for a device that has an active route cruise session
- **THEN** the response SHALL include `routeCruise` with the route cruise session state (deviceId, currentSegmentIndex, totalSegments, isPaused, loopCount, currentLocation)
- **AND** `route` SHALL include the route definition (waypoints, segments, loopMode)

#### Scenario: Device with route definition but no active cruise
- **WHEN** `getDeviceState` is called for a device that has a route definition but no active route cruise
- **THEN** the response SHALL include `route` with the route definition (waypoints, segments, loopMode)
- **AND** `routeCruise` SHALL be null

#### Scenario: Idle device with last location
- **WHEN** `getDeviceState` is called for an idle device (no cruise, no route) that has a persisted last location
- **THEN** the response SHALL include `location` from LastLocationService
- **AND** `cruise`, `route`, and `routeCruise` SHALL be null

#### Scenario: Device with no state
- **WHEN** `getDeviceState` is called for a device that has no persisted state at all
- **THEN** the response SHALL return all fields as null

#### Scenario: Device with tunnel
- **WHEN** `getDeviceState` is called for a physical device that has an active tunnel
- **THEN** the response SHALL include `tunnel` with status, address, port, and udid

#### Scenario: Device with location refresh active
- **WHEN** `getDeviceState` is called for a device that has a location refresh task running
- **THEN** the response SHALL include `isRefreshing: true`

### Requirement: getAllDeviceStates RPC method
The backend SHALL expose a `getAllDeviceStates` JSON-RPC method that returns lightweight badge-level state for all devices with active tasks.

#### Scenario: Multiple devices with active tasks
- **WHEN** `getAllDeviceStates` is called and device A is cruising and device B is route cruising at segment 3 of 5
- **THEN** the response SHALL be a dictionary keyed by deviceId, where device A's entry includes `{cruising: true, cruisePaused: false, routeCruising: false, routePaused: false, routeProgress: null}` and device B's entry includes `{cruising: false, cruisePaused: false, routeCruising: true, routePaused: false, routeProgress: "3/5"}`

#### Scenario: No active devices
- **WHEN** `getAllDeviceStates` is called and no devices have active tasks
- **THEN** the response SHALL be an empty dictionary `{}`

#### Scenario: Paused cruise device
- **WHEN** `getAllDeviceStates` is called and a device has a paused cruise session
- **THEN** that device's entry SHALL include `{cruising: true, cruisePaused: true}`

### Requirement: Remove selectDevice RPC method
The backend SHALL NOT expose a `selectDevice` JSON-RPC method. The `_selected_device` singleton field SHALL be removed from the server class.

#### Scenario: selectDevice call rejected
- **WHEN** a client sends a `selectDevice` RPC call
- **THEN** the backend SHALL return a method-not-found error

#### Scenario: RPC methods without deviceId
- **WHEN** an RPC method that requires a device (e.g., `setLocation`) is called without `deviceId` in params
- **THEN** the backend SHALL return an error indicating `deviceId` is required (no fallback to a selected device)
