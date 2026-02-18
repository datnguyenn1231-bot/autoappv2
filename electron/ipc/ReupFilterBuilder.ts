/**
 * ReupFilterBuilder.ts — Class chuyên nghiệp xây dựng FFmpeg filter chain.
 *
 * Nguyên tắc thiết kế:
 * 1. Mỗi filter được push riêng lẻ, KHÔNG join trước → tránh dấu phẩy thừa
 * 2. Mỗi filter PHẢI có tên đúng (eq=, colorbalance=, noise=...) → không bao giờ  
 *    bắt đầu bằng giá trị (VD: .98:gb=...)
 * 3. Logo overlay tách riêng filter_complex + extra input + -map
 * 4. Subtitle path Windows escape ĐÚNG: C\:/path (single backslash = escaped colon)
 * 5. Glow dùng unsharp (KHÔNG dùng split/blend — cần filter_complex)
 * 6. KHÔNG dùng -hwaccel_output_format nv12 (crash software filters)
 */

import type { ReupConfig } from './reup-filters.js'

// ─── Kết quả trả về cho FFmpeg command builder ───
export interface FilterResult {
    /** Chuỗi -vf (khi KHÔNG có logo) */
    vf: string
    /** Chuỗi -af */
    af: string
    /** Chuỗi -filter_complex (khi CÓ logo) */
    complexFilter: string
    /** File input thêm (logo path) → thêm -i cho mỗi file */
    extraInputs: string[]
    /** Cần -map khi dùng filter_complex */
    needsMapping: boolean
}

export class ReupFilterBuilder {
    private vFilters: string[] = []
    private aFilters: string[] = []
    private extraInputs: string[] = []
    private config: ReupConfig
    private hasLogo: boolean

    constructor(config: ReupConfig) {
        this.config = config
        this.hasLogo = !!(config.logoPath && config.logoPath.trim())
    }

    /** Build toàn bộ filter chain → trả về FilterResult */
    build(): FilterResult {
        // Reset
        this.vFilters = []
        this.aFilters = []
        this.extraInputs = []

        // ─── VIDEO FILTERS — THỨ TỰ CỰC KỲ QUAN TRỌNG ───
        // 1. Geometry changes (mirror, crop)
        this.addMirror()
        this.addSmartCrop()

        // 2. Pixel-level modifications (không thay đổi kích thước)
        this.addNoise()
        this.addRotate()
        this.addLensDistortion()

        // 3. Color modifications (không thay đổi kích thước)
        this.addHDR()
        this.addColorGrading()
        this.addGlow()

        // 4. Anti-detect pixel tricks (phải ĐẶT TRƯỚC frame template!)
        this.addPixelEnlarge()
        this.addRGBDrift()
        this.addChromaShuffle()

        // 5. Zoom effect (trước frame template để frame template set kích thước cuối)
        this.addZoomEffect()

        // 6. Frame Template (scale về kích thước target, VD: 1080x1920)
        //    PHẢI ĐẶT SAU tất cả filter thay đổi pixel, TRƯỚC border
        this.addFrameTemplate()

        // 7. Border (viền — thêm padding SAU khi đã scale về target size)
        this.addBorder()

        // 8. Overlays (text/sub — đặt sau khi kích thước đã cố định)
        this.addTitle()
        this.addSubtitle()

        // ─── SPEED (phải đặt trước format=yuv420p) ───
        this.addSpeed()

        // ─── Luôn kết thúc bằng format=yuv420p ───
        this.vFilters.push('format=yuv420p')

        // ─── AUDIO FILTERS ───
        this.addPitchShift()
        this.addVolumeBoost()
        this.addAudioEvade()

        // ─── BUILD FINAL RESULT ───
        return this.buildResult()
    }

    // ═══════════════════════════════════════════════════════════
    //  VIDEO FILTER METHODS
    // ═══════════════════════════════════════════════════════════

    /** L1: Mirror (lật ngang) */
    private addMirror(): void {
        if (this.config.mirror) {
            this.vFilters.push('hflip')
        }
    }

    /** L2: Smart Crop (cắt viền + scale chẵn pixel) */
    private addSmartCrop(): void {
        if (this.config.crop > 0) {
            const keep = 1 - this.config.crop
            this.vFilters.push(
                `crop=iw*${keep.toFixed(3)}:ih*${keep.toFixed(3)}:(iw-ow)/2:(ih-oh)/2`
            )
            this.vFilters.push(
                'scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos'
            )
            this.vFilters.push('setsar=1')
        }
    }

