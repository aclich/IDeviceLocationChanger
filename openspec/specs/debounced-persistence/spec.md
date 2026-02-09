## ADDED Requirements

### Requirement: LastLocationService debounces disk writes
`LastLocationService.update()` SHALL update the in-memory dictionary immediately but SHALL NOT write to disk on every call. Disk writes SHALL occur at most once every `FLUSH_INTERVAL` seconds (5 seconds).

#### Scenario: update() is memory-only
- **WHEN** `update(device_id, lat, lon)` is called
- **THEN** the in-memory `_locations` dict is updated immediately
- **AND** a `_dirty` flag is set to `True`
- **AND** no disk write occurs

#### Scenario: Rapid updates produce single disk write
- **WHEN** `update()` is called 50 times within 1 second (e.g., during cruise mode)
- **THEN** at most 1 disk write occurs (from the background flush)
- **AND** the written file contains the latest values from all 50 updates

### Requirement: Background flush thread writes dirty data periodically
LastLocationService SHALL run a daemon `threading.Thread` that checks the dirty flag every `FLUSH_INTERVAL` seconds and writes to disk if dirty.

#### Scenario: Flush loop writes when dirty
- **WHEN** the flush interval elapses and `_dirty` is `True`
- **THEN** the current `_locations` dict is written to `last_locations.json`
- **AND** `_dirty` is reset to `False`

#### Scenario: Flush loop skips when clean
- **WHEN** the flush interval elapses and `_dirty` is `False`
- **THEN** no disk write occurs

#### Scenario: Flush thread is daemon
- **WHEN** the flush thread is created
- **THEN** it is created with `daemon=True`
- **AND** it terminates automatically when the main process exits

### Requirement: Explicit flush on shutdown
LastLocationService SHALL provide a `flush()` method for immediate disk write and a `close()` method that stops the background thread and performs a final flush.

#### Scenario: flush() writes immediately
- **WHEN** `flush()` is called
- **THEN** if `_dirty` is `True`, the data is written to disk immediately
- **AND** `_dirty` is reset to `False`

#### Scenario: close() performs final flush
- **WHEN** `close()` is called during server shutdown
- **THEN** the flush thread's stop event is set
- **AND** `thread.join(timeout=2)` is called
- **AND** a final `flush()` is called to persist any remaining dirty data

### Requirement: get() always returns latest in-memory data
`LastLocationService.get()` SHALL always return the latest in-memory value, not the value last written to disk.

#### Scenario: get() returns updated value before flush
- **WHEN** `update(device_id, 25.0, 121.5)` is called but the flush thread has not yet written to disk
- **THEN** `get(device_id)` returns `{"lat": 25.0, "lon": 121.5}`
