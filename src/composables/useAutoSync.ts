/**
 * useAutoSync — Composable for SyncVideo/SyncImage logic.
 * v1-compatible: CONFIG flow, drop zone auto-detect, script preview.
 */

import { ref, watch, nextTick, onUnmounted } from 'vue'

// ── Types ──
interface SK1State {
    audioFile: string; scriptFile: string; videoDir: string; outputDir: string; outputName: string
    model: string; language: string
    running: boolean; progress: number; status: 'idle' | 'running' | 'done' | 'error'
    logs: string[]
}
interface SK3State {
    audioFile: string; scriptFile: string; imageDir: string; outputDir: string; outputName: string
    model: string; language: string
    running: boolean; progress: number; status: 'idle' | 'running' | 'done' | 'error'
    logs: string[]
}

// ── Constants (v1 MODEL_MAP) ──
export const WHISPER_MODELS = [
    { value: 'tiny', label: '⚡ LITE' },
    { value: 'base', label: '🔵 STARTER' },
    { value: 'small', label: '🟢 STANDARD' },
    { value: 'medium', label: '🔶 PRO' },
    { value: 'large-v3', label: '💎 PREMIUM' },
    { value: 'large-v3-turbo', label: '🚀 TURBO' },
]

export const LANGUAGES = [
    { value: 'auto', label: 'Auto Detect' },
    { value: 'vi', label: '🇻🇳 Vietnamese' },
    { value: 'en', label: '🇺🇸 English' },
    { value: 'ja', label: '🇯🇵 Japanese' },
    { value: 'ko', label: '🇰🇷 Korean' },
    { value: 'zh', label: '🇨🇳 Chinese' },
    { value: 'th', label: '🇹🇭 Thai' },
    { value: 'fr', label: '🇫🇷 French' },
    { value: 'de', label: '🇩🇪 German' },
    { value: 'es', label: '🇪🇸 Spanish' },
]

const AUDIO_EXT = ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'wma']
const VIDEO_EXT = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv']

function ext(f: string) { return f.split('.').pop()?.toLowerCase() || '' }