    /** L3: Noise/Grain (nhiễu film) */
    private addNoise(): void {
        if (this.config.noise) {
            const intensity = typeof this.config.noise === 'number' ? this.config.noise : 10
            this.vFilters.push(`noise=alls=${intensity}:allf=t+u`)
        }
    }

    /** L4: Subtle Rotate (xoay nhẹ) */
    private addRotate(): void {
        if (this.config.rotate) {
            const deg = typeof this.config.rotate === 'number' ? this.config.rotate : 2
            const rad = (deg * Math.PI / 180).toFixed(4)
            this.vFilters.push(`rotate=${rad}:c=none`)
        }
    }

    /** L5: Lens Distortion (méo ống kính nhẹ) */
    private addLensDistortion(): void {
        if (this.config.lensDistortion) {
            this.vFilters.push('lenscorrection=cx=0.5:cy=0.5:k1=-0.05:k2=-0.03')
        }
    }

    /** L6: HDR Enhancement (tăng contrast + sharpness) */
    private addHDR(): void {
        if (this.config.hdr) {
            this.vFilters.push('eq=contrast=1.10:saturation=1.10:brightness=0.010')
            this.vFilters.push('unsharp=5:5:0.9:3:3:0.5')
        }
    }

    /**
     * L7: Color Grading — MỖI filter LUÔN có tên đầy đủ.
     * KHÔNG BAO GIỜ push chuỗi bắt đầu bằng giá trị (VD: .98:gb=...)
     */
    private addColorGrading(): void {
        const style = this.config.colorGrading
        if (!style || style === 'none') return

        // Push TỪNG filter RIÊNG LẺ — tránh join(,) tạo chuỗi dài dễ bị cắt/thiếu tên
        switch (style) {
            case 'vibrant':
                this.vFilters.push('eq=brightness=0.15:contrast=1.08:saturation=1.22')
                this.vFilters.push('vibrance=intensity=0.15')
                this.vFilters.push('unsharp=5:5:0.8:5:5:0.0')
                this.vFilters.push("curves=all='0/0 0.5/0.55 1/1'")
                break
            case 'bw':
                this.vFilters.push('hue=s=0')
                this.vFilters.push('eq=contrast=1.20:brightness=0.05')
                this.vFilters.push('unsharp=7:7:1.2:7:7:0.0')
                this.vFilters.push("curves=all='0/0.05 0.5/0.5 1/0.95'")
                this.vFilters.push('noise=alls=2:allf=t')
                break
            case 'sepia':
                this.vFilters.push('colortemperature=temperature=8000')
                this.vFilters.push('eq=brightness=0.08:contrast=1.05:saturation=0.95:gamma=1.1')
                this.vFilters.push("curves=red='0/0.05 1/1':blue='0/0 1/0.92'")
                this.vFilters.push('colorbalance=rs=0.05:gs=0:bs=-0.08')
                this.vFilters.push('vignette=angle=PI/4:a=0.3')
                break
            case 'cool_blue':
                this.vFilters.push('eq=saturation=1.05:gamma_b=1.10:gamma_r=0.92')
                this.vFilters.push("curves=blue='0/0.03 1/1':red='0/0 1/0.95'")
                this.vFilters.push('colorbalance=bs=0.05:rs=-0.03')
                break
        }
    }

    /** L8: Glow/Bloom — dùng eq+unsharp (KHÔNG dùng split/blend) */
    private addGlow(): void {
        if (this.config.glow) {
            this.vFilters.push('eq=brightness=0.06:contrast=1.05')
            this.vFilters.push('unsharp=9:9:1.2:9:9:0.0')
        }
    }

    /** L9: Zoom Effect (Ken Burns) */
    private addZoomEffect(): void {
        const z = this.config.zoomIntensity
        if (this.config.zoomEffect && z && z > 1.0) {
            this.vFilters.push(
                `zoompan=z='min(zoom+0.0005,${z.toFixed(3)})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:fps=30`
            )
            this.vFilters.push('scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos')
        }
    }

