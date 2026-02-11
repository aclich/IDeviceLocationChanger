import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { isBrowserMode } from '../utils/backendClient';

// Simple logger for useBackend hook events
const logger = {
  prefix: '[useBackend]',
  info: (...args) => console.log(`%c${logger.prefix}`, 'color: #4ade80', ...args),
  error: (...args) => console.error(`%c${logger.prefix}`, 'color: #f87171', ...args),
  warn: (...args) => console.warn(`%c${logger.prefix}`, 'color: #fbbf24', ...args),
};

// Send request via window.backend (logging is handled by backendClient)
async function sendRequest(method, params = {}) {
  try {
    return await window.backend.send(method, params);
  } catch (error) {
    logger.error(`Request failed:`, error);
    return { error: { code: -1, message: error.message } };
  }
}

/**
 * Hook for backend communication.
 * Handles device management, location setting, tunnel management, and cruise mode.
 *
 * Note: Cruise mode runs in the backend to continue working when browser is inactive.
 * Joystick calculations still happen in useMovement hook (requires real-time input).
 */
export function useBackend() {
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [location, setLocation] = useState(null);
  const [tunnelStatus, setTunnelStatus] = useState(null); // { status, address?, port? } from enriched selectDevice
  const [tunneldState, setTunneldState] = useState({ state: 'starting' }); // tunneld daemon: starting, ready, error
  const [cruiseStatus, setCruiseStatus] = useState(null); // { state, location, target, speedKmh, remainingKm }
  const [routeStatus, setRouteStatus] = useState(null); // Route cruise session state
  const [routeState, setRouteState] = useState(null); // Route waypoints, segments, loop mode
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(true); // Updated in useEffect after backend init
  const [deviceSwitchLoading, setDeviceSwitchLoading] = useState(false);

  // Badge state for all devices (SSE-driven)
  const [badgeMap, setBadgeMap] = useState({});

  const cleanupRef = useRef(null);
  const healthCheckRef = useRef(null);

  // Ref to avoid stale closures in SSE handler
  const selectedDeviceRef = useRef(null);

  // Check backend connection
  const checkConnection = useCallback(async () => {
    if (!window.backend) {
      setIsConnected(false);
      return false;
    }

    const healthy = await window.backend.checkHealth();
    setIsConnected(healthy);
    if (!healthy) {
      setError('Backend not running. Start with: python backend/main.py');
    } else {
      setError(null);
    }
    return healthy;
  }, []);

  // Listen for backend events and set up initial connection
  useEffect(() => {
    if (!window.backend) {
      logger.error('Backend not available - window.backend is undefined');
      setError('Backend not available');
      setIsConnected(false);
      return;
    }

    // Check health on mount
    logger.info('Checking backend health');
    checkConnection();

    logger.info('Setting up backend event listener (SSE)');

    // Helper: update badge map for any device event
    const updateBadge = (data) => {
      const deviceId = data?.deviceId;
      if (!deviceId) return;
      setBadgeMap(prev => ({ ...prev, [deviceId]: { ...prev[deviceId] } }));
    };

    const updateBadgeCruise = (deviceId, cruising, paused) => {
      if (!deviceId) return;
      setBadgeMap(prev => ({
        ...prev,
        [deviceId]: {
          ...prev[deviceId],
          cruising,
          cruisePaused: paused,
          // Clear route fields if this is a standalone cruise
          routeCruising: prev[deviceId]?.routeCruising || false,
          routePaused: prev[deviceId]?.routePaused || false,
          routeProgress: prev[deviceId]?.routeProgress || null,
        },
      }));
    };

    const updateBadgeRoute = (deviceId, cruising, paused, progress) => {
      if (!deviceId) return;
      setBadgeMap(prev => ({
        ...prev,
        [deviceId]: {
          cruising: false,
          cruisePaused: false,
          routeCruising: cruising,
          routePaused: paused,
          routeProgress: progress,
        },
      }));
    };

    const clearBadge = (deviceId) => {
      if (!deviceId) return;
      setBadgeMap(prev => {
        const next = { ...prev };
        delete next[deviceId];
        return next;
      });
    };

    cleanupRef.current = window.backend.onEvent((message) => {
      const eventDeviceId = message.data?.deviceId;
      const isForSelected = eventDeviceId && selectedDeviceRef.current?.id === eventDeviceId;

      switch (message.event) {
        case 'connected':
          setIsConnected(true);
          setError(null);
          // Re-seed badge state on SSE reconnection
          sendRequest('getAllDeviceStates').then(resp => {
            if (resp.result) setBadgeMap(resp.result);
          });
          break;

        case 'error':
          setError(message.data?.message || 'Unknown error');
          break;

        case 'tunneldStatus':
          setTunneldState(message.data);
          break;

        case 'tunnelStatusChanged':
          if (message.data?.udid && isForSelected) {
            setTunnelStatus({
              status: message.data.status,
              address: message.data.address,
              port: message.data.port,
              udid: message.data.udid,
            });
          }
          break;

        // Cruise events — update badge for ALL, full state only for selected
        case 'cruiseStarted':
          updateBadgeCruise(eventDeviceId, true, false);
          if (isForSelected) setCruiseStatus(message.data);
          break;

        case 'cruiseUpdate':
          // Badge: no change needed (already cruising)
          if (isForSelected) {
            setCruiseStatus(message.data);
            if (message.data?.location) setLocation(message.data.location);
          }
          break;

        case 'cruiseArrived':
          updateBadgeCruise(eventDeviceId, false, false);
          if (isForSelected) {
            setCruiseStatus(null);
            if (message.data?.location) setLocation(message.data.location);
            logger.info(`Cruise arrived after ${message.data?.distanceTraveledKm?.toFixed(2)}km`);
          }
          break;

        case 'cruiseStopped':
          updateBadgeCruise(eventDeviceId, false, false);
          if (isForSelected) setCruiseStatus(null);
          break;

        case 'cruisePaused':
          updateBadgeCruise(eventDeviceId, true, true);
          if (isForSelected) setCruiseStatus(message.data);
          break;

        case 'cruiseResumed':
          updateBadgeCruise(eventDeviceId, true, false);
          if (isForSelected) setCruiseStatus(message.data);
          break;

        case 'cruiseError':
          updateBadgeCruise(eventDeviceId, false, false);
          if (isForSelected) {
            setCruiseStatus(null);
            setError(`Cruise error: ${message.data?.error}`);
          }
          break;

        // Route events — update badge for ALL, full state only for selected
        case 'routeStarted': {
          const total = message.data?.totalSegments || 0;
          const current = (message.data?.currentSegmentIndex || 0);
          updateBadgeRoute(eventDeviceId, true, false, `${current}/${total}`);
          if (isForSelected) setRouteStatus(message.data);
          break;
        }

        case 'routeUpdate': {
          const total = message.data?.totalSegments || 0;
          const current = (message.data?.currentSegmentIndex || 0);
          const isPaused = message.data?.state === 'paused';
          updateBadgeRoute(eventDeviceId, true, isPaused, `${current}/${total}`);
          if (isForSelected) {
            setRouteStatus(message.data);
            if (message.data?.route) setRouteState(message.data.route);
          }
          break;
        }

        case 'routeArrived':
          updateBadgeRoute(eventDeviceId, false, false, null);
          if (isForSelected) {
            setRouteStatus(null);
            setCruiseStatus(null);
          }
          break;

        case 'routeSegmentComplete': {
          const total = message.data?.totalSegments || 0;
          const current = (message.data?.currentSegmentIndex || 0);
          updateBadgeRoute(eventDeviceId, true, false, `${current}/${total}`);
          if (isForSelected) setRouteStatus(message.data);
          break;
        }

        case 'routeLoopComplete': {
          const total = message.data?.totalSegments || 0;
          updateBadgeRoute(eventDeviceId, true, false, `0/${total}`);
          if (isForSelected) setRouteStatus(message.data);
          break;
        }

        case 'routeWaypointAdded':
          if (isForSelected && message.data?.route) {
            setRouteState(message.data.route);
          }
          break;

        case 'routeError':
          updateBadgeRoute(eventDeviceId, false, false, null);
          if (isForSelected) {
            setRouteStatus(null);
            setError(`Route error: ${message.data?.error}`);
          }
          break;

        default:
          break;
      }
    });

    return () => {
      if (cleanupRef.current) {
        logger.info('Cleaning up backend event listener');
        cleanupRef.current();
      }
    };
  }, [checkConnection]);

  // Health check interval - only runs when disconnected
  useEffect(() => {
    // Clear any existing interval
    if (healthCheckRef.current) {
      clearInterval(healthCheckRef.current);
      healthCheckRef.current = null;
    }

    if (!isConnected) {
      // When disconnected, check every 5 seconds
      logger.info('Starting health check interval (disconnected)');
      healthCheckRef.current = setInterval(checkConnection, 5000);
    }

    return () => {
      if (healthCheckRef.current) {
        clearInterval(healthCheckRef.current);
        healthCheckRef.current = null;
      }
    };
  }, [isConnected, checkConnection]);

  // =========================================================================
  // Device Operations
  // =========================================================================

  const listDevices = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await sendRequest('listDevices');
      if (response.result) {
        setDevices(response.result.devices);
      } else if (response.error) {
        setError(response.error.message);
      }
      return response;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const selectDevice = useCallback(async (deviceId, deviceObj = null) => {
    setError(null);
    setDeviceSwitchLoading(true);
    try {
      // Find device object from devices list if not provided
      const device = deviceObj || devices.find(d => d.id === deviceId) || { id: deviceId, name: deviceId };
      setSelectedDevice(device);
      selectedDeviceRef.current = device;

      // Query backend for full device state
      const response = await sendRequest('getDeviceState', { deviceId });
      if (response.result) {
        const state = response.result;
        setLocation(state.location || null);
        setTunnelStatus(state.tunnel || null);
        setCruiseStatus(state.cruise || null);
        setRouteState(state.route || null);
        setRouteStatus(state.routeCruise || null);
        logger.info('Device selected:', device.name);
      } else if (response.error) {
        setError(response.error.message);
      }
      return response;
    } finally {
      setDeviceSwitchLoading(false);
    }
  }, [devices]);

  // =========================================================================
  // Location Operations
  // =========================================================================

  const setLocationOnDevice = useCallback(async (latitude, longitude) => {
    if (!selectedDevice) {
      setError('No device selected');
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('setLocation', {
      deviceId: selectedDevice.id,
      latitude,
      longitude,
    });
    if (response.result?.success) {
      setLocation({ latitude, longitude });
    } else if (response.error) {
      setError(response.error.message);
    } else if (response.result && !response.result.success) {
      setError(response.result.error || 'Failed to set location');
    }
    return response;
  }, [selectedDevice]);

  const clearLocation = useCallback(async () => {
    if (!selectedDevice) {
      setError('No device selected');
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('clearLocation', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) {
      setLocation(null);
      logger.info('Location cleared');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, [selectedDevice]);

  const getLastLocation = useCallback(async (deviceId = null) => {
    const id = deviceId || selectedDevice?.id;
    if (!id) {
      return { error: { message: 'No device specified' } };
    }
    const response = await sendRequest('getLastLocation', { deviceId: id });
    return response;
  }, [selectedDevice]);

  // =========================================================================
  // Tunnel Operations
  // =========================================================================

  const retryTunneld = useCallback(async () => {
    setTunneldState({ state: 'starting' });
    const response = await sendRequest('retryTunneld');
    // SSE events will update tunneldState
    return response;
  }, []);

  const disconnectDevice = useCallback(async (deviceId) => {
    const response = await sendRequest('disconnectDevice', { deviceId });
    if (response.result?.success) {
      setSelectedDevice(null);
      selectedDeviceRef.current = null;
      setLocation(null);
      setTunnelStatus(null);
      setCruiseStatus(null);
      setRouteStatus(null);
      setRouteState(null);
      // Clear badge for disconnected device
      setBadgeMap(prev => {
        const next = { ...prev };
        delete next[deviceId];
        return next;
      });
      logger.info('Device disconnected');
    }
    return response;
  }, []);

  // =========================================================================
  // Cruise Operations
  // =========================================================================

  const startCruise = useCallback(async (startLocation, targetLocation, speedKmh = 5) => {
    if (!selectedDevice) {
      setError('No device selected');
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('startCruise', {
      deviceId: selectedDevice.id,
      startLatitude: startLocation.latitude,
      startLongitude: startLocation.longitude,
      targetLatitude: targetLocation.latitude,
      targetLongitude: targetLocation.longitude,
      speedKmh,
    });
    if (response.result?.success) {
      setCruiseStatus(response.result.session);
      logger.info('Cruise started');
    } else if (response.error) {
      setError(response.error.message);
    } else if (response.result && !response.result.success) {
      setError(response.result.error || 'Failed to start cruise');
    }
    return response;
  }, [selectedDevice]);

  const stopCruise = useCallback(async () => {
    if (!selectedDevice) {
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('stopCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) {
      setCruiseStatus(null);
      logger.info('Cruise stopped');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, [selectedDevice]);

  const pauseCruise = useCallback(async () => {
    if (!selectedDevice) {
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('pauseCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) {
      setCruiseStatus(response.result.session);
      logger.info('Cruise paused');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, [selectedDevice]);

  const resumeCruise = useCallback(async () => {
    if (!selectedDevice) {
      return { error: { message: 'No device selected' } };
    }
    setError(null);
    const response = await sendRequest('resumeCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) {
      setCruiseStatus(response.result.session);
      logger.info('Cruise resumed');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, [selectedDevice]);

  const setCruiseSpeed = useCallback(async (speedKmh) => {
    if (!selectedDevice) {
      return { error: { message: 'No device selected' } };
    }
    const response = await sendRequest('setCruiseSpeed', {
      deviceId: selectedDevice.id,
      speedKmh,
    });
    if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, [selectedDevice]);

  const getCruiseStatus = useCallback(async () => {
    if (!selectedDevice) {
      return { error: { message: 'No device selected' } };
    }
    const response = await sendRequest('getCruiseStatus', {
      deviceId: selectedDevice.id,
    });
    if (response.result) {
      setCruiseStatus(response.result.state !== 'idle' ? response.result : null);
    }
    return response;
  }, [selectedDevice]);

  // =========================================================================
  // Route Cruise Operations
  // =========================================================================

  const addRouteWaypoint = useCallback(async (lat, lng) => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('addRouteWaypoint', {
      deviceId: selectedDevice.id, lat, lng,
    });
    if (response.result?.route) {
      setRouteState(response.result.route);
    }
    return response;
  }, [selectedDevice]);

  const undoRouteWaypoint = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('undoRouteWaypoint', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.route) {
      setRouteState(response.result.route);
    }
    return response;
  }, [selectedDevice]);

  const startRouteCruise = useCallback(async (speedKmh = 5) => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    setError(null);
    const response = await sendRequest('startRouteCruise', {
      deviceId: selectedDevice.id, speedKmh,
    });
    if (response.result?.session) {
      setRouteStatus(response.result.session);
    } else if (response.error) {
      setError(response.error.message);
    } else if (response.result && !response.result.success) {
      setError(response.result.error);
    }
    return response;
  }, [selectedDevice]);

  const pauseRouteCruise = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('pauseRouteCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.session) setRouteStatus(response.result.session);
    return response;
  }, [selectedDevice]);

  const resumeRouteCruise = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('resumeRouteCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.session) setRouteStatus(response.result.session);
    return response;
  }, [selectedDevice]);

  const rerouteRouteCruise = useCallback(async (lat, lng) => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('rerouteRouteCruise', {
      deviceId: selectedDevice.id, lat, lng,
    });
    if (response.result?.session) setRouteStatus(response.result.session);
    return response;
  }, [selectedDevice]);

  const stopRouteCruise = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('stopRouteCruise', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) setRouteStatus(null);
    return response;
  }, [selectedDevice]);

  const setRouteCruiseSpeed = useCallback(async (speedKmh) => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    return await sendRequest('setRouteCruiseSpeed', {
      deviceId: selectedDevice.id, speedKmh,
    });
  }, [selectedDevice]);

  const clearRoute = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('clearRoute', {
      deviceId: selectedDevice.id,
    });
    if (response.result?.success) {
      setRouteState(null);
      setRouteStatus(null);
    }
    return response;
  }, [selectedDevice]);

  const setRouteLoopMode = useCallback(async (enabled) => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('setRouteLoopMode', {
      deviceId: selectedDevice.id, enabled,
    });
    if (response.result?.route) {
      setRouteState(response.result.route);
    }
    return response;
  }, [selectedDevice]);

  const getRouteStatus = useCallback(async () => {
    if (!selectedDevice) return { error: { message: 'No device selected' } };
    const response = await sendRequest('getRouteStatus', {
      deviceId: selectedDevice.id,
    });
    if (response.result) {
      if (response.result.route) setRouteState(response.result.route);
      if (response.result.cruiseState) setRouteStatus(
        response.result.cruiseState.state !== 'idle' ? response.result.cruiseState : null
      );
    }
    return response;
  }, [selectedDevice]);

  // =========================================================================
  // Return API
  // =========================================================================

  // Seed badge map on initial load
  const seedBadges = useCallback(async () => {
    const resp = await sendRequest('getAllDeviceStates');
    if (resp.result) setBadgeMap(resp.result);
  }, []);

  return {
    // State
    devices,
    selectedDevice,
    location,
    tunnelStatus,
    tunneldState,
    cruiseStatus,
    error,
    isLoading,
    isConnected,
    isBrowserMode: isBrowserMode(),
    badgeMap,
    deviceSwitchLoading,

    // Device actions
    listDevices,
    selectDevice,
    disconnectDevice,
    seedBadges,

    // Location actions
    setLocation: setLocationOnDevice,
    clearLocation,
    getLastLocation,

    // Tunnel actions
    retryTunneld,

    // Cruise actions
    startCruise,
    stopCruise,
    pauseCruise,
    resumeCruise,
    setCruiseSpeed,
    getCruiseStatus,

    // Route state
    routeStatus,
    routeState,

    // Route actions
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
    getRouteStatus,

    // Utilities
    clearError: () => setError(null),
    checkConnection,
  };
}
