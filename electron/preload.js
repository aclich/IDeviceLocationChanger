/**
 * Electron Preload Script
 *
 * Exposes minimal configuration to the renderer process.
 * Uses IPC to get the backend URL from the main process.
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose backend URL getter to renderer
contextBridge.exposeInMainWorld('electronConfig', {
  // Async function to get backend URL from main process
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
});
