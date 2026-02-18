/**
 * merge-transitions — Transition rendering for SK2 Merge engine.
 * Contains custom transitions, segment-level smart rendering, and xfade.
 * Extracted from merge.ipc.ts to enforce ≤300 lines/file.
 */

import { spawn } from 'child_process'
import { BrowserWindow } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import os from 'node:os'

import { getFFmpegPath } from './ffmpeg.ipc.js'
import {
    resolveTransition as resolveXfade,
    isCustomTransition, FADE_TO_BLACK_CONFIG,
} from '../utils/transitions.js'

import {
    run, log, probe, escapeConcat, getDuration,
    checkNvenc, getEncoderArgs, isStopped,
} from './merge-helpers.js'

// ── Auto-fix videos to same codec/res/fps ──
export async function autoFixVideos(
    outputFolder: string, videos: string[], targetW: number, targetH: number,
    win: BrowserWindow
): Promise<string[]> {
    const fixDir = path.join(outputFolder, '_merge_fix')
    fs.mkdirSync(fixDir, { recursive: true })
    const fixed: string[] = []

    const useGpu = await checkNvenc()
    const encoderLabel = useGpu ? '🚀 GPU (NVENC)' : '💻 CPU (libx264)'
    log(win, `⚙️ Encoder: ${encoderLabel}`)

    for (let i = 0; i < videos.length; i++) {
        if (isStopped()) throw new Error('STOPPED')
        const v = videos[i]
        const info = await probe(v)
        const vs = info.streams?.find((s: any) => s.codec_type === 'video')
        const needsFix = !vs || vs.width !== targetW || vs.height !== targetH ||
            vs.codec_name !== 'h264'

        if (!needsFix) {
            fixed.push(v)
            continue
        }

        const outPath = path.join(fixDir, `fix_${i}${path.extname(v)}`)
        log(win, `[FIX ${i + 1}/${videos.length}] ${path.basename(v)}`)
        await run([
            '-y', '-i', v,
            '-vf', `scale=${targetW}:${targetH}:force_original_aspect_ratio=decrease,pad=${targetW}:${targetH}:(ow-iw)/2:(oh-ih)/2`,
            ...getEncoderArgs(useGpu),
            '-r', '30', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', '-loglevel', 'error', outPath,
        ], win)
        fixed.push(outPath)
    }
    return fixed
}

// ── Simple concat (no transitions) ─────────
export async function concatCopy(
    outputFolder: string, videos: string[], outPath: string, win: BrowserWindow
): Promise<void> {
    const tmpDir = path.join(outputFolder, '_merge_tmp')
    fs.mkdirSync(tmpDir, { recursive: true })
    const listFile = path.join(tmpDir, 'concat.txt')
    const lines = videos.map(v => `file '${escapeConcat(v)}'`)
    fs.writeFileSync(listFile, lines.join('\n'), 'utf-8')

    await run([
        '-y', '-f', 'concat', '-safe', '0', '-i', listFile,
        '-c:v', 'copy', '-c:a', 'copy',
        '-movflags', '+faststart', '-loglevel', 'error', outPath,
    ], win)
}

