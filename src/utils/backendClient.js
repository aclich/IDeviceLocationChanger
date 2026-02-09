/**
 * Unified Backend Client
 *
 * Provides HTTP + SSE communication with the Python backend.
 * Works identically in both Electron and Browser modes.
 *
 * Features:
 * - JSON-RPC requests via HTTP POST
 * - Real-time events via Server-Sent Events (SSE)
 * - Automatic reconnection with exponential backoff
 * - Request logging for debugging
 */

const DEFAULT_URL = 'http://127.0.0.1:8765';

// Simple logger utility
const logger = {
  prefix: '[BackendClient]',

  info: (...args) => {
    console.log(`%c${logger.prefix} INFO`, 'color: #4ade80', ...args);
  },

  request: (method, params) => {
    console.log(
      `%c${logger.prefix} >>> REQUEST`,
      'color: #60a5fa; font-weight: bold',
      `\n  Method: ${method}`,
      `\n  Params:`,
      params
    );
  },

  response: (method, response, duration) => {
    if (response.error) {
      console.log(
        `%c${logger.prefix} <<< RESPONSE (${duration}ms)`,
        'color: #f87171; font-weight: bold',
        `\n  Method: ${method}`,
        `\n  Error:`,
        response.error
      );
    } else {
      console.log(
        `%c${logger.prefix} <<< RESPONSE (${duration}ms)`,
        'color: #4ade80; font-weight: bold',
        `\n  Method: ${method}`,
        `\n  Result:`,
        response.result
      );
    }
  },

  event: (eventName, data) => {
    console.log(
      `%c${logger.prefix} <<< EVENT`,
      'color: #c084fc; font-weight: bold',
      `\n  Event: ${eventName}`,
      `\n  Data:`,
      data
    );
  },

  error: (...args) => {
    console.error(`%c${logger.prefix} ERROR`, 'color: #f87171', ...args);
  },

  warn: (...args) => {
    console.warn(`%c${logger.prefix} WARN`, 'color: #fbbf24', ...args);
  },

  debug: (...args) => {
    console.debug(`%c${logger.prefix} DEBUG`, 'color: #94a3b8', ...args);
  },
};

/**
 * Backend Client class
 *
 * Handles all communication with the Python backend server.
 */
class BackendClient {
  constructor(baseUrl = DEFAULT_URL) {
    this.baseUrl = baseUrl;
    this.requestId = 0;
    this.eventSource = null;
    this.eventListeners = new Set();

    // Reconnection settings
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.baseReconnectDelay = 1000; // 1 second
    this.maxReconnectDelay = 30000; // 30 seconds

    // Connection state
    this.isConnected = false;
    this.isConnecting = false;

    logger.info(`Initialized with base URL: ${this.baseUrl}`);
  }

