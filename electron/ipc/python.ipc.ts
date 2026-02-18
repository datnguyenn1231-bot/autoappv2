/**
 * Python IPC — Spawn Python subprocess and stream JSON output.
 * Used by SK1 (AI Cut) and SK3 (Image Flow).
 */

import { spawn, ChildProcess } from 'child_process'
import { ipcMain, BrowserWindow, app } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import os from 'node:os'

// ── Paths ──────────────────────────────────
function getAppRoot(): string {
    // In dev: project root (AuraSplit_v2/)
    // In prod: app.getAppPath() → resources/app.asar
    const appPath = app.getAppPath()
    return appPath.endsWith('dist') ? path.resolve(appPath, '..') : appPath
}

function getResourcesRoot(): string {
    // In packaged app: extraResources are in process.resourcesPath
    // In dev: same as project root
    if (app.isPackaged) {
        return process.resourcesPath
    }
    return getAppRoot()
}

function getPythonExe(): string {
    const resRoot = getResourcesRoot()
    const devRoot = getAppRoot()
    // Check multiple possible locations
    const candidates = [
        path.join(resRoot, 'python_embed', 'python.exe'),              // packaged: resources/python_embed/
        path.join(devRoot, 'python_embed', 'python.exe'),              // dev: AuraSplit_v2/python_embed/
        path.join(devRoot, '..', 'python_embed', 'python.exe'),        // dev fallback: AI_TOOL/python_embed/
    ]
    for (const p of candidates) {
        console.log('[PYTHON IPC] checking:', p, fs.existsSync(p))
        if (fs.existsSync(p)) return p
    }
    console.warn('[PYTHON IPC] python_embed not found, falling back to system python')
    return 'python' // fallback to system Python
}

function getApiWrapper(): string {
    const resRoot = getResourcesRoot()
    const devRoot = getAppRoot()
    // Packaged: resources/python/api_wrapper.py
    const packed = path.join(resRoot, 'python', 'api_wrapper.py')
    if (fs.existsSync(packed)) return packed
    // Dev: AuraSplit_v2/python/api_wrapper.py
    return path.join(devRoot, 'python', 'api_wrapper.py')
}

function getSubServer(): string {
    const resRoot = getResourcesRoot()
    const devRoot = getAppRoot()
    const packed = path.join(resRoot, 'python', 'sub_server.py')
    if (fs.existsSync(packed)) return packed
    return path.join(devRoot, 'python', 'sub_server.py')
}

// ── Active processes ───────────────────────
const activeProcesses = new Map<string, ChildProcess>()

// ── Persistent SUB Server ─────────────────
let subServerProc: ChildProcess | null = null
let subServerBuffer = ''
const subTaskListeners = new Map<string, BrowserWindow>()

