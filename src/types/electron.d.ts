/**
 * Type declarations for the Electron API exposed via preload.
 */

interface ElectronAPI {
    // Python IPC
    runPython: (taskId: string, taskType: string, config: object) => Promise<{ started: boolean; taskId: string }>
    stopPython: (taskId: string) => Promise<{ stopped: boolean }>
    pythonStatus: () => Promise<{ pythonExe: string; apiWrapper: string; activeTasks: string[] }>
    onPythonMessage: (taskId: string, callback: (msg: PythonMessage) => void) => () => void

    // FFmpeg IPC
    probeFile: (filePath: string) => Promise<object>
    runFFmpeg: (taskId: string, args: string[]) => Promise<{ started: boolean; taskId: string }>
    stopFFmpeg: (taskId: string) => Promise<{ stopped: boolean }>
    ffmpegPaths: () => Promise<{ ffmpeg: string; ffprobe: string }>
    remuxForSeeking: (filePath: string) => Promise<string>
    onFFmpegMessage: (taskId: string, callback: (msg: any) => void) => () => void

    // Dialog
    selectFiles: (options?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string[]>
    selectFolder: () => Promise<string | null>

    // Media
    getMediaUrl: (filePath: string) => Promise<string>
    readMediaFile: (filePath: string) => Promise<ArrayBuffer>

    // File System
    readFile: (filePath: string) => Promise<string>
    scanFolder: (dirPath: string) => Promise<{ files: string[]; dirs: string[] }>
    saveFile: (options: { title?: string; defaultPath?: string; filters?: any[]; content: string }) => Promise<string | null>

    // Shell
    openFolder: (folderPath: string) => Promise<void>
    showItemInFolder: (filePath: string) => Promise<void>

    // Merge (SK2)
    mergeScan: (folderPath: string) => Promise<{ videos: string[]; audios: string[]; hasVideosDir: boolean }>
    mergeRun: (config: object) => Promise<{ success: boolean; error?: string }>
    mergeStop: () => Promise<{ stopped: boolean }>
    onMergeLog: (callback: (msg: string) => void) => () => void

    // Reup
    reupScan: (folderPath: string) => Promise<{ videos: string[] }>
    reupRun: (config: object) => Promise<{ success: boolean; error?: string }>
    reupStop: () => Promise<{ stopped: boolean }>
    onReupLog: (callback: (msg: string) => void) => () => void
}

interface PythonMessage {
    type: 'progress' | 'log' | 'result' | 'error' | 'stderr' | 'exit'
    percent?: number
    message?: string
    data?: any
    code?: number
}

declare global {
    interface Window {
        electronAPI: ElectronAPI
    }
}

export { }