  /**
   * Send a JSON-RPC request to the backend
   *
   * @param {string} method - The RPC method name
   * @param {object} params - The method parameters
   * @returns {Promise<object>} - The response object
   */
  async send(method, params = {}) {
    const id = `req_${++this.requestId}`;
    const startTime = performance.now();

    logger.request(method, params);

    try {
      const response = await fetch(`${this.baseUrl}/rpc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method, params, id }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status} ${response.statusText}`);
      }

      const result = await response.json();
      const duration = Math.round(performance.now() - startTime);

      logger.response(method, result, duration);

      return result;
    } catch (error) {
      const duration = Math.round(performance.now() - startTime);
      logger.error(`Request failed after ${duration}ms:`, error.message);

      return {
        id,
        error: { code: -1, message: error.message },
      };
    }
  }

  /**
   * Subscribe to backend events via SSE
   *
   * @param {function} callback - Function to call when events are received
   * @returns {function} - Unsubscribe function
   */
  onEvent(callback) {
    this.eventListeners.add(callback);

    // Start SSE connection if not already connected
    if (!this.eventSource && !this.isConnecting) {
      this._connectSSE();
    }

    // Return unsubscribe function
    return () => {
      this.eventListeners.delete(callback);

      // Close SSE if no more listeners
      if (this.eventListeners.size === 0) {
        this._disconnectSSE();
      }
    };
  }

  /**
   * Connect to SSE endpoint
   * @private
   */
  _connectSSE() {
    if (this.eventSource || this.isConnecting) {
      return;
    }

    this.isConnecting = true;
    logger.info('Connecting to SSE...');

    try {
      this.eventSource = new EventSource(`${this.baseUrl}/events`);

      this.eventSource.onopen = () => {
        logger.info('SSE connected');
        this.isConnected = true;
        this.isConnecting = false;
        this.reconnectAttempts = 0;
      };

      // All events come through onmessage (no named SSE events).
      // Event type is in the JSON payload (data.event), parsed by _handleSSEMessage.
      this.eventSource.onmessage = (event) => {
        this._handleSSEMessage(event);
      };

      this.eventSource.onerror = (error) => {
        logger.warn('SSE error:', error);
        this.isConnected = false;
        this.isConnecting = false;

        if (this.eventSource?.readyState === EventSource.CLOSED) {
          this.eventSource = null;
          this._scheduleReconnect();
        }
      };
    } catch (error) {
      logger.error('Failed to create EventSource:', error);
      this.isConnecting = false;
      this._scheduleReconnect();
    }
  }

  /**
   * Handle incoming SSE message
   * @private
   */
  _handleSSEMessage(event) {
    try {
      const data = JSON.parse(event.data);
      const eventName = data.event || event.type || 'message';

      logger.event(eventName, data);

      // Notify all listeners
      for (const listener of this.eventListeners) {
        try {
          listener(data);
        } catch (listenerError) {
          logger.error('Event listener error:', listenerError);
        }
      }
    } catch (parseError) {
      logger.error('Failed to parse SSE event:', parseError, event.data);
    }
  }

  /**
   * Schedule SSE reconnection with exponential backoff
   * @private
   */
  _scheduleReconnect() {
    if (this.eventListeners.size === 0) {
      logger.debug('No listeners, skipping reconnect');
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logger.error(`Max reconnect attempts (${this.maxReconnectAttempts}) reached`);
      return;
    }

    this.reconnectAttempts++;

    // Exponential backoff with jitter
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1) +
        Math.random() * 1000,
      this.maxReconnectDelay
    );

    logger.info(
      `Reconnecting in ${Math.round(delay)}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})...`
    );

    setTimeout(() => {
      if (this.eventListeners.size > 0 && !this.eventSource) {
        this._connectSSE();
      }
    }, delay);
  }

  /**
   * Disconnect SSE
   * @private
   */
  _disconnectSSE() {
    if (this.eventSource) {
      logger.info('Disconnecting SSE');
      this.eventSource.close();
      this.eventSource = null;
      this.isConnected = false;
      this.isConnecting = false;
    }
  }

  /**
   * Check if backend is available
   *
   * @returns {Promise<boolean>} - True if backend is healthy
   */
  async checkHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        // Short timeout for health checks
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Get current connection status
   *
   * @returns {boolean} - True if SSE is connected
   */
  get connected() {
    return this.isConnected;
  }

  /**
   * Disconnect and cleanup
   */
  disconnect() {
    this._disconnectSSE();
    this.eventListeners.clear();
    this.reconnectAttempts = 0;
    logger.info('Disconnected');
  }

  /**
   * Update the base URL and reconnect
   *
   * @param {string} url - The new base URL
   */
  setBaseUrl(url) {
    this._disconnectSSE();
    this.baseUrl = url;
    this.reconnectAttempts = 0;
    logger.info(`Base URL updated to: ${url}`);
    // Reconnect SSE if we had listeners
    if (this.eventListeners.size > 0) {
      this._connectSSE();
    }
  }

  /**
   * Get current base URL
   *
   * @returns {string} - The current base URL
   */
  getBaseUrl() {
    return this.baseUrl;
  }
}

// ============================================================================
// Singleton and Initialization
// ============================================================================

