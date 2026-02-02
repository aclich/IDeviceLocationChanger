const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const PythonBridge = require('./python-bridge');

let mainWindow;
let pythonBridge;

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
    console.log('[Permission] Requested:', permission);
    if (permission === 'geolocation') {
      callback(true);
      return;
    }
    callback(false);
  });

  // Start Python backend
  pythonBridge = new PythonBridge();

  try {
    await pythonBridge.start();
    console.log('Python backend started');
  } catch (err) {
    console.error('Failed to start Python backend:', err);
  }

  // Forward events from Python to renderer
  pythonBridge.on('event', (event) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend-event', event);
    }
  });

  pythonBridge.on('exit', (code) => {
    console.log('Python backend exited, code:', code);
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

// Handle IPC from renderer
ipcMain.handle('backend-request', async (event, request) => {
  if (!pythonBridge) {
    return { error: { code: -1, message: 'Backend not initialized' } };
  }
  try {
    return await pythonBridge.send(request);
  } catch (err) {
    return { error: { code: -1, message: err.message } };
  }
});
