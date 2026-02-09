# Design: Simplify Tunnel Management UX

## Context

The current tunnel UX requires users to manually click "Start Tunnel" for iOS 17+ physical devices. This involves understanding what tunneld is and managing it through a dedicated button. The user sees a full "iOS 17+ Tunnel" section with status indicator, message, and Start/Stop buttons.

The tunneld daemon (from pymobiledevice3) runs as a system-level process on port 49151 with an HTTP API. It auto-discovers connected USB devices and creates tunnels for them. The app's "Start Tunnel" button was essentially a workaround for "tunneld isn't running yet" — once tunneld is running, tunnel info is available by simply querying the HTTP API.

Current backend:
- `TunnelManager._is_tunneld_running()` checks via HTTP GET to `:49151`
- `TunnelManager._query_tunneld_http(udid)` finds tunnel for specific device
- `TunnelManager.start_tunnel(udid)` checks for existing tunnel, then starts tunneld/lockdown with admin privileges if needed
- `LocationService._set_via_tunnel_with_retry()` already queries fresh tunnel info from tunneld on connection failure via a `_tunnel_provider` callback

Current frontend:
- `DevicePanel` renders a tunnel section with status dot, message, and Start/Stop button
- `useBackend` exposes `startTunnel()`, `stopTunnel()`, `getTunnelStatus()` functions
- SSE events exist for cruise/route but NOT for tunnel status changes

## Goals / Non-Goals

**Goals:**
- Zero-click tunnel management in the happy path (tunneld running + device plugged in)
- Automatic tunneld startup on backend initialization (non-blocking)
- Clear differentiation between "tunneld not running" (system-level) and "no tunnel for device" (device-level)
- Tunnel status updates via SSE when LocationService retry detects changes
- Clean device disconnect flow with [X] button

**Non-Goals:**
- Background polling for tunnel status (queries only on explicit triggers)
- Stopping/killing tunneld from the app (tunneld is infrastructure, let it run)
- Per-device tunnel start/stop controls (tunneld manages device tunnels automatically)
- Changing LocationService retry logic (it already works correctly)

## Decisions

### D1: Tunneld startup as background thread in `__init__`

**Decision:** Launch `ensure_tunneld()` in a `threading.Thread(daemon=True)` during `LocationSimulatorServer.__init__`, emitting SSE events for state transitions.

**Rationale:** Non-blocking means device listing and other RPC calls work immediately. The frontend shows "Starting tunneld..." while the check runs. If tunneld is already running, the thread completes in ~1 second (HTTP query timeout). If not, the admin prompt appears and the thread waits up to 60s.

**Alternative considered:** Lazy check on first `selectDevice` call. Rejected because the admin prompt would surprise users mid-workflow, and the "starting" state wouldn't have a natural place in the UI.

### D2: Three tunneld-level states via SSE

**Decision:** Emit `tunneldStatus` SSE event with `state` field: `starting`, `ready`, or `error`.

```
Event: tunneldStatus
Data:  { state: "starting" }           // check in progress
       { state: "ready" }              // tunneld HTTP API responding
       { state: "error", error: "..." }  // failed (admin cancelled, timeout)
```

**Rationale:** These are system-level states (not per-device). The frontend maintains a `tunneldState` variable and shows/hides the error banner based on it. The `starting` state prevents a flash of error on app startup.

**SSE emission points:**
- Backend startup thread: emits `starting` → `ready` or `error`
- `retryTunneld` RPC handler: emits `starting` → `ready` or `error`

### D3: Enrich `selectDevice` and `listDevices` responses with tunnel info

**Decision:** When `selectDevice` is called for a physical device, query tunneld for that device's tunnel info and include it in the response. When `listDevices` is called, query tunneld for all discovered physical devices.

`selectDevice` response:
```json
{
  "success": true,
  "device": { "id": "...", "name": "...", "type": "physical" },
  "tunnel": {
    "status": "connected",
    "address": "fdc2:9a08:dc6d::1",
    "port": 56583
  }
}
```

If no tunnel: `"tunnel": { "status": "no_tunnel" }`
If tunneld not running: `"tunnel": { "status": "tunneld_not_running" }`
Simulators: `"tunnel"` field omitted (not applicable).

