/**
 * useReup — Composable for Reup state & IPC calls.
 */

import { ref, onUnmounted } from 'vue'
import type { ReupConfig } from '../constants/reup-constants'

export function useReup() {
    const isRunning = ref(false)
    const logs = ref<string[]>([])
    const scanResult = ref<{ videos: string[] } | null>(null)

    let cleanupLog: (() => void) | null = null

    function setupLogListener() {
        cleanupLog = window.electronAPI.onReupLog((msg: string) => {
            logs.value.push(msg)
        })
    }

    async function scanFolder(folderPath: string) {
        try {
            scanResult.value = await window.electronAPI.reupScan(folderPath)
            return scanResult.value
        } catch (e: any) {
            logs.value.push(`❌ Scan error: ${e.message}`)
            return null
        }
    }

    async function startReup(config: ReupConfig) {
        logs.value = []
        isRunning.value = true
        setupLogListener()

        try {
            const result = await window.electronAPI.reupRun(config)
            if (!result.success) {
                logs.value.push('❌ Reup failed')
            }
        } catch (e: any) {
            logs.value.push(`❌ Error: ${e.message}`)
        } finally {
            isRunning.value = false
            if (cleanupLog) { cleanupLog(); cleanupLog = null }
        }
    }

    async function stopReup() {
        try {
            await window.electronAPI.reupStop()
            logs.value.push('⏹ Stopping...')
        } catch (e: any) {
            logs.value.push(`❌ Stop error: ${e.message}`)
        }
    }

    onUnmounted(() => {
        if (cleanupLog) { cleanupLog(); cleanupLog = null }
    })

    return {
        isRunning,
        logs,
        scanResult,
        scanFolder,
        startReup,
        stopReup,
    }
}
