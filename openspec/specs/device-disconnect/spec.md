## ADDED Requirements

### Requirement: Disconnect button on selected device
The DevicePanel SHALL display an [X] button on the currently selected device row. Unselected device rows SHALL NOT display the [X] button.

#### Scenario: Device is selected
- **WHEN** a device is selected in the device list
- **THEN** an [X] button SHALL appear on that device's row

#### Scenario: Device is not selected
- **WHEN** a device is not selected
- **THEN** no [X] button SHALL appear on that device's row

### Requirement: Disconnect confirmation dialog
When the user clicks the [X] button, the frontend SHALL display a confirmation dialog before proceeding with the disconnect.

#### Scenario: User confirms disconnect
- **WHEN** the user clicks [X] and confirms the dialog "This will disconnect location simulation for [device name]. Continue?"
- **THEN** the frontend SHALL call the `disconnectDevice` RPC method with the device ID

#### Scenario: User cancels disconnect
- **WHEN** the user clicks [X] and cancels the confirmation dialog
- **THEN** no action SHALL be taken; the device remains selected

### Requirement: disconnectDevice RPC method
The backend SHALL expose a `disconnectDevice` JSON-RPC method that accepts `{deviceId}` and cleans up all active tasks for that device.

#### Scenario: Disconnect device with active cruise
- **WHEN** `disconnectDevice` is called for a device that has an active cruise session
- **THEN** the backend SHALL stop the cruise session for that device

#### Scenario: Disconnect device with active route cruise
- **WHEN** `disconnectDevice` is called for a device that has an active route cruise session
- **THEN** the backend SHALL stop the route cruise session for that device

#### Scenario: Disconnect device with active location connection
- **WHEN** `disconnectDevice` is called for a device that has an active location connection
- **THEN** the backend SHALL close the location connection for that device

#### Scenario: Disconnect clears selected device
- **WHEN** `disconnectDevice` is called and the device matches the currently selected device
- **THEN** the backend SHALL clear the selected device state

#### Scenario: Disconnect device with no active tasks
- **WHEN** `disconnectDevice` is called for a device with no active cruise, route, or location
- **THEN** the backend SHALL return success (no-op cleanup is not an error)

### Requirement: Frontend state reset after disconnect
After a successful `disconnectDevice` response, the frontend SHALL reset all device-related UI state.

#### Scenario: State reset on disconnect
- **WHEN** the `disconnectDevice` RPC call returns successfully
- **THEN** the frontend SHALL set `selectedDevice` to null, clear the location display, clear the tunnel status display, clear cruise status, and clear route status
