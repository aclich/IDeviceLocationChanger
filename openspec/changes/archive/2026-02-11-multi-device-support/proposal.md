## Why

The app currently treats device selection as a global singleton — all frontend state (location, cruise, route, tunnel) is tied to one device at a time. Switching devices discards everything about the previous device's state. Backend services are already per-device (keyed by `device_id`), but the frontend can't take advantage of this. Users who work with multiple iOS devices must mentally track what each device is doing and lose all visual context when switching between them.

## What Changes

- **Backend removes `_selected_device` singleton** — The vestigial `selectDevice` RPC method and fallback logic in `main.py` are removed. Frontend already passes `deviceId` explicitly in every call.
- **New `getDeviceState` RPC method** — Single query that aggregates all per-device state (location, cruise, route, route cruise, tunnel) from existing services. Called on device switch and frontend refresh.
- **New `getAllDeviceStates` RPC method** — Lightweight batch query returning badge-level info (cruising? route progress? paused?) for all active devices. Called once on initial load to seed badge state.
- **Frontend SSE handler splits into two paths** — Full state updates filtered to the currently-viewed device; badge-level state tracked for ALL devices via a `Map<deviceId, badgeState>`.
- **Device switch = query + populate** — Clicking a different device calls `getDeviceState` and populates all state from the response. No backend "select" needed.
- **Device list badges** — Non-selected devices show real-time status indicators (e.g., "cruising...", "route 3/5", "paused") driven by SSE events.
- **Auto UI mode switch on device select** — Device with route → Route mode; device with regular cruise → Cruise mode; idle device → keep current mode.
- **Pending location and UI mode are global** — Persist across device switches. User can set up intent (pick location, toggle route mode) before selecting a device.
- **Speed slider is "sticky"** — Only updated when backend returns an active speed for the device; otherwise keeps its current value.
- **`disconnectDevice` remains unchanged** — Disconnect (✕ button) stops all tasks and cleans up. Switch (click device row) only changes the view.

## Capabilities

### New Capabilities
- `multi-device-state`: Backend aggregation of per-device state (`getDeviceState`, `getAllDeviceStates` RPCs) and removal of singleton `_selected_device`
- `device-switch-restore`: Frontend device switch flow — query backend, populate state, auto-set UI mode, SSE filtering by device
- `device-badges`: Real-time status badges on non-selected devices in the device list, driven by SSE events

### Modified Capabilities
- `device-disconnect`: Disconnect now coexists with switch — disconnect cleans up, switch just changes view. The disconnect spec itself doesn't change, but the frontend reset behavior must not interfere with the new switch flow.
- `route-mode-ui`: Route mode toggle becomes global (persists across device switches) and auto-activates when switching to a device with route state.

## Impact

- **Backend `main.py`**: Remove `_selected_device`, remove `selectDevice` method, add `getDeviceState` and `getAllDeviceStates` methods
- **Backend services**: No changes — already per-device. RouteService already preserves route definitions across cruise stop.
- **Frontend `useBackend.js`**: Major refactor of SSE handler (filtered + badge paths), `selectDevice` becomes pure frontend + backend query, new badge state management
- **Frontend `App.jsx`**: Device switch logic updated to use `getDeviceState`, auto mode switch, pending location preserved
- **Frontend `DevicePanel.jsx`**: Badge rendering on non-selected device rows
- **Frontend `useRouteCruise.js`**: Route mode auto-activation logic on device switch
- **JSON-RPC protocol**: Two new methods added (`getDeviceState`, `getAllDeviceStates`), one removed (`selectDevice`) — **BREAKING** for any client relying on `selectDevice`
