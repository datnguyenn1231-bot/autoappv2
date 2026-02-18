/**
 * reup-filters.ts — FFmpeg filter chain builder for anti-detection pipeline.
 * Includes 16 filter layers + Frame Templates + Title + Logo.
 */

export type ColorGradingStyle = 'none' | 'vibrant' | 'bw' | 'sepia' | 'cool_blue'

export interface ReupConfig {
    inputFolder: string
    singleFile?: string
    mirror: boolean
    crop: number
    noise: boolean | number
    rotate: boolean | number
    lensDistortion: boolean
    hdr: boolean
    speed: number
    pitchShift?: boolean
    audioEvade?: boolean
    cleanMetadata: boolean
    musicPath: string
    colorGrading: ColorGradingStyle
    glow: boolean
    volumeBoost: number
    srtPath?: string
    // Frame effects
    frameTemplate?: string
    borderWidth?: number
    borderColor?: string
    zoomEffect?: boolean
    zoomIntensity?: number
    // Pixel-level anti-detect
    pixelEnlarge?: boolean
    chromaShuffle?: boolean
    rgbDrift?: boolean
    // Title overlay
    titleTemplate?: string
    titleText?: string
    descText?: string
    // Logo
    logoPath?: string
    logoPosition?: string
    logoSize?: number
}

/** Color grading FFmpeg filter strings */
function getColorGradingFilter(style: ColorGradingStyle): string {
    switch (style) {
        case 'vibrant':
            return [
                'eq=brightness=0.15:contrast=1.08:saturation=1.22',
                'vibrance=intensity=0.15',
                'unsharp=5:5:0.8:5:5:0.0',
                "curves=all='0/0 0.5/0.55 1/1'",
            ].join(',')
        case 'bw':
            return [
                'hue=s=0',
                'eq=contrast=1.20:brightness=0.05',
                'unsharp=7:7:1.2:7:7:0.0',
                "curves=all='0/0.05 0.5/0.5 1/0.95'",
                'noise=alls=2:allf=t',
            ].join(',')
        case 'sepia':
            return [
                'colortemperature=temperature=8000',
                'eq=brightness=0.08:contrast=1.05:saturation=0.95:gamma=1.1',
                "curves=red='0/0.05 1/1':blue='0/0 1/0.92'",
                'colorbalance=rs=0.05:gs=0:bs=-0.08',
                'vignette=angle=PI/4:a=0.3',
            ].join(',')
        case 'cool_blue':
            return [
                'eq=saturation=1.05:gamma_b=1.10:gamma_r=0.92',
                "curves=blue='0/0.03 1/1':red='0/0 1/0.95'",
                'colorbalance=bs=0.05:rs=-0.03',
            ].join(',')
        default:
            return ''
    }
}

/** Logo position → FFmpeg overlay coordinates */
function getLogoOverlayPos(pos: string): string {
    const map: Record<string, string> = {
        'top-left': 'x=20:y=20',
        'top-right': 'x=W-w-20:y=20',
        'bottom-left': 'x=20:y=H-h-20',
        'bottom-right': 'x=W-w-20:y=H-h-20',
        'auto': 'x=W-w-20:y=H-h-20',
    }
    return map[pos] || map['bottom-right']
}

/** Frame template → FFmpeg scale + pad dimensions */
function getFrameDimensions(template: string): { w: number; h: number } | null {
    const map: Record<string, { w: number; h: number }> = {
        '9:16': { w: 1080, h: 1920 },
        '1:1': { w: 1080, h: 1080 },
        '4:3': { w: 1440, h: 1080 },
        '3:4': { w: 1080, h: 1440 },
        '16:9': { w: 1920, h: 1080 },
    }
    return map[template] || null
}

/**
 * Build FFmpeg filter chain from config.
 * Returns { vf, af, complexFilter, extraInputs }.
 * - If no logo: use simple -vf / -af
 * - If logo: use -filter_complex with complexFilter
 */
