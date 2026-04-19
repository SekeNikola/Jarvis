/**
 * JARVIS — Electron Preload Script
 * Exposes safe APIs to the renderer process.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('jarvis', {
  platform: process.platform,
  // Add more IPC bridges here as needed
});
