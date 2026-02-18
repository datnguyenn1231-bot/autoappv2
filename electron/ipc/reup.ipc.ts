/**
 * Reup IPC — Video processing with 9-layer anti-detection pipeline.
 * Filter chain logic is in reup-filters.ts (separated for testability).
 */

import { spawn, ChildProcess } from 'child_process'
import { ipcMain, BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import os from 'node:os'

import { getFFmpegPath, getFFprobePath } from './ffmpeg.ipc.js'
import { buildFilterChain, type ReupConfig } from './reup-filters.js'
import { getNVEncCPath, isNVEncCAvailable, canUseNVEncC, buildNVEncCArgs, needsSeparateAudio } from './nvenc-builder.js'

// ── Constants ──
const VIDEO_EXTS = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v']

// ── State ──
let activeProcs: ChildProcess[] = []
let stopped = false

// ── GPU Detection ──
let _nvencAvailable: boolean | null = null

async function checkNvenc(): Promise<boolean> {
    if (_nvencAvailable !== null) return _nvencAvailable
    const ffPath = getFFmpegPath()
    return new Promise((resolve) => {
        const proc = spawn(ffPath, [
            '-y', '-f', 'lavfi', '-i', 'nullsrc=s=256x256:d=0.1',
            '-c:v', 'h264_nvenc', '-f', 'null', 'NUL',
        ], { shell: true, windowsHide: true })
        proc.on('close', (code) => { _nvencAvailable = code === 0; resolve(_nvencAvailable) })
        proc.on('error', () => { _nvencAvailable = false; resolve(false) })
        setTimeout(() => { if (_nvencAvailable === null) { proc.kill(); _nvencAvailable = false; resolve(false) } }, 8000)
    })
}

// ── Helpers ──
function log(win: BrowserWindow, msg: string) {
    try { win.webContents.send('reup:log', msg) } catch { /* */ }
}

function runFF(args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
        if (stopped) return reject(new Error('Stopped'))
        const proc = spawn(getFFmpegPath(), args, { windowsHide: true })
        activeProcs.push(proc)
        let stderr = ''
        proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
        proc.on('close', (code) => {
            activeProcs = activeProcs.filter(p => p !== proc)
            code === 0 ? resolve() : reject(new Error(`FFmpeg exit ${code}: ${stderr.slice(-300)}`))
        })
        proc.on('error', (e) => { activeProcs = activeProcs.filter(p => p !== proc); reject(e) })
    })
}

function runNVEnc(args: string[]): Promise<void> {
    return new Promise((resolve, reject) => {
        if (stopped) return reject(new Error('Stopped'))
        const nvencPath = getNVEncCPath()
        if (!nvencPath) return reject(new Error('NVEncC64 not found'))
        const proc = spawn(nvencPath, args, { windowsHide: true })
        activeProcs.push(proc)
        let stderr = ''
        proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
        proc.stdout?.on('data', (d: Buffer) => { stderr += d.toString() })
        proc.on('close', (code) => {
            activeProcs = activeProcs.filter(p => p !== proc)
            code === 0 ? resolve() : reject(new Error(`NVEncC exit ${code}: ${stderr.slice(-300)}`))
        })
        proc.on('error', (e) => { activeProcs = activeProcs.filter(p => p !== proc); reject(e) })
    })
}

function listVideos(dir: string): string[] {
    if (!fs.existsSync(dir)) return []
    return fs.readdirSync(dir)
        .filter(f => VIDEO_EXTS.includes(path.extname(f).toLowerCase()))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        .map(f => path.join(dir, f))
}

