<script setup lang="ts">
/**
 * ReupPanel — Full AutoReup Pipeline.
 * ALL features in one panel, one START button.
 *
 * 4 sections:
 *   1. Visual Filters (Mirror, Crop, Noise, Rotate, Lens, Color, Glow)
 *   2. Frame & Effects (Zoom, Border)
 *   3. Title / Part (text overlay)
 *   4. Enhance (Logo, HDR, Speed, Pitch, Volume)
 */
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { FolderOpen, Play, Square, Repeat, Zap, Save, Trash2, Volume2 } from 'lucide-vue-next'
import { useReup } from '../../composables/useReup'
import {
  COLOR_GRADING_OPTIONS,
  ANTI_DETECT_LAYERS,
  RESET_PRESET,
  type ReupConfig,
  type ColorGradingStyle,
  type FrameTemplate,
  type TitleTemplate,
  type LogoPosition,
  type ReupPresetValues,
} from '../../constants/reup-constants'

const props = defineProps<{
  musicPath: string
  applyHDR: boolean
  // Visual Filters
  mirror: boolean
  crop: number
  noise: number
  rotate: number
  lensDistortion: boolean
  speed: number
  audioEvade: boolean
  colorGrading: ColorGradingStyle
  glow: boolean
  volumeBoost: number
  // Templates
  frameTemplate: FrameTemplate
  titleTemplate: TitleTemplate
  titleText: string
  descText: string
  // Frame & Effects
  borderWidth: number
  borderColor: string
  zoomEffect: boolean
  zoomIntensity: number
  // Logo
  logoPath: string
  logoPosition: LogoPosition
  logoSize: number
  // Pixel-level anti-detect
  pixelEnlarge: boolean
  chromaShuffle: boolean
  rgbDrift: boolean
}>()

const emit = defineEmits<{
  'update:mirror': [v: boolean]
  'update:crop': [v: number]
  'update:noise': [v: number]
  'update:rotate': [v: number]
  'update:lensDistortion': [v: boolean]
  'update:speed': [v: number]
  'update:audioEvade': [v: boolean]
  'update:colorGrading': [v: ColorGradingStyle]
  'update:glow': [v: boolean]
  'update:volumeBoost': [v: number]
  'update:titleTemplate': [v: TitleTemplate]
  'update:titleText': [v: string]
  'update:descText': [v: string]
  'update:borderWidth': [v: number]
  'update:borderColor': [v: string]
  'update:zoomEffect': [v: boolean]
  'update:zoomIntensity': [v: number]
  'update:logoPath': [v: string]
  'update:logoPosition': [v: LogoPosition]
  'update:logoSize': [v: number]
  'applyPreset': [values: ReupPresetValues]
  'update:pixelEnlarge': [v: boolean]
  'update:chromaShuffle': [v: boolean]
  'update:rgbDrift': [v: boolean]
  'getCurrentValues': []
}>()

// ── Custom Presets (localStorage) ──
const STORAGE_KEY = 'aurasplit_custom_presets'

interface CustomPreset {
  id: string
  label: string
  values: ReupPresetValues
}

const customPresets = ref<CustomPreset[]>([])
const showSaveInput = ref(false)
const newPresetName = ref('')

function loadCustomPresets() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) customPresets.value = JSON.parse(raw)
  } catch { customPresets.value = [] }
}

function saveCustomPresets() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(customPresets.value))
}

onMounted(() => loadCustomPresets())

function saveCurrentAsPreset() {
  const name = newPresetName.value.trim()
  if (!name) return
  const values: ReupPresetValues = {
    mirror: props.mirror, crop: props.crop, noise: props.noise,
    rotate: props.rotate, lensDistortion: props.lensDistortion,
    hdr: props.applyHDR, speed: props.speed, audioEvade: props.audioEvade,
    colorGrading: props.colorGrading, glow: props.glow, volumeBoost: props.volumeBoost,
    frameTemplate: props.frameTemplate,
    titleTemplate: props.titleTemplate, titleText: props.titleText, descText: props.descText,
    borderWidth: props.borderWidth, borderColor: props.borderColor,
    zoomEffect: props.zoomEffect, zoomIntensity: props.zoomIntensity,
    logoPath: props.logoPath, logoPosition: props.logoPosition, logoSize: props.logoSize,
    pixelEnlarge: props.pixelEnlarge, chromaShuffle: props.chromaShuffle, rgbDrift: props.rgbDrift,
  }
  customPresets.value.push({ id: `custom_${Date.now()}`, label: name, values })
  saveCustomPresets()
  newPresetName.value = ''
  showSaveInput.value = false
}

function deleteCustomPreset(id: string) {
  customPresets.value = customPresets.value.filter(p => p.id !== id)
  saveCustomPresets()
}

