## Context

The GPS simulator backend services (CruiseService, RouteService, LocationService, LastLocationService) are already fully per-device — all state is stored in `dict[str, ...]` keyed by `device_id`. SSE events already include `deviceId` in their payloads. The frontend, however, treats everything as singleton state tied to one selected device. The `_selected_device` field in `main.py` is vestigial — the frontend already passes `deviceId` explicitly in every RPC call.

The work is primarily a frontend refactor with two small backend additions (state aggregation endpoints) and one backend removal (singleton device selection).

## Goals / Non-Goals

**Goals:**
- Users can switch between devices without losing state (cruise continues in backend, UI restores on switch-back)
- Device list shows real-time status badges for background devices
- Device switch triggers a full state restore from backend
- SSE events are correctly routed to the active device's UI state vs badge state
- Pending location and UI mode toggle are preserved across switches (global intent)
- Speed slider is "sticky" — only overwritten by active backend speed

**Non-Goals:**
- Split-screen / simultaneous multi-device view — single-active-view only
- Per-device speed persistence for idle devices — slider keeps current value
- Route definition cleanup on disconnect (existing behavior preserved)
- Changes to backend services (CruiseService, RouteService, LocationService) — they're already per-device

## Decisions

### 1. State query on switch vs continuous background sync

**Decision:** Query backend on switch (`getDeviceState`), don't maintain full per-device state maps in frontend.

**Rationale:** Maintaining a `Map<deviceId, FullState>` from SSE events would require processing every SSE event for every device, duplicating the backend's state in the frontend. Instead, we query the backend for the full state snapshot on switch and only track lightweight badge data for background devices.

**Alternative considered:** Full SSE-driven state map for all devices. Rejected because it adds significant memory/complexity for a feature (simultaneous multi-view) we explicitly don't need.

### 2. Badge state: SSE-driven with initial seed

**Decision:** Maintain a lightweight `Map<deviceId, BadgeState>` updated from ALL SSE events (not filtered by selected device). Seed with `getAllDeviceStates()` on initial load.

**BadgeState shape:**
```
{
  cruising: boolean,
  cruisePaused: boolean,
  routeCruising: boolean,
  routePaused: boolean,
  routeProgress: string | null  // e.g. "3/5"
}
```

**Rationale:** Real-time badges require continuous updates. The SSE handler already receives all events — we just need to extract badge-level info into a separate map before the device-ID filter. The initial `getAllDeviceStates()` seed handles the case where cruises started before the frontend loaded.

### 3. `selectDevice` RPC removal

**Decision:** Remove `selectDevice` from `main.py._methods` and delete `_selected_device`. Frontend device selection becomes purely a UI concern — just query `getDeviceState` and update local state.

**Rationale:** The `_selected_device` is only used as a fallback when `deviceId` is not in params. The frontend always passes `deviceId`. Removing it eliminates misleading state and simplifies the backend.

**Migration:** The `selectDevice` call in `useBackend.js` is replaced with `getDeviceState`. No other callers exist.

### 4. SSE handler dual-path architecture

**Decision:** SSE events are processed in two paths:

```
SSE event arrives
  ├─ ALWAYS: update badgeMap[event.deviceId]  (lightweight)
  └─ IF event.deviceId === selectedDevice.id:
       update full state (location, cruiseStatus, routeStatus, etc.)
```

**Rationale:** Badges need all events. Full state updates must be scoped to the viewed device to prevent interleaving from concurrent cruises on different devices.

### 5. Auto UI mode on device switch

**Decision:** On switch, the UI mode is set based on device state, with idle devices preserving the current mode:

| Device state | UI mode action |
|---|---|
| Has route (cruising or not) | Switch to Route mode |
| Has regular cruise (active or paused) | Switch to Cruise mode (non-route) |
| Idle (no cruise, no route) | Keep current mode unchanged |

**Rationale:** The UI mode should reflect what the device is actually doing. But for idle devices, the user may have intentionally set a mode (e.g., Route mode) before picking a device, so we don't override it.

### 6. Global vs per-device state boundary

**Decision:**

| State | Scope | Rationale |
|---|---|---|
| `pendingLocation` | Global | User picks a location before targeting a device |
| `routeMode` toggle | Global (with auto-override) | User sets up mode before selecting device |
| Speed slider value | Global (sticky) | Backend overrides when active speed exists |
| `location` | Per-device (from backend) | Each device has its own GPS position |
| `cruiseStatus` | Per-device (from backend) | Independent cruise sessions |
| `routeState` | Per-device (from backend) | Independent route definitions |
| `routeStatus` | Per-device (from backend) | Independent route cruise sessions |
| `tunnelStatus` | Per-device (from backend) | Each physical device has its own tunnel |

### 7. `getDeviceState` aggregation

**Decision:** Single RPC method that queries all services internally:

```python
def _get_device_state(self, params):
    device_id = params["deviceId"]
    return {
        "location": self.location.get_last_location(device_id)
                    or self.last_location.get(device_id),
        "isRefreshing": device_id in self.location._refresh_tasks,
        "tunnel": self._get_tunnel_status_for(device_id),
        "cruise": self.cruise.get_cruise_status(device_id),
        "route": self.route.get_route(device_id),
        "routeCruise": self.route.get_route_session(device_id),
    }
```

**Rationale:** One round-trip on device switch vs multiple queries. Services already expose getters — this is pure aggregation.

## Risks / Trade-offs

**[Risk] SSE event race on device switch** — If the user switches device while SSE events are in-flight for the old device, the handler might apply stale events to the new device's state.
→ Mitigation: The `selectedDevice.id` check in the SSE handler uses the latest ref value. Since `getDeviceState` response sets state atomically, any trailing events for the old device will fail the ID check.

**[Risk] Badge state diverges from reality** — If SSE connection drops and reconnects, badges may show stale state.
→ Mitigation: Re-call `getAllDeviceStates()` on SSE reconnection. The existing SSE reconnect logic in `useBackend.js` can trigger this.

**[Risk] `selectDevice` removal is breaking** — Any external client using `selectDevice` will break.
→ Mitigation: This is a desktop app with a single frontend client. No external API consumers. Acceptable breaking change.

**[Trade-off] No idle speed persistence** — Switching from a cruising device (80 km/h) to an idle device keeps the slider at 80 km/h. This could be surprising if the user expects a "default" speed per device.
→ Accepted: Simple behavior, easy to understand. Users can adjust the slider. Persisting idle speed would require a new storage mechanism for marginal benefit.
