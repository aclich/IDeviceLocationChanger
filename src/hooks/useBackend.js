import { useState, useEffect, useCallback, useRef } from 'react';
import { isBrowserMode } from '../utils/browserBackend';

// Simple logger utility
const logger = {
  prefix: '[Frontend]',

  info: (...args) => {
    console.log(`%c${logger.prefix} INFO`, 'color: #4ade80', ...args);
  },

  request: (method, params) => {
    console.log(
      `%c${logger.prefix} >>> REQUEST`,
      'color: #60a5fa; font-weight: bold',
      `\n  Method: ${method}`,
      `\n  Params:`, params
    );
  },

  response: (method, response, duration) => {
    if (response.error) {
      console.log(
        `%c${logger.prefix} <<< RESPONSE (${duration}ms)`,
        'color: #f87171; font-weight: bold',
        `\n  Method: ${method}`,
        `\n  Error:`, response.error
      );
    } else {
      console.log(
        `%c${logger.prefix} <<< RESPONSE (${duration}ms)`,
        'color: #4ade80; font-weight: bold',
        `\n  Method: ${method}`,
        `\n  Result:`, response.result
      );
    }
  },

  event: (eventName, data) => {
    console.log(
      `%c${logger.prefix} <<< EVENT`,
      'color: #c084fc; font-weight: bold',
      `\n  Event: ${eventName}`,
      `\n  Data:`, data
    );
  },

  error: (...args) => {
    console.error(`%c${logger.prefix} ERROR`, 'color: #f87171', ...args);
  },

  warn: (...args) => {
    console.warn(`%c${logger.prefix} WARN`, 'color: #fbbf24', ...args);
  },
};

// Wrapper for backend.send with logging
async function sendWithLogging(method, params = {}) {
  const startTime = performance.now();

  logger.request(method, params);

  try {
    const response = await window.backend.send(method, params);
    const duration = Math.round(performance.now() - startTime);
    logger.response(method, response, duration);
    return response;
  } catch (error) {
    const duration = Math.round(performance.now() - startTime);
    logger.error(`Request failed after ${duration}ms:`, error);
    throw error;
  }
}

/**
 * Hook for backend communication.
 * Handles device management, location setting, and tunnel management.
 *
 * Note: Cruise mode and joystick calculations are handled in useMovement hook.
 */
export function useBackend() {
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [location, setLocation] = useState(null);
  const [tunnelStatus, setTunnelStatus] = useState({ running: false });
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(true); // Updated in useEffect after backend init

  const cleanupRef = useRef(null);
  const healthCheckRef = useRef(null);

  // Check backend connection (browser mode only)
  const checkConnection = useCallback(async () => {
    if (!window.backend) {
      setIsConnected(false);
      return false;
    }

    // If backend has checkHealth method (browser mode), use it
    if (window.backend.checkHealth) {
      const healthy = await window.backend.checkHealth();
      setIsConnected(healthy);
      if (!healthy) {
        setError('Backend not running. Start with: python python-backend/main.py --http');
      } else {
        setError(null);
      }
      return healthy;
    }

    // Electron mode - assume connected
    setIsConnected(true);
    return true;
  }, []);

  // Listen for backend events and set up initial connection
  useEffect(() => {
    if (!window.backend) {
      logger.error('Backend not available - window.backend is undefined');
      setError('Backend not available');
      setIsConnected(false);
      return;
    }

    // Browser mode: check health once on mount
    if (isBrowserMode()) {
      logger.info('Browser mode detected - checking backend health');
      checkConnection();
    }

    logger.info('Setting up backend event listener');

    cleanupRef.current = window.backend.onEvent((message) => {
      logger.event(message.event, message.data);

      switch (message.event) {
        case 'error':
          setError(message.data.message);
          logger.error('Backend error event:', message.data.message);
          break;
        default:
          logger.warn('Unknown event:', message.event);
      }
    });

    return () => {
      if (cleanupRef.current) {
        logger.info('Cleaning up backend event listener');
        cleanupRef.current();
      }
    };
  }, [checkConnection]);

  // Health check interval - only runs when disconnected in browser mode
  useEffect(() => {
    if (!isBrowserMode()) return;

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
      const response = await sendWithLogging('listDevices');
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
    const response = await sendWithLogging('selectDevice', { deviceId });
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
    const response = await sendWithLogging('setLocation', { latitude, longitude });
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
    const response = await sendWithLogging('clearLocation');
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
      const response = await sendWithLogging('startTunnel', params);
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
    const response = await sendWithLogging('stopTunnel', params);
    if (response.result?.success) {
      setTunnelStatus({ running: false, status: 'no_tunnel' });
      logger.info('Tunnel stopped');
    }
    return response;
  }, []);

  const getTunnelStatus = useCallback(async (udid = null) => {
    const params = udid ? { udid } : {};
    const response = await sendWithLogging('getTunnelStatus', params);
    if (response.result) {
      setTunnelStatus(response.result);
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

    // Utilities
    clearError: () => setError(null),
    checkConnection,
  };
}
