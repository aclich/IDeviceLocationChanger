import { useState, useCallback, useMemo } from 'react';

/**
 * Hook for managing route cruise mode state and actions.
 * Wraps useBackend route functions with local UI state management.
 */
export function useRouteCruise({
  addRouteWaypoint,
  undoRouteWaypoint,
  startRouteCruise,
  pauseRouteCruise,
  resumeRouteCruise,
  rerouteRouteCruise,
  stopRouteCruise,
  setRouteCruiseSpeed,
  clearRoute,
  setRouteLoopMode,
  routeStatus,
  routeState,
  location,
  selectedDevice,
}) {
  const [routeMode, setRouteMode] = useState(false);
  const [routeLoading, setRouteLoading] = useState(false);

  // Derive cruise state
  const isRouteCruising = routeStatus?.state === 'running' || routeStatus?.state === 'paused';
  const isRoutePaused = routeStatus?.state === 'paused';

  // Route info
  const waypoints = routeState?.waypoints || [];
  const segments = routeState?.segments || [];
  const loopMode = routeState?.loopMode || false;
  const totalDistanceKm = routeState?.totalDistanceKm || 0;
  const hasRoute = waypoints.length >= 2;

  // Add waypoint - handles START auto-set from device location
  const addWaypoint = useCallback(async (lat, lng) => {
    if (!selectedDevice) return;

    setRouteLoading(true);
    try {
      // If no waypoints yet and device has location, auto-set START
      if (waypoints.length === 0 && location) {
        await addRouteWaypoint(location.latitude, location.longitude);
      }

      return await addRouteWaypoint(lat, lng);
    } finally {
      setRouteLoading(false);
    }
  }, [selectedDevice, waypoints.length, location, addRouteWaypoint]);

  const startRoute = useCallback(async (speed) => {
    return await startRouteCruise(speed);
  }, [startRouteCruise]);

  const pauseRoute = useCallback(async () => {
    return await pauseRouteCruise();
  }, [pauseRouteCruise]);

  const resumeRoute = useCallback(async () => {
    // If we have a current location, reroute from it (handles joystick/direct deviations)
    if (location) {
      return await rerouteRouteCruise(location.latitude, location.longitude);
    }
    return await resumeRouteCruise();
  }, [resumeRouteCruise, rerouteRouteCruise, location]);

  const stopRoute = useCallback(async () => {
    return await stopRouteCruise();
  }, [stopRouteCruise]);

  const setRouteSpeed = useCallback(async (speed) => {
    return await setRouteCruiseSpeed(speed);
  }, [setRouteCruiseSpeed]);

  const toggleLoopMode = useCallback(async () => {
    return await setRouteLoopMode(!loopMode);
  }, [setRouteLoopMode, loopMode]);

  const undoWaypoint = useCallback(async () => {
    return await undoRouteWaypoint();
  }, [undoRouteWaypoint]);

  const clearRouteAction = useCallback(async () => {
    return await clearRoute();
  }, [clearRoute]);

  // Progress info
  const progressInfo = useMemo(() => {
    if (!routeStatus || !isRouteCruising) return null;

    const currentSegment = (routeStatus.currentSegmentIndex || 0) + 1;
    const totalSegments = routeStatus.totalSegments || segments.length;
    const remainingKm = routeStatus.remainingDistanceKm || 0;
    const traveledKm = routeStatus.distanceTraveledKm || 0;
    const loopsCompleted = routeStatus.loopsCompleted || 0;

    return {
      currentSegment,
      totalSegments,
      remainingKm,
      traveledKm,
      loopsCompleted,
    };
  }, [routeStatus, isRouteCruising, segments.length]);

  return {
    // State
    routeMode,
    setRouteMode,
    routeLoading,
    isRouteCruising,
    isRoutePaused,
    waypoints,
    segments,
    loopMode,
    totalDistanceKm,
    hasRoute,
    progressInfo,
    routeStatus,

    // Actions
    addWaypoint,
    undoWaypoint,
    startRoute,
    pauseRoute,
    resumeRoute,
    stopRoute,
    setRouteSpeed,
    toggleLoopMode,
    clearRoute: clearRouteAction,
  };
}
