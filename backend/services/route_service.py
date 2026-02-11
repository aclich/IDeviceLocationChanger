"""Route cruise service - manages multi-waypoint route navigation.

RouteService is a sequencer/orchestrator that breaks routes into consecutive
point pairs and delegates movement to CruiseService. It does NOT have its
own movement loop.

Flow:
    RouteService breaks each segment's polyline into consecutive point pairs
    → calls CruiseService.start_cruise(current_point, next_point)
    → listens for cruise arrival → advances to next point pair
    → when segment's polyline exhausted → advances to next segment
    → when all segments done → loops or stops

Hybrid sync/async design:
    - Route-building methods (add_waypoint, undo_waypoint, set_loop_mode,
      reroute_and_resume, _add_closure_segment) remain async because they
      call BrouterService.get_route() which is async.
    - Cruise orchestration methods (start/stop/pause/resume_route_cruise,
      _start_next_point_pair, _on_point_arrival, stop_all) are sync because
      they only call CruiseService methods which are sync.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .coordinate_utils import distance_between
from .cruise_service import CruiseService, arrival_threshold_km
from .brouter_service import BrouterService

logger = logging.getLogger(__name__)


class RouteState(str, Enum):
    """Route cruise session state."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ARRIVED = "arrived"
    STOPPED = "stopped"


@dataclass
class Waypoint:
    """A waypoint in the route."""
    lat: float
    lng: float
    name: str  # "START", "1", "2", ...

    def to_dict(self) -> dict:
        return {"lat": self.lat, "lng": self.lng, "name": self.name}


@dataclass
class RouteSegment:
    """A segment of the route between two waypoints."""
    from_waypoint: int  # Index into Route.waypoints
    to_waypoint: int
    path: list[list[float]]  # [[lat, lng], ...]
    distance_km: float
    is_closure: bool = False
    is_fallback: bool = False

    def to_dict(self) -> dict:
        return {
            "fromWaypoint": self.from_waypoint,
            "toWaypoint": self.to_waypoint,
            "path": self.path,
            "distanceKm": self.distance_km,
            "isClosure": self.is_closure,
            "isFallback": self.is_fallback,
        }


@dataclass
class Route:
    """A multi-waypoint route."""
    waypoints: list[Waypoint] = field(default_factory=list)
    segments: list[RouteSegment] = field(default_factory=list)
    loop_mode: bool = False
    total_distance_km: float = 0.0

    def recalculate_distance(self) -> None:
        """Recalculate total distance from segments."""
        self.total_distance_km = sum(s.distance_km for s in self.segments)

    def to_dict(self) -> dict:
        return {
            "waypoints": [w.to_dict() for w in self.waypoints],
            "segments": [s.to_dict() for s in self.segments],
            "loopMode": self.loop_mode,
            "totalDistanceKm": self.total_distance_km,
        }


@dataclass
class RouteSession:
    """Per-device route cruise session state.

    RouteService is a sequencer — it tracks which point pair to feed to
    CruiseService next. CruiseService owns the movement loop and thread.
    RouteSession only holds route progression state.
    """
    device_id: str
    route: Route
    speed_kmh: float
    state: RouteState = RouteState.IDLE

    # Route progression
    current_segment_index: int = 0
    current_step_in_segment: int = 0
    segments_completed: int = 0
    loops_completed: int = 0

    # Bridge cruise: smooth transition between segment endpoints
    bridge_from: Optional[list[float]] = None  # [lat, lng] — last point of completed segment
    is_bridging: bool = False  # True during a bridge cruise

    # Reroute state (temporary path from joystick/direct position to next waypoint)
    reroute_path: Optional[list[list[float]]] = None
    reroute_step: int = 0

    # Tracking
    start_time: float = field(default_factory=time.time)
    distance_traveled_km: float = 0.0

    def remaining_distance_km(self) -> float:
        """Calculate remaining distance in current iteration."""
        remaining = 0.0
        segments = self.route.segments

        if self.current_segment_index < len(segments):
            # Remaining in current segment
            seg = segments[self.current_segment_index]
            path = seg.path
            for i in range(self.current_step_in_segment, len(path) - 1):
                remaining += distance_between(
                    path[i][0], path[i][1],
                    path[i + 1][0], path[i + 1][1],
                )

            # Full remaining segments
            for i in range(self.current_segment_index + 1, len(segments)):
                remaining += segments[i].distance_km

        return remaining

    def to_dict(self) -> dict:
        return {
            "deviceId": self.device_id,
            "state": self.state.value,
            "speedKmh": self.speed_kmh,
            "currentSegmentIndex": self.current_segment_index,
            "currentStepInSegment": self.current_step_in_segment,
            "segmentsCompleted": self.segments_completed,
            "loopsCompleted": self.loops_completed,
            "distanceTraveledKm": self.distance_traveled_km,
            "remainingDistanceKm": self.remaining_distance_km(),
            "totalSegments": len(self.route.segments),
            "route": self.route.to_dict(),
        }


