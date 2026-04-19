/**
 * JARVIS — Electron Desktop Wrapper
 *
 * Wraps the Vite React app in a native desktop window.
 * Frameless, always-on-top option, transparent background.
 */

const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const path = require('path');

// In dev, load from Vite dev server; in prod, load built files
const isDev = process.env.NODE_ENV !== 'production';
const VITE_URL = 'http://localhost:5173';

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 600,
    minHeight: 500,
    frame: false,               // frameless for HUD feel
    transparent: false,
    backgroundColor: '#0a0a0f',
    titleBarStyle: 'hiddenInset', // macOS: hidden title bar with traffic lights
    vibrancy: 'ultra-dark',      // macOS translucency
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: path.join(__dirname, '..', 'public', 'icon.png'),
  });

  if (isDev) {
    mainWindow.loadURL(VITE_URL);
    // Uncomment to open DevTools on start:
    // mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  // ── Window controls via CSS -webkit-app-region ──
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  // Global shortcut to toggle window
  globalShortcut.register('CommandOrControl+Shift+J', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
        mainWindow.focus();
      }
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});
