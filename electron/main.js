/**
 * Electron Main Process
 *
 * Simplified version that:
 * 1. Starts the Python HTTP backend
 * 2. Creates the browser window
 * 3. Passes backend URL to renderer via preload
 *
 * No IPC handlers needed - frontend communicates directly via HTTP/SSE.
 */

const { app, BrowserWindow, session, ipcMain } = require('electron');
const path = require('path');
const PythonBridge = require('./python-bridge');

let mainWindow;
let pythonBridge;
let backendUrl = 'http://127.0.0.1:8765'; // Default, updated when Python starts

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 15, y: 15 },
  });

  // Load Vite dev server in development, built files in production
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  // Grant geolocation permission automatically
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    console.log('[Electron] Permission requested:', permission);
    if (permission === 'geolocation') {
      callback(true);
      return;
    }
    callback(false);
  });

  // Start Python backend (HTTP server)
  pythonBridge = new PythonBridge();

  try {
    await pythonBridge.start();
    backendUrl = pythonBridge.getUrl();
    console.log('[Electron] Python backend started at', backendUrl);
  } catch (err) {
    console.error('[Electron] Failed to start Python backend:', err);
    // Continue anyway - user will see connection error in UI
  }

  pythonBridge.on('exit', (code) => {
    console.log('[Electron] Python backend exited with code:', code);
    // Could show error dialog here if needed
  });

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (pythonBridge) {
    pythonBridge.stop();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pythonBridge) {
    pythonBridge.stop();
  }
});

// No IPC handlers needed - frontend communicates directly with backend via HTTP/SSE
// Except for getting the backend URL
ipcMain.handle('get-backend-url', () => backendUrl);