// ── 4-Layer Anti-Detect Defense ──
const activeLayers = ref<Set<string>>(new Set())

function isLayerActive(layerId: string): boolean {
  return activeLayers.value.has(layerId)
}

function toggleLayer(layerId: string) {
  const layer = ANTI_DETECT_LAYERS.find(l => l.id === layerId)
  if (!layer) return
  const next = new Set(activeLayers.value)
  if (next.has(layerId)) {
    // Turn OFF — reset only this layer's filters to defaults
    next.delete(layerId)
    const resetValues: ReupPresetValues = {}
    for (const key of Object.keys(layer.values) as (keyof ReupPresetValues)[]) {
      (resetValues as any)[key] = (RESET_PRESET as any)[key]
    }
    emit('applyPreset', resetValues)
  } else {
    // Turn ON — apply this layer's values
    next.add(layerId)
    emit('applyPreset', layer.values)
  }
  activeLayers.value = next
}

function activateFullShield() {
  const allValues: ReupPresetValues = {}
  const next = new Set<string>()
  for (const layer of ANTI_DETECT_LAYERS) {
    next.add(layer.id)
    Object.assign(allValues, layer.values)
  }
  activeLayers.value = next
  emit('applyPreset', allValues)
}

function resetAllLayers() {
  activeLayers.value = new Set()
  emit('applyPreset', RESET_PRESET)
}

const activeLayerCount = computed(() => activeLayers.value.size)

// ── useReup ──
const { isRunning, logs, scanResult, scanFolder, startReup, stopReup } = useReup()

// ── Folder ──
const folderPath = ref('')
const videoCount = computed(() => scanResult.value?.videos?.length ?? 0)
const cleanMetadata = ref(true)

async function pickFolder() {
  const result = await window.electronAPI.selectFolder()
  if (result) {
    folderPath.value = result
    await scanFolder(result)
  }
}



// ── Computed ──
const canRun = computed(() => folderPath.value && videoCount.value > 0 && !isRunning.value)
const activeFilterCount = computed(() => {
  let c = 0
  if (props.mirror) c++
  if (props.crop > 0) c++
  if (props.noise > 0) c++
  if (props.rotate) c++
  if (props.lensDistortion) c++
  if (props.applyHDR) c++
  if (props.speed !== 1.0) c++
  if (props.audioEvade) c++
  if (cleanMetadata.value) c++
  if (props.colorGrading !== 'none') c++
  if (props.glow) c++
  if (props.volumeBoost !== 1.0) c++
  if (props.borderWidth > 0) c++
  if (props.zoomEffect) c++
  if (props.logoPath) c++
  return c
})

const showVisual = ref(true)

// ── Log scroll ──
const logRef = ref<HTMLDivElement | null>(null)
watch(logs, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
}, { deep: true })



function run() {
  const config: ReupConfig = {
    inputFolder: folderPath.value,
    mirror: props.mirror,
    crop: props.crop,
    noise: props.noise,
    rotate: props.rotate,
    lensDistortion: props.lensDistortion,
    hdr: props.applyHDR,
    speed: props.speed,
    audioEvade: props.audioEvade,
    cleanMetadata: cleanMetadata.value,
    musicPath: props.musicPath,
    colorGrading: props.colorGrading,
    glow: props.glow,
    volumeBoost: props.volumeBoost,
    frameTemplate: props.frameTemplate,
    titleTemplate: props.titleTemplate,
    titleText: props.titleText,
    descText: props.descText,
    borderWidth: props.borderWidth,
    borderColor: props.borderColor,
    zoomEffect: props.zoomEffect,
    zoomIntensity: props.zoomIntensity,
    logoPath: props.logoPath,
    logoPosition: props.logoPosition,
    logoSize: props.logoSize,
    pixelEnlarge: props.pixelEnlarge,
    chromaShuffle: props.chromaShuffle,
    rgbDrift: props.rgbDrift,
    splitMode: 'none',
    segmentLength: 15,
  }
  startReup(config)
}
</script>