function ensureSubServer(): ChildProcess {
    if (subServerProc && !subServerProc.killed) return subServerProc

    const pythonExe = getPythonExe()
    const serverScript = getSubServer()
    console.log('[SUB SERVER] Starting persistent server:', serverScript)

    subServerProc = spawn(pythonExe, ['-u', serverScript], {
        cwd: path.join(getResourcesRoot(), 'python'),
        env: {
            ...process.env,
            PYTHONIOENCODING: 'utf-8',
            PYTHONUNBUFFERED: '1',
            HF_HUB_DISABLE_SYMLINKS: '1',
            HF_HUB_DISABLE_SYMLINKS_WARNING: '1',
            HF_HUB_DISABLE_XET: '1',
            HF_HUB_ENABLE_HF_TRANSFER: '0',
        },
        stdio: ['pipe', 'pipe', 'pipe'],
    })

    console.log('[SUB SERVER] PID:', subServerProc.pid)
    subServerBuffer = ''

    // Stream stdout (JSON lines with task_id routing)
    subServerProc.stdout?.on('data', (chunk: Buffer) => {
        subServerBuffer += chunk.toString('utf-8')
        const lines = subServerBuffer.split('\n')
        subServerBuffer = lines.pop() || ''

        for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue
            try {
                const msg = JSON.parse(trimmed)
                const taskId = msg.task_id || 'server'
                delete msg.task_id  // don't send internal routing field to renderer
                // Enhanced logging for result messages (contains segments data)
                if (msg.type === 'result') {
                    console.log(`[SUB SERVER] ★ RESULT task=${taskId} segments=${msg.data?.segments?.length || 0} srt=${msg.data?.srt_path || ''}`)
                } else {
                    console.log(`[SUB SERVER] task=${taskId} type=${msg.type} msg=${(msg.message || '').substring(0, 80)}`)
                }
                const win = subTaskListeners.get(taskId)
                if (win && !win.isDestroyed()) {
                    win.webContents.send(`python:${taskId}`, msg)
                } else {
                    console.log(`[SUB SERVER] ⚠️ No window listener for task=${taskId}`)
                }
            } catch (e) {
                console.log(`[SUB SERVER] ❌ JSON parse error (len=${trimmed.length}): ${trimmed.substring(0, 200)}`)
            }
        }
    })

    // Stderr → log
    subServerProc.stderr?.on('data', (chunk: Buffer) => {
        const text = chunk.toString('utf-8').trim()
        if (text && !text.includes('UserWarning') && !text.includes('FutureWarning')) {
            console.log(`[SUB SERVER stderr] ${text.substring(0, 200)}`)
        }
    })

    subServerProc.on('close', (code) => {
        console.log(`[SUB SERVER] Process exited with code ${code}`)
        subServerProc = null
        // Notify all active SUB tasks about the exit
        for (const [taskId, win] of subTaskListeners) {
            if (!win.isDestroyed()) {
                win.webContents.send(`python:${taskId}`, { type: 'exit', code })
            }
        }
        subTaskListeners.clear()
    })

    return subServerProc
}

function sendSubTask(
    taskId: string,
    config: Record<string, unknown>,
    win: BrowserWindow
): void {
    const server = ensureSubServer()
    subTaskListeners.set(taskId, win)

    // Inject model_cache_dir
    if (!config.model_cache_dir) {
        if (app.isPackaged) {
            const exeDir = path.dirname(app.getPath('exe'))
            config.model_cache_dir = path.join(exeDir, 'models_ai')
        } else {
            config.model_cache_dir = path.join(getAppRoot(), 'models_ai')
        }
    }

    const task = { task_id: taskId, ...config }
    const line = JSON.stringify(task) + '\n'
    console.log(`[SUB SERVER] Sending task ${taskId} (${line.length} bytes)`)
    server.stdin?.write(line)
}

function shutdownSubServer(): void {
    if (subServerProc && !subServerProc.killed) {
        console.log('[SUB SERVER] Shutting down...')
        try {
            subServerProc.stdin?.write(JSON.stringify({ cmd: 'shutdown' }) + '\n')
        } catch { /* ignore */ }
        setTimeout(() => {
            if (subServerProc && !subServerProc.killed) {
                subServerProc.kill()
                subServerProc = null
            }
        }, 3000)
    }
}

// Shutdown on app quit
app.on('before-quit', shutdownSubServer)

