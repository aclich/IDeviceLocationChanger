# Connection Management Specification

## Overview

This document specifies the connection management system for the Location Simulator's Python backend. The system manages persistent connections to iOS devices for reliable GPS location simulation.

## Goals

1. **Reliability**: Prevent simulated location from reverting to real GPS
2. **Resilience**: Automatically recover from connection failures
3. **Efficiency**: Reuse connections to minimize overhead
4. **Multi-device**: Support concurrent connections to multiple devices

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│  LocationService                                            │
│  ├─ _tunnel_connections: dict[device_id, TunnelConnection]  │
│  ├─ _usbmux_connections: dict[device_id, UsbmuxConnection]  │
│  ├─ _last_locations: dict[device_id, LocationState]         │
│  ├─ _refresh_tasks: dict[device_id, asyncio.Task]           │
│  └─ _tunnel_provider: Callable[[udid], RSDTunnel]           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  TunnelConnection (iOS 17+)                                 │
│  ├─ rsd: RemoteServiceDiscoveryService                      │
│  ├─ dvt: DvtSecureSocketProxyService                        │
│  ├─ location: LocationSimulation                            │
│  └─ tunnel: RSDTunnel (address, port, udid)                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  UsbmuxConnection (iOS 16 and earlier)                      │
│  ├─ lockdown: LockdownClient                                │
│  ├─ dvt: DvtSecureSocketProxyService                        │
│  └─ location: LocationSimulation                            │
└─────────────────────────────────────────────────────────────┘
```

### Data Structures

#### TunnelConnection
```python
{
    "rsd": RemoteServiceDiscoveryService,  # RSD connection to tunnel
    "dvt": DvtSecureSocketProxyService,    # DVT secure socket
    "location": LocationSimulation,         # Location simulation service
    "tunnel": RSDTunnel                     # Tunnel info (address, port, udid)
}
```

#### UsbmuxConnection
```python
{
    "lockdown": LockdownClient,            # Lockdown connection via usbmux
    "dvt": DvtSecureSocketProxyService,    # DVT secure socket
    "location": LocationSimulation          # Location simulation service
}
```

#### LocationState
```python
{
    "lat": float,      # Last latitude
    "lon": float,      # Last longitude
    "time": float      # Unix timestamp of last update
}
```

---

## Connection Lifecycle

### State Diagram

```
                    ┌─────────────┐
                    │   No Conn   │
                    └──────┬──────┘
                           │ set_location()
                           ▼
                    ┌─────────────┐
         ┌─────────│  Creating   │─────────┐
         │         └──────┬──────┘         │
         │ error          │ success        │ error (retry exhausted)
         │                ▼                │
         │         ┌─────────────┐         │
         │         │  Connected  │◄────┐   │
         │         └──────┬──────┘     │   │
         │                │            │   │
         │    set_location│  refresh   │   │
         │                │  (3s)      │   │
         │                ▼            │   │
         │         ┌─────────────┐     │   │
         │         │   Active    │─────┘   │
         │         └──────┬──────┘         │
         │                │                │
         │   clear_location / error        │
         │                │                │
         │                ▼                ▼
         │         ┌─────────────┐
         └────────►│   Closed    │
                   └─────────────┘
```

### Lifecycle Events

| Event | Action | Next State |
|-------|--------|------------|
| `set_location()` on new device | Create connection, set location, start refresh | Connected |
| `set_location()` on existing connection | Reuse connection, update location | Active |
| Refresh timer fires (3s idle) | Re-send last location | Active |
| `clear_location()` | Clear on device, close connection, stop refresh | Closed |
| Connection error | Close, retry with fresh tunnel (up to 5x) | Creating or Closed |
| App shutdown | Close all connections | Closed |

---

## Connection Operations

### Create Connection

#### Tunnel (iOS 17+)

```
1. Query tunnel info from tunneld (address, port)
2. Create RemoteServiceDiscoveryService(address, port)
3. await rsd.connect()
4. Create DvtSecureSocketProxyService(lockdown=rsd)
5. dvt.__enter__()
6. Create LocationSimulation(dvt)
7. Store in _tunnel_connections[device_id]
```

#### USBMux (iOS 16-)

```
1. Create lockdown via create_using_usbmux(serial=device_id)
2. Create DvtSecureSocketProxyService(lockdown=lockdown)
3. dvt.__enter__()
4. Create LocationSimulation(dvt)
5. Store in _usbmux_connections[device_id]
```

### Close Connection

```
1. Cancel refresh task if running
2. Remove from _last_locations
3. Call dvt.__exit__(None, None, None)
4. For tunnel: await rsd.close()
5. Remove from connection dict
```

### Set Location

```
1. Get or create connection
2. Call location.set(lat, lon)
3. Update _last_locations[device_id] = {lat, lon, time.time()}
4. Start refresh task if not running
5. Return success
```

### Clear Location

```
1. If connection exists: call location.clear()
2. Else: create temp connection, call clear
3. Close connection
4. Return success
```

---

## Refresh Mechanism

### Purpose

Keep the DVT connection active by periodically re-sending the last known location. iOS may revert to real GPS if no location updates are received.

### Configuration

```python
REFRESH_INTERVAL_SECONDS = 3  # Seconds between refresh checks
```

### Algorithm

```python
async def refresh_loop(device_id):
    while True:
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

        last = _last_locations.get(device_id)
        if not last:
            continue

        elapsed = time.time() - last["time"]
        if elapsed < REFRESH_INTERVAL_SECONDS:
            continue  # Recent update, skip

        # Re-send last location
        conn = _tunnel_connections.get(device_id) or _usbmux_connections.get(device_id)
        if conn and conn["location"]:
            conn["location"].set(last["lat"], last["lon"])
            _last_locations[device_id]["time"] = time.time()
