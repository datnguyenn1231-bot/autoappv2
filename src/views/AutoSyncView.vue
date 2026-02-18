<script setup lang="ts">
import {
  Scissors, ImagePlus, Sparkles, Play, FolderOpen,
  FileAudio, FileText, Film, Image, Loader2, Trash2
} from 'lucide-vue-next'
import { useAutoSync, WHISPER_MODELS, LANGUAGES } from '../composables/useAutoSync'

const {
  activeTab, sk1, sk3, scriptContent, dropHover,
  pickAudio, pickScript, pickVideoDir, pickImageDir, pickOutputDir,
  startTask, stopTask, openOutputFolder, handleDrop, clearFields, fileName, folderName,
} = useAutoSync()

const state = () => activeTab.value === 'sk1' ? sk1.value : sk3.value
</script>

<template>
  <div class="view">
    <div class="view-grid">
      <!-- LEFT: Config -->
      <div class="config-col">
        <header class="view-head">
          <div class="head-top">
            <div class="head-icon"><Sparkles :size="20" /></div>
            <h1 class="head-title">AutoSync</h1>
          </div>
          <p class="head-sub">WhisperX AI → Auto sync Video & Image</p>
        </header>

        <!-- Tabs -->
        <div class="tabs">
          <button class="tab" :class="{ active: activeTab === 'sk1' }" @click="activeTab = 'sk1'">
            <Scissors :size="16" /> SyncVideo
          </button>
          <button class="tab" :class="{ active: activeTab === 'sk3' }" @click="activeTab = 'sk3'">
            <ImagePlus :size="16" /> SyncImage
          </button>
        </div>

        <!-- ═══ SK1 Panel ═══ -->
        <div v-if="activeTab === 'sk1'" class="panel">
          <div class="field">
            <label class="lbl"><FileAudio :size="13" /> Audio</label>
            <div class="picker" @click="pickAudio('sk1')">
              <span class="pname">{{ sk1.audioFile ? fileName(sk1.audioFile) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>
          <div class="field">
            <label class="lbl"><FileText :size="13" /> Script (.txt)</label>
            <div class="picker" @click="pickScript('sk1')">
              <span class="pname">{{ sk1.scriptFile ? fileName(sk1.scriptFile) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>
          <div class="field">
            <label class="lbl"><Film :size="13" /> Video Source Folder</label>
            <div class="picker" @click="pickVideoDir()">
              <span class="pname">{{ sk1.videoDir ? folderName(sk1.videoDir) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>

          <!-- Drop Zone -->
          <div class="drop-row">
            <div class="dropzone" :class="{ hover: dropHover }"
              @dragover.prevent="dropHover = true" @dragleave="dropHover = false"
              @drop="handleDrop">
              📂 Kéo thả folder vào đây để tự động điền<br>
              <small>(Drag & drop folder here for auto-detect)</small>
            </div>
            <button class="btn-clear" @click="clearFields" title="Clear all fields">
              <Trash2 :size="14" /> Clear
            </button>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="lbl">🧠 Model</label>
              <select v-model="sk1.model" class="sel">
                <option v-for="m in WHISPER_MODELS" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </div>
            <div class="field">
              <label class="lbl">🌐 Language</label>
              <select v-model="sk1.language" class="sel">
                <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label class="lbl"><FolderOpen :size="13" /> Output Name</label>
            <div class="output-row">
              <input type="text" v-model="sk1.outputName" class="input-name" placeholder="Type project name, e.g. AIbubble" />
              <div class="picker picker-sm" @click="pickOutputDir('sk1')">
                <span class="pname">{{ sk1.outputDir ? folderName(sk1.outputDir) : '📂 Save to...' }}</span>
                <FolderOpen :size="14" />
              </div>
            </div>
            <div v-if="sk1.outputDir && sk1.outputName" class="output-preview">
              → {{ sk1.outputDir }}\{{ sk1.outputName }}
            </div>
          </div>

          <div class="btn-group">
            <button v-if="!sk1.running" class="btn-run"
              :disabled="!sk1.audioFile || !sk1.scriptFile || !sk1.videoDir"
              @click="startTask('sk1')">
              <Play :size="16" /> ▶ RUN SyncVideo
            </button>
            <button v-else class="btn-run running" @click="stopTask('sk1')">
              <Loader2 :size="16" class="spin" /> ⏹ STOP
            </button>
            <button v-if="sk1.outputDir"
              class="btn-output" @click="openOutputFolder('sk1')">
              <FolderOpen :size="14" /> 📂 Open Output
            </button>
          </div>

          <div v-if="sk1.status !== 'idle'" class="prog">
            <div class="prog-bar"><div class="prog-fill" :style="{ width: sk1.progress + '%' }" /></div>
            <span class="prog-pct">{{ sk1.progress }}%</span>
          </div>
        </div>

        <!-- ═══ SK3 Panel ═══ -->
        <div v-if="activeTab === 'sk3'" class="panel">
          <div class="field">
            <label class="lbl"><FileAudio :size="13" /> Audio</label>
            <div class="picker" @click="pickAudio('sk3')">
              <span class="pname">{{ sk3.audioFile ? fileName(sk3.audioFile) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>
          <div class="field">
            <label class="lbl"><FileText :size="13" /> Script (.txt)</label>
            <div class="picker" @click="pickScript('sk3')">
              <span class="pname">{{ sk3.scriptFile ? fileName(sk3.scriptFile) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>
          <div class="field">
            <label class="lbl"><Image :size="13" /> Image Folder</label>
            <div class="picker" @click="pickImageDir()">
              <span class="pname">{{ sk3.imageDir ? folderName(sk3.imageDir) : 'Click to select...' }}</span>
              <FolderOpen :size="14" />
            </div>
          </div>

          <!-- Drop Zone -->
          <div class="drop-row">
            <div class="dropzone" :class="{ hover: dropHover }"
              @dragover.prevent="dropHover = true" @dragleave="dropHover = false"
              @drop="handleDrop">
              📂 Kéo thả folder vào đây để tự động điền<br>
              <small>(Drag & drop folder here for auto-detect)</small>
            </div>
            <button class="btn-clear" @click="clearFields" title="Clear all fields">
              <Trash2 :size="14" /> Clear
            </button>
          </div>

          <div class="field-row">
            <div class="field">
              <label class="lbl">🧠 Model</label>
              <select v-model="sk3.model" class="sel">
                <option v-for="m in WHISPER_MODELS" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </div>
            <div class="field">
              <label class="lbl">🌐 Language</label>
              <select v-model="sk3.language" class="sel">
                <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label class="lbl"><FolderOpen :size="13" /> Output Name</label>
            <div class="output-row">
              <input type="text" v-model="sk3.outputName" class="input-name" placeholder="Type project name, e.g. bitcoin" />
              <div class="picker picker-sm" @click="pickOutputDir('sk3')">
                <span class="pname">{{ sk3.outputDir ? folderName(sk3.outputDir) : '📂 Save to...' }}</span>
                <FolderOpen :size="14" />
              </div>
            </div>
            <div v-if="sk3.outputDir && sk3.outputName" class="output-preview">
              → {{ sk3.outputDir }}\{{ sk3.outputName }}
            </div>
          </div>

          <div class="btn-group">
            <button v-if="!sk3.running" class="btn-run"
              :disabled="!sk3.audioFile || !sk3.scriptFile || !sk3.imageDir"
              @click="startTask('sk3')">
              <Play :size="16" /> ▶ RUN SyncImage
            </button>
            <button v-else class="btn-run running" @click="stopTask('sk3')">
              <Loader2 :size="16" class="spin" /> ⏹ STOP
            </button>
            <button v-if="sk3.outputDir"
              class="btn-output" @click="openOutputFolder('sk3')">
              <FolderOpen :size="14" /> 📂 Open Output
            </button>
          </div>

          <div v-if="sk3.status !== 'idle'" class="prog">
            <div class="prog-bar"><div class="prog-fill" :style="{ width: sk3.progress + '%' }" /></div>
            <span class="prog-pct">{{ sk3.progress }}%</span>
          </div>
        </div>
      </div>

      <!-- RIGHT: Logs -->
      <div class="logs-col">
        <div class="log-panel">
          <div class="log-header green">■ SYSTEM LOG</div>
          <div class="log-body" id="systemLog">
            <div class="log-line" v-for="(log, i) in state().logs.slice(-80)" :key="i">{{ log }}</div>
            <div v-if="!state().logs.length" class="log-empty">Socket ready… waiting for task.</div>
          </div>
        </div>
        <div class="log-panel">
          <div class="log-header orange">■ SCRIPT VIEW</div>
          <div class="log-body script">
            <pre v-if="scriptContent" class="script-text">{{ scriptContent }}</pre>
            <div v-else class="log-empty">Select a script (.txt) to preview content here.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ Layout ═══ */
.view { width: 100%; }
.view-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
@media (min-width: 900px) {
  .view-grid { grid-template-columns: minmax(380px, 500px) 1fr; }
}
.config-col { min-width: 0; }
.logs-col { display: flex; flex-direction: column; gap: 10px; min-width: 0; }

/* ═══ Header ═══ */
.view-head { margin-bottom: 20px; }
.head-top { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.head-icon { width: 36px; height: 36px; border-radius: 10px; background: linear-gradient(135deg, var(--cyan), hsl(200,70%,50%)); display: flex; align-items: center; justify-content: center; color: white; box-shadow: 0 2px 16px hsla(185,70%,55%,0.25); }
.head-title { font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
.head-sub { color: var(--text-secondary); font-size: 13px; padding-left: 48px; }

/* ═══ Tabs ═══ */
.tabs { display: flex; gap: 4px; margin-bottom: 16px; }
.tab { display: flex; align-items: center; gap: 8px; padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-subtle); background: transparent; color: var(--text-muted); font-size: 13px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all 0.2s; }
.tab:hover { background: rgba(255,255,255,0.03); }
.tab.active { background: var(--accent-glow); border-color: var(--border-accent); color: var(--accent); }

/* ═══ Panel ═══ */
.panel { background: var(--bg-card); border: 1px solid var(--border-default); border-radius: 14px; padding: 20px; margin-bottom: 16px; }
.field { margin-bottom: 12px; }
.lbl { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 5px; text-transform: uppercase; letter-spacing: 0.4px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

/* ═══ Picker ═══ */
.picker { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 10px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); cursor: pointer; transition: all 0.2s; color: var(--text-secondary); }
.picker:hover { border-color: var(--accent); background: rgba(255,255,255,0.08); box-shadow: 0 0 0 1px hsla(var(--accent-h),60%,50%,0.15); }
.pname { flex: 1; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }

/* ═══ Select ═══ */
.sel { width: 100%; padding: 10px 14px; border-radius: 10px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text-primary); font-size: 13px; font-family: inherit; cursor: pointer; outline: none; appearance: none; transition: all 0.2s; }
.sel:hover { border-color: rgba(255,255,255,0.20); }
.sel:focus { border-color: var(--accent); box-shadow: 0 0 0 2px hsla(var(--accent-h),60%,50%,0.15); }

/* ═══ Output Name ═══ */
.output-row { display: flex; gap: 8px; align-items: stretch; }
.input-name { flex: 1; padding: 10px 14px; border-radius: 10px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text-primary); font-size: 13px; font-family: inherit; outline: none; transition: all 0.2s; }
.input-name:focus { border-color: var(--accent); box-shadow: 0 0 0 2px hsla(var(--accent-h),60%,50%,0.15); }
.input-name::placeholder { color: var(--text-muted); }
.picker-sm { min-width: 140px; flex-shrink: 0; }
.output-preview { font-size: 11px; color: var(--accent); margin-top: 6px; padding: 4px 8px; background: rgba(255,255,255,0.03); border-radius: 6px; word-break: break-all; }

/* ═══ Drop Zone ═══ */
.drop-row { display: flex; gap: 10px; align-items: stretch; margin-bottom: 14px; }
.dropzone { flex: 1; padding: 16px; border: 2px dashed rgba(255,255,255,0.15); border-radius: 10px; text-align: center; font-size: 12px; color: var(--text-secondary); transition: all 0.3s; cursor: pointer; background: rgba(255,255,255,0.02); }
.dropzone:hover, .dropzone.hover { border-color: var(--accent); background: hsla(var(--accent-h),60%,50%,0.08); color: var(--text-primary); }
.dropzone small { font-size: 10px; opacity: 0.7; }
.btn-clear { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 8px 14px; border-radius: 10px; border: 1px solid rgba(255,100,100,0.2); background: rgba(255,80,80,0.06); color: #ff6b6b; font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-family: inherit; }
.btn-clear:hover { background: rgba(255,80,80,0.15); border-color: rgba(255,100,100,0.4); }

/* ═══ Buttons ═══ */
.btn-run { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 12px; border-radius: 10px; border: none; background: linear-gradient(135deg, var(--accent), hsl(calc(var(--accent-h) + 30),70%,45%)); color: white; font-size: 14px; font-weight: 700; font-family: inherit; cursor: pointer; transition: all 0.2s; letter-spacing: 0.3px; }
.btn-run:hover:not(:disabled) { box-shadow: 0 4px 20px hsla(var(--accent-h),80%,50%,0.3); transform: translateY(-1px); }
.btn-run:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-run.running { background: linear-gradient(135deg, #ef4444, #dc2626); }
.btn-group { display: flex; gap: 8px; }
.btn-group .btn-run { flex: 1; }
.btn-output { display: flex; align-items: center; justify-content: center; gap: 6px; padding: 12px 18px; border-radius: 10px; border: none; background: linear-gradient(135deg, #00c853, #009624); color: white; font-size: 13px; font-weight: 700; font-family: inherit; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
.btn-output:hover { box-shadow: 0 4px 20px hsla(145,80%,40%,0.3); transform: translateY(-1px); }

/* ═══ Progress ═══ */
.prog { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.prog-bar { flex: 1; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.08); overflow: hidden; }
.prog-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #00e676, var(--cyan)); transition: width 0.3s; }
.prog-pct { font-size: 12px; color: var(--text-secondary); font-weight: 600; min-width: 36px; }

/* ═══ Log Panels ═══ */
.log-panel { background: #0c0c12; border: 1px solid rgba(255,255,255,0.10); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; flex: 1; }
.log-header { padding: 6px 10px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.log-header.green { color: #00e676; }
.log-header.orange { color: #ff9800; }
.log-body { flex: 1; min-height: 200px; max-height: 50vh; overflow-y: auto; padding: 6px 10px; font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace; }
.log-line { font-size: 11px; color: #00ff00; line-height: 1.5; word-wrap: break-word; overflow-wrap: break-word; white-space: pre-wrap; }
.log-empty { font-size: 11px; color: #666; font-style: italic; }
.script-text { font-size: 11px; color: #ddd; line-height: 1.6; white-space: pre-wrap; word-break: break-word; margin: 0; font-family: inherit; }
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
