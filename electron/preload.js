const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('backend', {
  // Send request to Python backend
  send: (method, params = {}) => {
    return ipcRenderer.invoke('backend-request', { method, params });
  },

  // Listen for events from Python backend
  onEvent: (callback) => {
    const handler = (event, data) => callback(data);
    ipcRenderer.on('backend-event', handler);
    // Return cleanup function
    return () => ipcRenderer.removeListener('backend-event', handler);
  },

  // Remove all event listeners
  removeAllListeners: () => {
    ipcRenderer.removeAllListeners('backend-event');
  },
});