```

### Lifecycle

| Event | Refresh Task |
|-------|--------------|
| First `set_location()` | Start task |
| Subsequent `set_location()` | Keep running (timestamp updated) |
| `clear_location()` | Cancel task |
| Connection error | Task may fail (next set_location will restart) |
| App shutdown | Cancel all tasks |

---

## Retry Mechanism

### Purpose

Automatically recover from transient connection failures by retrying with fresh tunnel information.

### Configuration

```python
MAX_RETRY_ATTEMPTS = 5      # Maximum retry attempts
RETRY_DELAY_SECONDS = 0.5   # Delay between retries
```

### Algorithm

```python
async def set_via_tunnel_with_retry(device, tunnel, lat, lon):
    current_tunnel = tunnel

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            conn = await get_or_create_connection(device, current_tunnel)
            conn["location"].set(lat, lon)
            return {"success": True}

        except Exception as e:
            await close_connection(device.id)

            if attempt < MAX_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

                # Get fresh tunnel info
                if tunnel_provider:
                    fresh = await tunnel_provider(device.id)
                    if fresh:
                        current_tunnel = fresh

    return {"success": False, "error": "Max retries exceeded"}
```

### Tunnel Provider

The `tunnel_provider` callback is set by `main.py` to query tunneld for fresh tunnel info:

```python
# In main.py
self.location.set_tunnel_provider(self._get_tunnel_for_device)

async def _get_tunnel_for_device(self, udid: str) -> Optional[RSDTunnel]:
    return await self.tunnel.get_tunnel(udid)  # Queries tunneld HTTP API
```

### Retry Flow

```
Attempt 1: Use provided tunnel
    ├─ Success → Return
    └─ Failure → Close connection, wait 0.5s

Attempt 2: Query fresh tunnel from tunneld
    ├─ Success → Return
    └─ Failure → Close connection, wait 0.5s

Attempt 3-5: Same as Attempt 2

All attempts failed → Return error
```

---

## Multi-Device Support

### Design Principles

1. **Independent connections**: Each device has its own connection entry
2. **No interference**: Operations on device A don't affect device B
3. **Concurrent refresh**: Each device has its own refresh task
4. **Shared provider**: All devices use the same tunnel provider

### Connection Isolation

```python
# Each device has separate entries
_tunnel_connections = {
    "device-A-udid": {...},
    "device-B-udid": {...},
}

_refresh_tasks = {
    "device-A-udid": Task,
    "device-B-udid": Task,
}

_last_locations = {
    "device-A-udid": {"lat": 37.0, "lon": -122.0, "time": ...},
    "device-B-udid": {"lat": 40.0, "lon": -74.0, "time": ...},
}
```

### Device Switching

When user selects a different device:
- Previous device's connection **remains open**
- New device gets its own connection
- Both devices can be controlled (future multi-device UI)

---

## Error Handling

### Connection Errors

| Error Type | Handling |
|------------|----------|
| RSD connect failure | Retry with fresh tunnel |
| DVT service failure | Retry with fresh tunnel |
| Location set failure | Retry with fresh tunnel |
| Tunnel not found | Return error (no retry possible) |

### Refresh Errors

| Error Type | Handling |
|------------|----------|
| Location set failure | Log warning, continue loop |
| Connection gone | Task will fail, next set_location restarts |
| Task cancelled | Exit gracefully |

### Shutdown

```python
async def close_all_connections():
    # 1. Stop all refresh tasks
    for device_id in list(_refresh_tasks.keys()):
        await _stop_refresh_task(device_id)

    # 2. Close all connections
    for device_id in list(_tunnel_connections.keys()):
        await close_connection(device_id)
    for device_id in list(_usbmux_connections.keys()):
        await close_connection(device_id)
```

---

## API Reference

### Public Methods

| Method | Description |
|--------|-------------|
| `set_tunnel_provider(provider)` | Register callback for fresh tunnel info |
| `set_location(device, lat, lon, tunnel)` | Set location with auto-retry and refresh |
| `clear_location(device, tunnel)` | Clear location and close connection |
| `close_connection(device_id)` | Manually close a device's connection |
| `close_all_connections()` | Close all connections (shutdown) |

### Internal Methods

| Method | Description |
|--------|-------------|
| `_get_or_create_tunnel_connection()` | Get existing or create new tunnel connection |
| `_get_or_create_usbmux_connection()` | Get existing or create new usbmux connection |
| `_set_via_tunnel_with_retry()` | Set location with retry logic |
| `_set_via_usbmux_with_retry()` | Set location with retry logic |
| `_start_refresh_task()` | Start background refresh for device |
| `_stop_refresh_task()` | Stop background refresh for device |
| `_update_last_location()` | Update stored location state |

---

## Configuration Summary

| Constant | Value | Description |
|----------|-------|-------------|
| `REFRESH_INTERVAL_SECONDS` | 3 | Auto-refresh interval in seconds |
| `MAX_RETRY_ATTEMPTS` | 5 | Maximum retry attempts on error |
| `RETRY_DELAY_SECONDS` | 0.5 | Delay between retry attempts |