// ── Composable ──
export function useAutoSync() {
    const activeTab = ref<'sk1' | 'sk3'>('sk1')
    const scriptContent = ref('')
    const dropHover = ref(false)

    const sk1 = ref<SK1State>({
        audioFile: '', scriptFile: '', videoDir: '', outputDir: '', outputName: '',
        model: 'base', language: 'auto',
        running: false, progress: 0, status: 'idle', logs: [],
    })
    const sk3 = ref<SK3State>({
        audioFile: '', scriptFile: '', imageDir: '', outputDir: '', outputName: '',
        model: 'base', language: 'auto',
        running: false, progress: 0, status: 'idle', logs: [],
    })

    let cleanupFn: (() => void) | null = null
    let activeTaskId: string | null = null

    function addLog(state: { value: { logs: string[] } }, msg: string) {
        if (msg?.trim()) {
            state.value.logs.push(msg)
            if (state.value.logs.length > 300) state.value.logs.shift()
            // Auto-scroll log panel to bottom
            nextTick(() => {
                const el = document.getElementById('systemLog')
                if (el) el.scrollTop = el.scrollHeight
            })
        }
    }

    // ── Load script content when scriptFile changes ──
    watch(() => sk1.value.scriptFile, async (path) => {
        if (path) scriptContent.value = await window.electronAPI.readFile?.(path) || ''
    })
    watch(() => sk3.value.scriptFile, async (path) => {
        if (path) scriptContent.value = await window.electronAPI.readFile?.(path) || ''
    })

    // ── Drop Zone: scan folder → auto-detect files + subfolders ──
    async function handleDrop(e: DragEvent) {
        e.preventDefault()
        e.stopPropagation()
        dropHover.value = false
        const items = e.dataTransfer?.files
        if (!items?.length) return

        let droppedPath = (items[0] as any).path as string
        if (!droppedPath) return

        console.log('[DROP] droppedPath:', droppedPath)

        // Scan the dropped path
        const result = await window.electronAPI.scanFolder?.(droppedPath) as any
        let files: string[] = result?.files || []
        let dirs: string[] = result?.dirs || []

        // Quick-check: does this scan have audio + script at root?
        const hasAudio = files.some((f: string) => AUDIO_EXT.includes(ext(f)))
        const hasScript = files.some((f: string) => ext(f) === 'txt')

        // If dropped item is a file OR a subfolder (missing audio/script), try parent dir
        if (!hasAudio || !hasScript) {
            const parentDir = droppedPath.replace(/[\\/][^\\/]+$/, '')
            console.log('[DROP] Incomplete detection, trying parent:', parentDir)
            const parentResult = await window.electronAPI.scanFolder?.(parentDir) as any
            if (parentResult?.files?.length || parentResult?.dirs?.length) {
                // Check if parent is better (has more complete data)
                const pHasAudio = parentResult.files.some((f: string) => AUDIO_EXT.includes(ext(f)))
                const pHasScript = parentResult.files.some((f: string) => ext(f) === 'txt')
                if (pHasAudio || pHasScript) {
                    files = parentResult.files || []
                    dirs = parentResult.dirs || []
                    droppedPath = parentDir
                    console.log('[DROP] Using parent dir:', parentDir)
                }
            }
        }

        const state = activeTab.value === 'sk1' ? sk1 : sk3

        // ── Detect files at root level ──
        let foundAudio = '', foundScript = ''
        for (const f of files) {
            const e = ext(f)
            if (!foundAudio && AUDIO_EXT.includes(e)) foundAudio = f
            if (!foundScript && e === 'txt') foundScript = f
        }
        console.log('[DROP] foundAudio:', foundAudio, 'foundScript:', foundScript)

        // ── Detect subfolders by name ──
        const getDirName = (p: string) => p.replace(/[\\/]$/, '').split(/[\\/]/).pop()?.toLowerCase() || ''
        let videoDir = '', imageDir = ''
        for (const d of dirs) {
            const name = getDirName(d)
            console.log('[DROP] subfolder:', name, d)
            if (!videoDir && (name === 'video' || name === 'videos')) videoDir = d
            if (!imageDir && (name === 'anh' || name === 'image' || name === 'images' || name === 'img')) imageDir = d
            // Also check script subfolder for .txt
            if (!foundScript && (name === 'script' || name === 'scripts')) {
                const sub = await window.electronAPI.scanFolder?.(d) as any
                if (sub?.files) {
                    const txt = sub.files.find((f: string) => ext(f) === 'txt')
                    if (txt) foundScript = txt
                }
            }
        }
        console.log('[DROP] videoDir:', videoDir, 'imageDir:', imageDir)

        // ── Assign to state ──
        if (foundAudio) state.value.audioFile = foundAudio
        if (foundScript) state.value.scriptFile = foundScript
        if (activeTab.value === 'sk1') {
            sk1.value.videoDir = videoDir || droppedPath
        }
        if (activeTab.value === 'sk3') {
            sk3.value.imageDir = imageDir || droppedPath
        }

        // Auto-set output parent directory
        if (!state.value.outputDir) {
            state.value.outputDir = droppedPath
            console.log('[DROP] Auto-set outputDir (parent):', droppedPath)
        }

        console.log('[DROP] DONE — audio:', state.value.audioFile, 'script:', state.value.scriptFile)
    }

    // ── File Pickers ──
    async function pickAudio(t: 'sk1' | 'sk3') {
        const files = await window.electronAPI.selectFiles({
            title: 'Select Audio / Video',
            filters: [{ name: 'Media', extensions: [...AUDIO_EXT, ...VIDEO_EXT] }],
        })
        if (files.length) (t === 'sk1' ? sk1 : sk3).value.audioFile = files[0]
    }
    async function pickScript(t: 'sk1' | 'sk3') {
        const files = await window.electronAPI.selectFiles({
            title: 'Select Script (.txt)',
            filters: [{ name: 'Script', extensions: ['txt'] }],
        })
        if (files.length) (t === 'sk1' ? sk1 : sk3).value.scriptFile = files[0]
    }
    async function pickVideoDir() {
        const f = await window.electronAPI.selectFolder()
        if (f) sk1.value.videoDir = f
    }
    async function pickImageDir() {
        const f = await window.electronAPI.selectFolder()
        if (f) sk3.value.imageDir = f
    }
    async function pickOutputDir(t: 'sk1' | 'sk3') {
        const f = await window.electronAPI.selectFolder()
        if (f) (t === 'sk1' ? sk1 : sk3).value.outputDir = f
    }

    // ── Start / Stop ──
    async function startTask(taskType: 'sk1' | 'sk3') {
        const state = taskType === 'sk1' ? sk1 : sk3
        const taskId = `${taskType}_${Date.now()}`
        activeTaskId = taskId
        state.value.running = true; state.value.progress = 0
        state.value.status = 'running'; state.value.logs = []

        const finalOutput = state.value.outputName?.trim()
            ? `${state.value.outputDir}\\${state.value.outputName.trim()}`
            : state.value.outputDir

        const config = taskType === 'sk1'
            ? {
                audio_full_path: sk1.value.audioFile, script_path: sk1.value.scriptFile,
                video_source_dir: sk1.value.videoDir, output_dir: finalOutput,
                model_name: sk1.value.model, lang_code: sk1.value.language,
            }
            : {
                audio_full_path: sk3.value.audioFile, script_path: sk3.value.scriptFile,
                image_source_dir: sk3.value.imageDir, output_dir: finalOutput,
                model_name: sk3.value.model, lang_code: sk3.value.language,
            }

        cleanupFn = window.electronAPI.onPythonMessage(taskId, (msg) => {
            console.log('[PYTHON]', taskId, msg)
            if (msg.type === 'progress') {
                state.value.progress = msg.percent || 0
                if (msg.message) addLog(state, msg.message)
            } else if (msg.type === 'log') {
                addLog(state, msg.message || '')
            } else if (msg.type === 'stderr') {
                addLog(state, `⚠️ ${msg.message}`)
            } else if (msg.type === 'result') {
                state.value.status = 'done'; state.value.progress = 100
                addLog(state, '✅ Completed!')
            } else if (msg.type === 'error') {
                state.value.status = 'error'
                addLog(state, `❌ ${msg.message}`)
            } else if (msg.type === 'exit') {
                state.value.running = false
                if (state.value.status === 'running') {
                    state.value.status = msg.code === 0 ? 'done' : 'error'
                    if (msg.code === 0) state.value.progress = 100
                }
            }
        })

        console.log('[RUN]', taskType, 'taskId:', taskId, 'config:', config)
        try {
            const result = await window.electronAPI.runPython(taskId, taskType, config)
            console.log('[RUN] result:', result)
            addLog(state, `🚀 Task started: ${taskId}`)
        } catch (err: any) {
            console.error('[RUN] error:', err)
            state.value.running = false
            state.value.status = 'error'
            addLog(state, `❌ Failed to start: ${err.message || err}`)
        }
    }

    async function stopTask(t: 'sk1' | 'sk3') {
        const state = t === 'sk1' ? sk1 : sk3
        state.value.running = false
        state.value.status = 'idle'
        addLog(state, '🛑 Stopping...')
        // Kill the Python process
        if (activeTaskId) {
            try {
                await window.electronAPI.stopPython(activeTaskId)
                addLog(state, '🛑 Process killed.')
            } catch (err: any) {
                console.error('[STOP] Failed:', err)
            }
            activeTaskId = null
        }
        cleanupFn?.()
        cleanupFn = null
    }

    function fileName(p: string) { return p.split(/[\\\/]/).pop() || p }
    function folderName(p: string) {
        return p.replace(/[\\\/]$/, '').split(/[\\\/]/).pop() || p
    }

    function clearFields() {
        const state = activeTab.value === 'sk1' ? sk1 : sk3
        state.value.audioFile = ''
        state.value.scriptFile = ''
        state.value.outputDir = ''
        state.value.outputName = ''
        state.value.logs = []
        state.value.progress = 0
        state.value.status = 'idle'
        scriptContent.value = ''
        if (activeTab.value === 'sk1') sk1.value.videoDir = ''
        else sk3.value.imageDir = ''
        console.log('[CLEAR] All fields reset for', activeTab.value)
    }

    onUnmounted(() => cleanupFn?.())

    async function openOutputFolder(t: 'sk1' | 'sk3') {
        const dir = (t === 'sk1' ? sk1 : sk3).value.outputDir
        if (dir) {
            try {
                await (window as any).electronAPI.openFolder(dir)
            } catch (err: any) {
                console.error('[OPEN FOLDER] Failed:', err)
            }
        }
    }

    return {
        activeTab, sk1, sk3, scriptContent, dropHover,
        pickAudio, pickScript, pickVideoDir, pickImageDir, pickOutputDir,
        startTask, stopTask, openOutputFolder, handleDrop, clearFields, fileName, folderName,
    }
}
