import { useState, useCallback, useRef, useEffect } from 'react';
import { moveLocation, directionFromOffset, speedMultiplier, bearingTo, distanceBetween } from '../utils/coordinateCalculator';

const UPDATE_INTERVAL_MS = 500; // 500ms between location updates
const ARRIVAL_THRESHOLD_KM = 0.005; // 5 meters - consider arrived

/**
 * Hook for managing movement (cruise mode and joystick).
 * All coordinate calculations happen in frontend, then setLocation is called.
 *
 * @param {Object} options
 * @param {Object} options.location - Current location {latitude, longitude}
 * @param {Function} options.setLocation - Function to set location on device
 */
export function useMovement({ location, setLocation }) {
  // Movement state
  const [isMoving, setIsMoving] = useState(false);
  const [speed, setSpeed] = useState(5.0); // km/h
  const [cruiseTarget, setCruiseTarget] = useState(null); // {latitude, longitude}

  // Internal refs
  const intervalRef = useRef(null);
  const locationRef = useRef(location);
  const joystickRef = useRef({ dx: 0, dy: 0, maxDistance: 50 });
  const modeRef = useRef(null); // 'cruise' or 'joystick'
  const speedRef = useRef(speed);
  const targetRef = useRef(cruiseTarget);

  // Keep refs updated
  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  useEffect(() => {
    targetRef.current = cruiseTarget;
  }, [cruiseTarget]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  // =========================================================================
  // Movement Loop
  // =========================================================================

  const stopMovementLoop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    modeRef.current = null;
    setIsMoving(false);
  }, []);

  const startMovementLoop = useCallback((mode) => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }

    modeRef.current = mode;
    setIsMoving(true);

    intervalRef.current = setInterval(async () => {
      const currentLoc = locationRef.current;
      if (!currentLoc) return;

      let newLat, newLon;
      const durationSec = UPDATE_INTERVAL_MS / 1000;

      if (modeRef.current === 'cruise') {
        const target = targetRef.current;
        if (!target) {
          stopMovementLoop();
          return;
        }

        // Calculate distance to target
        const distance = distanceBetween(
          currentLoc.latitude,
          currentLoc.longitude,
          target.latitude,
          target.longitude
        );

        // Check if arrived
        if (distance < ARRIVAL_THRESHOLD_KM) {
          // Snap to target and stop
          await setLocation(target.latitude, target.longitude);
          stopMovementLoop();
          return;
        }

        // Calculate bearing to target
        const bearing = bearingTo(
          currentLoc.latitude,
          currentLoc.longitude,
          target.latitude,
          target.longitude
        );

        // Move towards target
        [newLat, newLon] = moveLocation(
          currentLoc.latitude,
          currentLoc.longitude,
          bearing,
          speedRef.current,
          durationSec
        );
      } else if (modeRef.current === 'joystick') {
        // Joystick mode: direction and speed based on joystick position
        const { dx, dy, maxDistance } = joystickRef.current;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance < 1) {
          return; // Joystick centered, don't move
        }

        const joystickDirection = directionFromOffset(dx, dy);
        const speedMult = speedMultiplier(dx, dy, maxDistance);
        const effectiveSpeed = speedRef.current * speedMult;

        [newLat, newLon] = moveLocation(
          currentLoc.latitude,
          currentLoc.longitude,
          joystickDirection,
          effectiveSpeed,
          durationSec
        );
      }

      if (newLat !== undefined && newLon !== undefined) {
        // Update local ref immediately for smooth movement
        locationRef.current = { latitude: newLat, longitude: newLon };
        // Send to backend
        await setLocation(newLat, newLon);
      }
    }, UPDATE_INTERVAL_MS);
  }, [setLocation, stopMovementLoop]);

  // =========================================================================
  // Cruise Mode
  // =========================================================================

  const startCruise = useCallback((target) => {
    if (!locationRef.current) {
      console.warn('Cannot start cruise: no location set');
      return false;
    }
    if (!target) {
      console.warn('Cannot start cruise: no target set');
      return false;
    }
    setCruiseTarget(target);
    targetRef.current = target;
    startMovementLoop('cruise');
    return true;
  }, [startMovementLoop]);

  const stopCruise = useCallback(() => {
    stopMovementLoop();
    setCruiseTarget(null);
  }, [stopMovementLoop]);

  // =========================================================================
  // Joystick Mode
  // =========================================================================

  const updateJoystick = useCallback((dx, dy, maxDistance = 50) => {
    joystickRef.current = { dx, dy, maxDistance };

    const distance = Math.sqrt(dx * dx + dy * dy);

    // Start movement if joystick moved significantly
    if (distance > 1 && modeRef.current !== 'joystick') {
      if (!locationRef.current) {
        console.warn('Cannot start joystick movement: no location set');
        return;
      }
      startMovementLoop('joystick');
    }
    // Stop if joystick returned to center
    else if (distance <= 1 && modeRef.current === 'joystick') {
      stopMovementLoop();
    }
  }, [startMovementLoop, stopMovementLoop]);

  const releaseJoystick = useCallback(() => {
    joystickRef.current = { dx: 0, dy: 0, maxDistance: 50 };
    if (modeRef.current === 'joystick') {
      stopMovementLoop();
    }
  }, [stopMovementLoop]);

  // =========================================================================
  // Settings
  // =========================================================================

  const updateSpeed = useCallback((newSpeed) => {
    setSpeed(Math.max(1, Math.min(50, newSpeed)));
  }, []);

  // =========================================================================
  // Return API
  // =========================================================================

  return {
    // State
    isMoving,
    speed,
    cruiseTarget,

    // Cruise mode
    startCruise,
    stopCruise,
    setCruiseTarget,

    // Joystick mode
    updateJoystick,
    releaseJoystick,

    // Settings
    setSpeed: updateSpeed,
  };
}