export function buildFilterChain(config: ReupConfig): {
    vf: string
    af: string
    complexFilter: string
    extraInputs: string[]
} {
    const vFilters: string[] = []
    const aFilters: string[] = []
    const extraInputs: string[] = []
    const hasLogo = !!(config.logoPath && config.logoPath.trim())

    // ─── VIDEO FILTERS ───

    // L1: Mirror
    if (config.mirror) vFilters.push('hflip')

    // L2: Smart Crop
    if (config.crop > 0) {
        const keep = 1 - config.crop
        vFilters.push(
            `crop=iw*${keep.toFixed(3)}:ih*${keep.toFixed(3)}:(iw-ow)/2:(ih-oh)/2`,
            'scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,setsar=1'
        )
    }

    // L3: Noise/Grain
    if (config.noise) {
        const intensity = typeof config.noise === 'number' ? config.noise : 10
        vFilters.push(`noise=alls=${intensity}:allf=t+u`)
    }

    // L4: Subtle Rotate
    if (config.rotate) {
        const deg = typeof config.rotate === 'number' ? config.rotate : 2
        const rad = (deg * Math.PI / 180).toFixed(4)
        vFilters.push(`rotate=${rad}:c=none`)
    }

    // L5: Lens Distortion
    if (config.lensDistortion) {
        vFilters.push('lenscorrection=cx=0.5:cy=0.5:k1=-0.05:k2=-0.03')
    }

    // L6: HDR
    if (config.hdr) {
        vFilters.push(
            'eq=contrast=1.10:saturation=1.10:brightness=0.010',
            'unsharp=5:5:0.9:3:3:0.5'
        )
    }

    // Color Grading
    if (config.colorGrading !== 'none') {
        const cgFilter = getColorGradingFilter(config.colorGrading)
        if (cgFilter) vFilters.push(cgFilter)
    }

    // Glow/Bloom — dùng unsharp thay vì split/blend (split/blend cần filter_complex)
    if (config.glow) {
        vFilters.push(
            'eq=brightness=0.06:contrast=1.05',
            'unsharp=9:9:1.2:9:9:0.0'
        )
    }

    // Zoom Effect (Ken Burns)
    if (config.zoomEffect && config.zoomIntensity && config.zoomIntensity > 1.0) {
        const z = config.zoomIntensity.toFixed(3)
        vFilters.push(
            `zoompan=z='min(zoom+0.0005,${z})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=iw*2:ih*2:fps=30`,
            'scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos'
        )
    }

    // Border
    if (config.borderWidth && config.borderWidth > 0) {
        const bw = config.borderWidth
        const bc = config.borderColor || '#000000'
        vFilters.push(`pad=iw+${bw * 2}:ih+${bw * 2}:${bw}:${bw}:color=${bc}`)
        vFilters.push('scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,setsar=1')
    }

    // Frame Template (aspect ratio conversion)
    if (config.frameTemplate && config.frameTemplate !== 'none') {
        const dim = getFrameDimensions(config.frameTemplate)
        if (dim) {
            vFilters.push(
                `scale=${dim.w}:${dim.h}:force_original_aspect_ratio=decrease:flags=lanczos`,
                `pad=${dim.w}:${dim.h}:(ow-iw)/2:(oh-ih)/2:color=black`,
                'setsar=1'
            )
        }
    }

    // Pixel Enlarge
    if (config.pixelEnlarge) {
        vFilters.push(
            'scale=iw*2:ih*2:flags=neighbor',
            'scale=trunc(iw/4)*2:trunc(ih/4)*2:flags=lanczos'
        )
    }

    // RGB Drift
    if (config.rgbDrift) {
        vFilters.push('rgbashift=rh=1:rv=-1:gh=0:gv=0:bh=-1:bv=1')
    }

    // ChromaShuffle
    if (config.chromaShuffle) {
        vFilters.push(
            'colorchannelmixer=rr=0.98:rg=0.01:rb=0.01:gr=0.01:gg=0.98:gb=0.01:br=0.01:bg=0.01:bb=0.98'
        )
    }

    // Title Text overlay (drawtext)
    if (config.titleTemplate && config.titleTemplate !== 'none') {
        const esc = (t: string) => t
            .replace(/:/g, '\\:')
            .replace(/'/g, "\\'")
            .replace(/,/g, '\\,')
            .replace(/%/g, '%%')
        const fontPath = 'C\\:/Windows/Fonts/arialbd.ttf'

        if (config.titleText) {
            vFilters.push(
                `drawtext=fontfile='${fontPath}':text='${esc(config.titleText)}':x=(w-text_w)/2:y=200:fontsize=60:fontcolor=white:borderw=5:bordercolor=black`
            )
        }
        if (config.descText) {
            vFilters.push(
                `drawtext=fontfile='${fontPath}':text='${esc(config.descText)}':x=(w-text_w)/2:y=h-th-200:fontsize=48:fontcolor=white:borderw=4:bordercolor=black`
            )
        }
    }

    // Subtitle burn-in — FFmpeg subtitles filter path escaping:
    // Windows: C:\Users\... → replace \ with / → C:/Users/...
    // Escape ':' with '\:' → C\:/Users/... (FFmpeg hiểu \: = literal colon)
    // ĐÚNG: C\:/path  (single backslash trước colon = escaped colon trong FFmpeg)
    // SAI:  C\\:/path (double backslash = literal backslash + bare colon)
    if (config.srtPath) {
        const srtEscaped = config.srtPath
            .replace(/\\/g, '/')
            .replace(/:/g, '\\:')
            .replace(/'/g, "\\'")
            .replace(/\[/g, '\\[')
            .replace(/\]/g, '\\]')
        vFilters.push(`subtitles='${srtEscaped}'`)
    }

    // Always ensure yuv420p
    vFilters.push('format=yuv420p')

    // ─── AUDIO FILTERS ───

    // Speed Change
    if (config.speed !== 1.0) {
        vFilters.splice(vFilters.length - 1, 0, `setpts=PTS/${config.speed.toFixed(3)}`)
        aFilters.push(`atempo=${config.speed.toFixed(3)}`)
    }

    // Pitch Shift
    if (config.pitchShift) {
        aFilters.push('asetrate=44100*1.03,aresample=44100')
    }

    // Volume boost
    if (config.volumeBoost && config.volumeBoost !== 1.0) {
        aFilters.push(`volume=${config.volumeBoost.toFixed(1)}`)
    }

    // Audio Evade
    if (config.audioEvade) {
        aFilters.push('asetrate=44100*1.03,aresample=44100')
    }

    // ─── BUILD FINAL FILTER ───

    const vfStr = vFilters.join(',')
    let complexFilter = ''

    // Logo overlay needs complex filtergraph (2 inputs)
    if (hasLogo) {
        extraInputs.push(config.logoPath!)
        const pct = (config.logoSize || 12) / 100
        const pos = getLogoOverlayPos(config.logoPosition || 'bottom-right')
        // Complex filter: apply all vf to [0:v], scale logo, overlay → output [v]
        complexFilter = `[0:v]${vfStr}[base];[1:v]scale=iw*${pct.toFixed(2)}:-1:flags=lanczos,format=rgba[logo];[base][logo]overlay=${pos}[v]`
    }

    return {
        vf: hasLogo ? '' : vfStr,
        af: aFilters.length > 0 ? aFilters.join(',') : '',
        complexFilter,
        extraInputs,
    }
}

/**
 * Build H→V filter chain (landscape → portrait 1080x1920).
 */
export function buildHtoVFilter(): string {
    return 'scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
}
