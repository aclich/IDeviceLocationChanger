import { useState, useEffect, useCallback, useRef } from 'react';
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
  const [tunnelStatus, setTunnelStatus] = useState({ running: false });
  const [cruiseStatus, setCruiseStatus] = useState(null); // { state, location, target, speedKmh, remainingKm }
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(true); // Updated in useEffect after backend init

  const cleanupRef = useRef(null);
  const healthCheckRef = useRef(null);

  // Check backend connection
  const checkConnection = useCallback(async () => {
    if (!window.backend) {
      setIsConnected(false);
      return false;
    }

    const healthy = await window.backend.checkHealth();
    setIsConnected(healthy);
    if (!healthy) {
      setError('Backend not running. Start with: python python-backend/main.py');
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

    cleanupRef.current = window.backend.onEvent((message) => {
      // Handle events (logging is done in backendClient)
      switch (message.event) {
        case 'connected':
          // SSE connection established
          setIsConnected(true);
          setError(null);
          break;

        case 'error':
          setError(message.data?.message || 'Unknown error');
          break;

        // Cruise events
        case 'cruiseStarted':
          setCruiseStatus(message.data);
          break;

        case 'cruiseUpdate':
          setCruiseStatus(message.data);
          // Update location from cruise movement
          if (message.data?.location) {
            setLocation(message.data.location);
          }
          break;

        case 'cruiseArrived':
          setCruiseStatus(null);
          // Snap to final location
          if (message.data?.location) {
            setLocation(message.data.location);
          }
          logger.info(`Cruise arrived after ${message.data?.distanceTraveledKm?.toFixed(2)}km`);
          break;

        case 'cruiseStopped':
          setCruiseStatus(null);
          break;

        case 'cruisePaused':
          setCruiseStatus(message.data);
          break;

        case 'cruiseResumed':
          setCruiseStatus(message.data);
          break;

        case 'cruiseError':
          setCruiseStatus(null);
          setError(`Cruise error: ${message.data?.error}`);
          break;

        default:
          // Unknown events are logged by backendClient
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

  const selectDevice = useCallback(async (deviceId) => {
    setError(null);
    const response = await sendRequest('selectDevice', { deviceId });
    if (response.result?.device) {
      setSelectedDevice(response.result.device);
      logger.info('Device selected:', response.result.device.name);
    } else if (response.error) {
      setError(response.error.message);
    } else if (response.result && !response.result.success) {
      setError(response.result.error || 'Failed to select device');
    }
    return response;
  }, []);

  // =========================================================================
  // Location Operations
  // =========================================================================

  const setLocationOnDevice = useCallback(async (latitude, longitude) => {
    setError(null);
    const response = await sendRequest('setLocation', { latitude, longitude });
    if (response.result?.success) {
      setLocation({ latitude, longitude });
    } else if (response.error) {
      setError(response.error.message);
    } else if (response.result && !response.result.success) {
      setError(response.result.error || 'Failed to set location');
    }
    return response;
  }, []);

  const clearLocation = useCallback(async () => {
    setError(null);
    const response = await sendRequest('clearLocation');
    if (response.result?.success) {
      setLocation(null);
      logger.info('Location cleared');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, []);

  // =========================================================================
  // Tunnel Operations
  // =========================================================================

  const startTunnel = useCallback(async (udid = null) => {
    setIsLoading(true);
    setError(null);
    try {
      const params = udid ? { udid } : {};
      const response = await sendRequest('startTunnel', params);
      if (response.result) {
        if (response.result.success) {
          // Map backend response to frontend tunnelStatus format
          setTunnelStatus({
            running: true,
            address: response.result.address,
            port: response.result.port,
            udid: response.result.udid,
          });
          logger.info(`Tunnel started: ${response.result.address}:${response.result.port}`);
        } else {
          setTunnelStatus({ running: false, message: response.result.error });
          setError(response.result.error || 'Failed to start tunnel');
        }
      }
      if (response.error) {
        setError(response.error.message);
      }
      return response;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const stopTunnel = useCallback(async (udid = null) => {
    const params = udid ? { udid } : {};
    const response = await sendRequest('stopTunnel', params);
    if (response.result?.success) {
      setTunnelStatus({ running: false, status: 'no_tunnel' });
      logger.info('Tunnel stopped');
    }
    return response;
  }, []);

  const getTunnelStatus = useCallback(async (udid = null) => {
    const params = udid ? { udid } : {};
    const response = await sendRequest('getTunnelStatus', params);
    if (response.result) {
      setTunnelStatus(response.result);
    }
    return response;
  }, []);

  // =========================================================================
  // Cruise Operations
  // =========================================================================

  const startCruise = useCallback(async (startLocation, targetLocation, speedKmh = 5) => {
    setError(null);
    const response = await sendRequest('startCruise', {
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
  }, []);

  const stopCruise = useCallback(async () => {
    setError(null);
    const response = await sendRequest('stopCruise', {});
    if (response.result?.success) {
      setCruiseStatus(null);
      logger.info('Cruise stopped');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, []);

  const pauseCruise = useCallback(async () => {
    setError(null);
    const response = await sendRequest('pauseCruise', {});
    if (response.result?.success) {
      setCruiseStatus(response.result.session);
      logger.info('Cruise paused');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, []);

  const resumeCruise = useCallback(async () => {
    setError(null);
    const response = await sendRequest('resumeCruise', {});
    if (response.result?.success) {
      setCruiseStatus(response.result.session);
      logger.info('Cruise resumed');
    } else if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, []);

  const setCruiseSpeed = useCallback(async (speedKmh) => {
    const response = await sendRequest('setCruiseSpeed', { speedKmh });
    if (response.error) {
      setError(response.error.message);
    }
    return response;
  }, []);

  const getCruiseStatus = useCallback(async () => {
    const response = await sendRequest('getCruiseStatus', {});
    if (response.result) {
      setCruiseStatus(response.result.state !== 'idle' ? response.result : null);
    }
    return response;
  }, []);

  // =========================================================================
  // Return API
  // =========================================================================

  return {
    // State
    devices,
    selectedDevice,
    location,
    tunnelStatus,
    cruiseStatus,
    error,
    isLoading,
    isConnected,
    isBrowserMode: isBrowserMode(),

    // Device actions
    listDevices,
    selectDevice,

    // Location actions
    setLocation: setLocationOnDevice,
    clearLocation,

    // Tunnel actions
    startTunnel,
    stopTunnel,
    getTunnelStatus,

    // Cruise actions
    startCruise,
    stopCruise,
    pauseCruise,
    resumeCruise,
    setCruiseSpeed,
    getCruiseStatus,

    // Utilities
    clearError: () => setError(null),
    checkConnection,
  };
}