`listDevices` response — tunnel info embedded per device:
```json
{
  "devices": [
    { "id": "...", "name": "...", "type": "physical",
      "tunnel": { "status": "connected", "address": "...", "port": 56583 } },
    { "id": "...", "name": "...", "type": "simulator" }
  ]
}
```

**Rationale:** Single RPC call gives frontend everything it needs. No separate `getTunnelStatus` round-trip. The `listDevices` enrichment means the refresh button also refreshes tunnel info.

**Alternative considered:** Keep `getTunnelStatus` as separate call. Rejected because it adds latency and complexity for the frontend to correlate two responses.

### D4: SSE for tunnel status changes during retry

**Decision:** When `LocationService._set_via_tunnel_with_retry()` queries fresh tunnel info via `_tunnel_provider` and the result differs from what was last known (different address/port, or tunnel appeared/disappeared), emit a `tunnelStatusChanged` SSE event.

```
Event: tunnelStatusChanged
Data:  { udid: "...", status: "connected", address: "...", port: 56583 }
       { udid: "...", status: "no_tunnel" }
```

**Implementation:** The `_get_tunnel_for_device` callback in `main.py` (which wraps `tunnel.get_tunnel(udid)`) compares the result against `tunnel._last_status[udid]` and emits SSE if changed.

**Rationale:** This is the only place where tunnel info can change without user action — during automatic retry after location failure. The frontend needs to know so it can update the displayed tunnel info.

### D5: `retryTunneld` RPC method replaces `startTunnel`

**Decision:** Add `retryTunneld` RPC method (no params). Remove `startTunnel`, `stopTunnel`, `getTunnelStatus` from the method registry.

`retryTunneld` reuses the same `ensure_tunneld()` logic as startup: emit `starting` SSE, check if tunneld running, start if not, emit `ready` or `error`.

**Rationale:** The retry button in the error banner is the only remaining user-initiated tunnel action. It operates at the tunneld daemon level (not per-device), so it doesn't need a UDID parameter.

### D6: `disconnectDevice` RPC method

**Decision:** Add `disconnectDevice` RPC method with `{deviceId}` param. Backend:
1. Stop any active cruise for the device (`cruise.stop(deviceId)`)
2. Stop any active route cruise for the device (`route.stop(deviceId)`)
3. Close location connection (`location.close_connection(deviceId)`)
4. Clear selected device if it matches

Frontend after successful response:
1. Set `selectedDevice` to null
2. Clear location, tunnel status, cruise status, route status display

**Rationale:** Clean separation — backend handles task cleanup, frontend handles UI state reset. No tunnel process is killed (tunneld keeps running).

### D7: [X] button placement and confirmation

**Decision:** [X] button appears on the selected device row only (not on unselected devices). Clicking shows a browser `window.confirm()` dialog: "This will disconnect location simulation for [device name]. Continue?"

**Rationale:** Simple native confirm dialog is sufficient — no need for a custom modal component. The X is only shown on the selected device since unselected devices have no active state to clear.

### D8: Address/port display format

**Decision:** Display tunnel address and port separated by a space: `Connected (fdc2:9a08:dc6d::1 56583)`. Currently uses colon separator which is confusing with IPv6.

**Rationale:** IPv6 addresses contain colons. Using space as separator eliminates ambiguity.

## Risks / Trade-offs

**[Risk] Admin prompt on startup may confuse users who don't have physical devices**
→ Only attempt tunneld startup if not already running. If tunneld is already running (common after first use since it persists), no prompt appears. If the user cancels, the app works fine for simulators — the error banner specifically says "Physical iOS 17+ devices won't work."

**[Risk] `selectDevice` becomes slower for physical devices (adds tunneld HTTP query)**
→ The tunneld HTTP query has a 2-second timeout (existing `_query_tunneld_http`). In practice it responds in <100ms when running. If tunneld is down, the query fails fast and returns `tunneld_not_running` status.

**[Risk] Removing `startTunnel`/`stopTunnel` RPC methods is a breaking API change**
→ These methods are only called by the frontend, which is updated in the same change. No external consumers of the JSON-RPC API exist.

**[Trade-off] No background tunnel monitoring means stale status is possible**
→ Accepted: Tunnel status only updates on selectDevice, listDevices (refresh), or retry. If a tunnel drops between these events, the UI won't know until the next interaction. This is acceptable because (1) location retry handles it automatically, and (2) the user can click refresh to get current state.
