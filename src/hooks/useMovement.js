import { useState, useCallback, useRef, useEffect } from 'react';
import { moveLocation, directionFromOffset, speedMultiplier } from '../utils/coordinateCalculator';

const UPDATE_INTERVAL_BASE_MS = 100; // Base interval between location updates
const UPDATE_INTERVAL_JITTER_MS = 100; // Random jitter (0-100ms) added to base

// Helper to get next interval with jitter (100-200ms)
const getNextInterval = () => UPDATE_INTERVAL_BASE_MS + Math.random() * UPDATE_INTERVAL_JITTER_MS;

/**
 * Hook for managing joystick movement.
 * Joystick mode requires real-time user input, so it stays in the frontend.
 *
 * Note: Cruise mode is now handled by the backend (useBackend hook).
 *
 * @param {Object} options
 * @param {Object} options.location - Current location {latitude, longitude}
 * @param {Function} options.setLocation - Function to set location on device
 */
export function useMovement({ location, setLocation }) {
  // Movement state
  const [isMoving, setIsMoving] = useState(false);
  const [speed, setSpeed] = useState(5.0); // km/h

  // Internal refs
  const timeoutRef = useRef(null);
  const lastUpdateTimeRef = useRef(null);
  const locationRef = useRef(location);
  const joystickRef = useRef({ dx: 0, dy: 0, maxDistance: 50 });
  const speedRef = useRef(speed);

  // Keep refs updated
  useEffect(() => {
    locationRef.current = location;
  }, [location]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  // =========================================================================
  // Movement Loop
  // =========================================================================

  const stopMovementLoop = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    lastUpdateTimeRef.current = null;
    setIsMoving(false);
  }, []);

  const startMovementLoop = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    setIsMoving(true);
    lastUpdateTimeRef.current = performance.now();

    const tick = async () => {
      // Calculate actual elapsed time for accurate movement
      const now = performance.now();
      const durationSec = (now - lastUpdateTimeRef.current) / 1000;
      lastUpdateTimeRef.current = now;

      const currentLoc = locationRef.current;
      if (!currentLoc) {
        timeoutRef.current = setTimeout(tick, getNextInterval());
        return;
      }

      // Joystick mode: direction and speed based on joystick position
      const { dx, dy, maxDistance } = joystickRef.current;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < 1) {
        // Joystick centered, don't move but keep loop running
        timeoutRef.current = setTimeout(tick, getNextInterval());
        return;
      }

      const joystickDirection = directionFromOffset(dx, dy);
      const speedMult = speedMultiplier(dx, dy, maxDistance);
      const effectiveSpeed = speedRef.current * speedMult;

      const [newLat, newLon] = moveLocation(
        currentLoc.latitude,
        currentLoc.longitude,
        joystickDirection,
        effectiveSpeed,
        durationSec
      );

      // Update local ref immediately for smooth movement
      locationRef.current = { latitude: newLat, longitude: newLon };
      // Send to backend
      await setLocation(newLat, newLon);

      // Schedule next tick with jitter
      timeoutRef.current = setTimeout(tick, getNextInterval());
    };

    // Start the loop
    timeoutRef.current = setTimeout(tick, getNextInterval());
  }, [setLocation, stopMovementLoop]);

  // =========================================================================
  // Joystick Mode
  // =========================================================================

  const updateJoystick = useCallback((dx, dy, maxDistance = 50) => {
    joystickRef.current = { dx, dy, maxDistance };

    const distance = Math.sqrt(dx * dx + dy * dy);

    // Start movement if joystick moved significantly
    if (distance > 1 && !timeoutRef.current) {
      if (!locationRef.current) {
        console.warn('Cannot start joystick movement: no location set');
        return;
      }
      startMovementLoop();
    }
    // Stop if joystick returned to center
    else if (distance <= 1 && timeoutRef.current) {
      stopMovementLoop();
    }
  }, [startMovementLoop, stopMovementLoop]);

  const releaseJoystick = useCallback(() => {
    joystickRef.current = { dx: 0, dy: 0, maxDistance: 50 };
    stopMovementLoop();
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

    // Joystick mode
    updateJoystick,
    releaseJoystick,

    // Settings
    setSpeed: updateSpeed,
  };
}
