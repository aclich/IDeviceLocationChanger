## ADDED Requirements

### Requirement: Enriched selectDevice response with tunnel info
When `selectDevice` is called for a physical device, the backend SHALL query tunneld for that device's tunnel info and include it in the response as a `tunnel` field. For simulators, the `tunnel` field SHALL be omitted.

#### Scenario: Physical device with active tunnel
- **WHEN** a physical device is selected and tunneld has a tunnel for it
- **THEN** the response SHALL include `"tunnel": { "status": "connected", "address": "<addr>", "port": <port> }`

#### Scenario: Physical device with no tunnel
- **WHEN** a physical device is selected and tunneld is running but has no tunnel for it
- **THEN** the response SHALL include `"tunnel": { "status": "no_tunnel" }`

#### Scenario: Physical device when tunneld is not running
- **WHEN** a physical device is selected and tunneld HTTP API is not responding
- **THEN** the response SHALL include `"tunnel": { "status": "tunneld_not_running" }`

#### Scenario: Simulator device selected
- **WHEN** a simulator device is selected
- **THEN** the response SHALL NOT include a `tunnel` field

### Requirement: Enriched listDevices response with tunnel info
When `listDevices` is called, the backend SHALL query tunneld and embed tunnel info in each physical device object in the response. Simulator devices SHALL NOT include tunnel info.

#### Scenario: Device list with mixed device types
- **WHEN** the device list contains both physical and simulator devices
- **THEN** each physical device object SHALL include a `tunnel` field with `status`, and optionally `address` and `port`; simulator device objects SHALL NOT include a `tunnel` field

### Requirement: Tunneld error banner with retry
The frontend SHALL display an error banner at the top of the DevicePanel when tunneld state is `error`. The banner SHALL include a message indicating that physical iOS 17+ devices won't work and a [Retry] button that calls the `retryTunneld` RPC method.

#### Scenario: Tunneld fails to start
- **WHEN** the frontend receives a `tunneldStatus` SSE event with `{ state: "error" }`
- **THEN** an error banner SHALL be displayed with the error message and a [Retry] button

#### Scenario: Tunneld becomes ready
- **WHEN** the frontend receives a `tunneldStatus` SSE event with `{ state: "ready" }`
- **THEN** the error banner SHALL be hidden

#### Scenario: Tunneld starting
- **WHEN** the frontend receives a `tunneldStatus` SSE event with `{ state: "starting" }`
- **THEN** a banner SHALL be displayed showing "Starting tunneld..." with a spinner (not an error state)

#### Scenario: User clicks retry
- **WHEN** the user clicks the [Retry] button on the error banner
- **THEN** the frontend SHALL call the `retryTunneld` RPC method and the banner SHALL show the "starting" state with spinner

### Requirement: Read-only tunnel status display
The DevicePanel SHALL display tunnel status as a read-only line below the device list. The tunnel section SHALL NOT contain any Start/Stop buttons.

#### Scenario: Tunnel connected
- **WHEN** a physical device is selected and has an active tunnel
- **THEN** the tunnel status SHALL display "Connected (<address> <port>)" with a green indicator, using a space (not colon) between address and port

#### Scenario: No tunnel for device
- **WHEN** a physical device is selected and has no tunnel
- **THEN** the tunnel status SHALL display "No tunnel" with a gray indicator

#### Scenario: Simulator selected
- **WHEN** a simulator device is selected
- **THEN** the tunnel status section SHALL be hidden (not applicable)

#### Scenario: No device selected
- **WHEN** no device is selected
- **THEN** the tunnel status section SHALL be hidden

### Requirement: Frontend tunnel status updates via SSE
The frontend SHALL listen for `tunnelStatusChanged` SSE events and update the displayed tunnel status for the corresponding device without requiring user action.

#### Scenario: Tunnel status changes for selected device
- **WHEN** a `tunnelStatusChanged` SSE event is received for the currently selected device
- **THEN** the tunnel status display SHALL update to reflect the new status (connected with new address/port, or no_tunnel)

#### Scenario: Tunnel status changes for non-selected device
- **WHEN** a `tunnelStatusChanged` SSE event is received for a device that is not currently selected
- **THEN** no visible UI change SHALL occur (the info is stored for when that device is selected)

### Requirement: Remove Start/Stop Tunnel buttons
The DevicePanel SHALL NOT render Start Tunnel or Stop Tunnel buttons. The `onStartTunnel` and `onStopTunnel` props SHALL be removed from DevicePanel. The `startTunnel` and `stopTunnel` functions SHALL be removed from useBackend.

#### Scenario: DevicePanel rendered
- **WHEN** the DevicePanel component is rendered
- **THEN** no Start Tunnel or Stop Tunnel buttons SHALL be present