// ── Process single video ──
async function processVideo(inputPath: string, outputDir: string, config: ReupConfig, useGpu: boolean): Promise<string> {
    const basename = path.basename(inputPath, path.extname(inputPath))
    const outPath = path.join(outputDir, `${basename}_REUP.mp4`)

    // Try NVEncC + libplacebo shaders (10-15x faster) if compatible
    if (useGpu && isNVEncCAvailable() && canUseNVEncC(config)) {
        try {
            if (needsSeparateAudio(config)) {
                // Audio effects need FFmpeg — process audio separately
                const tmpVideo = path.join(outputDir, `${basename}_tmpvideo.mp4`)
                const tmpAudio = path.join(outputDir, `${basename}_tmpaudio.aac`)

                // Step 1: NVEncC encodes video (no audio)
                const nvArgs = buildNVEncCArgs(config, inputPath, tmpVideo)
                await runNVEnc(nvArgs)

                // Step 2: FFmpeg extracts + processes audio
                const { af } = buildFilterChain(config)
                const audioArgs = ['-y', '-i', inputPath]
                if (af) audioArgs.push('-af', af)
                audioArgs.push('-vn', '-c:a', 'aac', '-b:a', '192k', tmpAudio)
                await runFF(audioArgs)

                // Step 3: FFmpeg muxes video + audio
                await runFF(['-y', '-i', tmpVideo, '-i', tmpAudio,
                    '-c:v', 'copy', '-c:a', 'copy',
                    '-movflags', '+faststart', outPath])

                // Cleanup temp files
                try { fs.unlinkSync(tmpVideo) } catch { /* */ }
                try { fs.unlinkSync(tmpAudio) } catch { /* */ }
            } else {
                // No audio effects — NVEncC handles everything
                const nvArgs = buildNVEncCArgs(config, inputPath, outPath)
                await runNVEnc(nvArgs)
            }
            return outPath
        } catch {
            // NVEncC failed — fallback to FFmpeg below
        }
    }

    // FFmpeg path (with all filters)
    const { vf, af, complexFilter, extraInputs } = buildFilterChain(config)
    const args: string[] = ['-y', '-i', inputPath]
    for (const inp of extraInputs) args.push('-i', inp)
    if (complexFilter) {
        args.push('-filter_complex', complexFilter)
    } else if (vf) {
        args.push('-vf', vf)
    }
    if (af) args.push('-af', af)
    if (config.cleanMetadata) args.push('-map_metadata', '-1')

    if (useGpu) args.push('-c:v', 'h264_nvenc', '-preset', 'p2', '-cq', '23')
    else args.push('-c:v', 'libx264', '-preset', 'fast', '-crf', '23')

    args.push('-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-loglevel', 'error', outPath)
    await runFF(args)
    return outPath
}

// ── Main pipeline ──
async function runReup(config: ReupConfig, win: BrowserWindow): Promise<boolean> {
    stopped = false
    const videos = listVideos(config.inputFolder)
    if (videos.length === 0) { log(win, '❌ No videos found'); return false }

    const outputDir = path.join(config.inputFolder, '_REUP')
    if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true })

    const useGpu = await checkNvenc()
    log(win, useGpu ? '🚀 GPU (NVENC)' : '💻 CPU (libx264)')
    log(win, `📂 ${videos.length} videos → _REUP/`)

    const parallel = useGpu ? 3 : Math.min(os.cpus().length, 8)
    let completed = 0, failed = 0

    async function worker(queue: string[]) {
        while (queue.length > 0 && !stopped) {
            const file = queue.shift()!
            const name = path.basename(file)
            try {
                log(win, `[${completed + failed + 1}/${videos.length}] ⚡ ${name}`)
                await processVideo(file, outputDir, config, useGpu)
                completed++
                log(win, `[${completed + failed}/${videos.length}] ✅ ${name}`)
            } catch (e: any) {
                failed++
                log(win, `[${completed + failed}/${videos.length}] ❌ ${name}: ${e.message}`)
            }
        }
    }

    const queue = [...videos]
    await Promise.all(Array.from({ length: Math.min(parallel, queue.length) }, () => worker(queue)))

    if (stopped) { log(win, '⏹ Stopped'); return false }
    log(win, `\n✅ DONE: ${completed}/${videos.length} success, ${failed} failed`)
    log(win, `📂 ${outputDir}`)
    return true
}

// ── Get video duration (seconds) ──
function getVideoDuration(filePath: string): Promise<number> {
    return new Promise((resolve, reject) => {
        const probePath = getFFprobePath()
        const proc = spawn(probePath, [
            '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', filePath,
        ], { windowsHide: true })
        let out = ''
        let err = ''
        proc.stdout?.on('data', (d: Buffer) => { out += d.toString() })
        proc.stderr?.on('data', (d: Buffer) => { err += d.toString() })
        proc.on('close', (code) => {
            const dur = parseFloat(out.trim())
            if (code === 0 && !isNaN(dur)) resolve(dur)
            else reject(new Error(`ffprobe exit ${code}: ${err.slice(-200) || out.slice(-100) || 'no output'} | path: ${probePath}`))
        })
        proc.on('error', (e) => reject(new Error(`ffprobe spawn error: ${e.message} | path: ${probePath}`)))
    })
}