let clientInstance = null;
let initPromise = null;

/**
 * Get the backend URL from various sources
 * Handles async getBackendUrl from Electron preload
 *
 * Priority: localStorage > Electron config > env variable > auto-detect > default
 *
 * @returns {Promise<string>} - The backend URL
 */
async function resolveBackendUrl() {
  // Check localStorage first (user-configured in debug page)
  if (typeof window !== 'undefined' && window.localStorage) {
    const storedUrl = window.localStorage.getItem('backendUrl');
    if (storedUrl) {
      logger.debug('Got backend URL from localStorage:', storedUrl);
      return storedUrl;
    }
  }

  // Check Electron config (async in new version)
  if (typeof window !== 'undefined' && window.electronConfig?.getBackendUrl) {
    try {
      const url = await window.electronConfig.getBackendUrl();
      if (url) {
        logger.debug('Got backend URL from Electron:', url);
        return url;
      }
    } catch (err) {
      logger.warn('Failed to get backend URL from Electron:', err);
    }
  }

  // Check Vite env variable
  if (typeof import.meta !== 'undefined' && import.meta.env?.VITE_BACKEND_URL) {
    return import.meta.env.VITE_BACKEND_URL;
  }

  // Auto-detect: If accessed from non-localhost, use same host for backend
  // This enables port forwarding scenarios where both frontend and backend
  // are forwarded to the same network interface
  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname;
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      const autoUrl = `http://${hostname}:8765`;
      logger.info(`Auto-detected non-localhost access, using backend: ${autoUrl}`);
      return autoUrl;
    }
  }

  // Default
  return DEFAULT_URL;
}

/**
 * Get the singleton BackendClient instance (sync version)
 * Note: Must call initBackend() first to ensure client is initialized
 *
 * @returns {BackendClient|null} - The client instance or null if not initialized
 */
export function getBackendClient() {
  return clientInstance;
}

/**
 * Initialize window.backend for compatibility with existing code
 *
 * This sets up window.backend to match the interface expected by useBackend.js
 * Returns a promise that resolves when initialization is complete.
 *
 * @returns {Promise<boolean>} - True if initialization succeeded
 */
export async function initBackend() {
  if (typeof window === 'undefined') {
    return false;
  }

  // Don't reinitialize if already set up
  if (window.backend && window.backend._isBackendClient) {
    logger.debug('Backend already initialized');
    return true;
  }

  // Reuse existing initialization promise if in progress
  if (initPromise) {
    return initPromise;
  }

  initPromise = (async () => {
    try {
      const url = await resolveBackendUrl();
      clientInstance = new BackendClient(url);

      window.backend = {
        // Mark as our client for detection
        _isBackendClient: true,

        // Send JSON-RPC request
        send: (method, params) => clientInstance.send(method, params),

        // Subscribe to events
        onEvent: (callback) => clientInstance.onEvent(callback),

        // Health check
        checkHealth: () => clientInstance.checkHealth(),

        // Get connection status
        get isConnected() {
          return clientInstance.connected;
        },

        // Get current base URL
        getBaseUrl: () => clientInstance.getBaseUrl(),

        // Update base URL and reconnect
        setBaseUrl: (url) => {
          clientInstance.setBaseUrl(url);
          // Persist to localStorage
          window.localStorage.setItem('backendUrl', url);
        },

        // Clear custom URL (revert to default)
        clearCustomUrl: () => {
          window.localStorage.removeItem('backendUrl');
        },
      };

      logger.info('Initialized window.backend');
      return true;
    } catch (error) {
      logger.error('Failed to initialize backend:', error);
      initPromise = null;
      return false;
    }
  })();

  return initPromise;
}

/**
 * Check if running in browser mode (not Electron with IPC)
 *
 * Now always returns true since we unified on HTTP/SSE
 */
export function isBrowserMode() {
  // With the unified approach, we're always using HTTP/SSE
  // This function is kept for backwards compatibility
  return true;
}

export default BackendClient;
