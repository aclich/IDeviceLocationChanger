## ADDED Requirements

### Requirement: Tunnel info is cached per device during active cruise
The `_set_location_for_cruise` callback SHALL maintain a per-device cache of tunnel info (`RSDTunnel`) to avoid querying tunneld on every cruise tick. The cache SHALL be stored as `{device_id: (RSDTunnel, timestamp)}`.

#### Scenario: Cache hit skips tunneld query
- **WHEN** the cruise callback is invoked for a device with a cached tunnel entry younger than `TUNNEL_CACHE_TTL` (30 seconds)
- **THEN** the cached `RSDTunnel` is used directly
- **AND** no HTTP request is made to tunneld

#### Scenario: Cache miss triggers tunneld query
- **WHEN** the cruise callback is invoked for a device with no cache entry or an expired entry (age >= 30s)
- **THEN** `TunnelManager.get_tunnel(device_id)` is called
- **AND** the result is stored in the cache with the current timestamp

#### Scenario: Cache stores None for no-tunnel result
- **WHEN** `TunnelManager.get_tunnel()` returns `None` (tunneld timeout or no tunnel)
- **THEN** `None` is stored in the cache with the current timestamp
- **AND** subsequent ticks within TTL skip the tunneld query and pass `None` to LocationService (which falls back to its own cached DVT connection)

### Requirement: Cache is invalidated on location set failure
When `LocationService.set_location` returns `{"success": False}`, the tunnel cache entry for that device SHALL be invalidated so the next tick queries tunneld fresh.

#### Scenario: Location failure clears cache
- **WHEN** `set_location` returns `success: false` for a device
- **THEN** the cache entry for that device is removed
- **AND** `TunnelManager.invalidate(device_id)` is called (existing behavior)
- **AND** the next cruise tick will query tunneld for fresh tunnel info

### Requirement: Cache is cleared on cruise stop
When a cruise session ends (stop, arrival, or error), the tunnel cache entry for that device SHALL be removed.

#### Scenario: Stop cruise clears cache
- **WHEN** `stop_cruise` is called or the cruise arrives at the target
- **THEN** the tunnel cache entry for that device_id is removed

### Requirement: Tunnel cache reduces tunneld queries to at most one per TTL period
During normal cruise operation (no errors), the tunneld HTTP API SHALL be queried at most once every `TUNNEL_CACHE_TTL` seconds per device.

#### Scenario: Query frequency during normal cruise
- **WHEN** a cruise runs for 60 seconds with no connection errors and TTL=30s
- **THEN** at most 2 tunneld HTTP queries are made for that device (initial + 1 refresh)
- **AND** all other cruise ticks (300-600 ticks) use the cached value

#### Scenario: Query frequency during intermittent errors
- **WHEN** a location set fails during cruise
- **THEN** the cache is invalidated and the next tick queries tunneld
- **AND** if the fresh query succeeds, normal caching resumes for the next TTL period
