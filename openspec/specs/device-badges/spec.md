# Spec: Device Badges

### Requirement: Device list shows status badges
The DevicePanel SHALL display a status badge on each non-selected device row that has active backend tasks.

#### Scenario: Device is cruising
- **WHEN** a non-selected device has an active cruise session
- **THEN** the device row SHALL display a "cruising..." badge

#### Scenario: Device has paused cruise
- **WHEN** a non-selected device has a paused cruise session
- **THEN** the device row SHALL display a "paused" badge

#### Scenario: Device is route cruising
- **WHEN** a non-selected device has an active route cruise at segment 3 of 5
- **THEN** the device row SHALL display a "route 3/5" badge

#### Scenario: Device has paused route cruise
- **WHEN** a non-selected device has a paused route cruise
- **THEN** the device row SHALL display a "route paused" badge

#### Scenario: Device is idle
- **WHEN** a non-selected device has no active tasks
- **THEN** the device row SHALL NOT display any badge

#### Scenario: Selected device does not show badge
- **WHEN** a device is selected (active view)
- **THEN** the device row SHALL NOT display a badge (full state is shown in the main UI)

### Requirement: Badge state driven by SSE events
The frontend SHALL maintain a `Map<deviceId, BadgeState>` that is updated from ALL SSE events regardless of which device is selected.

#### Scenario: Cruise starts on background device
- **WHEN** a `cruiseStarted` SSE event arrives for a non-selected device
- **THEN** the badge map SHALL update to show `cruising: true` for that device
- **AND** the device row badge SHALL immediately reflect the change

#### Scenario: Cruise arrives on background device
- **WHEN** a `cruiseArrived` SSE event arrives for a non-selected device
- **THEN** the badge map SHALL clear the cruising state for that device
- **AND** the badge SHALL disappear from the device row

#### Scenario: Route cruise progresses on background device
- **WHEN** a `routeSegmentComplete` SSE event arrives for a non-selected device indicating segment 3 of 5
- **THEN** the badge map SHALL update `routeProgress` to "3/5" for that device

### Requirement: Badge state seeded on initial load
The frontend SHALL call `getAllDeviceStates` on initial load to seed the badge state map for devices that already have active tasks.

#### Scenario: Frontend loads with active background cruises
- **WHEN** the frontend loads and two devices are cruising in the backend
- **THEN** after the initial `getAllDeviceStates` call, both devices SHALL show badges in the device list

#### Scenario: SSE reconnection re-seeds badge state
- **WHEN** the SSE connection drops and reconnects
- **THEN** the frontend SHALL re-call `getAllDeviceStates` to resynchronize badge state