// ── Split single video ──
async function splitVideo(
    inputPath: string, outputDir: string,
    splitMode: string, segmentLength: number, cutAtSecond: number,
    win: BrowserWindow
): Promise<number> {
    const basename = path.basename(inputPath, path.extname(inputPath))
    const ext = path.extname(inputPath)
    const duration = await getVideoDuration(inputPath)

    let segments: { start: number; duration: number; label: string }[] = []

    if (splitMode === 'half') {
        const half = duration / 2
        segments = [
            { start: 0, duration: half, label: `${basename}_part1${ext}` },
            { start: half, duration: half, label: `${basename}_part2${ext}` },
        ]
    } else if (splitMode === 'at_second') {
        // Cut at exact second
        const cutAt = Math.min(cutAtSecond, duration)
        if (cutAt > 0.5) {
            segments.push({ start: 0, duration: cutAt, label: `${basename}_part1${ext}` })
        }
        if (duration - cutAt > 0.5) {
            segments.push({ start: cutAt, duration: duration - cutAt, label: `${basename}_part2${ext}` })
        }
    } else {
        // segments mode — split by duration
        let idx = 1
        for (let t = 0; t < duration; t += segmentLength) {
            const len = Math.min(segmentLength, duration - t)
            if (len < 0.5) break // skip tiny remainders
            segments.push({ start: t, duration: len, label: `${basename}_seg${String(idx).padStart(3, '0')}${ext}` })
            idx++
        }
    }

    for (const seg of segments) {
        if (stopped) break
        const outPath = path.join(outputDir, seg.label)
        const args = [
            '-y', '-ss', String(seg.start),
            '-i', `"${inputPath}"`,
            '-t', String(seg.duration),
            '-c', 'copy',
            '-movflags', '+faststart', `"${outPath}"`,
        ]
        await runFF(args)
        log(win, `  → ${seg.label}`)
    }
    return segments.length
}
// ── Scene Detection using FFmpeg ──
function detectScenes(filePath: string, threshold: number, _win: BrowserWindow): Promise<number[]> {
    return new Promise((resolve, reject) => {
        const args = [
            '-i', `"${filePath}"`,
            '-vf', `select='gt(scene\\,${threshold})',showinfo`,
            '-f', 'null', 'NUL',
        ]
        const proc = spawn(getFFmpegPath(), args, { shell: true, windowsHide: true })
        activeProcs.push(proc)
        let stderr = ''
        proc.stderr?.on('data', (d: Buffer) => { stderr += d.toString() })
        proc.on('close', (_code) => {
            activeProcs = activeProcs.filter(p => p !== proc)
            // Parse showinfo output for timestamps: pts_time:123.456
            const timestamps: number[] = [0] // always start at 0
            const regex = /pts_time:\s*([\d.]+)/g
            let match
            while ((match = regex.exec(stderr)) !== null) {
                const t = parseFloat(match[1])
                if (!isNaN(t) && t > 0) timestamps.push(t)
            }
            resolve(timestamps)
        })
        proc.on('error', (e) => {
            activeProcs = activeProcs.filter(p => p !== proc)
            reject(e)
        })
    })
}

// ── Split by detected scenes ──
async function splitByScenes(
    inputPath: string, outputDir: string,
    timestamps: number[], duration: number,
    minSceneSec: number, win: BrowserWindow
): Promise<number> {
    const basename = path.basename(inputPath, path.extname(inputPath))
    const ext = path.extname(inputPath)

    // Filter out scenes shorter than minSceneSec
    const filtered: number[] = [timestamps[0]]
    for (let i = 1; i < timestamps.length; i++) {
        if (timestamps[i] - filtered[filtered.length - 1] >= minSceneSec) {
            filtered.push(timestamps[i])
        }
    }

    // Build segments from timestamps
    const segments: { start: number; end: number; label: string }[] = []
    for (let i = 0; i < filtered.length; i++) {
        const start = filtered[i]
        const end = i + 1 < filtered.length ? filtered[i + 1] : duration
        if (end - start < 0.1) continue
        segments.push({
            start,
            end,
            label: `${basename}_Canh-${String(i + 1).padStart(3, '0')}${ext}`,
        })
    }

    // Split each segment
    for (const seg of segments) {
        if (stopped) break
        const outPath = path.join(outputDir, seg.label)
        const args = [
            '-y', '-ss', String(seg.start),
            '-i', `"${inputPath}"`,
            '-t', String(seg.end - seg.start),
            '-c', 'copy',
            '-movflags', '+faststart', `"${outPath}"`,
        ]
        await runFF(args)
        log(win, `  → ${seg.label}`)
    }

    // Write CSV
    const csvPath = path.join(outputDir, `${basename}_scenes.csv`)
    const csvLines = ['Scene,Start,End,Duration']
    segments.forEach((seg, i) => {
        const dur = (seg.end - seg.start).toFixed(2)
        csvLines.push(`${String(i + 1).padStart(3, '0')},${seg.start.toFixed(3)},${seg.end.toFixed(3)},${dur}`)
    })
    fs.writeFileSync(csvPath, csvLines.join('\n'), 'utf-8')

    return segments.length
}

