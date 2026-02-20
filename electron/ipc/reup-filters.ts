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
    needsMapping: boolean
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

    // L5: Lens Distortion — CSS preview: perspective(500px) rotateY(2deg) → rất rõ
    // FFmpeg: tăng k1/k2 để visible (k1=-0.18 barrel distortion rõ, k2=-0.08 pincushion)
    if (config.lensDistortion) {
        vFilters.push('lenscorrection=cx=0.5:cy=0.5:k1=-0.18:k2=-0.08')
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

    // Glow/Bloom — tăng cường cho match CSS preview (drop-shadow(0 0 8px rgba(255,200,100,0.35)))
    if (config.glow) {
        vFilters.push(
            'eq=brightness=0.10:contrast=1.08',
            'unsharp=13:13:1.8:13:13:0.0'
        )
    }
    // Zoom Effect — crop center mạnh hơn (CSS preview: scale animation rất rõ)
    if (config.zoomEffect && config.zoomIntensity && config.zoomIntensity > 1.0) {
        // Tăng cropRatio mạnh hơn gấp 1.3x để match CSS preview
        const boostedZoom = config.zoomIntensity * 1.3
        const cropRatio = (1 / boostedZoom).toFixed(4)
        vFilters.push(
            `crop=iw*${cropRatio}:ih*${cropRatio}:(iw-ow)/2:(ih-oh)/2`
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

    // Pixel Enlarge — scale 3x neighbor rồi scale lại (CSS preview: blur(0.4px) contrast(1.12))
    if (config.pixelEnlarge) {
        vFilters.push(
            'scale=iw*3:ih*3:flags=neighbor',
            'scale=trunc(iw/6)*2:trunc(ih/6)*2:flags=lanczos'
        )
    }

    // RGB Drift — CSS preview: drop-shadow(3px 0 rgb(255,0,0,0.5)) → 3px offset rõ ràng
    if (config.rgbDrift) {
        vFilters.push('rgbashift=rh=3:rv=-2:gh=0:gv=0:bh=-3:bv=2')
    }

    // ChromaShuffle — CSS preview: hue-rotate(12deg) saturate(1.25) → rõ ràng hơn
    if (config.chromaShuffle) {
        vFilters.push(
            'colorchannelmixer=rr=0.90:rg=0.06:rb=0.04:gr=0.04:gg=0.90:gb=0.06:br=0.06:bg=0.04:bb=0.90',
            'eq=saturation=1.25'
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
        needsMapping: hasLogo,
    }
}

/**
 * Build H→V filter chain (landscape → portrait 1080x1920).
 */
export function buildHtoVFilter(): string {
    return 'scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
}
