/**
 * Browser Backend Adapter
 *
 * Provides the same interface as window.backend (Electron IPC)
 * but uses HTTP fetch() to communicate with the Python backend.
 */

const BACKEND_URL = 'http://127.0.0.1:8765';

let requestId = 0;
const eventListeners = new Set();

/**
 * Send a JSON-RPC request to the backend via HTTP
 */
async function send(method, params = {}) {
  const id = `req_${++requestId}`;

  const response = await fetch(`${BACKEND_URL}/rpc`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ method, params, id }),
  });

  if (!response.ok) {
    throw new Error(`HTTP error: ${response.status}`);
  }

  return response.json();
}

/**
 * Register an event listener (for compatibility with Electron API)
 * Note: HTTP mode doesn't support real-time events, but we keep the interface
 */
function onEvent(callback) {
  eventListeners.add(callback);
  return () => eventListeners.delete(callback);
}

/**
 * Check if the backend server is available
 */
async function checkHealth() {
  try {
    const response = await fetch(`${BACKEND_URL}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Initialize browser backend - sets up window.backend if in browser mode
 */
export function initBrowserBackend() {
  // Only initialize if window.backend doesn't exist (not in Electron)
  if (typeof window !== 'undefined' && !window.backend) {
    window.backend = {
      send,
      onEvent,
      checkHealth,
      isBrowserMode: true,
    };
    console.log('[BrowserBackend] Initialized - using HTTP mode');
    return true;
  }
  return false;
}

/**
 * Check if running in browser mode (not Electron)
 */
export function isBrowserMode() {
  return typeof window !== 'undefined' &&
         (!window.backend || window.backend.isBrowserMode === true);
}

export default {
  send,
  onEvent,
  checkHealth,
  initBrowserBackend,
  isBrowserMode,
};