<template>
  <div class="rp-panel">
    <!-- Folder Picker -->
    <div class="rp-section">
      <button class="rp-folder-btn" @click="pickFolder">
        <FolderOpen :size="14" />
        {{ folderPath ? folderPath.split('\\').pop() : 'Select Folder' }}
      </button>
      <div v-if="videoCount > 0" class="rp-found">
        📂 Found <strong>{{ videoCount }}</strong> videos
      </div>
    </div>

    <div class="rp-divider" />

    <!-- ═══════ 4-LAYER ANTI-DETECT DEFENSE ═══════ -->
    <div class="rp-section">
      <div class="rp-section-header">
        <Zap :size="12" />
        <span>Anti-Detect Defense</span>
        <span v-if="activeLayerCount > 0" class="rp-layer-count">{{ activeLayerCount }}/4</span>
      </div>

      <!-- Master buttons -->
      <div class="rp-shield-row">
        <button class="rp-shield-btn" :class="{ active: activeLayerCount === 4 }" @click="activateFullShield" title="Bật tất cả 4 lớp phòng thủ">
          🛡️ FULL SHIELD
        </button>
        <button class="rp-reset-btn-master" @click="resetAllLayers" title="Tắt tất cả">
          🔄 Reset
        </button>
      </div>

      <!-- Compact layer labels — glow when active -->
      <div v-if="activeLayerCount > 0" class="rp-layer-compact">
        <span
          v-for="layer in ANTI_DETECT_LAYERS" :key="layer.id"
          class="rp-layer-pill" :class="{ active: isLayerActive(layer.id) }"
          @click="toggleLayer(layer.id)"
          :title="layer.desc"
        >{{ layer.emoji }} {{ layer.label }}</span>
      </div>
    </div>

      <!-- Custom presets -->
      <div v-if="customPresets.length > 0" class="rp-custom-presets">
        <div
          v-for="cp in customPresets" :key="cp.id"
          class="rp-custom-card"
        >
          <button class="rp-custom-load" @click="emit('applyPreset', cp.values)" :title="cp.label">
            ⭐ {{ cp.label }}
          </button>
          <button class="rp-custom-delete" @click="deleteCustomPreset(cp.id)" title="Xóa">
            <Trash2 :size="10" />
          </button>
        </div>
      </div>

      <!-- Save current as preset -->
      <div class="rp-save-row">
        <button v-if="!showSaveInput" class="rp-save-btn" @click="showSaveInput = true">
          <Save :size="11" /> 💾 Lưu preset hiện tại
        </button>
        <div v-else class="rp-save-input-row">
          <input
            v-model="newPresetName"
            class="rp-save-input"
            placeholder="Đặt tên preset..."
            @keyup.enter="saveCurrentAsPreset"
            autofocus
          />
          <button class="rp-save-confirm" @click="saveCurrentAsPreset" :disabled="!newPresetName.trim()">✓</button>
          <button class="rp-save-cancel" @click="showSaveInput = false; newPresetName = ''">✕</button>
        </div>
      </div>

    <div class="rp-divider" />

    <!-- ═══════ SECTION 1: Visual Filters ═══════ -->
    <div class="rp-section">
      <div class="rp-section-header" @click="showVisual = !showVisual">
        <Repeat :size="12" />
        <span>Visual Filters ({{ activeFilterCount }})</span>
        <span class="rp-chevron" :class="{ open: showVisual }">▾</span>
      </div>

      <div v-if="showVisual" class="rp-section-body">
        <!-- L1: Mirror -->
        <label class="rp-check">
          <input type="checkbox" :checked="mirror" @change="emit('update:mirror', ($event.target as HTMLInputElement).checked)" />
          🪞 Mirror
        </label>

        <!-- L2: Smart Crop -->
        <label class="rp-check">
          <input type="checkbox" :checked="crop > 0" @change="emit('update:crop', ($event.target as HTMLInputElement).checked ? 0.05 : 0)" />
          🔍 Smart Crop
        </label>
        <div v-if="crop > 0" class="rp-slider-row">
          <input type="range" min="0.02" max="0.30" step="0.01" :value="crop" @input="emit('update:crop', parseFloat(($event.target as HTMLInputElement).value))" class="rp-slider" />
          <span class="rp-slider-val">{{ Math.round(crop * 100) }}%</span>
        </div>

        <!-- L3: Noise/Grain (intensity slider) -->
        <label class="rp-check">
          <input type="checkbox" :checked="noise > 0" @change="emit('update:noise', ($event.target as HTMLInputElement).checked ? 50 : 0)" />
          🌫️ Noise/Grain
        </label>
        <div v-if="noise > 0" class="rp-slider-row" style="padding-left: 22px;">
          <span style="font-size:10px; color: var(--text-muted);">Intensity</span>
          <input type="range" min="1" max="100" step="1" :value="noise" @input="emit('update:noise', +($event.target as HTMLInputElement).value)" class="rp-slider" />
          <span class="rp-val">{{ noise }}%</span>
        </div>

        <!-- L4: Rotate -->
        <label class="rp-check">
          <input type="checkbox" :checked="rotate !== 0" @change="emit('update:rotate', ($event.target as HTMLInputElement).checked ? 2 : 0)" />
          🔄 Subtle Rotate
        </label>
        <div v-if="rotate !== 0" class="rp-slider-row">
          <input type="range" min="-10" max="10" step="0.5" :value="rotate" @input="emit('update:rotate', parseFloat(($event.target as HTMLInputElement).value))" class="rp-slider" />
          <span class="rp-slider-val">{{ rotate }}°</span>
        </div>

        <!-- L5: Lens Distortion -->
        <label class="rp-check">
          <input type="checkbox" :checked="lensDistortion" @change="emit('update:lensDistortion', ($event.target as HTMLInputElement).checked)" />
          🔮 Lens Distortion
        </label>

        <!-- L6: Color Grading -->
        <div class="rp-select-row">
          <span class="rp-select-label">🎨 Color</span>
          <select class="rp-select" :value="colorGrading" @change="emit('update:colorGrading', ($event.target as HTMLSelectElement).value as ColorGradingStyle)">
            <option v-for="o in COLOR_GRADING_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>

        <!-- L7: Glow/Bloom -->
        <label class="rp-check">
          <input type="checkbox" :checked="glow" @change="emit('update:glow', ($event.target as HTMLInputElement).checked)" />
          ✨ Glow/Bloom
        </label>

        <!-- L8: Zoom Effect (moved from center) -->
        <label class="rp-check">
          <input type="checkbox" :checked="zoomEffect" @change="emit('update:zoomEffect', ($event.target as HTMLInputElement).checked)" />
          🔎 Zoom Effect
        </label>
        <div v-if="zoomEffect" class="rp-slider-row">
          <input type="range" min="1.05" max="1.5" step="0.05" :value="zoomIntensity" @input="emit('update:zoomIntensity', parseFloat(($event.target as HTMLInputElement).value))" class="rp-slider" />
          <span class="rp-slider-val">{{ zoomIntensity.toFixed(2) }}x</span>
        </div>

        <!-- L9: Border (moved from center) -->
        <label class="rp-check">
          <input type="checkbox" :checked="borderWidth > 0" @change="emit('update:borderWidth', ($event.target as HTMLInputElement).checked ? 4 : 0)" />
          🔲 Border / Viền
        </label>
        <div v-if="borderWidth > 0" class="rp-slider-row">
          <input type="range" min="2" max="20" step="1" :value="borderWidth" @input="emit('update:borderWidth', parseFloat(($event.target as HTMLInputElement).value))" class="rp-slider" />
          <span class="rp-slider-val">{{ borderWidth }}px</span>
          <input type="color" :value="borderColor" @input="emit('update:borderColor', ($event.target as HTMLInputElement).value)" class="rp-color" />
        </div>

        <!-- L0: Clean Metadata -->
        <label class="rp-check rp-always">
          <input type="checkbox" v-model="cleanMetadata" disabled />
          🧹 Clean Metadata
          <span class="rp-always-badge">Always</span>
        </label>
      </div>
    </div>

    <div class="rp-divider" />

    <!-- ═══════ SECTION 2: Audio Anti-Detect ═══════ -->
    <div class="rp-section">
      <div class="rp-section-header">
        <Volume2 :size="12" />
        <span>Audio Anti-Detect</span>
      </div>
      <div class="rp-section-body">
        <!-- Speed -->
        <label class="rp-check">
          <input type="checkbox" :checked="speed !== 1.0" @change="emit('update:speed', ($event.target as HTMLInputElement).checked ? 1.5 : 1.0)" />
          ⏩ Speed
        </label>
        <div v-if="speed !== 1.0" class="rp-slider-row">
          <input type="range" min="0.5" max="3.0" step="0.1" :value="speed" @input="emit('update:speed', parseFloat(($event.target as HTMLInputElement).value))" class="rp-slider" />
          <span class="rp-slider-val">{{ speed.toFixed(1) }}x</span>
        </div>

        <!-- Lách âm thanh -->
        <label class="rp-check">
          <input type="checkbox" :checked="audioEvade" @change="emit('update:audioEvade', ($event.target as HTMLInputElement).checked)" />
          🔊 Lách âm thanh
        </label>
        <p v-if="audioEvade" style="font-size:9px; color:var(--text-muted); margin:0; padding:0 4px 0 24px; line-height:1.3;">Pitch shift + Channel swap + EQ random + Micro-echo — phá audio fingerprint</p>
      </div>
    </div>

    <div class="rp-divider" />

    <!-- Actions (at top for quick access) -->
    <div class="rp-actions">
      <button class="rp-btn run" @click="run" :disabled="!canRun">
        <Play :size="14" />
        START REUP
      </button>
      <button class="rp-btn stop" @click="stopReup" :disabled="!isRunning">
        <Square :size="14" />
        STOP
      </button>
    </div>

    <!-- Logs -->
    <div v-if="logs.length > 0" class="rp-log" ref="logRef">
      <div v-for="(line, i) in logs" :key="i" class="rp-log-line">{{ line }}</div>
    </div>
  </div>
</template>

<style src="../../styles/reup-panel.css" scoped></style>