// ── Split pipeline ──
async function runSplit(config: any, win: BrowserWindow): Promise<boolean> {
    stopped = false
    const videos = listVideos(config.inputFolder)
    if (videos.length === 0) { log(win, '❌ No videos found'); return false }

    const mode = config.splitMode || 'segments'
    const isScene = mode === 'scenes'
    const outputDir = path.join(config.inputFolder, isScene ? '_TACH_CANH' : '_SPLIT')
    if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true })

    if (isScene) {
        const threshold = config.sceneThreshold || 0.3
        const minScene = config.minSceneSec || 0.35
        log(win, `🎬 Scene Detect: threshold=${threshold}, min=${minScene}s`)
        log(win, `📂 ${videos.length} videos → _TACH_CANH/`)

        let completed = 0, failed = 0
        for (const file of videos) {
            if (stopped) break
            const name = path.basename(file)
            try {
                log(win, `[${completed + failed + 1}/${videos.length}] 🔍 Detecting: ${name}`)
                const scenes = await detectScenes(file, threshold, win)
                const duration = await getVideoDuration(file)
                log(win, `  → Found ${scenes.length - 1} scene changes`)

                // Create per-video subfolder
                const videoOutDir = path.join(outputDir, path.basename(file, path.extname(file)))
                if (!fs.existsSync(videoOutDir)) fs.mkdirSync(videoOutDir, { recursive: true })

                const parts = await splitByScenes(file, videoOutDir, scenes, duration, minScene, win)
                completed++
                log(win, `[${completed + failed}/${videos.length}] ✅ ${name} → ${parts} scenes`)
            } catch (e: any) {
                failed++
                log(win, `[${completed + failed}/${videos.length}] ❌ ${name}: ${e.message}`)
            }
        }

        if (stopped) { log(win, '⏹ Stopped'); return false }
        log(win, `\n✅ DONE: ${completed}/${videos.length} success, ${failed} failed`)
        log(win, `📂 ${outputDir}`)
        return true
    }

    // Duration-based split
    const segLen = config.segmentLength || 15
    log(win, `✂️ Split by ${segLen}s`)
    log(win, `📂 ${videos.length} videos → _SPLIT/`)

    let completed = 0, failed = 0
    for (const file of videos) {
        if (stopped) break
        const name = path.basename(file)
        try {
            log(win, `[${completed + failed + 1}/${videos.length}] ✂️ ${name}`)
            const parts = await splitVideo(file, outputDir, mode, segLen, 0, win)
            completed++
            log(win, `[${completed + failed}/${videos.length}] ✅ ${name} → ${parts} parts`)
        } catch (e: any) {
            failed++
            log(win, `[${completed + failed}/${videos.length}] ❌ ${name}: ${e.message}`)
        }
    }

    if (stopped) { log(win, '⏹ Stopped'); return false }
    log(win, `\n✅ DONE: ${completed}/${videos.length} success, ${failed} failed`)
    log(win, `📂 ${outputDir}`)
    return true
}

