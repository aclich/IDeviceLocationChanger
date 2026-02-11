## ADDED Requirements

### Requirement: Device switch queries backend state
When the user clicks a different device in the device list, the frontend SHALL call `getDeviceState` and populate all device-specific UI state from the response.

#### Scenario: Switch to device with active cruise
- **WHEN** the user clicks a device that has an active cruise in the backend
- **THEN** the frontend SHALL set `location` to the cruise's current position
- **AND** set `cruiseStatus` to the cruise session state
- **AND** the map SHALL show the cruise target marker and movement indicator

#### Scenario: Switch to device with route and route cruise
- **WHEN** the user clicks a device that has a route definition and an active route cruise
- **THEN** the frontend SHALL set `routeState` to the route definition (waypoints, segments)
- **AND** set `routeStatus` to the route cruise session state
- **AND** set `location` to the route cruise's current position
- **AND** the map SHALL show waypoint markers, route polylines, and cruise progress

#### Scenario: Switch to device with route but no active cruise
- **WHEN** the user clicks a device that has a route definition but no active cruise
- **THEN** the frontend SHALL set `routeState` to the route definition
- **AND** set `routeStatus` to null
- **AND** the map SHALL show waypoint markers and route polylines without cruise animation

#### Scenario: Switch to idle device with last location
- **WHEN** the user clicks a device that is idle with only a persisted last location
- **THEN** the frontend SHALL set `location` to the last known position
- **AND** clear `cruiseStatus`, `routeStatus`, and `routeState`

#### Scenario: Switch to device with no state
- **WHEN** the user clicks a device that has no backend state
- **THEN** the frontend SHALL clear `location`, `cruiseStatus`, `routeStatus`, and `routeState`

### Requirement: Pending location preserved on switch
The pending location (uncommitted map click) SHALL NOT be discarded when switching devices. It is global UI state.

#### Scenario: Pending location survives device switch
- **WHEN** the user clicks the map to create a pending location marker
- **AND** then switches to a different device
- **THEN** the pending location marker SHALL remain visible on the map
- **AND** clicking "Set Location" SHALL apply the pending location to the newly selected device

### Requirement: Auto UI mode on device switch
When switching to a device, the frontend SHALL automatically set the UI mode based on the device's backend state.

#### Scenario: Switch to device with route state
- **WHEN** the user switches to a device that has a route definition (cruising or not)
- **THEN** the UI SHALL automatically switch to Route mode

#### Scenario: Switch to device with regular cruise
- **WHEN** the user switches to a device that has an active or paused regular cruise (not route cruise)
- **THEN** the UI SHALL automatically switch to Cruise mode (non-route panel)

#### Scenario: Switch to idle device
- **WHEN** the user switches to a device that has no cruise and no route
- **THEN** the UI SHALL keep the current mode unchanged (user's prior intent preserved)

### Requirement: Speed slider sticky behavior
The speed slider SHALL only be updated from the backend when the device has an active speed setting. Otherwise it SHALL retain its current value.

#### Scenario: Switch to cruising device
- **WHEN** the user switches to a device that is actively cruising at 80 km/h
- **AND** the speed slider was previously set to 20 km/h
- **THEN** the speed slider SHALL update to 80 km/h

#### Scenario: Switch to idle device
- **WHEN** the user switches to a device with no active cruise
- **AND** the speed slider was previously set to 80 km/h
- **THEN** the speed slider SHALL remain at 80 km/h

### Requirement: SSE event filtering by selected device
The frontend SSE handler SHALL only apply full state updates for events whose `deviceId` matches the currently selected device.

#### Scenario: SSE event for selected device
- **WHEN** an SSE event arrives with `deviceId` matching the currently selected device
- **THEN** the frontend SHALL update the corresponding state (cruiseStatus, location, routeStatus, etc.)

#### Scenario: SSE event for non-selected device
- **WHEN** an SSE event arrives with `deviceId` NOT matching the currently selected device
- **THEN** the frontend SHALL NOT update full state (location, cruiseStatus, routeStatus)
- **AND** the event SHALL still be processed for badge state updates

### Requirement: Loading overlay during device switch
The frontend SHALL display a loading overlay while the `getDeviceState` call is in progress, to indicate that the device switch is being processed.

#### Scenario: Loading overlay shown during switch
- **WHEN** the user clicks a different device in the device list
- **THEN** a loading overlay SHALL appear over the main content area immediately
- **AND** the overlay SHALL remain visible until the `getDeviceState` response is received and state is populated

#### Scenario: Loading overlay dismissed on success
- **WHEN** the `getDeviceState` call completes successfully
- **THEN** the loading overlay SHALL be dismissed
- **AND** the UI SHALL display the new device's state

#### Scenario: Loading overlay dismissed on error
- **WHEN** the `getDeviceState` call fails
- **THEN** the loading overlay SHALL be dismissed
- **AND** an error message SHALL be displayed to the user

### Requirement: State restore on frontend refresh
When the frontend loads or refreshes, if a device was previously selected, the frontend SHALL call `getDeviceState` to restore that device's full state.

#### Scenario: Frontend refresh with selected device
- **WHEN** the frontend refreshes while a device was selected
- **AND** that device has active cruise or route state in the backend
- **THEN** the frontend SHALL restore all state from `getDeviceState` and resume showing the correct UI