// ── Core: Run Python task ──────────────────
function runPythonTask(
    taskId: string,
    taskType: string,
    config: Record<string, unknown>,
    win: BrowserWindow
): void {
    const pythonExe = getPythonExe()
    const wrapper = getApiWrapper()

    console.log('[PYTHON IPC] pythonExe:', pythonExe)
    console.log('[PYTHON IPC] wrapper:', wrapper)
    console.log('[PYTHON IPC] exists?', fs.existsSync(pythonExe), fs.existsSync(wrapper))

    // Inject paths that Python needs but vary between DEV and EXE
    if (!config.model_cache_dir) {
        if (app.isPackaged) {
            // In EXE: use models_ai next to the exe (writable, not inside resources)
            const exeDir = path.dirname(app.getPath('exe'))
            config.model_cache_dir = path.join(exeDir, 'models_ai')
        } else {
            // In DEV: use project-level models_ai
            config.model_cache_dir = path.join(getAppRoot(), 'models_ai')
        }
    }
    console.log('[PYTHON IPC] model_cache_dir:', config.model_cache_dir)

    // Write config to temp file
    const configPath = path.join(os.tmpdir(), `aurasplit_${taskId}.json`)
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8')
    console.log('[PYTHON IPC] config saved to:', configPath)

    const proc = spawn(pythonExe, [
        '-u',  // Force unbuffered stdout/stderr for realtime log streaming
        wrapper,
        '--task', taskType,
        '--config', configPath,
    ], {
        cwd: path.join(getResourcesRoot(), 'python'),
        env: {
            ...process.env,
            PYTHONIOENCODING: 'utf-8',
            PYTHONUNBUFFERED: '1',
            // Fix Windows symlink errors (WinError 1314)
            HF_HUB_DISABLE_SYMLINKS: '1',
            HF_HUB_DISABLE_SYMLINKS_WARNING: '1',
            HF_HUB_DISABLE_XET: '1',
            HF_HUB_ENABLE_HF_TRANSFER: '0',
        },
        stdio: ['ignore', 'pipe', 'pipe'],
    })

    console.log('[PYTHON IPC] spawned PID:', proc.pid)

    activeProcesses.set(taskId, proc)

    // Stream stdout (JSON lines)
    let buffer = ''
    let msgCount = 0
    let progressFilePoller: ReturnType<typeof setInterval> | null = null
    let progressFileOffset = 0

    // Auto-start polling for progress file by PID
    // Python writes to %TEMP%/aurasplit_progress_{PID}.jsonl
    // We can't rely on stdout signal because stdout breaks during FFmpeg loop
    const progressFilePath = path.join(os.tmpdir(), `aurasplit_progress_${proc.pid}.jsonl`)
    console.log(`[PYTHON IPC] Will poll progress file: ${progressFilePath}`)

    progressFilePoller = setInterval(() => {
        try {
            if (!fs.existsSync(progressFilePath)) return
            const content = fs.readFileSync(progressFilePath, 'utf-8')
            // Use character-based offset (not line-count!) to avoid off-by-one
            // from trailing empty string in split('\n')
            if (content.length <= progressFileOffset) return
            const newContent = content.substring(progressFileOffset)
            progressFileOffset = content.length

            const newLines = newContent.split('\n')
            for (const line of newLines) {
                const trimmed = line.trim()
                if (!trimmed) continue
                try {
                    const msg = JSON.parse(trimmed)
                    console.log(`[PROGRESS FILE] type=${msg.type} msg=${(msg.message || '').substring(0, 80)}`)
                    win.webContents.send(`python:${taskId}`, msg)
                } catch (e) {
                    console.log(`[PROGRESS FILE] JSON parse error: ${trimmed.substring(0, 100)}`)
                }
            }
        } catch { /* file not ready */ }
    }, 500)

    function stopProgressFilePolling() {
        if (progressFilePoller) {
            clearInterval(progressFilePoller)
            progressFilePoller = null
        }
        // Clean up temp file
        try { fs.unlinkSync(progressFilePath) } catch { /* ignore */ }
    }

    proc.stdout?.on('data', (chunk: Buffer) => {
        const raw = chunk.toString('utf-8')
        buffer += raw
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // keep incomplete line

        for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue
            msgCount++
            if (msgCount <= 5 || msgCount % 10 === 0) {
                console.log(`[PYTHON IPC] msg#${msgCount} len=${trimmed.length} type=${trimmed.substring(0, 80)}`)
            }
            try {
                const msg = JSON.parse(trimmed)
                // Skip internal progress file signal (no longer needed, but filter it out)
                if (msg.type === 'log' && typeof msg.message === 'string' && msg.message.startsWith('[PROGRESS_FILE]')) {
                    continue
                }
                win.webContents.send(`python:${taskId}`, msg)
            } catch {
                console.log(`[PYTHON IPC] non-JSON: ${trimmed.substring(0, 100)}`)
                win.webContents.send(`python:${taskId}`, {
                    type: 'log',
                    message: trimmed,
                })
            }
        }
    })

    // Stderr → parse JSON lines (same as stdout), fallback to log
    let stderrBuffer = ''
    proc.stderr?.on('data', (chunk: Buffer) => {
        stderrBuffer += chunk.toString('utf-8')
        const lines = stderrBuffer.split('\n')
        stderrBuffer = lines.pop() || ''

        for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed) continue
            try {
                // Try parsing as JSON first (per-clip progress from cutting loop)
                const msg = JSON.parse(trimmed)
                if (msg.type) {
                    win.webContents.send(`python:${taskId}`, msg)
                    continue
                }
            } catch { /* not JSON, treat as text */ }
            // Non-JSON stderr → forward as log (filter noise)
            if (!trimmed.includes('UserWarning') && !trimmed.includes('FutureWarning')) {
                win.webContents.send(`python:${taskId}`, {
                    type: 'log',
                    message: trimmed,
                })
            }
        }
    })

    // Process exit
    proc.on('close', (code) => {
        activeProcesses.delete(taskId)

        // ── Flush remaining stdout buffer (critical for last message like 'result') ──
        if (buffer.trim()) {
            try {
                const msg = JSON.parse(buffer.trim())
                console.log(`[PYTHON IPC] flush stdout buffer: type=${msg.type}`)
                win.webContents.send(`python:${taskId}`, msg)
            } catch {
                console.log(`[PYTHON IPC] flush stdout (non-JSON): ${buffer.trim().substring(0, 100)}`)
            }
            buffer = ''
        }

        // ── Flush remaining stderr buffer ──
        if (stderrBuffer.trim()) {
            try {
                const msg = JSON.parse(stderrBuffer.trim())
                if (msg.type) {
                    win.webContents.send(`python:${taskId}`, msg)
                }
            } catch { /* not JSON, ignore */ }
            stderrBuffer = ''
        }

        // Final poll to catch remaining progress messages
        if (progressFilePath && fs.existsSync(progressFilePath)) {
            try {
                const content = fs.readFileSync(progressFilePath, 'utf-8')
                const newContent = content.substring(progressFileOffset)
                const newLines = newContent.split('\n')
                for (const line of newLines) {
                    const trimmed = line.trim()
                    if (!trimmed) continue
                    try {
                        const msg = JSON.parse(trimmed)
                        win.webContents.send(`python:${taskId}`, msg)
                    } catch { /* skip */ }
                }
            } catch { /* ignore */ }
        }
        // Stop polling and clean up
        stopProgressFilePolling()
        // Clean up temp config
        try { fs.unlinkSync(configPath) } catch { /* ignore */ }

        win.webContents.send(`python:${taskId}`, {
            type: 'exit',
            code,
        })
    })
}

