## MODIFIED Requirements

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

#### Scenario: Disconnect device with no active tasks
- **WHEN** `disconnectDevice` is called for a device with no active cruise, route, or location
- **THEN** the backend SHALL return success (no-op cleanup is not an error)

## REMOVED Requirements

### Requirement: Disconnect clears selected device
**Reason**: The `_selected_device` singleton is removed. There is no backend-side "selected device" to clear.
**Migration**: Frontend manages selected device state locally. Disconnect clears frontend `selectedDevice` state directly.

### Requirement: Frontend state reset after disconnect
**Reason**: Replaced by new requirement below that accounts for badge state cleanup.
**Migration**: See new ADDED requirement.

## ADDED Requirements

### Requirement: Frontend state reset after disconnect
After a successful `disconnectDevice` response, the frontend SHALL reset all device-related UI state and clear the badge for that device.

#### Scenario: State reset on disconnect
- **WHEN** the `disconnectDevice` RPC call returns successfully
- **THEN** the frontend SHALL set `selectedDevice` to null, clear the location display, clear the tunnel status display, clear cruise status, clear route status, and clear route state
- **AND** the badge map entry for that device SHALL be removed
