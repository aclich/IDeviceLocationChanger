# Proposal: Simplify Tunnel Management UX

## Why

The current tunnel management UX requires users to manually click "Start Tunnel" for iOS 17+ physical devices before they can simulate location. Users must understand what tunneld is, when to start it, and manage its lifecycle through a dedicated button. This creates unnecessary friction — especially for first-time users who don't realize a tunnel is required. The app should handle tunneld lifecycle automatically and present tunnel status as read-only information, reducing the tunnel interaction to zero clicks in the happy path.

## What Changes

- **Auto-start tunneld on backend startup**: Backend checks if tunneld is running on startup (non-blocking). If not running, starts it with admin privileges. Frontend shows a "Starting tunneld..." state during this process.
- **Error banner with retry**: If tunneld fails to start (user cancels admin prompt, timeout, crash), frontend shows an error banner with a [Retry] button. Banner disappears when tunneld is confirmed running.
- **Three tunneld-level states**: `starting` (spinner during startup/retry), `ready` (banner hidden, normal operation), `error` (banner with retry).
- **Enrich `selectDevice` with tunnel info**: When a device is selected, backend queries tunneld for that device's tunnel and returns it alongside device info. No separate `getTunnelStatus` call needed.
- **Enrich `listDevices` (refresh) with tunnel info**: Refresh button now also queries tunnel status for all discovered devices.
- **Remove Start/Stop Tunnel buttons**: Tunnel section becomes read-only status display showing "Connected (addr port)" or "No tunnel".
- **Differentiate "tunneld not running" vs "no tunnel for device"**: "tunneld not running" is a system-level error (banner). "No tunnel for this device" is a device-level status (inline, gray).
- **Add [X] disconnect button on selected device**: An X button on the selected device row to disconnect. Shows confirmation dialog ("This will disconnect location simulation"), then clears backend tasks (cruise, route, location) and unselects device on frontend.
- **SSE for tunnel status changes on retry**: When LocationService retries a failed connection and gets updated tunnel info from tunneld, backend emits SSE event so frontend can update tunnel display without user action.
- **Address/port display format**: Show tunnel address and port separated by space (not colon) to avoid confusion with IPv6. E.g., `Connected (fdc2:9a08:dc6d::1 56583)`.

## Capabilities

### New Capabilities
- `tunneld-lifecycle`: Automatic tunneld daemon management — startup check, non-blocking start with admin privileges, three-state model (starting/ready/error), retry mechanism, SSE status events.
- `tunnel-status-display`: Read-only tunnel status in DevicePanel — device-level tunnel info from enriched selectDevice/listDevices responses, tunneld-level error banner with retry, "Connected (addr port)" / "No tunnel" inline display.
- `device-disconnect`: [X] button on selected device to disconnect — confirmation dialog, backend task cleanup (cruise, route, location), frontend state reset (unselect device, clear location/tunnel info).

### Modified Capabilities
_(No existing specs affected — tunnel management and device panel are not currently spec'd.)_

## Impact

### Backend (`backend/`)
- **`main.py`**: Add tunneld startup check on init (background thread). Enrich `selectDevice` and `listDevices` responses with tunnel info. Add new `retryTunneld` RPC method for retry button. Remove or deprecate `startTunnel` / `stopTunnel` RPC methods. Add device disconnect RPC that clears cruise/route/location tasks.
- **`services/tunnel_manager.py`**: Add `ensure_tunneld_running()` method for startup. Add `is_tunneld_running()` public method. SSE emission on tunnel status changes during retry. Keep `get_tunnel(udid)` and `start_tunnel(udid)` internally but they're no longer exposed as direct user actions.
- **`services/event_bus.py`**: No changes — existing SSE infrastructure is sufficient.

### Frontend (`src/`)
- **`src/components/DevicePanel.jsx`**: Remove tunnel-section buttons (Start/Stop). Add error banner component with retry. Add [X] button on selected device row. Tunnel status becomes read-only line. Update status display to use space separator for addr/port.
- **`src/hooks/useBackend.js`**: Remove `startTunnel` / `stopTunnel` functions. Add `retryTunneld` function. Update `selectDevice` to consume tunnel info from response. Add SSE listener for `tunneldStatus` and `tunnelStatusChanged` events. Add `disconnectDevice` function. Add tunneld-level state (starting/ready/error).
- **`src/App.jsx`**: Remove `onStartTunnel` / `onStopTunnel` props passed to DevicePanel. Add tunneld state management. Wire up disconnect flow.

### No changes to
- Cruise/route/location services (internal logic unchanged)
- Favorites, port forwarding, debug features
- Electron/IPC layer (JSON-RPC interface shape changes but transport doesn't)