// ── Custom transition rendering (Fade to Black, etc.) ──
async function renderWithCustomTransition(
    outputFolder: string, videos: string[], transName: string,
    win: BrowserWindow, outPath: string
): Promise<void> {
    const cfg = FADE_TO_BLACK_CONFIG
    const totalTransDur = cfg.fadeOutDuration + cfg.blackHoldDuration + cfg.fadeInDuration
    log(win, `[CUSTOM] "${transName}" (${totalTransDur}s per cut)`)

    const durations: number[] = []
    for (const v of videos) durations.push(await getDuration(v))

    const tmpDir = path.join(outputFolder, '_merge_tmp')
    fs.mkdirSync(tmpDir, { recursive: true })

    const useGpu = await checkNvenc()
    const segments: string[] = []

    for (let i = 0; i < videos.length; i++) {
        if (isStopped()) throw new Error('STOPPED')
        const v = videos[i]
        const dur = durations[i]

        const fadeIn = i > 0
        const fadeOut = i < videos.length - 1

        const segOut = path.join(tmpDir, `seg_${String(i).padStart(4, '0')}.mp4`)

        let vf = ''
        if (fadeIn && fadeOut) {
            vf = `fade=t=in:st=0:d=${cfg.fadeInDuration}:color=black,` +
                `fade=t=out:st=${Math.max(0, dur - cfg.fadeOutDuration)}:d=${cfg.fadeOutDuration}:color=black`
        } else if (fadeIn) {
            vf = `fade=t=in:st=0:d=${cfg.fadeInDuration}:color=black`
        } else if (fadeOut) {
            vf = `fade=t=out:st=${Math.max(0, dur - cfg.fadeOutDuration)}:d=${cfg.fadeOutDuration}:color=black`
        }

        const args = ['-y', '-i', v]
        if (vf) args.push('-vf', vf)
        args.push('-an', ...getEncoderArgs(useGpu))
        args.push('-movflags', '+faststart', '-loglevel', 'error', segOut)
        await run(args, win)
        segments.push(segOut)

        // Add black hold between clips (except after last)
        if (fadeOut && cfg.blackHoldDuration > 0) {
            const info = await probe(v)
            const vs = info.streams?.find((s: any) => s.codec_type === 'video')
            const w = vs?.width || 1920
            const h = vs?.height || 1080
            const blackSeg = path.join(tmpDir, `black_${String(i).padStart(4, '0')}.mp4`)
            await run([
                '-y', '-f', 'lavfi', '-i', `color=c=black:s=${w}x${h}:d=${cfg.blackHoldDuration}:r=30`,
                ...getEncoderArgs(useGpu),
                '-movflags', '+faststart', '-loglevel', 'error', blackSeg,
            ], win)
            segments.push(blackSeg)
        }

        log(win, `[CUSTOM] Processed ${i + 1}/${videos.length}: ${path.basename(v)}`)
    }

    const listFile = path.join(tmpDir, 'custom_concat.txt')
    const lines = segments.map(f => `file '${escapeConcat(f)}'`)
    fs.writeFileSync(listFile, lines.join('\n'), 'utf-8')

    await run([
        '-y', '-f', 'concat', '-safe', '0', '-i', listFile,
        '-c:v', 'copy', '-an',
        '-movflags', '+faststart', '-loglevel', 'error', outPath,
    ], win)
    log(win, `[CUSTOM] ✅ Rendered with "${transName}"`)
}

// ── Trim segment with re-encoding ──────────
async function trimSegment(
    input: string, output: string, ss: number, t?: number,
    useGpu?: boolean
): Promise<void> {
    const args = ['-y', '-ss', ss.toFixed(3), '-i', input]
    if (t !== undefined && t > 0) args.push('-t', t.toFixed(3))
    args.push(...getEncoderArgs(useGpu ?? false), '-an', '-loglevel', 'error', output)
    const ffPath = getFFmpegPath()
    return new Promise((resolve, reject) => {
        const proc = spawn(ffPath, args)
        let err = ''
        proc.stderr?.on('data', (d: Buffer) => { err += d.toString() })
        proc.on('close', (code) => {
            if (code === 0) resolve()
            else reject(new Error(`trim exit ${code}: ${err.slice(0, 200)}`))
        })
    })
}

// ── Render a single 1-second transition pair ──
async function renderTransitionPair(
    clipA: string, clipB: string,
    durA: number, transDur: number, transName: string,
    outPath: string, useGpu: boolean, _win: BrowserWindow
): Promise<void> {
    const ffPath = getFFmpegPath()
    const offset = Math.max(0, durA - transDur)
    const args = [
        '-y',
        '-i', clipA, '-i', clipB,
        '-filter_complex',
        `[0:v][1:v]xfade=transition=${transName}:duration=${transDur}:offset=${offset.toFixed(3)}[vout]`,
        '-map', '[vout]', '-an',
        ...getEncoderArgs(useGpu),
        '-movflags', '+faststart', '-loglevel', 'error', outPath,
    ]
    return new Promise((resolve, reject) => {
        const proc = spawn(ffPath, args)
        let err = ''
        proc.stderr?.on('data', (d: Buffer) => { err += d.toString() })
        proc.on('close', (code) => {
            if (code === 0) resolve()
            else reject(new Error(`xfade exit ${code}: ${err.slice(0, 200)}`))
        })
    })
}

