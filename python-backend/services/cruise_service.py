"""Cruise mode service - manages automatic movement towards targets.

Handles cruise mode in the backend so it continues working when the browser
tab is inactive. Emits events to frontend for UI updates.

Features:
- Per-device cruise sessions with independent asyncio tasks
- Pause/resume functionality
- Speed adjustment mid-cruise
- Event emission for UI updates
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Awaitable

from .coordinate_utils import move_location, bearing_to, distance_between

logger = logging.getLogger(__name__)

# Configuration
UPDATE_INTERVAL_BASE_MS = 100  # Base interval between updates
UPDATE_INTERVAL_JITTER_MS = 100  # Random jitter (0-100ms) added to base
ARRIVAL_THRESHOLD_KM = 0.005  # 5 meters - consider arrived


def _get_next_interval() -> float:
    """Get next interval with jitter (100-200ms) in seconds."""
    import random
    return (UPDATE_INTERVAL_BASE_MS + random.random() * UPDATE_INTERVAL_JITTER_MS) / 1000


class CruiseState(str, Enum):
    """Cruise session state."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ARRIVED = "arrived"
    STOPPED = "stopped"


@dataclass
class CruiseSession:
    """Per-device cruise session state."""
    device_id: str
    start_lat: float
    start_lon: float
    target_lat: float
    target_lon: float
    speed_kmh: float
    state: CruiseState = CruiseState.IDLE

    # Current position (updated as we move)
    current_lat: float = field(init=False)
    current_lon: float = field(init=False)

    # Tracking
    start_time: float = field(default_factory=time.time)
    distance_traveled_km: float = 0.0
    last_update_time: float = field(default_factory=time.time)

    # Internal
    _task: Optional[asyncio.Task] = field(default=None, repr=False)

    def __post_init__(self):
        self.current_lat = self.start_lat
        self.current_lon = self.start_lon

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "deviceId": self.device_id,
            "state": self.state.value,
            "location": {
                "latitude": self.current_lat,
                "longitude": self.current_lon,
            },
            "target": {
                "latitude": self.target_lat,
                "longitude": self.target_lon,
            },
            "speedKmh": self.speed_kmh,
            "remainingKm": distance_between(
                self.current_lat, self.current_lon,
                self.target_lat, self.target_lon
            ),
            "distanceTraveledKm": self.distance_traveled_km,
            "durationSeconds": time.time() - self.start_time,
        }


# Type for location setter callback
LocationSetter = Callable[[str, float, float], Awaitable[dict]]
# Type for event emitter callback
EventEmitter = Callable[[dict], None]


