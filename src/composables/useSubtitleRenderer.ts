/**
 * useSubtitleRenderer — Computed properties for subtitle overlay rendering.
 * Handles karaoke words, typewriter effect, word-pop groups, style maps,
 * position classes, and animation selection.
 * Extracted from VideoPreview.vue to enforce ≤300 lines/file.
 */

import { computed, type Ref } from 'vue'

interface SubSegment {
    start: number
    end: number
    text: string
}

interface SubtitleProps {
    subtitles: SubSegment[]
    subtitleStyle: string
    subtitleSize: number
    subtitleAnimation: string
    subtitlePosition: string
    subtitleOffsetX: number
    subtitleOffsetY: number
}

const WORD_POP_COLORS = ['#FFD700', '#00E5FF', '#FF4081', '#76FF03', '#FF9100', '#448AFF', '#FF1744', '#E040FB']

export function useSubtitleRenderer(currentTime: Ref<number>, props: SubtitleProps) {

    // ── Current active segment ──
    const currentSegment = computed(() => {
        if (!props.subtitles || props.subtitles.length === 0) return null
        const t = currentTime.value
        return props.subtitles.find(s => t >= s.start && t <= s.end) || null
    })

    const currentSubtitle = computed(() => {
        return currentSegment.value ? currentSegment.value.text : ''
    })

    // ── Karaoke: split text into words with estimated per-word timing ──
    const karaokeWords = computed(() => {
        const seg = currentSegment.value
        if (!seg) return []
        const words = seg.text.split(/\s+/).filter(w => w.length > 0)
        if (words.length === 0) return []
        const segDuration = seg.end - seg.start
        const wordDuration = segDuration / words.length
        return words.map((word, i) => ({
            word,
            start: seg.start + i * wordDuration,
            end: seg.start + (i + 1) * wordDuration,
        }))
    })

    // ── Typewriter: reveal characters progressively ──
    const typewriterText = computed(() => {
        const seg = currentSegment.value
        if (!seg) return ''
        const text = seg.text
        const elapsed = currentTime.value - seg.start
        const segDuration = seg.end - seg.start
        if (segDuration <= 0) return text
        const progress = Math.min(elapsed / (segDuration * 0.7), 1) // finish 70% into segment
        const chars = Math.ceil(progress * text.length)
        return text.substring(0, chars)
    })

    // ── Dynamic Caption: random-sized word groups with colors ──
    const wordPopGroups = computed(() => {
        const seg = currentSegment.value
        if (!seg) return []
        const words = seg.text.split(/\s+/).filter(w => w.length > 0)
        if (words.length === 0) return []

        // Deterministic seed from text
        let seed = 0
        for (let i = 0; i < seg.text.length; i++) seed = ((seed << 5) - seed + seg.text.charCodeAt(i)) | 0
        const rand = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return (seed % 100) / 100 }

        // Group words into random chunks of 1-4, random colors
        const groups: Array<{ text: string; color: string; start: number; wordIndex: number }> = []
        let idx = 0
        let lastColorIdx = -1
        while (idx < words.length) {
            const remaining = words.length - idx
            const size = remaining <= 2 ? remaining : Math.max(1, Math.min(4, Math.floor(rand() * 4) + 1))
            const chunk = words.slice(idx, idx + size).join(' ')
            // Random color, avoid same as previous
            let ci = Math.floor(rand() * WORD_POP_COLORS.length)
            if (ci === lastColorIdx) ci = (ci + 1) % WORD_POP_COLORS.length
            lastColorIdx = ci
            groups.push({ text: chunk, color: WORD_POP_COLORS[ci], start: 0, wordIndex: idx })
            idx += size
        }

        // Assign timing — each group gets equal share of 80% of segment duration
        const segDuration = seg.end - seg.start
        const activeTime = segDuration * 0.8
        const groupInterval = groups.length > 1 ? activeTime / groups.length : activeTime
        groups.forEach((g, i) => {
            g.start = seg.start + i * groupInterval
        })
        return groups
    })

    // Current active word pop group (only ONE at a time)
    const currentWordPopGroup = computed(() => {
        const groups = wordPopGroups.value
        if (!groups.length) return null
        const t = currentTime.value
        let active: typeof groups[0] | null = null
        for (let i = groups.length - 1; i >= 0; i--) {
            if (t >= groups[i].start) { active = groups[i]; break }
        }
        return active
    })

    // ── Position CSS class ──
    const positionClass = computed(() => {
        const map: Record<string, string> = {
            top: 'vp-sub-pos-top',
            center: 'vp-sub-pos-center',
            bottom: '', // default
        }
        return map[props.subtitlePosition ?? 'bottom'] || ''
    })

    // Effective animation: auto-force word_pop when dynamic_caption style
    const effectiveAnimation = computed(() => {
        if (props.subtitleStyle === 'dynamic_caption') return 'word_pop'
        return props.subtitleAnimation
    })

    // Subtitle offset for drag-to-reposition
    const subOverlayStyle = computed(() => ({
        transform: `translate(${props.subtitleOffsetX ?? 0}px, ${props.subtitleOffsetY ?? 0}px)`,
    }))

    // Animation CSS class name
    const animClass = computed(() => {
        const map: Record<string, string> = {
            fade: 'vp-sub-anim-fade',
            pop: 'vp-sub-anim-pop',
            slide_up: 'vp-sub-anim-slide-up',
            bounce: 'vp-sub-anim-bounce',
        }
        return map[props.subtitleAnimation] || ''
    })

    // ── Style CSS map ──
    const subtitleCss = computed((): Record<string, string> => {
        const styleMap: Record<string, Record<string, string>> = {
            bold_center: {
                fontFamily: '"Montserrat", "Arial Black", sans-serif',
                fontWeight: '900',
                color: '#ffffff',
                textShadow: '2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0 3px 6px rgba(0,0,0,0.6)',
                textTransform: 'uppercase',
            },
            karaoke: {
                fontFamily: '"Poppins", "Segoe UI", sans-serif',
                fontWeight: '700',
                color: '#FFD700',
                textShadow: '2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0 0 12px rgba(255,215,0,0.4)',
            },
            thin_minimal: {
                fontFamily: '"Poppins", "Helvetica Neue", sans-serif',
                fontWeight: '600',
                color: 'rgba(255,255,255,0.95)',
                textShadow: '1px 1px 0 #000, -1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000',
            },
            neon_glow: {
                fontFamily: '"Bangers", "Luckiest Guy", cursive',
                fontWeight: '400',
                color: '#00ffcc',
                textShadow: '0 0 10px #00ffcc, 0 0 20px #00ffcc, 0 0 40px #00997a, 2px 2px 0 #000, -2px -2px 0 #000',
                letterSpacing: '2px',
            },
            dynamic_caption: {
                fontFamily: '"Montserrat", "Arial Black", sans-serif',
                fontWeight: '900',
                color: '#ffffff',
                textShadow: '3px 3px 0 #000, -3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 0 4px 8px rgba(0,0,0,0.6)',
                textTransform: 'uppercase',
            },
        }
        const base = styleMap[props.subtitleStyle] || styleMap.bold_center
        return { ...base, fontSize: props.subtitleSize + 'px' }
    })

    return {
        currentSegment, currentSubtitle,
        karaokeWords, typewriterText,
        wordPopGroups, currentWordPopGroup,
        positionClass, effectiveAnimation,
        subOverlayStyle, animClass, subtitleCss,
    }
}
