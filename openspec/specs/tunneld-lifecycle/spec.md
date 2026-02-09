## ADDED Requirements

### Requirement: Backend checks tunneld on startup
The backend SHALL check if the tunneld daemon is running during initialization by querying its HTTP API at `http://127.0.0.1:49151/`. This check SHALL run in a background thread (non-blocking) so that other RPC methods (listDevices, etc.) are available immediately.

#### Scenario: Tunneld already running
- **WHEN** the backend starts and tunneld HTTP API responds successfully
- **THEN** the backend SHALL emit a `tunneldStatus` SSE event with `{ state: "ready" }`

#### Scenario: Tunneld not running
- **WHEN** the backend starts and tunneld HTTP API does not respond
- **THEN** the backend SHALL emit a `tunneldStatus` SSE event with `{ state: "starting" }` and attempt to start tunneld with admin privileges

### Requirement: Backend starts tunneld with admin privileges
When tunneld is not running, the backend SHALL start it using the platform-appropriate admin privilege mechanism (macOS: `osascript` with `with administrator privileges`; Linux: `pkexec`). The command SHALL be `python3 -m pymobiledevice3 remote tunneld -d`.

#### Scenario: Tunneld starts successfully
- **WHEN** tunneld is started and its HTTP API becomes responsive
- **THEN** the backend SHALL emit a `tunneldStatus` SSE event with `{ state: "ready" }`

#### Scenario: User cancels admin prompt
- **WHEN** the user cancels the macOS admin password dialog
- **THEN** the backend SHALL emit a `tunneldStatus` SSE event with `{ state: "error", error: "Admin authentication cancelled" }`

#### Scenario: Tunneld startup times out
- **WHEN** tunneld does not become responsive within the timeout period
- **THEN** the backend SHALL emit a `tunneldStatus` SSE event with `{ state: "error", error: "Tunnel did not become available" }`

### Requirement: Three tunneld-level states
The system SHALL track tunneld daemon status as one of three states: `starting`, `ready`, or `error`. These states are system-level (not per-device).

#### Scenario: State transitions on startup or retry
- **WHEN** the backend performs a tunneld check (startup or retry)
- **THEN** it SHALL transition through `starting` → `ready` (on success) or `starting` → `error` (on failure), emitting a `tunneldStatus` SSE event for each transition

#### Scenario: Tunneld killed externally
- **WHEN** tunneld is killed or crashes while the backend is running, and the next device query (`selectDevice`, `listDevices`, or location retry) detects tunneld is no longer responding
- **THEN** the backend SHALL transition from `ready` to `error` and emit a `tunneldStatus` SSE event with `{ state: "error", error: "tunneld stopped unexpectedly" }`

#### Scenario: Tunneld recovered externally
- **WHEN** tunneld is restarted externally (e.g., by the user) while the backend has state `error`, and the next device query detects tunneld is responding
- **THEN** the backend SHALL transition from `error` to `ready` and emit a `tunneldStatus` SSE event with `{ state: "ready" }`

### Requirement: retryTunneld RPC method
The backend SHALL expose a `retryTunneld` JSON-RPC method (no parameters) that re-runs the tunneld startup check. It SHALL reuse the same logic as the startup check: emit `starting` SSE, check tunneld, start if needed, emit `ready` or `error`.

#### Scenario: Retry when tunneld is down
- **WHEN** the frontend calls `retryTunneld` and tunneld is not running
- **THEN** the backend SHALL emit `tunneldStatus` with `{ state: "starting" }`, attempt to start tunneld, and emit `{ state: "ready" }` or `{ state: "error", error: "..." }` based on the result

#### Scenario: Retry when tunneld is already running
- **WHEN** the frontend calls `retryTunneld` and tunneld is already running
- **THEN** the backend SHALL emit `tunneldStatus` with `{ state: "starting" }` followed by `{ state: "ready" }`

### Requirement: SSE tunnel status change on retry
When the `_get_tunnel_for_device` callback (tunnel provider for LocationService retry) queries tunneld and the result differs from the last known status for that device (different address/port, tunnel appeared, or tunnel disappeared), the backend SHALL emit a `tunnelStatusChanged` SSE event.

#### Scenario: Tunnel info changed during retry
- **WHEN** LocationService retries a failed connection and the tunnel provider returns tunnel info that differs from the last known state for that device
- **THEN** the backend SHALL emit a `tunnelStatusChanged` SSE event with `{ udid, status: "connected", address, port }` or `{ udid, status: "no_tunnel" }`

#### Scenario: Tunnel info unchanged during retry
- **WHEN** LocationService retries and the tunnel provider returns the same info as last known
- **THEN** no `tunnelStatusChanged` SSE event SHALL be emitted

### Requirement: SSE uses data-only format
All SSE events SHALL be sent without the `event:` field (data-only format: `data: <json>\n\n`). The event type SHALL be included in the JSON payload as the `event` key. This ensures all events are received by the frontend via the `onmessage` handler without requiring per-event-type `addEventListener` registration.

#### Scenario: SSE event delivery
- **WHEN** the backend emits any SSE event (tunneldStatus, tunnelStatusChanged, cruiseUpdate, etc.)
- **THEN** the event SHALL be sent as `data: {"event": "<name>", "data": {...}}\n\n` without an `event:` field

### Requirement: Initial tunneld state on SSE connect
When an SSE client connects, the backend SHALL immediately send the current tunneld state as a `tunneldStatus` event. This ensures the frontend receives the correct state even if the background startup thread completed before any SSE client connected, or if the client reconnects after a disconnect.

#### Scenario: SSE client connects after tunneld is ready
- **WHEN** an SSE client connects and the tunneld state is `ready`
- **THEN** the backend SHALL send a `tunneldStatus` event with `{ state: "ready" }` immediately after the `connected` event

#### Scenario: SSE client connects while tunneld is starting
- **WHEN** an SSE client connects and the tunneld state is `starting`
- **THEN** the backend SHALL send a `tunneldStatus` event with `{ state: "starting" }` immediately, followed by the final state when the check completes

### Requirement: Remove startTunnel, stopTunnel, getTunnelStatus RPC methods
The backend SHALL remove the `startTunnel`, `stopTunnel`, and `getTunnelStatus` entries from the JSON-RPC method registry. These are replaced by `retryTunneld` and enriched `selectDevice`/`listDevices` responses.

#### Scenario: Old methods no longer available
- **WHEN** the frontend calls `startTunnel`, `stopTunnel`, or `getTunnelStatus`
- **THEN** the backend SHALL return a method-not-found error