// ── IPC Registration ──
export function registerReupIPC(): void {
    ipcMain.handle('reup:scan', async (_e, { folderPath }) => ({ videos: listVideos(folderPath) }))

    ipcMain.handle('reup:run', async (event, { config }) => {
        const win = BrowserWindow.fromWebContents(event.sender)
        if (!win) return { success: false, error: 'No window' }
        // Route by mode
        if (config?.mode === 'split') {
            return { success: await runSplit(config, win) }
        }
        return { success: await runReup(config, win) }
    })

    ipcMain.handle('reup:stop', async () => {
        stopped = true
        for (const p of activeProcs) { try { p.kill('SIGTERM') } catch { /* */ } }
        activeProcs = []
        return { stopped: true }
    })

    // ── Fast Export: Split & Stitch + GPU Pipeline ──

    /** Encode a single chunk — NVEncC + shaders first, FFmpeg fallback */
    async function encodeChunk(
        chunkPath: string, outPath: string,
        vf: string, af: string, complexFilter: string, extraInputs: string[],
        config: ReupConfig, useGpu: boolean, useNVEncC: boolean
    ): Promise<void> {
        // Try NVEncC + libplacebo shaders (full GPU pipeline, 10-15x faster)
        if (useNVEncC) {
            try {
                if (needsSeparateAudio(config)) {
                    // Audio effects need FFmpeg — process separately
                    const tmpVideo = outPath.replace('.mp4', '_tmpv.mp4')
                    const tmpAudio = outPath.replace('.mp4', '_tmpa.aac')

                    // Step 1: NVEncC encodes video (no audio)
                    const nvArgs = buildNVEncCArgs(config, chunkPath, tmpVideo)
                    await runNVEnc(nvArgs)

                    // Step 2: FFmpeg processes audio
                    const audioArgs = ['-y', '-i', chunkPath]
                    if (af) audioArgs.push('-af', af)
                    audioArgs.push('-vn', '-c:a', 'aac', '-b:a', '192k', tmpAudio)
                    await runFF(audioArgs)

                    // Step 3: Mux video + audio
                    await runFF(['-y', '-i', tmpVideo, '-i', tmpAudio,
                        '-c:v', 'copy', '-c:a', 'copy',
                        '-movflags', '+faststart', outPath])

                    // Cleanup
                    try { fs.unlinkSync(tmpVideo) } catch { /* */ }
                    try { fs.unlinkSync(tmpAudio) } catch { /* */ }
                } else {
                    // No audio effects — NVEncC handles everything
                    const nvArgs = buildNVEncCArgs(config, chunkPath, outPath)
                    await runNVEnc(nvArgs)
                }
                return
            } catch {
                // NVEncC failed — fallback to FFmpeg
            }
        }

        // FFmpeg path
        const args: string[] = ['-y']
        if (useGpu) args.push('-hwaccel', 'cuda', '-hwaccel_output_format', 'nv12')
        args.push('-i', chunkPath)
        for (const inp of extraInputs) args.push('-i', inp)
        if (complexFilter) {
            args.push('-filter_complex', complexFilter)
        } else if (vf) {
            args.push('-vf', vf)
        }
        if (af) args.push('-af', af)
        if (config.cleanMetadata) args.push('-map_metadata', '-1')
        if (useGpu) args.push('-c:v', 'h264_nvenc', '-preset', 'p1', '-cq', '23')
        else args.push('-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23')
        args.push('-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', '-loglevel', 'error', outPath)
        await runFF(args)
    }

    /** Split & Stitch parallel export */
    async function fastExport(
        inputPath: string, outPath: string,
        config: ReupConfig, useGpu: boolean,
        win: BrowserWindow
    ): Promise<void> {
        const duration = await getVideoDuration(inputPath)
        const CHUNK_SEC = 30       // seconds per chunk
        const MAX_PARALLEL = useGpu ? 3 : Math.min(os.cpus().length, 4)

        const numChunks = Math.max(1, Math.ceil(duration / CHUNK_SEC))
        const tmpDir = path.join(os.tmpdir(), `aurasplit_export_${Date.now()}`)
        fs.mkdirSync(tmpDir, { recursive: true })

        try {
            // ── Phase 1: Split at keyframes (instant, -c copy) ──
            log(win, `✂️ Splitting into ${numChunks} chunks...`)
            const chunkPaths: string[] = []

            for (let i = 0; i < numChunks; i++) {
                if (stopped) throw new Error('Stopped')
                const start = i * CHUNK_SEC
                const chunkLen = Math.min(CHUNK_SEC, duration - start)
                if (chunkLen < 0.1) break

                const chunkFile = path.join(tmpDir, `chunk_${String(i).padStart(4, '0')}.mp4`)
                chunkPaths.push(chunkFile)

                await runFF([
                    '-y', '-ss', String(start),
                    '-i', inputPath,
                    '-t', String(chunkLen),
                    '-c', 'copy', '-avoid_negative_ts', '1',
                    '-movflags', '+faststart', chunkFile,
                ])
            }

            // ── Phase 2: Encode chunks in parallel ──
            const useNVEncC = useGpu && isNVEncCAvailable() && canUseNVEncC(config)
            const encoderLabel = useNVEncC ? '⚡ NVEncC (full GPU)' : (useGpu ? '🚀 FFmpeg+NVENC' : '💻 FFmpeg CPU')
            log(win, `${encoderLabel} — Encoding ${chunkPaths.length} chunks × ${MAX_PARALLEL} parallel...`)
            const { vf, af, complexFilter, extraInputs } = buildFilterChain(config)
            const encodedPaths: string[] = []
            const queue = [...chunkPaths]
            let doneCount = 0

            async function worker() {
                while (queue.length > 0 && !stopped) {
                    const chunk = queue.shift()!
                    const idx = chunkPaths.indexOf(chunk)
                    const encodedFile = path.join(tmpDir, `enc_${String(idx).padStart(4, '0')}.mp4`)
                    encodedPaths[idx] = encodedFile

                    await encodeChunk(chunk, encodedFile, vf, af, complexFilter, extraInputs, config, useGpu, useNVEncC)
                    doneCount++
                    log(win, `  [${doneCount}/${chunkPaths.length}] ✅ chunk ${idx + 1}`)
                }
            }

            await Promise.all(
                Array.from({ length: Math.min(MAX_PARALLEL, chunkPaths.length) }, () => worker())
            )

            if (stopped) throw new Error('Stopped')

            // ── Phase 3: Concat encoded chunks ──
            log(win, `🔗 Stitching ${encodedPaths.length} chunks...`)
            const concatList = path.join(tmpDir, 'concat.txt')
            const lines = encodedPaths.map(p => `file '${p.replace(/\\/g, '/')}'`)
            fs.writeFileSync(concatList, lines.join('\n'), 'utf-8')

            await runFF([
                '-y', '-f', 'concat', '-safe', '0',
                '-i', concatList,
                '-c', 'copy', '-movflags', '+faststart',
                outPath,
            ])

        } finally {
            // ── Phase 4: Cleanup temp ──
            try { fs.rmSync(tmpDir, { recursive: true, force: true }) } catch { /* */ }
        }
    }

    // ── Export single video with effects + optional SUB ──
    ipcMain.handle('reup:export', async (event, { config, outputPath }) => {
        const win = BrowserWindow.fromWebContents(event.sender)
        if (!win) return { success: false, error: 'No window' }

        const inputPath = config.singleFile
        if (!inputPath || !fs.existsSync(inputPath)) {
            log(win, '❌ No video file to export')
            return { success: false, error: 'No video file' }
        }

        let tempSrtPath = ''
        try {
            stopped = false
            const useGpu = await checkNvenc()
            log(win, useGpu ? '🚀 GPU (NVENC) + Split&Stitch' : '💻 CPU + Split&Stitch')
            log(win, `📦 Exporting: ${path.basename(inputPath)}`)

            // Copy SRT to temp with simple ASCII name (avoid Unicode path issues in FFmpeg filter)
            if (config.srtPath && fs.existsSync(config.srtPath)) {
                tempSrtPath = path.join(os.tmpdir(), `aurasplit_sub_${Date.now()}.srt`)
                fs.copyFileSync(config.srtPath, tempSrtPath)
                config.srtPath = tempSrtPath
                log(win, `📝 Subtitles: ${path.basename(config.srtPath)}`)
            }

            // Determine output path
            let outPath = outputPath
            if (!outPath) {
                const basename = path.basename(inputPath, path.extname(inputPath))
                const dir = path.dirname(inputPath)
                outPath = path.join(dir, `${basename}_REUP.mp4`)
            }

            const startTime = Date.now()
            await fastExport(inputPath, outPath, config, useGpu, win)
            const elapsed = ((Date.now() - startTime) / 1000).toFixed(1)

            log(win, `✅ Exported in ${elapsed}s: ${outPath}`)
            return { success: true, outputPath: outPath }
        } catch (e: any) {
            log(win, `❌ Export failed: ${e.message}`)
            return { success: false, error: e.message }
        } finally {
            // Cleanup temp SRT
            if (tempSrtPath) try { fs.unlinkSync(tempSrtPath) } catch { /* */ }
        }
    })
}