    /** L10: Border (viền đen/màu) */
    private addBorder(): void {
        const bw = this.config.borderWidth
        if (bw && bw > 0) {
            const bc = this.config.borderColor || '#000000'
            this.vFilters.push(`pad=iw+${bw * 2}:ih+${bw * 2}:${bw}:${bw}:color=${bc}`)
            this.vFilters.push('scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos')
            this.vFilters.push('setsar=1')
        }
    }

    /** L11: Frame Template (đổi tỷ lệ khung hình) */
    private addFrameTemplate(): void {
        const tpl = this.config.frameTemplate
        if (!tpl || tpl === 'none') return

        const dimMap: Record<string, { w: number; h: number }> = {
            '9:16': { w: 1080, h: 1920 },
            '1:1': { w: 1080, h: 1080 },
            '4:3': { w: 1440, h: 1080 },
            '3:4': { w: 1080, h: 1440 },
            '16:9': { w: 1920, h: 1080 },
        }
        const dim = dimMap[tpl]
        if (dim) {
            this.vFilters.push(
                `scale=${dim.w}:${dim.h}:force_original_aspect_ratio=decrease:flags=lanczos`
            )
            this.vFilters.push(`pad=${dim.w}:${dim.h}:(ow-iw)/2:(oh-ih)/2:color=black`)
            this.vFilters.push('setsar=1')
        }
    }

    /** L12: Pixel Enlarge (phóng to pixel → thu nhỏ lại) */
    private addPixelEnlarge(): void {
        if (this.config.pixelEnlarge) {
            this.vFilters.push('scale=iw*2:ih*2:flags=neighbor')
            this.vFilters.push('scale=trunc(iw/4)*2:trunc(ih/4)*2:flags=lanczos')
        }
    }

    /** L13: RGB Drift (dịch kênh màu) */
    private addRGBDrift(): void {
        if (this.config.rgbDrift) {
            this.vFilters.push('rgbashift=rh=1:rv=-1:gh=0:gv=0:bh=-1:bv=1')
        }
    }

    /** L14: ChromaShuffle (xáo trộn kênh màu nhẹ — anti-detect) */
    private addChromaShuffle(): void {
        if (this.config.chromaShuffle) {
            // QUAN TRỌNG: phải push đầy đủ tên filter colorchannelmixer=
            this.vFilters.push(
                'colorchannelmixer=rr=0.98:rg=0.01:rb=0.01:gr=0.01:gg=0.98:gb=0.01:br=0.01:bg=0.01:bb=0.98'
            )
        }
    }

