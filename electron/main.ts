import { app, BrowserWindow, dialog, ipcMain, shell, protocol, net } from 'electron'
import { fileURLToPath, pathToFileURL } from 'node:url'
import path from 'node:path'
import { registerPythonIPC } from './ipc/python.ipc'
import { registerFFmpegIPC } from './ipc/ffmpeg.ipc'
import { registerMergeIPC } from './ipc/merge.ipc'
import { registerReupIPC } from './ipc/reup.ipc'
import fs from 'node:fs'

// Register custom protocol scheme (must be before app.ready)
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'local-media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      stream: true,        // critical for video streaming/seeking
      bypassCSP: true,
    },
  },
])

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL
  ? path.join(process.env.APP_ROOT, 'public')
  : RENDERER_DIST

let win: BrowserWindow | null

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    title: 'AuraSplit v2',
    frame: false,
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#18181f',
      symbolColor: '#8b8ba0',
      height: 36
    },
    backgroundColor: '#14141a',
    icon: path.join(process.env.VITE_PUBLIC, 'electron-vite.svg'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      webSecurity: false,
    },
  })

  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  // Prevent Electron from opening dropped files as navigation
  // This allows the Vue drop zone to handle drag-and-drop properly
  win.webContents.on('will-navigate', (event) => {
    event.preventDefault()
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

function registerDialogIPC() {
  ipcMain.handle('dialog:selectFiles', async (_event, options: any) => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'multiSelections'],
      filters: options?.filters || [],
      title: options?.title || 'Select Files',
    })
    return result.canceled ? [] : result.filePaths
  })

  ipcMain.handle('dialog:selectFolder', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      title: 'Select Folder',
    })
    return result.canceled ? null : result.filePaths[0]
  })

  // Save file with content — shows "Save As" dialog then writes
  ipcMain.handle('dialog:saveFile', async (_event, options: { title?: string; defaultPath?: string; filters?: any[]; content: string }) => {
    const result = await dialog.showSaveDialog({
      title: options.title || 'Save File',
      defaultPath: options.defaultPath || '',
      filters: options.filters || [{ name: 'All Files', extensions: ['*'] }],
    })
    if (result.canceled || !result.filePath) return null
    fs.writeFileSync(result.filePath, options.content, 'utf-8')
    return result.filePath
  })

  // Select save path only — shows "Save As" dialog, returns path WITHOUT writing
  ipcMain.handle('dialog:selectSavePath', async (_event, options: { title?: string; defaultPath?: string; filters?: any[] }) => {
    const result = await dialog.showSaveDialog({
      title: options.title || 'Save As',
      defaultPath: options.defaultPath || '',
      filters: options.filters || [{ name: 'All Files', extensions: ['*'] }],
    })
    if (result.canceled || !result.filePath) return null
    return result.filePath
  })
}

function registerFsIPC() {
  // Read text file content (for script preview)
  ipcMain.handle('fs:readFile', async (_event, filePath: string) => {
    try {
      return fs.readFileSync(filePath, 'utf-8')
    } catch { return '' }
  })

  // Scan folder → list files AND subdirectories (for drop zone auto-detect)
  ipcMain.handle('fs:scanFolder', async (_event, dirPath: string) => {
    try {
      if (!fs.statSync(dirPath).isDirectory()) return { files: [], dirs: [] }
      const entries = fs.readdirSync(dirPath)
      const files: string[] = []
      const dirs: string[] = []
      for (const entry of entries) {
        const fullPath = path.join(dirPath, entry)
        const stat = fs.statSync(fullPath)
        if (stat.isFile()) files.push(fullPath)
        else if (stat.isDirectory()) dirs.push(fullPath)
      }
      return { files, dirs }
    } catch { return { files: [], dirs: [] } }
  })
}

app.whenReady().then(() => {
  // Register local-media:// protocol to serve local files to renderer
  protocol.handle('local-media', (request) => {
    // URL format: local-media://media/C:/path/to/file.mp4
    const url = new URL(request.url)
    let filePath = decodeURIComponent(url.pathname)
    // Remove leading slash on Windows (e.g., /C:/foo → C:/foo)
    if (process.platform === 'win32' && filePath.startsWith('/')) {
      filePath = filePath.slice(1)
    }
    const fileUrl = pathToFileURL(filePath).toString()
    // Forward original request (including Range headers) for video streaming
    return net.fetch(fileUrl, {
      method: request.method,
      headers: request.headers,
    })
  })

  registerPythonIPC()
  registerFFmpegIPC()
  registerMergeIPC()
  registerReupIPC()
  registerDialogIPC()
  registerFsIPC()

  // Media: convert file path to streamable URL
  ipcMain.handle('media:getUrl', async (_event, filePath: string) => {
    const encoded = encodeURIComponent(filePath).replace(/%2F/g, '/').replace(/%3A/g, ':')
    return `local-media://media/${encoded}`
  })

  // Media: read file as binary buffer (for blob URL in renderer)
  ipcMain.handle('media:readFile', async (_event, filePath: string) => {
    return fs.readFileSync(filePath)
  })

  // Shell: open folder in Explorer
  ipcMain.handle('shell:openPath', async (_event, folderPath: string) => {
    return shell.openPath(folderPath)
  })

  // Shell: reveal file in Explorer
  ipcMain.handle('shell:showItemInFolder', async (_event, filePath: string) => {
    shell.showItemInFolder(filePath)
  })

  createWindow()
})