// ── IPC Handlers ───────────────────────────
export function registerPythonIPC(): void {
    ipcMain.handle('python:run', async (event, { taskId, taskType, config }) => {
        const win = BrowserWindow.fromWebContents(event.sender)
        if (!win) return { error: 'No window' }

        // SUB tasks → persistent server (keeps model cached)
        if (taskType === 'sub') {
            sendSubTask(taskId, config, win)
            return { started: true, taskId, persistent: true }
        }

        // Other tasks (SK1, SK3) → spawn per task
        runPythonTask(taskId, taskType, config, win)
        return { started: true, taskId }
    })

    ipcMain.handle('python:stop', async (_event, { taskId }) => {
        const proc = activeProcesses.get(taskId)
        if (proc && proc.pid) {
            console.log(`[STOP] Killing PID ${proc.pid} (task: ${taskId})`)
            // Windows: SIGTERM doesn't work. Use taskkill /F /T to kill entire process tree
            try {
                const { execSync } = require('child_process')
                execSync(`taskkill /F /T /PID ${proc.pid}`, { stdio: 'ignore' })
            } catch {
                // Fallback: try Node.js kill
                try { proc.kill() } catch { /* already dead */ }
            }
            activeProcesses.delete(taskId)
            return { stopped: true }
        }
        return { stopped: false }
    })

    ipcMain.handle('python:status', async () => {
        return {
            pythonExe: getPythonExe(),
            apiWrapper: getApiWrapper(),
            activeTasks: Array.from(activeProcesses.keys()),
        }
    })
}
