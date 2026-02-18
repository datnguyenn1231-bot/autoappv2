/**
 * Preload script — expose IPC bridge to renderer.
 * Renderer CANNOT directly access Node.js APIs (security).
 */

import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  // ── Python IPC ──
  runPython: (taskId: string, taskType: string, config: object) =>
    ipcRenderer.invoke('python:run', { taskId, taskType, config }),

  stopPython: (taskId: string) =>
    ipcRenderer.invoke('python:stop', { taskId }),

  pythonStatus: () =>
    ipcRenderer.invoke('python:status'),

  onPythonMessage: (taskId: string, callback: (msg: any) => void) => {
    const channel = `python:${taskId}`
    const handler = (_event: any, msg: any) => callback(msg)
    ipcRenderer.on(channel, handler)
    // Return cleanup function
    return () => ipcRenderer.removeListener(channel, handler)
  },

  // ── FFmpeg IPC ──
  probeFile: (filePath: string) =>
    ipcRenderer.invoke('ffmpeg:probe', { filePath }),

  runFFmpeg: (taskId: string, args: string[]) =>
    ipcRenderer.invoke('ffmpeg:run', { taskId, args }),

  stopFFmpeg: (taskId: string) =>
    ipcRenderer.invoke('ffmpeg:stop', { taskId }),

  ffmpegPaths: () =>
    ipcRenderer.invoke('ffmpeg:paths'),

  remuxForSeeking: (filePath: string): Promise<string> =>
    ipcRenderer.invoke('ffmpeg:remux', { filePath }),

  onFFmpegMessage: (taskId: string, callback: (msg: any) => void) => {
    const channel = `ffmpeg:${taskId}`
    const handler = (_event: any, msg: any) => callback(msg)
    ipcRenderer.on(channel, handler)
    return () => ipcRenderer.removeListener(channel, handler)
  },

  // ── Dialog ──
  selectFiles: (options: object) =>
    ipcRenderer.invoke('dialog:selectFiles', options),

  selectFolder: () =>
    ipcRenderer.invoke('dialog:selectFolder'),

  saveFile: (options: { title?: string; defaultPath?: string; filters?: any[]; content: string }) =>
    ipcRenderer.invoke('dialog:saveFile', options),

  selectSavePath: (options: { title?: string; defaultPath?: string; filters?: any[] }) =>
    ipcRenderer.invoke('dialog:selectSavePath', options),

  // ── Media ──
  getMediaUrl: (filePath: string) =>
    ipcRenderer.invoke('media:getUrl', filePath),
  readMediaFile: (filePath: string): Promise<ArrayBuffer> =>
    ipcRenderer.invoke('media:readFile', filePath),

  // ── File System ──
  readFile: (filePath: string) =>
    ipcRenderer.invoke('fs:readFile', filePath),

  scanFolder: (dirPath: string) =>
    ipcRenderer.invoke('fs:scanFolder', dirPath),

  // ── Shell ──
  openFolder: (folderPath: string) =>
    ipcRenderer.invoke('shell:openPath', folderPath),

  showItemInFolder: (filePath: string) =>
    ipcRenderer.invoke('shell:showItemInFolder', filePath),

  // ── Merge (SK2) ──
  mergeScan: (folderPath: string) =>
    ipcRenderer.invoke('merge:scan', { folderPath }),

  mergeRun: (config: object) =>
    ipcRenderer.invoke('merge:run', { config }),

  mergeStop: () =>
    ipcRenderer.invoke('merge:stop'),

  onMergeLog: (callback: (msg: string) => void) => {
    const handler = (_event: any, msg: string) => callback(msg)
    ipcRenderer.on('merge:log', handler)
    return () => ipcRenderer.removeListener('merge:log', handler)
  },

  // ── Reup ──
  reupScan: (folderPath: string) =>
    ipcRenderer.invoke('reup:scan', { folderPath }),

  reupRun: (config: object) =>
    ipcRenderer.invoke('reup:run', { config }),

  reupStop: () =>
    ipcRenderer.invoke('reup:stop'),

  reupExport: (config: object, outputPath?: string) =>
    ipcRenderer.invoke('reup:export', { config, outputPath }),

  onReupLog: (callback: (msg: string) => void) => {
    const handler = (_event: any, msg: string) => callback(msg)
    ipcRenderer.on('reup:log', handler)
    return () => ipcRenderer.removeListener('reup:log', handler)
  },
})