// ── Segment-level parallel rendering (Smart Render) ──
async function renderSegmentLevel(
    outputFolder: string, videos: string[], transIn: string,
    transDur: number, win: BrowserWindow, outPath: string
): Promise<void> {
    const useGpu = await checkNvenc()
    const tmpDir = path.join(outputFolder, '_smart_render')
    fs.mkdirSync(tmpDir, { recursive: true })

    const n = videos.length
    const encodeParallel = useGpu ? 3 : Math.min(os.cpus().length, 8)

    // Step 0: Get all durations
    log(win, `[SMART] Getting durations for ${n} clips...`)
    const durations: number[] = []
    for (const v of videos) durations.push(await getDuration(v))

    // Step 1: Resolve all transitions
    const transitions: string[] = []
    for (let i = 0; i < n - 1; i++) {
        transitions.push(resolveXfade(transIn))
    }

    // Step 2: Trim body segments
    log(win, `[SMART] Trimming ${n} body segments (-c copy)...`)
    const bodyFiles: string[] = []
    const trimJobs: (() => Promise<void>)[] = []

    for (let i = 0; i < n; i++) {
        if (isStopped()) throw new Error('STOPPED')
        const bodyOut = path.join(tmpDir, `body_${String(i).padStart(4, '0')}.mp4`)
        bodyFiles.push(bodyOut)

        const ss = i === 0 ? 0 : transDur
        const bodyLen = i === n - 1
            ? durations[i] - (i === 0 ? 0 : transDur)
            : durations[i] - (i === 0 ? transDur : 2 * transDur)

        if (bodyLen > 0.01) {
            const capturedSs = ss
            const capturedBodyLen = bodyLen
            const capturedI = i
            trimJobs.push(() => trimSegment(videos[capturedI], bodyOut, capturedSs, capturedBodyLen, useGpu))
        } else {
            trimJobs.push(async () => { bodyFiles[i] = '' })
        }
    }

    // Run trim jobs in parallel
    for (let g = 0; g < trimJobs.length; g += encodeParallel) {
        if (isStopped()) throw new Error('STOPPED')
        const batch = trimJobs.slice(g, g + encodeParallel)
        await Promise.all(batch.map(fn => fn()))
    }

    // Step 3: Render transition regions in parallel
    log(win, `[SMART] Rendering ${n - 1} transitions (${encodeParallel} parallel, NVENC=${useGpu})...`)
    const transFiles: string[] = []
    const transJobs: (() => Promise<void>)[] = []

    for (let i = 0; i < n - 1; i++) {
        const transOut = path.join(tmpDir, `trans_${String(i).padStart(4, '0')}.mp4`)
        transFiles.push(transOut)

        const tailFile = path.join(tmpDir, `tail_${String(i).padStart(4, '0')}.mp4`)
        const headFile = path.join(tmpDir, `head_${String(i + 1).padStart(4, '0')}.mp4`)

        const capturedI = i
        transJobs.push(async () => {
            if (isStopped()) throw new Error('STOPPED')
            const tailStart = Math.max(0, durations[capturedI] - transDur)
            const tailLen = durations[capturedI] - tailStart
            await trimSegment(videos[capturedI], tailFile, tailStart, tailLen, useGpu)

            const headLen = Math.min(transDur, durations[capturedI + 1])
            await trimSegment(videos[capturedI + 1], headFile, 0, headLen, useGpu)

            await renderTransitionPair(
                tailFile, headFile,
                tailLen, transDur,
                transitions[capturedI],
                transOut, useGpu, win
            )

            try { fs.unlinkSync(tailFile) } catch { /* */ }
            try { fs.unlinkSync(headFile) } catch { /* */ }
        })
    }

    // Run transition jobs in parallel
    for (let g = 0; g < transJobs.length; g += encodeParallel) {
        if (isStopped()) throw new Error('STOPPED')
        const batch = transJobs.slice(g, g + encodeParallel)
        log(win, `[SMART] Transitions ${g + 1}-${Math.min(g + encodeParallel, transJobs.length)}/${transJobs.length}...`)
        await Promise.all(batch.map(fn => fn()))
    }

    // Step 4: Build concat list
    log(win, `[SMART] Concatenating ${n + n - 1} segments (-c copy)...`)
    const concatSegments: string[] = []
    for (let i = 0; i < n; i++) {
        if (bodyFiles[i] && fs.existsSync(bodyFiles[i])) {
            concatSegments.push(bodyFiles[i])
        }
        if (i < n - 1 && fs.existsSync(transFiles[i])) {
            concatSegments.push(transFiles[i])
        }
    }

    const concatList = path.join(tmpDir, 'concat.txt')
    const lines = concatSegments.map(f => `file '${escapeConcat(f)}'`)
    fs.writeFileSync(concatList, lines.join('\n'), 'utf-8')

    await run([
        '-y', '-f', 'concat', '-safe', '0', '-i', concatList,
        '-c', 'copy', '-movflags', '+faststart',
        '-loglevel', 'error', outPath,
    ], win)

    try { fs.rmSync(tmpDir, { recursive: true, force: true }) } catch { /* */ }
    log(win, `[SMART] ✅ Done!`)
}

// ── Render with xfade transitions (dispatcher) ──
export async function renderWithTransitions(
    _outputFolder: string, videos: string[], transIn: string,
    duration: number, win: BrowserWindow, outPath: string
): Promise<void> {
    if (videos.length < 2) {
        fs.copyFileSync(videos[0], outPath)
        return
    }

    if (isCustomTransition(transIn)) {
        await renderWithCustomTransition(_outputFolder, videos, transIn, win, outPath)
        return
    }

    await renderSegmentLevel(_outputFolder, videos, transIn, duration, win, outPath)
}
