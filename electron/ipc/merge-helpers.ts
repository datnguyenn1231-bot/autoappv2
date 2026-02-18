/**
 * merge-helpers — Shared utilities for SK2 Merge engine.
 * Contains: FFmpeg runner, probe, GPU detection, file listing, and constants.
 */

import { spawn, ChildProcess } from 'child_process'
import { BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'

import { getFFmpegPath, getFFprobePath } from './ffmpeg.ipc.js'

// ── Constants ──────────────────────────────
export const VIDEO_EXTS = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v']
export const AUDIO_EXTS = ['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg']

// ── State ──────────────────────────────────
export let activeProc: ChildProcess | null = null
let stopped = false

export function isStopped(): boolean { return stopped }
export function setStopped(val: boolean) { stopped = val }
export function setActiveProc(proc: ChildProcess | null) { activeProc = proc }

// ── GPU (NVENC) Detection ──────────────────
let _nvencAvailable: boolean | null = null

export async function checkNvenc(): Promise<boolean> {
    if (_nvencAvailable !== null) return _nvencAvailable
    try {
        const ffPath = getFFmpegPath()
        return new Promise((resolve) => {
            const proc = spawn(ffPath, [
                '-f', 'lavfi', '-i', 'nullsrc=s=64x64:d=0.1',
                '-c:v', 'h264_nvenc', '-f', 'null', '-',
            ])
            proc.on('close', (code) => {
                _nvencAvailable = code === 0
                resolve(_nvencAvailable)
            })
            proc.on('error', () => {
                _nvencAvailable = false
                resolve(false)
            })
            setTimeout(() => {
                try { proc.kill() } catch { /* */ }
                if (_nvencAvailable === null) {
                    _nvencAvailable = false
                    resolve(false)
                }
            }, 5000)
        })
    } catch {
        _nvencAvailable = false
        return false
    }
}

export function getEncoderArgs(useGpu: boolean): string[] {
    if (useGpu) {
        return ['-c:v', 'h264_nvenc', '-preset', 'p1', '-rc', 'vbr', '-cq', '20', '-b:v', '0', '-pix_fmt', 'yuv420p']
    }
    return ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p']
}

// ── Helpers ────────────────────────────────
export function naturalSort(a: string, b: string): number {
    return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })
}

export function listMedia(folder: string, exts: string[]): string[] {
    if (!fs.existsSync(folder)) return []
    return fs.readdirSync(folder)
        .filter(f => exts.includes(path.extname(f).toLowerCase()))
        .sort(naturalSort)
        .map(f => path.join(folder, f))
}

export function escapeConcat(p: string): string {
    return p.replace(/'/g, "'\\''")
}

export function log(win: BrowserWindow, msg: string) {
    win.webContents.send('merge:log', msg)
}

export async function probe(filePath: string): Promise<any> {
    return new Promise((resolve, reject) => {
        const proc = spawn(getFFprobePath(), [
            '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', filePath,
        ])
        let out = ''
        proc.stdout?.on('data', (d: Buffer) => { out += d.toString() })
        proc.on('close', (code) => {
            if (code === 0) {
                try { resolve(JSON.parse(out)) } catch { reject(new Error('Parse error')) }
            } else reject(new Error(`ffprobe exit ${code}`))
        })
    })
}

export async function run(args: string[], win: BrowserWindow, cwd?: string): Promise<void> {
    if (stopped) throw new Error('STOPPED')
    return new Promise((resolve, reject) => {
        const proc = spawn(getFFmpegPath(), args, cwd ? { cwd } : undefined)
        activeProc = proc
        proc.stderr?.on('data', (d: Buffer) => {
            const text = d.toString().trim()
            if (text) log(win, text)
        })
        proc.on('close', (code) => {
            activeProc = null
            if (stopped) reject(new Error('STOPPED'))
            else if (code === 0) resolve()
            else reject(new Error(`FFmpeg exit ${code}`))
        })
    })
}

// ── Parse output resolution ────────────────
export function parseOutputDims(label: string): { w: number; h: number } {
    const m = label.match(/(\d+)\s*[x×]\s*(\d+)/)
    if (m) return { w: parseInt(m[1]), h: parseInt(m[2]) }
    return { w: 1920, h: 1080 }
}

// ── Get video duration ─────────────────────
export async function getDuration(filePath: string): Promise<number> {
    const info = await probe(filePath)
    return parseFloat(info.format?.duration || '0')
}
