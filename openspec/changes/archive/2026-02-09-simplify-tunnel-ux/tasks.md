## 1. Backend: Tunneld Lifecycle

- [x] 1.1 Add `ensure_tunneld()` method to `TunnelManager` that checks if tunneld is running via HTTP, starts it with admin privileges if not, and returns the final state (`ready` or `error` with message). Reuse existing `_is_tunneld_running()` and `_start_tunneld_macos()`/`_start_tunnel_linux()` logic.
- [x] 1.2 Add `_tunneld_state` field to `TunnelManager` tracking current daemon state (`starting`, `ready`, `error`) and an event emitter callback for SSE.
- [x] 1.3 Launch `ensure_tunneld()` in a background `threading.Thread(daemon=True)` during `LocationSimulatorServer.__init__`. Emit `tunneldStatus` SSE events for each state transition (`starting` → `ready` or `error`).
- [x] 1.4 Add `retryTunneld` RPC method to `main.py` (no params) that calls `ensure_tunneld()` in a background thread, reusing the same logic and SSE emission as startup. Register in `self._methods`.
- [x] 1.5 Remove `startTunnel`, `stopTunnel`, `getTunnelStatus` from `self._methods` registry and delete the corresponding `_start_tunnel`, `_stop_tunnel`, `_get_tunnel_status` handler methods from `main.py`.

## 2. Backend: Enriched RPC Responses

- [x] 2.1 Add a helper method `_get_tunnel_info_for_device(device)` in `main.py` that queries tunneld for a physical device and returns a tunnel info dict (`{ status, address?, port? }`) or `None` for simulators. Handle three cases: connected, no_tunnel, tunneld_not_running.
- [x] 2.2 Modify `_select_device` to call `_get_tunnel_info_for_device()` and include the result as a `tunnel` field in the response for physical devices.
- [x] 2.3 Modify `_list_devices` to query tunneld for all physical devices and embed `tunnel` info in each device dict in the response.

## 3. Backend: SSE on Tunnel Status Change During Retry

- [x] 3.1 Modify `_get_tunnel_for_device` callback in `main.py` to compare the tunnel query result against `tunnel._last_status[udid]` before returning. If the status changed (different address/port, appeared, or disappeared), emit a `tunnelStatusChanged` SSE event via `event_bus.publish_sync()`.

## 4. Backend: Device Disconnect

- [x] 4.1 Add `_disconnect_device` handler method in `main.py` that accepts `{deviceId}`, stops cruise (`cruise.stop(deviceId)`), stops route cruise (`route.stop(deviceId)`), closes location connection (`location.close_connection(deviceId)`), and clears `_selected_device` if it matches. Register `disconnectDevice` in `self._methods`.

## 5. Frontend: Tunneld State Management

- [x] 5.1 Add `tunneldState` state variable to `useBackend.js` (initial value: `{ state: "starting" }`). Add SSE event handler for `tunneldStatus` events that updates this state.
- [x] 5.2 Add `retryTunneld` function to `useBackend.js` that calls `sendRequest('retryTunneld')`. Expose it in the hook return value.
- [x] 5.3 Add SSE event handler for `tunnelStatusChanged` events in `useBackend.js` that updates tunnel info for the corresponding device.
- [x] 5.4 Remove `startTunnel`, `stopTunnel`, `getTunnelStatus` functions from `useBackend.js`.

## 6. Frontend: Tunnel Status Display

- [x] 6.1 Update `selectDevice` handler in `useBackend.js` to extract tunnel info from the enriched `selectDevice` response and store it in `tunnelStatus` state.
- [x] 6.2 Update `listDevices` handler in `useBackend.js` to extract per-device tunnel info from the enriched `listDevices` response.
- [x] 6.3 Add tunneld error banner component to `DevicePanel.jsx` — shown when `tunneldState.state` is `error` (with error message and [Retry] button) or `starting` (with "Starting tunneld..." and spinner). Hidden when `ready`.
- [x] 6.4 Convert tunnel section in `DevicePanel.jsx` to read-only: remove Start/Stop Tunnel buttons, remove `onStartTunnel`/`onStopTunnel` props. Show "Connected (<address> <port>)" with space separator, "No tunnel" (gray), or hide section for simulators/no selection.
- [x] 6.5 Remove `onStartTunnel`/`onStopTunnel` props from `App.jsx` where DevicePanel is rendered. Pass `tunneldState` and `onRetryTunneld` instead.

## 7. Frontend: Device Disconnect

- [x] 7.1 Add `disconnectDevice` function to `useBackend.js` that calls `sendRequest('disconnectDevice', {deviceId})` and on success resets `selectedDevice`, `location`, `tunnelStatus`, `cruiseStatus`, and `routeStatus` to null/initial state.
- [x] 7.2 Add [X] button to the selected device row in `DevicePanel.jsx`. Only visible on the currently selected device.
- [x] 7.3 Wire [X] button click to show `window.confirm("This will disconnect location simulation for [device name]. Continue?")` and call `disconnectDevice` on confirm.
- [x] 7.4 Pass `onDisconnectDevice` prop from `App.jsx` to `DevicePanel`.