    /** L15: Title Overlay (drawtext) */
    private addTitle(): void {
        const tpl = this.config.titleTemplate
        if (!tpl || tpl === 'none') return

        // Escape text cho FFmpeg drawtext
        const esc = (t: string) => t
            .replace(/:/g, '\\:')
            .replace(/'/g, "\\'")
            .replace(/,/g, '\\,')
            .replace(/%/g, '%%')

        // Font path Windows — escape colon cho FFmpeg filter syntax
        const fontPath = 'C\\:/Windows/Fonts/arialbd.ttf'

        if (this.config.titleText) {
            this.vFilters.push(
                `drawtext=fontfile='${fontPath}':text='${esc(this.config.titleText)}':` +
                `x=(w-text_w)/2:y=200:fontsize=60:fontcolor=white:borderw=5:bordercolor=black`
            )
        }
        if (this.config.descText) {
            this.vFilters.push(
                `drawtext=fontfile='${fontPath}':text='${esc(this.config.descText)}':` +
                `x=(w-text_w)/2:y=h-th-200:fontsize=48:fontcolor=white:borderw=4:bordercolor=black`
            )
        }
    }

    /**
     * L16: Subtitle burn-in.
     * QUAN TRỌNG: Windows path escaping cho FFmpeg subtitles filter:
     *   C:\Users\... → C:/Users/... → C\:/Users/...
     *   \: = escaped colon = FFmpeg hiểu là literal ':'
     *   ĐÚNG: C\:/path  (single backslash)
     *   SAI:  C\\:/path (double backslash = escaped backslash + bare colon)
     */
    private addSubtitle(): void {
        if (!this.config.srtPath) return

        const escaped = this.config.srtPath
            .replace(/\\/g, '/')        // backslash → forward slash
            .replace(/:/g, '\\:')       // escape colon cho FFmpeg filter
            .replace(/'/g, "\\'")       // escape quote
            .replace(/\[/g, '\\[')      // escape brackets
            .replace(/\]/g, '\\]')

        this.vFilters.push(`subtitles='${escaped}'`)
    }

    // ═══════════════════════════════════════════════════════════
    //  SPEED & AUDIO FILTERS
    // ═══════════════════════════════════════════════════════════

    /** Speed change — video setpts + audio atempo */
    private addSpeed(): void {
        if (this.config.speed !== 1.0) {
            this.vFilters.push(`setpts=PTS/${this.config.speed.toFixed(3)}`)
            this.aFilters.push(`atempo=${this.config.speed.toFixed(3)}`)
        }
    }

    /** Pitch Shift (đổi cao độ nhẹ — anti-detect audio) */
    private addPitchShift(): void {
        if (this.config.pitchShift) {
            this.aFilters.push('asetrate=44100*1.03,aresample=44100')
        }
    }

    /** Volume Boost */
    private addVolumeBoost(): void {
        if (this.config.volumeBoost && this.config.volumeBoost !== 1.0) {
            this.aFilters.push(`volume=${this.config.volumeBoost.toFixed(1)}`)
        }
    }

    /** Audio Evade (thay đổi tần số nhẹ — anti-detect audio) */
    private addAudioEvade(): void {
        if (this.config.audioEvade) {
            this.aFilters.push('asetrate=44100*1.03,aresample=44100')
        }
    }

    // ═══════════════════════════════════════════════════════════
    //  BUILD FINAL RESULT
    // ═══════════════════════════════════════════════════════════

    private buildResult(): FilterResult {
        // Lọc bỏ filter rỗng và join bằng dấu phẩy
        const cleanFilters = this.vFilters.filter(f => f.trim().length > 0)
        const vfStr = cleanFilters.join(',')

        let complexFilter = ''
        let needsMapping = false

        if (this.hasLogo) {
            // Logo cần filter_complex: 2 inputs, overlay, output [v]
            this.extraInputs.push(this.config.logoPath!)
            const pct = (this.config.logoSize || 12) / 100
            const pos = this.getLogoOverlayPos()
            // [0:v] → tất cả video filters → [base]
            // [1:v] → scale logo → [logo]
            // overlay → [v] (output label cho -map)
            complexFilter = [
                `[0:v]${vfStr}[base]`,
                `[1:v]scale=iw*${pct.toFixed(2)}:-1:flags=lanczos,format=rgba[logo]`,
                `[base][logo]overlay=${pos}[v]`
            ].join(';')
            needsMapping = true
        }

        return {
            vf: this.hasLogo ? '' : vfStr,
            af: this.aFilters.filter(f => f.trim().length > 0).join(','),
            complexFilter,
            extraInputs: this.extraInputs,
            needsMapping,
        }
    }

    /** Logo position → FFmpeg overlay coordinates */
    private getLogoOverlayPos(): string {
        const pos = this.config.logoPosition || 'bottom-right'
        const map: Record<string, string> = {
            'top-left': 'x=20:y=20',
            'top-right': 'x=W-w-20:y=20',
            'bottom-left': 'x=20:y=H-h-20',
            'bottom-right': 'x=W-w-20:y=H-h-20',
            'auto': 'x=W-w-20:y=H-h-20',
        }
        return map[pos] || map['bottom-right']
    }

    // ═══════════════════════════════════════════════════════════
    //  STATIC HELPERS
    // ═══════════════════════════════════════════════════════════

    /** Debug: in ra filter chain để kiểm tra */
    static debugPrint(result: FilterResult): void {
        console.log('═══ ReupFilterBuilder Debug ═══')
        if (result.complexFilter) {
            console.log('Mode: filter_complex (có logo)')
            console.log('  filter_complex:', result.complexFilter)
            console.log('  extraInputs:', result.extraInputs)
            console.log('  needsMapping:', result.needsMapping)
        } else {
            console.log('Mode: simple -vf')
            console.log('  vf:', result.vf)
        }
        if (result.af) console.log('  af:', result.af)
        console.log('═══════════════════════════════')
    }
}

/**
 * Build FFmpeg filter chain — wrapper tương thích ngược.
 * Dùng class ReupFilterBuilder bên trong.
 */
export function buildFilterChain(config: ReupConfig): FilterResult {
    const builder = new ReupFilterBuilder(config)
    return builder.build()
}

/** Build H→V filter chain (landscape → portrait 1080x1920) */
export function buildHtoVFilter(): string {
    return 'scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'
}
