## 1. Backend: Remove singleton device selection

- [x] 1.1 Remove `_selected_device` field from `LocationSimulatorServer.__init__` in `main.py`
- [x] 1.2 Remove `selectDevice` from `self._methods` dict and delete `_select_device` method
- [x] 1.3 Remove `deviceId` fallback logic (the `if not device_id and self._selected_device` pattern) from all RPC methods — return error if `deviceId` missing
- [x] 1.4 Update `_disconnect_device` to remove the `_selected_device` clearing logic

## 2. Backend: Add getDeviceState RPC method

- [x] 2.1 Add `get_route` and `get_route_session` getter methods to `RouteService` (return route definition and active session for a device_id, or None)
- [x] 2.2 Add `get_cruise_status` getter to `CruiseService` if not already present (return session dict for a device_id, or None)
- [x] 2.3 Add helper `_get_tunnel_status_for(device_id)` in `main.py` that returns tunnel status for a specific device
- [x] 2.4 Implement `_get_device_state` method in `main.py` that aggregates location, isRefreshing, tunnel, cruise, route, routeCruise
- [x] 2.5 Register `getDeviceState` in `self._methods`

## 3. Backend: Add getAllDeviceStates RPC method

- [x] 3.1 Implement `_get_all_device_states` method that queries CruiseService and RouteService for all active sessions, returns badge-level dict keyed by deviceId
- [x] 3.2 Register `getAllDeviceStates` in `self._methods`

## 4. Frontend: SSE handler dual-path refactor

- [x] 4.1 Add `badgeMap` state (`Map<deviceId, BadgeState>`) to `useBackend.js`
- [x] 4.2 Refactor SSE event handler: always update `badgeMap` for all events with `deviceId`
- [x] 4.3 Add device ID filter: only update full state (`cruiseStatus`, `location`, `routeStatus`, `routeState`) when `event.deviceId === selectedDevice.id`
- [x] 4.4 Use a ref for `selectedDevice` in SSE handler to avoid stale closure issues

## 5. Frontend: Device switch flow

- [x] 5.1 Replace `selectDevice` RPC call with `getDeviceState` call in `useBackend.js`
- [x] 5.2 Populate all state from `getDeviceState` response: location, cruiseStatus, routeState, routeStatus, tunnelStatus
- [x] 5.3 Implement auto UI mode switch: route state → Route mode, regular cruise → Cruise mode, idle → keep current mode
- [x] 5.4 Implement sticky speed slider: only update speed from backend if cruise is active, otherwise keep current value
- [x] 5.5 Ensure `pendingLocation` is NOT cleared on device switch (global state)
- [x] 5.6 Add loading overlay state and component — show over main content during `getDeviceState` call, dismiss on response or error
- [x] 5.7 Call `getAllDeviceStates` on initial load to seed badge map

## 6. Frontend: Device badges in DevicePanel

- [x] 6.1 Pass `badgeMap` to `DevicePanel` component
- [x] 6.2 Render status badge on non-selected device rows based on `badgeMap` entry (cruising, paused, route progress)
- [x] 6.3 Style badges to be compact and non-intrusive (reuse existing `.loop-badge` pattern or similar)
- [x] 6.4 Hide badge on selected device row (full state shown in main UI)

## 7. Frontend: Disconnect cleanup update

- [x] 7.1 Update `disconnectDevice` in `useBackend.js` to also clear the badge map entry for the disconnected device
- [x] 7.2 Ensure disconnect does not interfere with badge state of other devices

## 8. Frontend: SSE reconnection and refresh

- [x] 8.1 On SSE reconnection, re-call `getAllDeviceStates` to resync badge state
- [x] 8.2 On frontend refresh with a previously selected device, call `getDeviceState` to restore full state

## 9. Testing

- [x] 9.1 Backend: Test `getDeviceState` returns correct aggregated state for various device scenarios
- [x] 9.2 Backend: Test `getAllDeviceStates` returns correct badge-level state
- [x] 9.3 Backend: Test that RPC methods without `deviceId` return error (no fallback)
- [x] 9.4 Frontend: Test SSE event filtering — events for non-selected device only update badge map
- [x] 9.5 Frontend: Test device switch populates state from `getDeviceState` response
- [x] 9.6 Frontend: Test auto UI mode switch on device selection
