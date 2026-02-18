<script setup lang="ts">
/**
 * ReupView — Video Reup main view.
 * 3-column: Left Toolbar | Center Preview (live CSS) | Right Settings
 *
 * Top bar: Ratio dropdown + Music picker + HDR toggle
 * Toolbar: AutoReup | Cut | Music
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import {
  Repeat, Music, Sun, Settings2, Loader2, X, MonitorSmartphone, ChevronDown,
  Frame, Type, Sparkles, Image, Download,
} from 'lucide-vue-next'
import { useEditor } from '../composables/useEditor'
import { useReupPreview } from '../composables/useReupPreview'
import {
  REUP_DEFAULTS, FRAME_TEMPLATE_OPTIONS, TITLE_TEMPLATE_OPTIONS, SUB_ANIMATION_OPTIONS, SUB_POSITION_OPTIONS,
  type ColorGradingStyle, type FrameTemplate, type TitleTemplate,
  type SplitMode, type LogoPosition, type ReupPresetValues,
} from '../constants/reup-constants'

const LOGO_POSITIONS: { value: LogoPosition; label: string }[] = [
  { value: 'top-left', label: '↖ Top Left' },
  { value: 'top-right', label: '↗ Top Right' },
  { value: 'bottom-left', label: '↙ Bottom Left' },
  { value: 'bottom-right', label: '↘ Bottom Right' },
]

const TEXT_FONTS = [
  'Dancing Script', 'Pacifico', 'Lobster', 'Sigmar One', 'Bungee Shade',
  'Patrick Hand', 'Dela Gothic One', 'Fugaz One', 'Luckiest Guy', 'Bangers',
]
import VideoPreview from '../components/editor/VideoPreview.vue'
import ReupToolbar from '../components/reup/ReupToolbar.vue'
import ReupDropzone from '../components/reup/ReupDropzone.vue'
import ReupPanel from '../components/reup/ReupPanel.vue'
import SplitPanel from '../components/reup/SplitPanel.vue'
import { useReupSubtitle } from '../composables/useReupSubtitle'

// ── Editor (video preview) ──
const {
  videoUrl, metadata, hasVideo, isLoading, error, isPlaying, volume,
  loadVideo, closeVideo,
} = useEditor()

// ── Toolbar ──
type ReupFeature = 'auto' | 'music'
const activeFeature = ref<ReupFeature>('auto')
const toolbarItems: { id: ReupFeature; label: string; icon: any }[] = [
  { id: 'auto',  label: 'AutoReup', icon: Repeat },
  { id: 'music', label: 'Music',    icon: Music },
]
const showSplit = ref(false)

// ── Filter State ──
const mirror = ref(REUP_DEFAULTS.mirror)
const crop = ref(REUP_DEFAULTS.crop)
const noise = ref(REUP_DEFAULTS.noise)
const rotate = ref(REUP_DEFAULTS.rotate)
const lensDistortion = ref(REUP_DEFAULTS.lensDistortion)
const speed = ref(REUP_DEFAULTS.speed)
const audioEvade = ref(REUP_DEFAULTS.audioEvade)
const applyHDR = ref(false)
const colorGrading = ref<ColorGradingStyle>(REUP_DEFAULTS.colorGrading)
const glow = ref(REUP_DEFAULTS.glow)
const volumeBoost = ref(REUP_DEFAULTS.volumeBoost)
const frameTemplate = ref<FrameTemplate>(REUP_DEFAULTS.frameTemplate)
const titleTemplate = ref<TitleTemplate>(REUP_DEFAULTS.titleTemplate)
const titleText = ref(REUP_DEFAULTS.titleText)
const descText = ref(REUP_DEFAULTS.descText)
const titleOffsetX = ref(0)  // Title X offset (px) — draggable
const titleOffsetY = ref(0)  // Title Y offset (px) — draggable
const descOffsetX = ref(0)   // Desc X offset (px) — draggable independently
const descOffsetY = ref(0)   // Desc Y offset (px) — draggable independently
const titleFontSize = ref(24) // Title font size (px)
const descFontSize = ref(14)  // Desc font size (px)
const textFont = ref('Inter') // Title font family
const descFont = ref('Inter') // Description font family
const textColor = ref('#ffffff') // Text color
const autoTitle = ref(false) // Auto-fill title from video filename
const currentVideoPath = ref('') // Track current video file path
const splitMode = ref<SplitMode>('none')

// New features
const borderWidth = ref(REUP_DEFAULTS.borderWidth)
const borderColor = ref(REUP_DEFAULTS.borderColor)
const zoomEffect = ref(REUP_DEFAULTS.zoomEffect)
const zoomIntensity = ref(REUP_DEFAULTS.zoomIntensity)
const logoPath = ref(REUP_DEFAULTS.logoPath)
const logoPosition = ref<LogoPosition>(REUP_DEFAULTS.logoPosition)
const logoSize = ref(REUP_DEFAULTS.logoSize)
// Pixel-level anti-detect (from Chế Độ 1)
const pixelEnlarge = ref(REUP_DEFAULTS.pixelEnlarge)
const chromaShuffle = ref(REUP_DEFAULTS.chromaShuffle)
const rgbDrift = ref(REUP_DEFAULTS.rgbDrift)

// Enhance — visual overlay features
const overlayPath = ref('')       // Overlay folder path
const overlayOpacity = ref(60)    // 0-100 opacity
const overlayFiles = ref<string[]>([])  // scanned overlay files from folder
const overlayBlink = ref(false)   // Auto blink on/off
const overlayBlinkSpeed = ref(0.5) // Blink interval in seconds
const overlayVisible = ref(true)  // Current blink state (true=show, false=hide)
let overlayBlinkTimer: ReturnType<typeof setInterval> | null = null
const bgBlur = ref(false)        // Background mờ đằng sau
const bgBlurAmount = ref(40)     // Blur intensity (px) 5-80
const bgVideoRef = ref<HTMLVideoElement | null>(null)
const overlayVideoRef = ref<HTMLVideoElement | null>(null)

// Overlay blink timer logic
watch([overlayBlink, overlayBlinkSpeed], ([blink, speed]) => {
  if (overlayBlinkTimer) { clearInterval(overlayBlinkTimer); overlayBlinkTimer = null }
  overlayVisible.value = true
  if (blink) {
    overlayBlinkTimer = setInterval(() => {
      overlayVisible.value = !overlayVisible.value
    }, (speed as number) * 1000)
  }
}, { immediate: true })

// Reframe — Scale X/Y/Z + Position
const videoZoom = ref(100)       // Z: 50–300 (%) uniform zoom
const videoScaleX = ref(100)     // X: 50–200 (%) stretch width
const videoScaleY = ref(100)     // Y: 50–200 (%) stretch height
const syncScale = ref(true)      // đồng bộ: lock X/Y together
const reframeEditMode = ref(false) // drag-to-pan mode

// Position (via drag)
const videoPosX = ref(0)         // translate X (px)
const videoPosY = ref(0)         // translate Y (px)

// Drag-to-pan state
const isDragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartPosX = 0
let dragStartPosY = 0

function onReframeDragStart(e: MouseEvent) {
  if (!reframeEditMode.value) return
  isDragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartPosX = videoPosX.value
  dragStartPosY = videoPosY.value
  e.preventDefault()
}
function onReframeDragMove(e: MouseEvent) {
  if (!isDragging.value) return
  const totalScaleX = (videoZoom.value / 100) * (videoScaleX.value / 100)
  const totalScaleY = (videoZoom.value / 100) * (videoScaleY.value / 100)
  videoPosX.value = Math.round(dragStartPosX + (e.clientX - dragStartX) / totalScaleX)
  videoPosY.value = Math.round(dragStartPosY + (e.clientY - dragStartY) / totalScaleY)
}
function onReframeDragEnd() {
  isDragging.value = false
}

// ── Title drag-to-reposition ──
function onTitleDragStart(e: MouseEvent) {
  const startX = e.clientX
  const startY = e.clientY
  const startOX = titleOffsetX.value
  const startOY = titleOffsetY.value
  const onMove = (ev: MouseEvent) => {
    titleOffsetX.value = Math.round(startOX + ev.clientX - startX)
    titleOffsetY.value = Math.round(startOY + ev.clientY - startY)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ── Desc drag-to-reposition (independent from title) ──
function onDescDragStart(e: MouseEvent) {
  const startX = e.clientX
  const startY = e.clientY
  const startOX = descOffsetX.value
  const startOY = descOffsetY.value
  const onMove = (ev: MouseEvent) => {
    descOffsetX.value = Math.round(startOX + ev.clientX - startX)
    descOffsetY.value = Math.round(startOY + ev.clientY - startY)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ── Sub drag-to-reposition ──
function onSubDragStart(e: MouseEvent) {
  if (!subEditMode.value) return
  const startX = e.clientX
  const startY = e.clientY
  const startOX = subOffsetX.value
  const startOY = subOffsetY.value
  const onMove = (ev: MouseEvent) => {
    subOffsetX.value = Math.round(startOX + ev.clientX - startX)
    subOffsetY.value = Math.round(startOY + ev.clientY - startY)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// Sync X/Y when đồng bộ is on
watch(videoScaleX, (val) => {
  if (syncScale.value) videoScaleY.value = val
})
watch(videoScaleY, (val) => {
  if (syncScale.value) videoScaleX.value = val
})

// ── Ratio Dropdown ──
const showRatioDropdown = ref(false)
const ratioLabel = computed(() => {
  if (frameTemplate.value === 'none') return 'Ratio'
  const opt = FRAME_TEMPLATE_OPTIONS.find(o => o.value === frameTemplate.value)
  return opt ? opt.label : frameTemplate.value
})
function selectRatio(val: FrameTemplate) {
  frameTemplate.value = val
  showRatioDropdown.value = false
}
function closeDropdown(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (!target.closest('.ru-ratio-wrapper')) {
    showRatioDropdown.value = false
  }
}
onMounted(() => document.addEventListener('click', closeDropdown))
onUnmounted(() => document.removeEventListener('click', closeDropdown))

// ── Live Preview CSS ──
const {
  previewTransform, previewFilter, previewPlaybackRate,
  previewRatioClass, previewBorderStyle, previewZoomClass, previewMirrorClass, previewPixelClass,
  previewLogoInfo, previewCropZoom, activeFilterCount,
} = useReupPreview({
  mirror, crop, noise, rotate, lensDistortion, applyHDR, speed, audioEvade,
  colorGrading, glow, volumeBoost, frameTemplate, titleTemplate, titleText, descText, splitMode,
  borderWidth, borderColor, zoomEffect, zoomIntensity,
  pixelEnlarge, chromaShuffle, rgbDrift,
  logoPath, logoPosition, logoSize,
})

// ── Music ──
const musicPath = ref('')
const musicFileName = computed(() => {
  if (!musicPath.value) return ''
  return musicPath.value.split('\\').pop() || musicPath.value.split('/').pop() || ''
})
async function pickMusic() {
  const files = await window.electronAPI.selectFiles({
    title: 'Select Music',
    filters: [{ name: 'Audio', extensions: ['mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg'] }],
  })
  if (files?.length) musicPath.value = files[0]
}
function clearMusic() { musicPath.value = '' }

// ── Toggle refs for center column sections ──
const showFrame = ref(false)
const showText = ref(false)
const showEnhance = ref(false)
const showReframe = ref(true)  // open by default

// ── SUB (Subtitle) — extracted to composable ──
const {
  SUB_LANGUAGES,
  showSub, subLang, subRunning, subProgress, subStatus,
  subSegments, subSrtPath, subDetectedLang, subError,
  subEngine, subLogs, showSubLog,
  subStyle, subFontSize, subAnimation, subPosition,
  subOffsetX, subOffsetY, subEditMode,
  formatSubTime, startSubTranscribe: _startSub, stopSubTranscribe, exportSrt: _exportSrt,
} = useReupSubtitle()

// Wrappers pass currentVideoPath to composable
async function startSubTranscribe() { await _startSub(currentVideoPath.value) }
async function exportSrt() { await _exportSrt(currentVideoPath.value) }


// ── Video handlers ──
async function onLoadVideo(filePath: string) {
  currentVideoPath.value = filePath
  await loadVideo(filePath)
}

// Auto-fill titleText from video filename
function getFilenameTitle(fp: string): string {
  const name = fp.split('\\').pop()?.split('/').pop() || ''
  return name.replace(/\.[^.]+$/, '') // Remove extension
}
watch(autoTitle, (on) => {
  if (on && currentVideoPath.value) {
    titleText.value = getFilenameTitle(currentVideoPath.value)
  }
})
watch(currentVideoPath, (fp) => {
  if (autoTitle.value && fp) {
    titleText.value = getFilenameTitle(fp)
  }
})
function onTimeUpdate(t: number) {
  // Sync background blur video time
  const bg = bgVideoRef.value
  if (bg && Math.abs(bg.currentTime - t) > 0.3) {
    bg.currentTime = t
  }
  // Sync overlay video time
  const ov = overlayVideoRef.value
  if (ov && Math.abs(ov.currentTime - t) > 0.3) {
    ov.currentTime = t
  }
}
function onDurationChange(_d: number) {}

// Sync bg video play/pause with main
watch(isPlaying, (playing) => {
  const bg = bgVideoRef.value
  if (!bg) return
  if (playing) bg.play().catch(() => {})
  else bg.pause()
})

// When bgBlur toggled ON, sync the bg video to current playback state
watch(bgBlur, async (enabled) => {
  if (!enabled) return
  await nextTick()  // wait for <video> to mount
  const bg = bgVideoRef.value
  if (!bg) return
  // Sync time with main video
  const mainVideo = document.querySelector('.vp-video') as HTMLVideoElement | null
  if (mainVideo) {
    bg.currentTime = mainVideo.currentTime
  }
  // Start playing if main is playing
  if (isPlaying.value) {
    bg.play().catch(() => {})
  }
})




// Sync overlay video play/pause
watch(isPlaying, (playing) => {
  const ov = overlayVideoRef.value
  if (!ov) return
  if (playing) ov.play().catch(() => {})
  else ov.pause()
})

// ── Logo picker (via electronAPI IPC bridge) ──
async function pickLogo() {
  const files = await window.electronAPI.selectFiles({
    title: 'Select Logo Image',
    filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp', 'svg'] }],
  })
  if (files?.length) logoPath.value = files[0]
}
function clearLogo() { logoPath.value = '' }

// Logo URL — convert file path to displayable media URL
const logoUrl = ref('')
watch(logoPath, async (path) => {
  if (!path) { logoUrl.value = ''; return }
  try { logoUrl.value = await window.electronAPI.getMediaUrl(path) }
  catch { logoUrl.value = '' }
})

// ── Overlay picker (folder scan via electronAPI IPC bridge) ──
async function pickOverlay() {
  const folderPath = await window.electronAPI.selectFolder()
  if (!folderPath) return
  overlayPath.value = folderPath
  // Scan folder for video + image files via IPC
  try {
    const result = await window.electronAPI.scanFolder(folderPath)
    const mediaExts = ['.mp4', '.mov', '.webm', '.avi', '.mkv', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']
    overlayFiles.value = (result?.files || [])
      .filter((f: string) => mediaExts.some(ext => f.toLowerCase().endsWith(ext)))
      .sort()
  } catch (e) {
    console.error('[Overlay] Scan error:', e)
    overlayFiles.value = []
  }
}
function clearOverlay() {
  overlayPath.value = ''
  overlayFiles.value = []
}
// First overlay file for preview — use electronAPI to get proper media URL
const firstOverlayUrl = ref('')
const imageExts = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp']
const isOverlayImage = computed(() => {
  const first = overlayFiles.value[0]
  return first ? imageExts.some(ext => first.toLowerCase().endsWith(ext)) : false
})
watch(() => overlayFiles.value[0], async (firstFile) => {
  if (!firstFile) { firstOverlayUrl.value = ''; return }
  try {
    firstOverlayUrl.value = await window.electronAPI.getMediaUrl(firstFile)
  } catch { firstOverlayUrl.value = '' }
})

// ── Apply Preset (1-click fill all refs from preset values) ──
function applyPreset(values: ReupPresetValues) {
  if (values.mirror !== undefined) mirror.value = values.mirror
  if (values.crop !== undefined) crop.value = values.crop
  if (values.noise !== undefined) noise.value = values.noise
  if (values.rotate !== undefined) rotate.value = values.rotate
  if (values.lensDistortion !== undefined) lensDistortion.value = values.lensDistortion
  if (values.speed !== undefined) speed.value = values.speed
  if (values.audioEvade !== undefined) audioEvade.value = values.audioEvade
  if (values.hdr !== undefined) applyHDR.value = values.hdr
  if (values.colorGrading !== undefined) colorGrading.value = values.colorGrading
  if (values.glow !== undefined) glow.value = values.glow
  if (values.volumeBoost !== undefined) volumeBoost.value = values.volumeBoost
  if (values.frameTemplate !== undefined) frameTemplate.value = values.frameTemplate
  if (values.titleTemplate !== undefined) titleTemplate.value = values.titleTemplate
  if (values.titleText !== undefined) titleText.value = values.titleText
  if (values.descText !== undefined) descText.value = values.descText
  if (values.borderWidth !== undefined) borderWidth.value = values.borderWidth
  if (values.borderColor !== undefined) borderColor.value = values.borderColor
  if (values.zoomEffect !== undefined) zoomEffect.value = values.zoomEffect
  if (values.zoomIntensity !== undefined) zoomIntensity.value = values.zoomIntensity
  if (values.logoPath !== undefined) logoPath.value = values.logoPath
  if (values.logoPosition !== undefined) logoPosition.value = values.logoPosition
  if (values.logoSize !== undefined) logoSize.value = values.logoSize
  if (values.pixelEnlarge !== undefined) pixelEnlarge.value = values.pixelEnlarge
  if (values.chromaShuffle !== undefined) chromaShuffle.value = values.chromaShuffle
  if (values.rgbDrift !== undefined) rgbDrift.value = values.rgbDrift
}

// ── Direct video element control for speed & volume ──
const videoPreviewRef = ref<InstanceType<typeof VideoPreview> | null>(null)

watch([speed, volumeBoost], ([newSpeed, newBoost]) => {
  const vp = videoPreviewRef.value
  if (!vp?.videoRef) return
  const video = vp.videoRef as HTMLVideoElement
  // Speed
  if (newSpeed !== 1.0 && video.playbackRate !== newSpeed) {
    video.playbackRate = newSpeed
    console.log('[ReupView] Direct speed set:', newSpeed)
  } else if (newSpeed === 1.0 && video.playbackRate !== 1.0) {
    video.playbackRate = 1.0
  }
  // Volume boost — directly multiply volume
  const baseVol = video.volume
  // We'll handle boost via gain or volume scaling
  console.log('[ReupView] Direct volume boost:', newBoost, 'base vol:', baseVol)
}, { immediate: false })

// ── Export Single Video ──
const isExporting = ref(false)
const exportStatus = ref('')

async function exportVideo() {
  if (!currentVideoPath.value || isExporting.value) return

  const api = (window as any).electronAPI
  if (!api?.reupExport) {
    console.error('[Export] electronAPI.reupExport not available')
    return
  }

  // Build config from current settings — ALL filters must be included
  const config = {
    singleFile: currentVideoPath.value,
    inputFolder: '',
    // Core 9 layers
    mirror: mirror.value,
    crop: crop.value,
    noise: noise.value,
    rotate: rotate.value,
    lensDistortion: lensDistortion.value,
    hdr: applyHDR.value,
    speed: speed.value,
    pitchShift: audioEvade.value,
    audioEvade: audioEvade.value,
    cleanMetadata: true,
    musicPath: musicPath.value,
    // Color & Glow
    colorGrading: colorGrading.value,
    glow: glow.value,
    volumeBoost: volumeBoost.value,
    // Frame effects
    frameTemplate: frameTemplate.value,
    borderWidth: borderWidth.value,
    borderColor: borderColor.value,
    zoomEffect: zoomEffect.value,
    zoomIntensity: zoomIntensity.value,
    // Pixel-level anti-detect
    pixelEnlarge: pixelEnlarge.value,
    chromaShuffle: chromaShuffle.value,
    rgbDrift: rgbDrift.value,
    // Title
    titleTemplate: titleTemplate.value,
    titleText: titleText.value,
    descText: descText.value,
    // Logo
    logoPath: logoPath.value,
    logoPosition: logoPosition.value,
    logoSize: logoSize.value,
    // Split
    splitMode: splitMode.value,
    segmentLength: 15,
    // Subtitles
    srtPath: subSrtPath.value || '',
  }

  isExporting.value = true
  exportStatus.value = 'Choosing output location...'

  try {
    // Show Save As dialog with suggested filename
    const inputName = currentVideoPath.value.split('\\').pop()?.replace(/\.[^.]+$/, '') || 'output'
    const suggestedPath = `${inputName}_REUP.mp4`

    const savePath = await api.selectSavePath({
      title: 'Export Video — Choose Output',
      defaultPath: suggestedPath,
      filters: [{ name: 'MP4 Video', extensions: ['mp4'] }],
    })

    if (!savePath) {
      exportStatus.value = ''
      isExporting.value = false
      return
    }

    exportStatus.value = 'Starting export...'
    const result = await api.reupExport(config, savePath)
    if (result?.success) {
      exportStatus.value = `✅ Exported: ${result.outputPath}`
      // Highlight exported file in Explorer
      if (api.showItemInFolder) api.showItemInFolder(result.outputPath)
    } else {
      exportStatus.value = `❌ ${result?.error || 'Export failed'}`
    }
  } catch (e: any) {
    exportStatus.value = `❌ ${e.message}`
    console.error('[Export] Error:', e)
  } finally {
    isExporting.value = false
    // Clear status after 8s
    setTimeout(() => { exportStatus.value = '' }, 8000)
  }
}
</script>

<template>
  <div class="reup-layout">
    <!-- SVG Grain Filter (noise preview) — intensity controlled by noise ref (0-100) -->
    <svg class="hidden-svg" width="0" height="0">
      <defs>
        <filter id="grain">
          <feTurbulence type="fractalNoise" :baseFrequency="(0.3 + noise * 0.007).toFixed(3)" numOctaves="3" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
          <feBlend in="SourceGraphic" :mode="noise > 60 ? 'multiply' : 'overlay'" />
        </filter>
      </defs>
    </svg>

    <!-- Top Bar -->
    <header class="ru-topbar">
      <div class="ru-topbar-left">
        <div class="ru-logo"><Repeat :size="16" /></div>
        <span class="ru-title">Reup Video</span>

        <!-- Ratio Dropdown -->
        <div class="ru-ratio-wrapper">
          <button class="ru-ratio-btn" :class="{ active: frameTemplate !== 'none', open: showRatioDropdown }" @click.stop="showRatioDropdown = !showRatioDropdown">
            <MonitorSmartphone :size="12" />
            <span>{{ ratioLabel }}</span>
            <ChevronDown :size="10" class="ru-ratio-chevron" :class="{ open: showRatioDropdown }" />
          </button>
          <Transition name="dropdown">
            <div v-if="showRatioDropdown" class="ru-ratio-menu">
              <button
                v-for="opt in FRAME_TEMPLATE_OPTIONS" :key="opt.value"
                class="ru-ratio-option"
                :class="{ selected: frameTemplate === opt.value }"
                @click="selectRatio(opt.value)"
              >
                <span class="ru-ratio-opt-label">{{ opt.label }}</span>
                <span class="ru-ratio-opt-desc">{{ opt.desc }}</span>
              </button>
            </div>
          </Transition>
        </div>

        <!-- Music picker -->
        <div class="ru-path-item" @click="pickMusic">
          <Music :size="12" />
          <span class="ru-path-label">Music</span>
          <span class="ru-path-value" :class="{ empty: !musicPath }">{{ musicFileName || 'None' }}</span>
        </div>
        <button v-if="musicPath" class="ru-path-clear" @click.stop="clearMusic">✕</button>

        <div class="ru-hdr-toggle" :class="{ active: applyHDR }" @click="applyHDR = !applyHDR">
          <Sun :size="12" /><span>HDR</span>
        </div>
        <span class="ru-filter-badge">{{ activeFilterCount }} layers</span>
      </div>
      <div class="ru-topbar-right">
        <span v-if="metadata" class="ru-meta-badge">{{ metadata.width }}×{{ metadata.height }}</span>
        <span v-if="hasVideo" class="ru-live-badge">LIVE PREVIEW</span>
        <button
          v-if="hasVideo"
          class="ru-export-btn"
          :class="{ exporting: isExporting }"
          :disabled="isExporting"
          @click="exportVideo"
          :title="isExporting ? 'Exporting...' : 'Export video with all effects' + (subSrtPath ? ' + subtitles' : '')"
        >
          <Download :size="13" :class="{ spin: isExporting }" />
          <span>{{ isExporting ? 'Exporting...' : 'Export' }}</span>
        </button>
      </div>
      <div v-if="exportStatus" class="ru-export-status">{{ exportStatus }}</div>
    </header>

    <!-- Main 3-Column -->
    <div class="ru-main">
      <!-- LEFT: Toolbar -->
      <ReupToolbar
        :activeFeature="activeFeature"
        :toolbarItems="toolbarItems"
        :musicFileName="musicFileName"
        @update:activeFeature="activeFeature = $event"
        @clear-music="clearMusic"
      />

      <!-- CENTER: Preview -->
      <main class="ru-center">
        <div v-if="isLoading" class="ru-loading">
          <Loader2 :size="24" class="spin" /><span>Loading video...</span>
        </div>
        <div v-if="error" class="ru-error">{{ error }}</div>

        <ReupDropzone v-if="!hasVideo && !isLoading" @load-video="onLoadVideo" />

        <div v-if="hasVideo" class="ru-preview" :class="{ 'bg-blur-active': bgBlur }">
          <!-- Background Blur Layer — fills ENTIRE preview area -->
          <video
            v-if="bgBlur && videoUrl"
            ref="bgVideoRef"
            :src="videoUrl"
            class="ru-bg-blur"
            :style="{ '--bg-blur-amount': bgBlurAmount + 'px' }"
            muted
            playsinline
            preload="auto"
          />
          <div class="ru-frame-wrapper" :class="[previewRatioClass, previewZoomClass]"
            :style="{ '--zoom-intensity': zoomIntensity }">
            <div class="ru-preview-fx"
              :class="[previewMirrorClass, previewPixelClass, { 'reframe-edit': reframeEditMode }]"
              :style="{
                '--pv-transform': previewTransform,
                '--pv-filter': previewFilter,
                '--reframe-sx': (videoZoom * videoScaleX / 10000) * previewCropZoom,
                '--reframe-sy': (videoZoom * videoScaleY / 10000) * previewCropZoom,
                '--reframe-x': videoPosX + 'px',
                '--reframe-y': videoPosY + 'px',
              }"
              @mousedown="onReframeDragStart"
              @mousemove="onReframeDragMove"
              @mouseup="onReframeDragEnd"
              @mouseleave="onReframeDragEnd"
            >
              <VideoPreview
                ref="videoPreviewRef"
                :src="videoUrl!"
                :isPlaying="isPlaying"
                :volume="volume"
                :playbackRate="previewPlaybackRate"
                :volumeBoost="volumeBoost"
                :subtitles="subSegments"
                :subtitleStyle="subStyle"
                :subtitleSize="subFontSize"
                :subtitleAnimation="subAnimation"
                :subtitlePosition="subPosition"
                :subtitleOffsetX="subOffsetX"
                :subtitleOffsetY="subOffsetY"
                @update:isPlaying="isPlaying = $event"
                @update:volume="volume = $event"
                @timeupdate="onTimeUpdate"
                @durationchange="onDurationChange"
              />
            </div>
            <!-- Overlay preview (video or image) — respects blink visibility -->
            <video
              v-if="firstOverlayUrl && videoUrl && !isOverlayImage && overlayVisible"
              ref="overlayVideoRef"
              :src="firstOverlayUrl"
              class="ru-overlay-video"
              :style="{ opacity: overlayOpacity / 100 }"
              muted
              playsinline
              preload="auto"
              loop
            />
            <img
              v-if="firstOverlayUrl && videoUrl && isOverlayImage && overlayVisible"
              :src="firstOverlayUrl"
              class="ru-overlay-video"
              :style="{ opacity: overlayOpacity / 100 }"
              alt="overlay"
            />
            <!-- Border overlay -->
            <div v-if="borderWidth > 0" class="ru-border-overlay" :style="previewBorderStyle" />

            <!-- Logo overlay preview (actual image) — INSIDE frame-wrapper -->
            <div v-if="previewLogoInfo && logoUrl" class="ru-logo-overlay" :class="previewLogoInfo.position">
              <img :src="logoUrl" class="ru-logo-img" :style="{ width: previewLogoInfo.size + '%' }" alt="logo" />
            </div>

            <!-- Title (TEXT ON SCREEN) overlay — independent from SUB -->
            <div v-if="titleText" class="ru-title-overlay center"
              :style="{ transform: `translate(${titleOffsetX}px, ${titleOffsetY}px)` }"
              @mousedown.prevent="onTitleDragStart"
            >
              <div class="ru-title-text" :style="{
                fontFamily: textFont,
                fontWeight: '700',
                fontSize: titleFontSize + 'px',
                color: textColor,
                textShadow: '2px 2px 6px rgba(0,0,0,0.8), -1px -1px 3px rgba(0,0,0,0.5)',
              }">{{ titleText }}</div>
            </div>

            <!-- Desc (Mô tả) overlay — independent, draggable -->
            <div v-if="descText" class="ru-title-overlay bottom"
              :style="{ transform: `translate(${descOffsetX}px, ${descOffsetY}px)` }"
              @mousedown.prevent="onDescDragStart"
            >
              <div class="ru-desc-text" :style="{
                fontFamily: descFont,
                fontSize: descFontSize + 'px',
                color: textColor,
                textShadow: '1px 1px 4px rgba(0,0,0,0.7)',
              }">{{ descText }}</div>
            </div>

            <!-- Subtitle drag overlay (when sub edit mode active) -->
            <div v-if="subEditMode && subSegments.length" class="ru-sub-drag-overlay"
              @mousedown.prevent="onSubDragStart"
            >
              <span class="ru-sub-drag-hint">✋ Kéo để di chuyển subtitles</span>
            </div>
          </div>

          <button class="ru-cancel-video" @click="closeVideo" title="Close video"><X :size="14" /></button>
        </div>

        <!-- ═══════ CENTER FEATURES (always visible, below preview) ═══════ -->
        <div class="ru-features-scroll">
        <div class="ru-center-features">

          <!-- Reframe (Scale X/Y/Z) -->
          <div class="ruf-section">
            <div class="ruf-header" @click="showReframe = !showReframe">
              <MonitorSmartphone :size="12" />
              <span>Reframe (X/Y/Z)</span>
              <span v-if="videoZoom !== 100 || videoScaleX !== 100 || videoScaleY !== 100 || videoPosX !== 0 || videoPosY !== 0" class="ruf-badge">active</span>
              <span class="ruf-chevron" :class="{ open: showReframe }">▾</span>
            </div>
            <div v-if="showReframe" class="ruf-body">
              <!-- Drag mode -->
              <button class="ruf-edit-toggle" :class="{ active: reframeEditMode }" @click="reframeEditMode = !reframeEditMode">
                {{ reframeEditMode ? '✋ Đang kéo — Click tắt' : '🖱️ Bật kéo thả di chuyển' }}
              </button>

              <!-- Sync toggle -->
              <label class="ruf-check ruf-sync-toggle">
                <input type="checkbox" v-model="syncScale" />
                🔗 Đồng bộ X/Y
                <span class="ruf-sync-hint">{{ syncScale ? '(khóa tỷ lệ)' : '(tự do)' }}</span>
              </label>

              <!-- Z: Zoom -->
              <div class="ruf-slider-row">
                <span class="ruf-slider-label">🔍 Z</span>
                <input type="range" min="50" max="300" step="5" v-model.number="videoZoom" class="ruf-slider" />
                <span class="ruf-val">{{ videoZoom }}%</span>
              </div>
              <!-- X: Scale Width -->
              <div class="ruf-slider-row">
                <span class="ruf-slider-label">↔️ X</span>
                <input type="range" min="50" max="200" step="5" v-model.number="videoScaleX" class="ruf-slider" />
                <span class="ruf-val">{{ videoScaleX }}%</span>
              </div>
              <!-- Y: Scale Height -->
              <div class="ruf-slider-row">
                <span class="ruf-slider-label">↕️ Y</span>
                <input type="range" min="50" max="200" step="5" v-model.number="videoScaleY" class="ruf-slider" />
                <span class="ruf-val">{{ videoScaleY }}%</span>
              </div>

              <!-- Position display (from drag) -->
              <div v-if="videoPosX !== 0 || videoPosY !== 0" class="ruf-pos-display">
                📌 Vị trí: X={{ videoPosX }}px, Y={{ videoPosY }}px
              </div>

              <button v-if="videoZoom !== 100 || videoScaleX !== 100 || videoScaleY !== 100 || videoPosX !== 0 || videoPosY !== 0" class="ruf-reset-btn" @click="videoZoom = 100; videoScaleX = 100; videoScaleY = 100; videoPosX = 0; videoPosY = 0; reframeEditMode = false">
                🔄 Reset
              </button>
            </div>
          </div>

          <!-- Frame & Effects → Nâng cao (can thiệp pixel) -->
          <div class="ruf-section">
            <div class="ruf-header" @click="showFrame = !showFrame">
              <Frame :size="12" />
              <span>Nâng cao (can thiệp pixel)</span>
              <span v-if="pixelEnlarge || chromaShuffle || rgbDrift" class="ruf-badge">active</span>
              <span class="ruf-chevron" :class="{ open: showFrame }">▾</span>
            </div>
            <div v-if="showFrame" class="ruf-body">
              <label class="ruf-check">
                <input type="checkbox" v-model="pixelEnlarge" /> 🟦 Pixel Enlarge
              </label>
              <div class="ruf-desc">→ Phóng to pixel, film-like bloom</div>
              <label class="ruf-check">
                <input type="checkbox" v-model="chromaShuffle" /> 🎨 Chroma Shuffle
              </label>
              <div class="ruf-desc">→ Xáo trộn kênh màu YUV 16×16</div>
              <label class="ruf-check">
                <input type="checkbox" v-model="rgbDrift" /> 🌈 RGB Drift
              </label>
              <div class="ruf-desc">→ Dịch kênh RGB ±2px, anti-detect mạnh</div>
            </div>
          </div>

          <!-- TEXT (Tiêu đề + Mô tả) -->
          <div class="ruf-section">
            <div class="ruf-header" @click="showText = !showText">
              <Type :size="12" />
              <span>📝 TEXT</span>
              <span v-if="titleText || descText" class="ruf-badge">active</span>
              <span class="ruf-chevron" :class="{ open: showText }">▾</span>
            </div>
            <div v-if="showText" class="ruf-body">
              <!-- Auto title checkbox -->
              <label class="ruf-check" style="margin-bottom:4px;">
                <input type="checkbox" v-model="autoTitle" />
                📌 Tự động lấy tiêu đề từ tên video
              </label>
              <div class="ruf-input-row">
                <label>Tiêu đề</label>
                <input v-model="titleText" placeholder="Auto: filename" class="ruf-input" />
              </div>
              <div class="ruf-slider-row">
                <span style="font-size:11px;">📏 Cỡ chữ</span>
                <input type="range" min="10" max="48" step="1" v-model.number="titleFontSize" class="ruf-slider" />
                <span class="ruf-val">{{ titleFontSize }}px</span>
              </div>
              <!-- Font Picker: Tiêu đề -->
              <div style="margin-top:2px;">
                <span style="font-size:10px; color:var(--text-muted);">Font Tiêu đề</span>
                <div class="ruf-font-grid">
                  <button v-for="f in TEXT_FONTS" :key="'t-'+f"
                    class="ruf-font-btn" :class="{ active: textFont === f }"
                    :style="{ fontFamily: f }" @click="textFont = f"
                  >{{ f }}</button>
                </div>
              </div>

              <div style="height:1px; background:var(--border-default); margin:6px 0;" />

              <div class="ruf-input-row">
                <label>Mô tả</label>
                <input v-model="descText" placeholder="e.g. Please comment below" class="ruf-input" />
              </div>
              <div class="ruf-slider-row">
                <span style="font-size:11px;">📏 Cỡ chữ</span>
                <input type="range" min="8" max="36" step="1" v-model.number="descFontSize" class="ruf-slider" />
                <span class="ruf-val">{{ descFontSize }}px</span>
              </div>
              <!-- Font Picker: Mô tả -->
              <div style="margin-top:2px;">
                <span style="font-size:10px; color:var(--text-muted);">Font Mô tả</span>
                <div class="ruf-font-grid">
                  <button v-for="f in TEXT_FONTS" :key="'d-'+f"
                    class="ruf-font-btn" :class="{ active: descFont === f }"
                    :style="{ fontFamily: f }" @click="descFont = f"
                  >{{ f }}</button>
                </div>
              </div>

              <div class="ruf-desc">💡 Kéo thả text trên video preview để di chuyển vị trí</div>
              <!-- Color Picker -->
              <div class="ruf-slider-row" style="margin-top:4px;">
                <span style="font-size:11px;">🎨 Màu chữ</span>
                <input type="color" v-model="textColor" class="ruf-color-input" />
                <span class="ruf-val">{{ textColor }}</span>
              </div>
              <button v-if="titleOffsetX !== 0 || titleOffsetY !== 0 || descOffsetX !== 0 || descOffsetY !== 0" class="ruf-reset-btn" @click="titleOffsetX = 0; titleOffsetY = 0; descOffsetX = 0; descOffsetY = 0">
                🔄 Reset vị trí
              </button>
            </div>
          </div>

          <!-- SUB (Audio-to-Text Subtitle — Qwen3-ASR) -->
          <div class="ruf-section">
            <div class="ruf-header" @click="showSub = !showSub">
              <Type :size="12" />
              <span>🎬 SUB</span>
              <span v-if="subSegments.length" class="ruf-badge">{{ subSegments.length }} segs</span>
              <span v-if="subRunning" class="ruf-badge" style="background:rgba(59,130,246,0.3);color:#93c5fd;">⏳</span>
              <span class="ruf-chevron" :class="{ open: showSub }">▾</span>
            </div>
            <div v-if="showSub" class="ruf-body">
              <!-- Language selector -->
              <div class="sub-row">
                <span class="sub-label">🌍 Language</span>
                <select v-model="subLang" class="ruf-select sub-select" :disabled="subRunning">
                  <option v-for="l in SUB_LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
                </select>
              </div>

              <!-- Style selector grid -->
              <div class="sub-style-grid">
                <div
                  v-for="opt in TITLE_TEMPLATE_OPTIONS"
                  :key="opt.value"
                  class="sub-style-card"
                  :class="{ active: subStyle === opt.value }"
                  @click="subStyle = opt.value"
                >
                  <span class="sub-style-icon">{{ opt.label.split(' ')[0] }}</span>
                  <span class="sub-style-name">{{ opt.label.replace(/^\S+\s/, '') }}</span>
                  <span class="sub-style-desc">{{ opt.desc }}</span>
                </div>
              </div>

              <!-- Font size slider -->
              <div class="sub-size-row">
                <span class="sub-label">📏 Size</span>
                <input
                  type="range"
                  class="sub-size-slider"
                  v-model.number="subFontSize"
                  min="10" max="60" step="1"
                />
                <span class="sub-size-value">{{ subFontSize }}px</span>
              </div>

              <!-- Animation selector -->
              <div class="sub-row">
                <span class="sub-label">🎬 Animation</span>
                <select v-model="subAnimation" class="ruf-select sub-select">
                  <option v-for="a in SUB_ANIMATION_OPTIONS" :key="a.value" :value="a.value">{{ a.label }}</option>
                </select>
              </div>

              <!-- Position selector -->
              <div class="sub-row">
                <span class="sub-label">📍 Position</span>
                <select v-model="subPosition" class="ruf-select sub-select">
                  <option v-for="p in SUB_POSITION_OPTIONS" :key="p.value" :value="p.value">{{ p.label }}</option>
                </select>
              </div>

              <!-- Drag toggle + offset display -->
              <div class="sub-row">
                <button class="ruf-edit-toggle" :class="{ active: subEditMode }" @click="subEditMode = !subEditMode">
                  {{ subEditMode ? '✋ Đang kéo — Click tắt' : '🖱️ Kéo thả vị trí sub' }}
                </button>
              </div>
              <div v-if="subOffsetX !== 0 || subOffsetY !== 0" class="sub-row">
                <span class="sub-label">📍 Offset</span>
                <span class="sub-detected">X:{{ subOffsetX }} Y:{{ subOffsetY }}</span>
                <button class="sub-btn-mini" @click="subOffsetX = 0; subOffsetY = 0" title="Reset">🔄</button>
              </div>

              <!-- Transcribe button -->
              <div class="sub-row">
                <button
                  v-if="!subRunning"
                  class="sub-btn sub-btn-primary"
                  :disabled="!currentVideoPath"
                  @click="startSubTranscribe"
                >
                  🎤 Generate Subtitles
                </button>
                <button v-else class="sub-btn sub-btn-stop" @click="stopSubTranscribe">
                  ⬛ Stop
                </button>
              </div>

              <!-- Progress bar -->
              <div v-if="subRunning || subProgress > 0" class="sub-progress-wrap">
                <div class="sub-progress-bar">
                  <div class="sub-progress-fill" :style="{ width: subProgress + '%' }"></div>
                </div>
                <span class="sub-progress-text">{{ subProgress }}%</span>
              </div>

              <!-- Status -->
              <div v-if="subStatus" class="sub-status">{{ subStatus }}</div>
              <div v-if="subError" class="sub-status sub-error">❌ {{ subError }}</div>

              <!-- Engine indicator -->
              <div v-if="subEngine" class="sub-row">
                <span class="sub-label">🔧 Engine</span>
                <span class="sub-detected">{{ subEngine === 'whisper' ? '🚀 WhisperX' : subEngine === 'whisperx' ? '🚀 WhisperX' : '🧠 Qwen3-ASR' }}</span>
              </div>

              <!-- System Log toggle -->
              <div v-if="subLogs.length" class="sub-row">
                <button class="sub-btn-mini sub-log-toggle" @click="showSubLog = !showSubLog">
                  {{ showSubLog ? '🔽' : '▶️' }} System Log ({{ subLogs.length }})
                </button>
              </div>

              <!-- System Log panel -->
              <div v-if="showSubLog && subLogs.length" class="sub-log-panel">
                <div class="sub-log-content" ref="subLogContainer">
                  <div v-for="(log, i) in subLogs" :key="i" class="sub-log-line">{{ log }}</div>
                </div>
              </div>

              <!-- Detected language -->
              <div v-if="subDetectedLang" class="sub-row">
                <span class="sub-label">Detected</span>
                <span class="sub-detected">{{ subDetectedLang }}</span>
              </div>

              <!-- SRT Preview -->
              <div v-if="subSegments.length" class="sub-preview">
                <div class="sub-preview-header">
                  📝 Subtitle Preview ({{ subSegments.length }} segments)
                </div>
                <div class="sub-preview-list">
                  <div v-for="(seg, i) in subSegments.slice(0, 20)" :key="i" class="sub-seg">
                    <span class="sub-seg-time">{{ formatSubTime(seg.start) }} → {{ formatSubTime(seg.end) }}</span>
                    <span class="sub-seg-text">{{ seg.text }}</span>
                  </div>
                  <div v-if="subSegments.length > 20" class="sub-seg sub-seg-more">
                    ... +{{ subSegments.length - 20 }} more segments
                  </div>
                </div>
              </div>

              <!-- Export SRT button -->
              <div v-if="subSegments.length" class="sub-row sub-srt-actions">
                <button class="sub-srt-btn sub-srt-export" @click="exportSrt">
                  📝 Export SRT
                </button>
                <span v-if="subSrtPath" class="sub-path" :title="subSrtPath">✅ {{ subSrtPath.split('\\').pop() }}</span>
              </div>
            </div>
          </div>

          <!-- Enhance -->
          <div class="ruf-section">
            <div class="ruf-header" @click="showEnhance = !showEnhance">
              <Sparkles :size="12" />
              <span>Enhance</span>
              <span v-if="logoPath || overlayPath || bgBlur" class="ruf-badge">active</span>
              <span class="ruf-chevron" :class="{ open: showEnhance }">▾</span>
            </div>
            <div v-if="showEnhance" class="ruf-body">
              <label class="ruf-check" @click.prevent="pickLogo">
                <Image :size="12" /> 🖼️ Logo Watermark
              </label>
              <div v-if="logoPath" class="ruf-logo-info">
                <span>{{ logoPath.split('\\').pop() }}</span>
                <button @click="clearLogo" class="ruf-clear">✕</button>
              </div>
              <div v-if="logoPath" class="ruf-slider-row">
                <span style="font-size:11px;">Position</span>
                <button 
                  class="ruf-auto-btn" 
                  :class="{ active: logoPosition === 'auto' }"
                  @click="logoPosition = logoPosition === 'auto' ? 'bottom-left' : 'auto'"
                >🔄 AUTO</button>
                <select v-model="logoPosition" class="ruf-select" :disabled="logoPosition === 'auto'" :style="logoPosition === 'auto' ? { opacity: 0.4 } : {}">
                  <option v-for="p in LOGO_POSITIONS" :key="p.value" :value="p.value">{{ p.label }}</option>
                </select>
              </div>
              <div v-if="logoPath" class="ruf-slider-row">
                <span style="font-size:11px;">Size</span>
                <input type="range" min="5" max="80" step="1" v-model.number="logoSize" class="ruf-slider" />
                <span class="ruf-val">{{ logoSize }}%</span>
              </div>

              <!-- Overlay Video -->
              <label class="ruf-check" @click.prevent="pickOverlay">
                📝 Overlay Video
              </label>
              <div v-if="overlayPath" class="ruf-logo-info">
                <span>📂 {{ overlayFiles.length }} file(s)</span>
                <button @click="clearOverlay" class="ruf-clear">✕</button>
              </div>
              <div v-if="overlayPath" class="ruf-slider-row">
                <span style="font-size:11px;">Opacity</span>
                <input type="range" min="0" max="100" step="5" v-model.number="overlayOpacity" class="ruf-slider" />
                <span class="ruf-val">{{ overlayOpacity }}%</span>
              </div>
              <div v-if="overlayPath" class="ruf-slider-row">
                <span style="font-size:11px;">Blink</span>
                <button 
                  class="ruf-auto-btn" 
                  :class="{ active: overlayBlink }"
                  @click="overlayBlink = !overlayBlink"
                >⚡ AUTO</button>
                <select v-if="overlayBlink" v-model.number="overlayBlinkSpeed" class="ruf-select" style="max-width:80px;">
                  <option :value="0.10">0.10s ⚡</option>
                  <option :value="0.25">0.25s</option>
                  <option :value="0.5">0.5s</option>
                  <option :value="1.0">1.0s</option>
                  <option :value="1.5">1.5s</option>
                </select>
              </div>
              <div v-if="overlayPath" class="ruf-desc">
                → {{ overlayFiles.length }} overlay sẽ tự khớp N video input theo thứ tự, tốc độ tự điều chỉnh
              </div>

              <label class="ruf-check">
                <input type="checkbox" v-model="bgBlur" /> 🌫️ Background mờ
              </label>
              <div v-if="bgBlur" class="ruf-slider-row">
                <span style="font-size:11px;">Độ mờ</span>
                <input type="range" min="5" max="80" step="5" v-model.number="bgBlurAmount" class="ruf-slider" />
                <span class="ruf-val">{{ bgBlurAmount }}px</span>
              </div>
            </div>
          </div>
        </div>
        </div> <!-- /ru-features-scroll -->
      </main>

      <!-- RIGHT: Settings -->
      <aside class="ru-right">
        <div class="ru-right-header">
          <Settings2 :size="14" />
          <span>{{ toolbarItems.find(t => t.id === activeFeature)?.label }}</span>
          <button v-if="activeFeature === 'auto'" class="ru-header-cut-btn" :class="{ active: showSplit }" @click="showSplit = !showSplit">
            ✂️ Cut
          </button>
        </div>

        <ReupPanel
          v-if="activeFeature === 'auto' && !showSplit"
          :musicPath="musicPath" :applyHDR="applyHDR"
          :frameTemplate="frameTemplate"
          v-model:mirror="mirror" v-model:crop="crop"
          v-model:noise="noise" v-model:rotate="rotate"
          v-model:lensDistortion="lensDistortion"
          v-model:speed="speed" v-model:audioEvade="audioEvade"
          v-model:colorGrading="colorGrading"
          v-model:glow="glow" v-model:volumeBoost="volumeBoost"
          v-model:titleTemplate="titleTemplate"
          v-model:titleText="titleText"
          v-model:descText="descText"
          v-model:borderWidth="borderWidth"
          v-model:borderColor="borderColor"
          v-model:zoomEffect="zoomEffect"
          v-model:zoomIntensity="zoomIntensity"
          v-model:logoPath="logoPath"
          v-model:logoPosition="logoPosition"
          v-model:logoSize="logoSize"
          v-model:pixelEnlarge="pixelEnlarge"
          v-model:chromaShuffle="chromaShuffle"
          v-model:rgbDrift="rgbDrift"
          @applyPreset="applyPreset"
        />

        <SplitPanel v-if="activeFeature === 'auto' && showSplit" />

        <div v-if="activeFeature === 'music'" class="ru-music-panel">
          <div class="ru-music-section">
            <p class="ru-music-title">🎵 Background Music</p>
            <p class="ru-music-desc">Mixed into all reup'd videos at 25% volume (looped).</p>
            <button class="ru-music-pick" @click="pickMusic">
              <Music :size="14" />{{ musicFileName || 'Select Music File' }}
            </button>
            <button v-if="musicPath" class="ru-music-remove" @click="clearMusic">✕ Remove Music</button>
            <div v-if="musicPath" class="ru-music-info">
              <span class="ru-music-badge">Active</span><span>{{ musicFileName }}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style src="../styles/reup.css" />