class CruiseService:
    """Service for managing cruise mode sessions.

    Runs asyncio tasks that move devices towards targets and emit
    events for frontend updates.
    """

    def __init__(self):
        # Per-device sessions
        self._sessions: dict[str, CruiseSession] = {}

        # Callbacks set by main.py
        self._set_location: Optional[LocationSetter] = None
        self._emit_event: Optional[EventEmitter] = None

    def set_location_callback(self, callback: LocationSetter) -> None:
        """Set the callback for setting device location.

        Called by main.py during initialization.
        The callback should set location on the device and return result.
        """
        self._set_location = callback

    def set_event_emitter(self, emitter: EventEmitter) -> None:
        """Set the callback for emitting events to frontend.

        Called by main.py during initialization.
        """
        self._emit_event = emitter

    def _emit(self, event: str, data: dict) -> None:
        """Emit an event to the frontend."""
        if self._emit_event:
            self._emit_event({"event": event, "data": data})

    # =========================================================================
    # Public API
    # =========================================================================

    async def start_cruise(
        self,
        device_id: str,
        start_lat: float,
        start_lon: float,
        target_lat: float,
        target_lon: float,
        speed_kmh: float
    ) -> dict:
        """Start cruise mode for a device.

        Args:
            device_id: Device identifier
            start_lat: Starting latitude
            start_lon: Starting longitude
            target_lat: Target latitude
            target_lon: Target longitude
            speed_kmh: Speed in km/h

        Returns:
            Result dict with success status
        """
        # Stop any existing cruise for this device
        if device_id in self._sessions:
            await self.stop_cruise(device_id)

        # Validate
        if not self._set_location:
            return {"success": False, "error": "Location callback not configured"}

        distance = distance_between(start_lat, start_lon, target_lat, target_lon)
        if distance < ARRIVAL_THRESHOLD_KM:
            return {"success": False, "error": "Already at target location"}

        # Create session
        session = CruiseSession(
            device_id=device_id,
            start_lat=start_lat,
            start_lon=start_lon,
            target_lat=target_lat,
            target_lon=target_lon,
            speed_kmh=speed_kmh,
        )
        session.state = CruiseState.RUNNING
        self._sessions[device_id] = session

        # Start movement task
        session._task = asyncio.create_task(self._cruise_loop(session))

        logger.info(f"[{device_id[:8]}] Cruise started: {distance:.3f}km to target at {speed_kmh}km/h")

        self._emit("cruiseStarted", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    async def stop_cruise(self, device_id: str) -> dict:
        """Stop cruise mode for a device.

        Args:
            device_id: Device identifier

        Returns:
            Result dict with success status
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"success": True, "message": "No active cruise"}

        # Cancel task
        if session._task and not session._task.done():
            session._task.cancel()
            try:
                await session._task
            except asyncio.CancelledError:
                pass

        session.state = CruiseState.STOPPED
        del self._sessions[device_id]

        logger.info(f"[{device_id[:8]}] Cruise stopped")

        self._emit("cruiseStopped", {
            "deviceId": device_id,
            "reason": "stopped",
        })

        return {"success": True}

    async def pause_cruise(self, device_id: str) -> dict:
        """Pause cruise mode for a device.

        Args:
            device_id: Device identifier

        Returns:
            Result dict with success status
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active cruise"}

        if session.state != CruiseState.RUNNING:
            return {"success": False, "error": f"Cannot pause: cruise is {session.state.value}"}

        session.state = CruiseState.PAUSED

        logger.info(f"[{device_id[:8]}] Cruise paused")

        self._emit("cruisePaused", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    async def resume_cruise(self, device_id: str) -> dict:
        """Resume paused cruise mode for a device.

        Args:
            device_id: Device identifier

        Returns:
            Result dict with success status
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active cruise"}

        if session.state != CruiseState.PAUSED:
            return {"success": False, "error": f"Cannot resume: cruise is {session.state.value}"}

        session.state = CruiseState.RUNNING
        session.last_update_time = time.time()  # Reset timing for smooth movement

        logger.info(f"[{device_id[:8]}] Cruise resumed")

        self._emit("cruiseResumed", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    def set_cruise_speed(self, device_id: str, speed_kmh: float) -> dict:
        """Update cruise speed for a device.

        Args:
            device_id: Device identifier
            speed_kmh: New speed in km/h

        Returns:
            Result dict with success status
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active cruise"}

        speed_kmh = max(1, min(50, speed_kmh))  # Clamp to 1-50 km/h
        session.speed_kmh = speed_kmh

        logger.debug(f"[{device_id[:8]}] Cruise speed set to {speed_kmh}km/h")

        return {"success": True, "speedKmh": speed_kmh}

    def get_cruise_status(self, device_id: str) -> dict:
        """Get cruise status for a device.

        Args:
            device_id: Device identifier

        Returns:
            Status dict with session info or idle state
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"state": CruiseState.IDLE.value, "deviceId": device_id}

        return session.to_dict()

    async def stop_all(self) -> None:
        """Stop all cruise sessions. Called on shutdown."""
        for device_id in list(self._sessions.keys()):
            await self.stop_cruise(device_id)

    # =========================================================================
    # Movement Loop
    # =========================================================================

    async def _cruise_loop(self, session: CruiseSession) -> None:
        """Movement loop that runs for each cruise session.

        Moves the device towards the target, emitting updates and
        checking for arrival.
        """
        device_id = session.device_id

        try:
            while True:
                await asyncio.sleep(_get_next_interval())

                # Skip if paused
                if session.state == CruiseState.PAUSED:
                    continue

                # Check if still running
                if session.state != CruiseState.RUNNING:
                    break

                # Calculate actual elapsed time for accurate movement
                now = time.time()
                duration_sec = now - session.last_update_time
                session.last_update_time = now

                # Calculate distance to target
                distance = distance_between(
                    session.current_lat, session.current_lon,
                    session.target_lat, session.target_lon
                )

                # Check if arrived
                if distance < ARRIVAL_THRESHOLD_KM:
                    # Snap to target
                    session.current_lat = session.target_lat
                    session.current_lon = session.target_lon

                    # Set final location on device
                    if self._set_location:
                        await self._set_location(
                            device_id,
                            session.target_lat,
                            session.target_lon
                        )

                    session.state = CruiseState.ARRIVED
                    del self._sessions[device_id]

                    logger.info(
                        f"[{device_id[:8]}] Cruise arrived after "
                        f"{session.distance_traveled_km:.3f}km"
                    )

                    self._emit("cruiseArrived", {
                        "deviceId": device_id,
                        "location": {
                            "latitude": session.current_lat,
                            "longitude": session.current_lon,
                        },
                        "distanceTraveledKm": session.distance_traveled_km,
                        "durationSeconds": time.time() - session.start_time,
                    })
                    return

                # Calculate bearing to target
                bearing = bearing_to(
                    session.current_lat, session.current_lon,
                    session.target_lat, session.target_lon
                )

                # Calculate new position
                new_lat, new_lon = move_location(
                    session.current_lat,
                    session.current_lon,
                    bearing,
                    session.speed_kmh,
                    duration_sec
                )

                # Update distance traveled
                step_distance = distance_between(
                    session.current_lat, session.current_lon,
                    new_lat, new_lon
                )
                session.distance_traveled_km += step_distance

                # Update position
                session.current_lat = new_lat
                session.current_lon = new_lon

                # Set location on device
                if self._set_location:
                    result = await self._set_location(device_id, new_lat, new_lon)
                    if not result.get("success"):
                        logger.warning(
                            f"[{device_id[:8]}] Failed to set location: "
                            f"{result.get('error')}"
                        )
                        # Continue cruise anyway - device might reconnect

                # Emit update event
                self._emit("cruiseUpdate", session.to_dict())

        except asyncio.CancelledError:
            logger.debug(f"[{device_id[:8]}] Cruise loop cancelled")
            raise
        except Exception as e:
            logger.error(f"[{device_id[:8]}] Cruise loop error: {e}")
            session.state = CruiseState.STOPPED
            if device_id in self._sessions:
                del self._sessions[device_id]
            self._emit("cruiseError", {
                "deviceId": device_id,
                "error": str(e),
            })