# Type for event emitter callback
EventEmitter = Callable[[dict], None]


class RouteService:
    """Service for managing route cruise sessions.

    Orchestrates multi-waypoint routes by delegating point-pair movement
    to CruiseService and advancing on arrival.

    Hybrid sync/async: route-building methods are async (BrouterService),
    cruise orchestration methods are sync (CruiseService is sync).
    """

    def __init__(self, cruise_service: CruiseService, brouter_service: BrouterService):
        self._cruise_service = cruise_service
        self._brouter_service = brouter_service

        # Per-device route state (route exists even without active cruise)
        self._routes: dict[str, Route] = {}
        # Per-device cruise sessions (only when cruising)
        self._sessions: dict[str, RouteSession] = {}

        # Event emitter callback
        self._emit_event: Optional[EventEmitter] = None

    def set_event_emitter(self, emitter: EventEmitter) -> None:
        """Set the callback for emitting events to frontend."""
        self._emit_event = emitter

    def _emit(self, event: str, data: dict) -> None:
        """Emit an event to the frontend."""
        if self._emit_event:
            self._emit_event({"event": event, "data": data})

    # =========================================================================
    # Route Building API (async - calls BrouterService)
    # =========================================================================

    async def add_waypoint(
        self, device_id: str, lat: float, lng: float
    ) -> dict:
        """Add a waypoint to the device's route.

        If no route exists, creates one. The first point becomes START
        (auto-set from device location or first click). Subsequent points
        trigger pathfinding from the previous waypoint.
        """
        route = self._routes.get(device_id)
        if route is None:
            route = Route()
            self._routes[device_id] = route

        # If no waypoints yet, this is the START position
        if len(route.waypoints) == 0:
            wp = Waypoint(lat=lat, lng=lng, name="START")
            route.waypoints.append(wp)
            logger.info(f"[{device_id[:8]}] Route: START set at ({lat:.5f},{lng:.5f})")
            self._emit("routeWaypointAdded", {
                "deviceId": device_id,
                "waypoint": wp.to_dict(),
                "route": route.to_dict(),
            })
            return {"success": True, "route": route.to_dict()}

        # Add numbered waypoint and calculate path from previous
        wp_index = len(route.waypoints)
        wp = Waypoint(lat=lat, lng=lng, name=str(wp_index))

        # If loop mode is ON, remove the current closure segment first
        if route.loop_mode and route.segments and route.segments[-1].is_closure:
            route.segments.pop()

        # Get path from last waypoint to new waypoint
        last_wp = route.waypoints[-1]
        result = await self._brouter_service.get_route(
            (last_wp.lat, last_wp.lng), (lat, lng)
        )

        segment = RouteSegment(
            from_waypoint=wp_index - 1,
            to_waypoint=wp_index,
            path=result["path"],
            distance_km=result["distance_km"],
            is_fallback=result["is_fallback"],
        )
        route.waypoints.append(wp)
        route.segments.append(segment)

        # If loop mode is ON, recalculate closure
        if route.loop_mode and len(route.waypoints) >= 2:
            await self._add_closure_segment(device_id, route)

        route.recalculate_distance()

        logger.info(
            f"[{device_id[:8]}] Route: waypoint {wp.name} added, "
            f"{len(route.segments)} segments, {route.total_distance_km:.2f}km"
        )

        self._emit("routeWaypointAdded", {
            "deviceId": device_id,
            "waypoint": wp.to_dict(),
            "route": route.to_dict(),
        })

        return {"success": True, "route": route.to_dict()}

    async def undo_waypoint(self, device_id: str) -> dict:
        """Remove the last waypoint and its segment.

        If loop mode is ON, also removes old closure and recalculates.
        """
        route = self._routes.get(device_id)
        if not route or len(route.waypoints) == 0:
            return {"success": False, "error": "No waypoint to undo"}

        # Cannot modify while cruising
        session = self._sessions.get(device_id)
        if session and session.state == RouteState.RUNNING:
            return {"success": False, "error": "Cannot modify route while cruising"}

        # If only START remains, clear the route entirely
        if len(route.waypoints) == 1:
            self._routes.pop(device_id, None)
            logger.info(f"[{device_id[:8]}] Route: undo START, route cleared")
            self._emit("routeWaypointAdded", {
                "deviceId": device_id,
                "route": Route().to_dict(),
            })
            return {"success": True, "route": Route().to_dict()}

        # Remove closure segment if present
        if route.loop_mode and route.segments and route.segments[-1].is_closure:
            route.segments.pop()

        # Remove last waypoint and its incoming segment
        route.waypoints.pop()
        if route.segments:
            route.segments.pop()

        # Recalculate closure if loop mode is ON and we have enough waypoints
        if route.loop_mode and len(route.waypoints) >= 2:
            await self._add_closure_segment(device_id, route)

        route.recalculate_distance()

        logger.info(
            f"[{device_id[:8]}] Route: undo, now {len(route.waypoints)} waypoints"
        )

        self._emit("routeWaypointAdded", {
            "deviceId": device_id,
            "route": route.to_dict(),
        })

        return {"success": True, "route": route.to_dict()}

    async def set_loop_mode(self, device_id: str, enabled: bool) -> dict:
        """Toggle loop mode for the route.

        Safe to call during active cruise. When disabling loop while
        cruising on the closure segment, we keep it so the segment
        finishes naturally - the route will just stop instead of looping.
        """
        route = self._routes.get(device_id)
        if not route:
            route = Route()
            self._routes[device_id] = route

        route.loop_mode = enabled
        session = self._sessions.get(device_id)

        if enabled and len(route.waypoints) >= 2:
            # Add closure segment if not already present
            if not route.segments or not route.segments[-1].is_closure:
                await self._add_closure_segment(device_id, route)
        elif not enabled:
            # Remove closure segment only if no active session is on it
            if route.segments and route.segments[-1].is_closure:
                closure_index = len(route.segments) - 1
                on_closure = (
                    session
                    and session.state == RouteState.RUNNING
                    and session.current_segment_index >= closure_index
                )
                if not on_closure:
                    route.segments.pop()
                # If on closure, keep it - route will stop after this segment

        route.recalculate_distance()

        logger.info(f"[{device_id[:8]}] Route: loop mode {'ON' if enabled else 'OFF'}")

        return {"success": True, "route": route.to_dict()}

    def clear_route(self, device_id: str) -> dict:
        """Clear all waypoints and segments for a device."""
        # Stop any active cruise first
        session = self._sessions.get(device_id)
        if session:
            return {"success": False, "error": "Stop route cruise before clearing"}

        self._routes.pop(device_id, None)

        logger.info(f"[{device_id[:8]}] Route: cleared")

        return {"success": True, "route": Route().to_dict()}

    def get_route(self, device_id: str) -> Optional[dict]:
        """Get route definition for a device, or None if no route exists."""
        route = self._routes.get(device_id)
        return route.to_dict() if route else None

    def get_route_session(self, device_id: str) -> Optional[dict]:
        """Get active route cruise session for a device, or None."""
        session = self._sessions.get(device_id)
        return session.to_dict() if session else None

    def get_route_status(self, device_id: str) -> dict:
        """Get current route and cruise state for a device."""
        route = self._routes.get(device_id)
        session = self._sessions.get(device_id)

        result = {
            "route": route.to_dict() if route else Route().to_dict(),
        }

        if session:
            result["cruiseState"] = session.to_dict()
        else:
            result["cruiseState"] = {"state": RouteState.IDLE.value}

        return result

    async def _add_closure_segment(self, device_id: str, route: Route) -> None:
        """Calculate and append closure segment (last waypoint -> START)."""
        last_wp = route.waypoints[-1]
        start_wp = route.waypoints[0]

        result = await self._brouter_service.get_route(
            (last_wp.lat, last_wp.lng), (start_wp.lat, start_wp.lng)
        )

        closure = RouteSegment(
            from_waypoint=len(route.waypoints) - 1,
            to_waypoint=0,
            path=result["path"],
            distance_km=result["distance_km"],
            is_closure=True,
            is_fallback=result["is_fallback"],
        )
        route.segments.append(closure)

    # =========================================================================
    # Route Cruise API (sync - CruiseService is sync)
    # =========================================================================

    def start_route_cruise(
        self, device_id: str, speed_kmh: float
    ) -> dict:
        """Start cruising along the route.

        Registers an arrival callback on CruiseService and feeds the
        first point pair.
        """
        route = self._routes.get(device_id)
        if not route or len(route.waypoints) < 2:
            return {"success": False, "error": "Route needs at least 2 points"}

        if not route.segments:
            return {"success": False, "error": "Route has no segments"}

        # Stop any existing route cruise
        if device_id in self._sessions:
            self.stop_route_cruise(device_id)

        # Stop any existing regular cruise
        self._cruise_service.stop_cruise(device_id)

        # Create session
        session = RouteSession(
            device_id=device_id,
            route=route,
            speed_kmh=speed_kmh,
        )
        session.state = RouteState.RUNNING
        self._sessions[device_id] = session

        # Register arrival callback
        self._cruise_service.on_arrival(device_id, self._on_point_arrival)

        # Feed first point pair
        self._start_next_point_pair(session)

        logger.info(
            f"[{device_id[:8]}] Route cruise started: "
            f"{len(route.segments)} segments, {route.total_distance_km:.2f}km "
            f"at {speed_kmh}km/h"
        )

        self._emit("routeStarted", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    def pause_route_cruise(self, device_id: str) -> dict:
        """Pause route cruise."""
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active route cruise"}

        if session.state != RouteState.RUNNING:
            return {"success": False, "error": f"Cannot pause: route is {session.state.value}"}

        session.state = RouteState.PAUSED
        self._cruise_service.pause_cruise(device_id)

        logger.info(f"[{device_id[:8]}] Route cruise paused")

        self._emit("routeUpdate", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    def resume_route_cruise(self, device_id: str) -> dict:
        """Resume paused route cruise."""
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active route cruise"}

        if session.state != RouteState.PAUSED:
            return {"success": False, "error": f"Cannot resume: route is {session.state.value}"}

        session.state = RouteState.RUNNING
        self._cruise_service.resume_cruise(device_id)

        logger.info(f"[{device_id[:8]}] Route cruise resumed")

        self._emit("routeUpdate", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    def stop_route_cruise(self, device_id: str) -> dict:
        """Stop route cruise."""
        session = self._sessions.pop(device_id, None)
        if not session:
            return {"success": True, "message": "No active route cruise"}

        session.state = RouteState.STOPPED

        # Remove arrival callback and stop underlying cruise
        self._cruise_service.remove_arrival_callback(device_id)
        self._cruise_service.stop_cruise(device_id)

        logger.info(f"[{device_id[:8]}] Route cruise stopped")

        self._emit("routeUpdate", session.to_dict())

        return {"success": True}

    async def reroute_and_resume(
        self, device_id: str, current_lat: float, current_lng: float
    ) -> dict:
        """Resume route cruise with rerouting from current position.

        Used after joystick/direct mode moves the device away from the
        expected route position. Calculates a new path from the current
        position to the next waypoint target and resumes cruising.

        Async because it calls BrouterService.get_route(), but delegates
        to sync _start_next_point_pair() for cruise orchestration.
        """
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active route cruise"}

        if session.state != RouteState.PAUSED:
            return {
                "success": False,
                "error": f"Cannot reroute: route is {session.state.value}",
            }

        segments = session.route.segments
        if session.current_segment_index >= len(segments):
            return {"success": False, "error": "Route has no remaining segments"}

        # Find target waypoint of current segment
        seg = segments[session.current_segment_index]
        target_wp = session.route.waypoints[seg.to_waypoint]

        logger.info(
            f"[{device_id[:8]}] Rerouting from ({current_lat:.5f},{current_lng:.5f}) "
            f"to waypoint {target_wp.name} ({target_wp.lat:.5f},{target_wp.lng:.5f})"
        )

        # Get Brouter path from current position to target waypoint
        result = await self._brouter_service.get_route(
            (current_lat, current_lng), (target_wp.lat, target_wp.lng)
        )

        # Set reroute path - _start_next_point_pair will process this first
        session.reroute_path = result["path"]
        session.reroute_step = 0
        session.state = RouteState.RUNNING

        # Ensure arrival callback is registered
        self._cruise_service.on_arrival(device_id, self._on_point_arrival)

        # Start feeding point pairs from reroute path (sync call)
        self._start_next_point_pair(session)

        logger.info(f"[{device_id[:8]}] Route cruise rerouted and resumed")

        self._emit("routeUpdate", session.to_dict())

        return {"success": True, "session": session.to_dict()}

    def set_route_speed(self, device_id: str, speed_kmh: float) -> dict:
        """Update route cruise speed."""
        session = self._sessions.get(device_id)
        if not session:
            return {"success": False, "error": "No active route cruise"}

        speed_kmh = max(0.1, speed_kmh)
        session.speed_kmh = speed_kmh
        self._cruise_service.set_cruise_speed(device_id, speed_kmh)

        logger.debug(f"[{device_id[:8]}] Route cruise speed set to {speed_kmh}km/h")

        return {"success": True, "speedKmh": speed_kmh}

    def stop_all(self) -> None:
        """Stop all route cruise sessions. Called on shutdown."""
        for device_id in list(self._sessions.keys()):
            self.stop_route_cruise(device_id)

    # =========================================================================
    # Internal: Point-Pair Sequencing (sync - called from cruise thread)
    # =========================================================================

    def _start_next_point_pair(self, session: RouteSession) -> None:
        """Feed the next point pair from the polyline to CruiseService."""
        # Handle reroute path first (from joystick/direct mode deviation)
        if session.reroute_path is not None:
            path = session.reroute_path
            step = session.reroute_step

            if step >= len(path) - 1:
                # Reroute complete, advance to next segment
                session.bridge_from = path[-1]
                session.reroute_path = None
                session.reroute_step = 0
                session.current_segment_index += 1
                session.current_step_in_segment = 0
                session.segments_completed += 1
                logger.debug(
                    f"[{session.device_id[:8]}] Reroute segment complete, "
                    f"advancing to segment {session.current_segment_index}"
                )
                self._emit("routeSegmentComplete", session.to_dict())
                self._start_next_point_pair(session)
                return

            current_pt = path[step]
            next_pt = path[step + 1]

            # Skip pairs closer than arrival threshold (5m) - auto-advance
            dist = distance_between(
                current_pt[0], current_pt[1], next_pt[0], next_pt[1]
            )
            if dist < arrival_threshold_km(session.speed_kmh):
                session.reroute_step += 1
                self._start_next_point_pair(session)
                return

            self._cruise_service.start_cruise(
                device_id=session.device_id,
                start_lat=current_pt[0],
                start_lon=current_pt[1],
                target_lat=next_pt[0],
                target_lon=next_pt[1],
                speed_kmh=session.speed_kmh,
            )
            return

        segments = session.route.segments

        # Check if all segments are traversed
        if session.current_segment_index >= len(segments):
            if session.route.loop_mode:
                session.bridge_from = segments[-1].path[-1]
                session.current_segment_index = 0
                session.current_step_in_segment = 0
                session.loops_completed += 1
                logger.info(
                    f"[{session.device_id[:8]}] Route loop {session.loops_completed} complete"
                )
                self._emit("routeLoopComplete", session.to_dict())
                # Continue with first segment
                self._start_next_point_pair(session)
                return
            else:
                # Route complete
                session.state = RouteState.ARRIVED
                self._cruise_service.remove_arrival_callback(session.device_id)
                # Clean up CruiseService session (we're inside its callback)
                self._cruise_service.cleanup_session(session.device_id)
                del self._sessions[session.device_id]
                logger.info(
                    f"[{session.device_id[:8]}] Route arrived after "
                    f"{session.distance_traveled_km:.2f}km"
                )
                self._emit("routeArrived", session.to_dict())
                return

        # Bridge cruise: smooth transition between segment endpoints
        if session.bridge_from is not None:
            bridge_from = session.bridge_from
            session.bridge_from = None

            seg = segments[session.current_segment_index]
            bridge_to = seg.path[0]
            gap = distance_between(bridge_from[0], bridge_from[1], bridge_to[0], bridge_to[1])

            if gap >= arrival_threshold_km(session.speed_kmh):
                session.is_bridging = True
                self._cruise_service.start_cruise(
                    device_id=session.device_id,
                    start_lat=bridge_from[0], start_lon=bridge_from[1],
                    target_lat=bridge_to[0], target_lon=bridge_to[1],
                    speed_kmh=session.speed_kmh,
                )
                return
            # Gap < 5m — fall through to normal processing

        segment = segments[session.current_segment_index]
        coordinates = segment.path
        step = session.current_step_in_segment

        if step >= len(coordinates) - 1:
            # Segment polyline exhausted, advance to next segment
            session.bridge_from = coordinates[-1]
            session.current_segment_index += 1
            session.current_step_in_segment = 0
            session.segments_completed += 1
            logger.debug(
                f"[{session.device_id[:8]}] Segment {session.segments_completed} complete"
            )
            self._emit("routeSegmentComplete", session.to_dict())
            # Recurse to start next segment
            self._start_next_point_pair(session)
            return

        # Feed point pair to CruiseService
        current_pt = coordinates[step]
        next_pt = coordinates[step + 1]

        # Skip pairs closer than arrival threshold (5m) - auto-advance
        dist = distance_between(
            current_pt[0], current_pt[1], next_pt[0], next_pt[1]
        )
        if dist < arrival_threshold_km(session.speed_kmh):
            session.current_step_in_segment += 1
            self._start_next_point_pair(session)
            return

        self._cruise_service.start_cruise(
            device_id=session.device_id,
            start_lat=current_pt[0],
            start_lon=current_pt[1],
            target_lat=next_pt[0],
            target_lon=next_pt[1],
            speed_kmh=session.speed_kmh,
        )

    def _on_point_arrival(
        self, device_id: str, cruise_status: dict
    ) -> None:
        """Called by CruiseService when it arrives at the current target point."""
        session = self._sessions.get(device_id)
        if not session or session.state != RouteState.RUNNING:
            return

        # Track distance from this point pair
        session.distance_traveled_km += cruise_status.get(
            "distanceTraveledKm", 0
        )

        # Advance to next point in reroute or normal path
        if session.is_bridging:
            session.is_bridging = False
            # Bridge done — don't advance step; normal processing starts from step 0
        elif session.reroute_path is not None:
            session.reroute_step += 1
        else:
            session.current_step_in_segment += 1

        # Emit progress update
        self._emit("routeUpdate", session.to_dict())

        # Feed next point pair
        self._start_next_point_pair(session)
