# AuraSplit v2 — ALL-IN-ONE Video Tool
## 📋 FINAL MASTER PLAN — Consensus từ Antigravity + Grok + AI Studio

> **Document này là FINAL PLAN** sau khi 3 AI đã review và thống nhất.
> Mỗi Discussion Point đã được giải quyết với **consensus 3/3 hoặc 2/3 đồng ý**.
>
> ⚠️ **Platform: WINDOWS ONLY** — Không cần Mac/Linux.
> 🎮 **Dev style: Vibe Coding** — Owner dùng AI assistants để build toàn bộ.

---

## 1. Bối cảnh & Bài học từ v1

AuraSplit v1 (Python/tkinter) thất bại vì:

| Vấn đề | Hậu quả | Giải pháp v2 |
|---------|---------|---------------|
| tkinter UI xấu, lag | UX kém | Vue 3 + Tailwind CSS |
| PyInstaller + Cython .pyd | SK3 crash 2 tháng | Electron + V8 bytecode |
| DEV ≠ USER mode | DEV OK, EXE crash | DEV = USER từ ngày 1 |
| `app.py` 3,400 + `editor_ui.py` 3,405 dòng | AI không debug nổi | Max 300 dòng/file |
| Không auto-update | Cài lại thủ công | NSIS + electron-builder |

### v1 Source Code → v2 Strategy

**✅ Consensus 3/3: Hybrid Strategy — UI rewrite 100%, Python AI keep & wrap, TTS port sang TS**

| File/Folder v1 | Lines | v2 Strategy | Lý do |
|----------------|:-----:|-------------|-------|
| `editor_ui.py` | 3,405 | **Rewrite 100%** → 15 Vue components | Paradigm khác (Imperative → Reactive) |
| `app.py` | ~2,200 | **Rewrite 100%** → 6 views | Tách monolith |
| `ai_scripts/sk1_worker.py` | ~570 | **Keep nguyên** + JSON wrapper | Đã hoạt động, isolated |
| `ai_scripts/sk3_worker.py` | ~490 | **Keep nguyên** + JSON wrapper | Đã hoạt động, isolated |
| `engines/sk1_cutting.py` | ~380 | **Keep logic** + TS wrapper | Core logic tốt |
| `engines/sk3_image_flow.py` | ~750 | **Keep logic** + TS wrapper | Core logic tốt |
| `engines/sk2_merging.py` | ~900 | **Rewrite** sang TypeScript | Logic đơn giản, clean hơn |
| `engines/sk4_hdr.py` | ~160 | **Rewrite** sang TypeScript | Logic đơn giản |
| `engines/sk5_effects.py` | ~270 | **Rewrite** sang TypeScript | Logic đơn giản |
| `engines/sk6_metadata.py` | ~180 | **Rewrite** sang TypeScript | Logic đơn giản |
| `AuraSplit_Voice/` | 26 files | **Rewrite** sang TypeScript | Python chậm cho API calls |
| `core/ffmpeg.py` | ~110 | **Rewrite** → `useFFmpeg.ts` | Port sang Node.js |
| `process_task.py` | ~1,050 | **Rewrite** → tách theo feature | Monolith → modular |

> **AI Studio note**: Tạo `api_wrapper.py` chuẩn hóa JSON input/output cho tất cả Python workers.

---

## 2. Tech Stack

**✅ Consensus 3/3: Vue 3 + Pinia + Tailwind**

| Layer | Công nghệ | Vai trò |
|-------|-----------|---------|
| Framework | **Electron** | Desktop shell (Windows) |
| Frontend | **Vue 3** + **Tailwind CSS** | UI components |
| Build | **electron-vite** | HMR, fast bundling |
| State | **Pinia** | Lightweight state management |
| Backend | **Node.js** main process | File I/O, subprocess, IPC |
| AI Engine | **Python 3.11** subprocess | WhisperX, torch (isolated) |
| Video | **FFmpeg** (child_process) | Encode/decode/cut/merge |
| Video Player | **HTML5 `<video>`** + Canvas | Preview (upgrade Vidstack nếu cần) |
| Canvas | **Konva.js** | Timeline + text overlay (Canvas 2D) |
| Download | **yt-dlp** (child_process) | YouTube/TikTok download |
| Local DB | **better-sqlite3** hoặc **lowdb** | Metadata, projects, settings |
| Auth | **Supabase** | License, user management |
| AI Chat | **Google GenAI** | AI assistant |
| Monitoring | **Sentry** | Crash tracking (EXE mode) |
| Testing | **Vitest** + **Playwright** | Unit + E2E tests |
| Protection | **V8 bytecode** (.jsc) via `bytenode` | JS code protection |
| Installer | **NSIS** + electron-builder | Windows installer + auto-update |

### Ngôn ngữ:

| Ngôn ngữ | % | Vai trò |
|----------|:-:|---------|
| TypeScript | 65% | UI logic, IPC, state |
| Vue SFC (.vue) | 20% | UI components |
| Python | 10% | AI scripts (giữ từ v1) |
| CSS (Tailwind) | 5% | Styling |

> **Grok note**: Vue SFC = AI thấy HTML+JS+CSS trong 1 file → context window hiệu quả hơn React.
> **AI Studio note**: Thêm `better-sqlite3` / `lowdb` cho local DB thay vì JSON files.

---

## 3. Feature Architecture — 6 Modules

```
┌─────────────────────────────────────────────────────┐
│               AuraSplit v2 (Electron)                │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐     │
│  │ Feature 1  │  │ Feature 2  │  │ Feature 3  │     │
│  │  AI CUT    │  │   VIDEO    │  │    TTS     │     │
│  │ SK1 + SK3  │  │  EDITOR    │  │   Audio    │     │
│  │ (WhisperX) │  │SK2+SK4+SK5 │  │ (đa ngôn   │     │
│  │            │  │+Omniclip   │  │  ngữ)      │     │
│  └────────────┘  └────────────┘  └────────────┘     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐     │
│  │ Feature 4  │  │ Feature 5  │  │ Feature 6  │     │
│  │  DOWNLOAD  │  │  METADATA  │  │  LICENSE   │     │
│  │  yt-dlp    │  │   SK6      │  │ (code cuối │     │
│  │            │  │ xóa AI det │  │  cùng)     │     │
│  └────────────┘  └────────────┘  └────────────┘     │
└─────────────────────────────────────────────────────┘
```

### Feature 1: AI CUT (SK1 + SK3) — Module riêng

**✅ Consensus 3/3: Giữ WhisperX, keep Python workers, wrap JSON**

| | SK1 (AI Cut) | SK3 (Image Flow) |
|---|---|---|
| **Input** | Audio/Video file | Images + Audio |
| **Logic** | Transcript → word timestamps → cắt video | Transcript → ghép images + audio → Ken Burns |
| **Output** | Clips cắt sẵn | Video hoàn chỉnh |
| **v1 source** | `sk1_cutting.py` + `sk1_worker.py` | `sk3_image_flow.py` + `sk3_worker.py` |

```
Logic flow:
User chọn audio + Whisper model
    ↓
Node.js spawn → python_embed/python.exe api_wrapper.py --task sk1 config.json
    ↓
WhisperX load model → Transcribe → word-level timestamps
    ↓
Output: result.json → Node.js đọc → FFmpeg cắt/ghép
```

> **AI Studio**: Tạo `api_wrapper.py` chuẩn hóa → tất cả Python workers dùng chung entry point.

---

### Feature 2: VIDEO EDITOR (SK2 + SK4 + SK5)

**✅ Consensus 3/3: Build from scratch, tham khảo concepts từ OpenCut/Omniclip/LosslessCut**

**Sources tham khảo (KHÔNG fork):**
- `editor_ui.py` v1 → concepts, refactor → 15 Vue components
- **OpenCut** → inspiration UX multi-track
- **Omniclip** → Canvas timeline + undo/redo ideas
- **LosslessCut** → Electron + FFmpeg pipeline architecture

#### editor_ui.py → Refactoring Map

| Class/Logic v1 | Lines | → Vue Component | Est. |
|----------------|:-----:|-----------------|:----:|
| `DraggableTextItem` | ~110 | `TextOverlay.vue` | ~150 |
| `DraggableVideo` | ~175 | `VideoCanvas.vue` | ~200 |
| Timeline logic | ~400 | `Timeline.vue` (Konva canvas) | ~250 |
| Subtitle panel | ~300 | `SubEditor.vue` + `SubGenerator.vue` | ~350 |
| FFmpeg export | ~250 | `useFFmpeg.ts` | ~150 |
| SK2 merge | ~300 | `CutMerge.vue` | ~200 |
| Main layout | ~500 | `EditorView.vue` | ~250 |
| Others | ~1,370 | Various components | ~640 |
| **TOTAL** | **3,405** | **15 components** | **~2,190** |

#### Tính năng Editor:

| Tính năng | Mô tả | Auto? |
|-----------|-------|:-----:|
| Cắt/Trim | Cắt video tại điểm bất kỳ | Manual |
| Ghép (SK2) | Merge clips | Manual/Auto |
| Chèn Text | Drag & drop (Konva.js) | Manual |
| Subtitle AI | WhisperX → User review sửa chính tả → Burn | Semi-auto |
| Xuất SRT | Export .srt file | Auto |
| Hiệu ứng | HDR (SK4), transitions (SK5), fade | Manual |
| Export | FFmpeg render final | Auto |

#### ⚠️ Subtitle Workflow

**✅ Consensus 3/3: WhisperX + User review UI (không cần đổi model)**

```
WhisperX generate transcript (word-level timestamps)
    ↓
[Optional] Gemini spell-check post-process
    ↓
User review/edit trong SubEditor.vue ← QUAN TRỌNG NHẤT
    ↓
Burn SRT vào video hoặc export .srt
```

> **AI Studio**: "Building a slick Subtitle Editor component is more important than changing the model."
> **Grok**: Thêm Gemini spell-check layer tăng accuracy ~99%.

---

### Feature 3: TTS (Text-to-Speech) — Module riêng

**✅ Consensus 2/3: EdgeTTS default (instant, free), Kokoro lazy download**

> AI Studio: Ship EdgeTTS default → feature works instantly. Local models = on-demand download.
> Grok: Kokoro default → nhẹ nhất. Nhưng vẫn cần download.
> **Verdict**: AI Studio đúng — EdgeTTS = ZERO download, works ngay.

#### TTS Strategy:

```
Tier 1 (Instant, Free):     EdgeTTS → default, no download needed
Tier 2 (Download, Local):   Kokoro (82M, CPU) → "Download HQ Voices" button
Tier 3 (Download, Premium): XTTS-v2 / F5-TTS → optional heavy models
Tier 4 (Cloud, Paid):       ElevenLabs / Minimax → API key
```

#### 🔄 Hot-Swap Architecture

Port từ v1 `AuraSplit_Voice/` (26 files) → TypeScript:

```
providers/tts/
├── base_provider.ts        ← Interface cố định
├── provider_factory.ts     ← Factory + fallback
├── edge_tts.ts             ← DEFAULT (free, instant) ✅
├── elevenlabs.ts           ← Cloud PAID, hot-update
├── minimax.ts              ← Cloud PAID, hot-update
└── local/
    ├── kokoro.ts           ← On-demand download ✅
    ├── xtts_v2.ts          ← Optional heavy
    ├── f5tts.ts            ← Best for VN
    └── ...
```

#### Local TTS Models (on-demand download):

| Model | Size | License | Ngôn ngữ | GPU? | Đặc biệt |
|-------|------|---------|----------|:----:|-----------|
| **Kokoro** | ~300MB | Apache ✅ | ~8 langs | CPU | Siêu nhẹ, default local |
| **XTTS-v2** | ~2GB | Non-commercial | 17 langs | GPU | Chất lượng cao, clone |
| **F5-TTS** | ~1GB | MIT | VN ✅ | GPU | Best Vietnamese |
| **Chatterbox-ML** | ~1.5GB | MIT | 23+ langs | GPU | Accent control |
| **GPT-SoVITS** | ~1.5GB | MIT | Asian langs | GPU | JA/KO/CN tốt nhất |

---

### Feature 4: VIDEO DOWNLOAD

- yt-dlp qua `child_process`
- Download YouTube, TikTok, Instagram...
- Hot-update khi platform đổi API

### Feature 5: METADATA CLEANER (SK6)

- Xóa metadata tránh AI platform phát hiện
- Port từ `engines/sk6_metadata.py` → TypeScript
- FFmpeg strip metadata + optional re-encode

### Feature 6: LICENSE — Code sau cùng

- Supabase + HWID protection
- Port logic từ v1 (`safe_kernel.py`, `security.py`)
- **Chỉ code khi app hoàn thiện**

---

## 4. ⚡ Video Preview — KHÔNG lag

**✅ Consensus 3/3: HTML5 `<video>` + Canvas, start simple → upgrade nếu cần**

### Strategy:

```
Phase 1:  HTML5 <video> + Canvas wrapper (draw video → canvas 60fps)
          + Konva.js overlay (text, shapes)
          + "Scrub" = pause + video.currentTime

Phase 2:  Nếu 4K lag → FFmpeg generate 720p proxy (như Premiere/DaVinci)
          User edit trên proxy → export từ original

Phase 3:  Nếu vẫn lag → upgrade WebCodecs API
```

**Key findings (3/3 đồng ý):**
- CapCut desktop = Electron-based → HTML5 video đủ
- LosslessCut (20k+ stars) = chứng minh đủ mượt
- Timeline lag = do DOM → dùng **Konva.js Canvas-based** timeline
- `<video>` tag không frame-accurate → Canvas wrapper fix

> **AI Studio crucial tip**: Nếu 4K lag → implement **Proxy workflow** (720p copy cho preview). Đây là cách Premiere/DaVinci làm.

---

## 5. File Structure — Max 300 dòng, Target 100-200

**✅ Consensus 3/3: "Quy tắc quan trọng nhất trong document"**

### 5.1 Tại sao (Vibe Coding critical)

| File size | AI behavior | Debug |
|:---------:|-------------|-------|
| **< 150** | AI thấy toàn bộ, sửa chính xác | ✅ |
| **150-300** | AI OK, quản lý được | ✅ |
| 300-500 | AI quên đầu file, sửa sai | ⚠️ |
| 500-1000 | AI hallucinate | ❌ |
| 1000+ | AI không thể xử lý | 💀 |

### 5.2 v1 vs v2

```
v1:  3,400 avg/file (2 files)     😱
v2:    114 avg/file (48 files)    ✅  (giảm 30x)
```

### 5.3 Line Count Summary

| Nhóm | Files | Total | Avg |
|------|:-----:|:-----:|:---:|
| Main process | 7 | ~800 | **114** |
| Views | 6 | ~1,070 | **178** |
| Components | 14 | ~1,780 | **127** |
| Logic (stores+composables) | 7 | ~590 | **84** |
| Providers | 9 | ~990 | **110** |
| Config/other | 5 | ~230 | **46** |
| **TOTAL** | **48** | **~5,460** | **~114** |

### 5.4 Enforcement

> **AI Studio**: Thêm **pre-commit hook** hoặc script fail build nếu file > 300 dòng.

### 5.5 Folder Structure

```
AuraSplit_v2/
├── package.json
├── electron.vite.config.ts
├── electron-builder.yml
│
├── src/
│   ├── main/                        # 7 files, ~800 lines
│   │   ├── index.ts                 # App lifecycle
│   │   ├── updater.ts               # Auto-update
│   │   └── ipc/                     # Split by domain
│   │       ├── ffmpeg.ipc.ts
│   │       ├── python.ipc.ts
│   │       ├── ytdlp.ipc.ts
│   │       ├── file.ipc.ts
│   │       └── auth.ipc.ts
│   │
│   ├── preload/
│   │   └── index.ts                 # contextBridge
│   │
│   ├── renderer/                    # 27 files, ~3,440 lines
│   │   ├── App.vue
│   │   ├── router.ts
│   │   ├── views/                   # 1 view per feature
│   │   ├── components/
│   │   │   ├── editor/              # 6 files ← editor_ui.py
│   │   │   ├── ai-cut/              # 2 files
│   │   │   ├── tts/                 # 3 files
│   │   │   └── shared/              # 3 files
│   │   ├── stores/                  # 4 Pinia stores
│   │   └── composables/             # 3 composables
│   │
│   └── shared/                      # Shared between main/renderer
│       └── providers/               # Hot-updatable
│           ├── tts/                 # ← AuraSplit_Voice/ port
│           │   ├── base_provider.ts
│           │   ├── provider_factory.ts
│           │   └── local/
│           └── download/
│               └── ytdlp_wrapper.ts
│
├── python_embed/                    # Giữ từ v1
├── ai_scripts/                      # Giữ từ v1
│   ├── api_wrapper.py               # NEW: chuẩn hóa JSON I/O
│   ├── sk1_worker.py
│   └── sk3_worker.py
├── models_ai/                       # HuggingFace cache
└── binaries/
    ├── ffmpeg.exe
    ├── ffprobe.exe
    └── yt-dlp.exe
```

> **AI Studio**: Move `providers/` inside `src/shared/` (part of app logic).
> **AI Studio**: IPC folder split by domain ✅ (đã làm).

---

## 6. Build Strategy — DEV = USER

**✅ Consensus 3/3**

| | DEV | USER |
|---|-----|------|
| Run | `npm run dev` | `AuraSplit.exe` |
| UI | Vue (HMR) | Vue (bundled) |
| FFmpeg | `binaries/ffmpeg.exe` | `resources/ffmpeg.exe` |
| Python | `python_embed/python.exe` | `resources/python_embed/` |
| IPC | **Giống nhau** ✅ | **Giống nhau** ✅ |

### Protection:

| Layer | Tool | Target |
|-------|------|--------|
| JavaScript | V8 bytecode (.jsc) via `bytenode` | Electron code ✅ |
| Python | **Nuitka** (optional) | Thử compile — nếu crash thì bỏ |

> Python chỉ 10% codebase (WhisperX workers). License/security logic = TypeScript → V8 protect.
> v1 crash 2 tháng vì Cython → Nuitka là **optional**: thử compile, nếu OK thì dùng, nếu bug thì ship `.py` thường.

### CI/CD:

Simple GitHub Actions: `npm run build` on push → verify build không broken.

---

## 7. Hot-Update System

**✅ Consensus 3/3: SHA256 mandatory, GitHub Releases hosting**

```
App start → fetch manifest.json từ GitHub Releases
         → so sánh version
         → download provider mới nếu có (~5KB)
         → verify SHA-256 checksum ← BẮT BUỘC
         → fallback nếu lỗi
```

> **AI Studio WARNING**: Download executable code at runtime = security risk (RCE).
> Solution: SHA-256 verify + sandbox providers (limit file system access).
> Hosting: **GitHub Releases** (free, versioning built-in, public CDN).

---

## 8. 🤖 AI Models Inventory

### WhisperX (cho SK1, SK3, Subtitle)

| Model | Name | Size | Speed | Quality |
|-------|------|------|:-----:|:-------:|
| `tiny` | 💨 LITE | ~75MB | ⚡⚡⚡⚡⚡ | ★☆☆☆☆ |
| `base` | ⚡ BASIC | ~145MB | ⚡⚡⚡⚡ | ★★☆☆☆ |
| `small` | 🔷 STANDARD | ~500MB | ⚡⚡⚡ | ★★★☆☆ |
| `medium` | 🔶 ADVANCED | ~1.5GB | ⚡⚡ | ★★★★☆ |
| `large-v3-turbo` | 🚀 PREMIUM | ~3GB | ⚡⚡ | ★★★★★ |

### Binary Tools

| Tool | Size | Vai trò |
|------|------|---------|
| `ffmpeg.exe` | ~130MB | Video processing |
| `ffprobe.exe` | ~50MB | Video metadata |
| `yt-dlp.exe` | ~10MB | Download |

---

## 9. Timeline — 25 buổi / 6 tuần

**✅ Consensus: 20 buổi quá optimistic → 25 buổi + 5 buffer = 6 tuần**

```
Phase 1: FOUNDATION (Tuần 1 — 4 buổi)
  Buổi 1:  Scaffold electron-vite + Vue + Tailwind + dark theme
  Buổi 2:  Sidebar nav + 6 view shells + Vue Router
  Buổi 3:  Auto-update (electron-builder) + NSIS installer
  Buổi 4:  CI/CD GitHub Actions + Sentry setup
  → TEST BUILD #1 ✅

Phase 2: AI CUT — Feature 1 (Tuần 2 — 3 buổi) ← Wow factor first
  Buổi 5:  SK1 UI + api_wrapper.py + Python subprocess
  Buổi 6:  SK3 UI + IPC progress reporting
  Buổi 7:  Test DEV + EXE cả SK1 lẫn SK3
  → TEST BUILD #2 ✅
  Sources: ai_scripts/ (giữ nguyên), engines/sk1+sk3

Phase 3: VIDEO EDITOR — Feature 2 (Tuần 3-4 — 7 buổi) ← Heaviest
  Buổi 8:   Konva Canvas timeline + snap/zoom
  Buổi 9:   HTML5 video preview + Canvas wrapper
  Buổi 10:  Cut/Join basic (SK2 port)
  Buổi 11:  Text overlay (Konva drag & drop)
  Buổi 12:  Subtitle AI + SubEditor UI + SRT export
  Buổi 13:  Effects (SK4 HDR + SK5 transitions)
  Buổi 14:  Export pipeline + proxy workflow
  → TEST BUILD #3 ✅
  Sources: editor_ui.py refactor, OpenCut/Omniclip concepts

Phase 4: TTS + EXTRAS (Tuần 5 — 4 buổi)
  Buổi 15:  TTS UI + EdgeTTS default (instant)
  Buổi 16:  LocalModelMgr + Kokoro on-demand download
  Buổi 17:  Download UI (yt-dlp) + Metadata cleaner (SK6)
  Buổi 18:  Hot-update system + manifest + SHA256
  → TEST BUILD #4 ✅
  Sources: AuraSplit_Voice/ port, engines/sk6

Phase 5: POLISH + SHIP (Tuần 6 — 4 buổi)
  Buổi 19:  UI polish + animations + dark theme tuning
  Buổi 20:  Full regression test DEV + EXE
  Buổi 21:  License system (Supabase + HWID)
  Buổi 22:  Final build + installer test
  → FINAL BUILD ✅

Buffer: 3 buổi cho "Integration Hell" (Python/FFmpeg/Vue sync)
  Buổi 23-25: Debug, hotfix, edge cases
```

### Phase Order Logic:

**AI Studio wins** — AI Cut trước Editor:

```
Phase 1 (Foundation) ← Base
    ↓
Phase 2 (AI Cut) ← "Wow factor", technically easier, proves Python+Node works
    ↓
Phase 3 (Editor) ← Heaviest, needs stable foundation + proven FFmpeg pipeline
    ↓
Phase 4 (TTS+Download+Meta) ← Independent modules
    ↓
Phase 5 (Polish+License) ← Everything works first
```

> **AI Studio**: AI Cut trước = wow factor + proves Python subprocess pipeline.
> **Grok**: Editor trước = core UX. ← Nhưng Editor quá heavy cho Phase 2.
> **Verdict**: AI Cut trước. Editor cần stable foundation.

---

## 10. Open-Source — Build from Scratch

**✅ Consensus 3/3: KHÔNG fork. Build from scratch + import libraries.**

| Tham khảo | Học gì | KHÔNG fork |
|-----------|--------|:----------:|
| **LosslessCut** | Electron + FFmpeg architecture | ✅ |
| **OpenCut** | UX inspiration multi-track | ✅ |
| **Omniclip** | Canvas timeline + undo/redo ideas | ✅ |
| **Shotcut** | Export pipeline ideas | ✅ |
| **Olive Editor** | Timeline component concepts | ✅ |

### Libraries (import):

| Library | Dùng cho |
|---------|----------|
| **Konva.js** | Canvas timeline + text overlay |
| **WaveSurfer.js** | Audio waveform |
| **vis-timeline** | Alternative timeline (if Konva not enough) |

> **AI Studio**: "Forking puts you in a codebase that violates your 300-line rule immediately."

---

## 11. Quy tắc TUYỆT ĐỐI cho AI Assistants

**Từ cả 3 AI đồng ý:**

1. **Max 300 dòng/file** — pre-commit hook enforce
2. **Python CHỈ cho AI** — không cho UI
3. **IPC cho MỌI thứ** — renderer KHÔNG import `fs` hoặc `child_process`
4. **Test BUILD mỗi phase** — `npm run build` → test `.exe`
5. **TypeScript bắt buộc** — không `.js`
6. **Hot-updatable providers** — không hardcode API
7. **Windows ONLY** — không cross-platform
8. **6 features riêng biệt** — không lẫn lộn
9. **Mock Data First** — build UI trước, không chờ Python backend
10. **FFmpeg is the engine** — Node.js chỉ là driver, keep logic thin

---

## 📊 Consensus Summary

| # | Topic | Grok | AI Studio | Antigravity | Result |
|:-:|-------|:----:|:---------:|:-----------:|--------|
| 1 | Source Strategy | Hybrid | Hybrid | Hybrid | **✅ 3/3** |
| 2 | Tech (Vue+Pinia) | ✅ | ✅ | ✅ | **✅ 3/3** |
| 3 | Subtitle (WhisperX) | ✅ | ✅ | ✅ | **✅ 3/3** |
| 4 | TTS default | Kokoro | EdgeTTS | EdgeTTS | **✅ 2/3 EdgeTTS** |
| 5 | Preview (HTML5) | ✅ | ✅ + proxy | ✅ | **✅ 3/3** |
| 6 | 300 lines | 10/10 | Approved | ✅ | **✅ 3/3** |
| 7 | V8 bytecode | ✅ | ✅ + Nuitka | ✅ | **✅ 3/3** |
| 8 | Hot-update (SHA256) | Supabase | GitHub | GitHub | **✅ 2/3 GitHub** |
| 9 | Timeline | 28 buổi | 25+ buffer | 25 buổi | **✅ 25 buổi** |
| 10 | No fork | ✅ | ✅ | ✅ | **✅ 3/3** |

**Phase order: AI Cut trước Editor** (AI Studio 2/3 win)

---

## 🚀 Ready to Build — Phase 1 starts NOW

---

## 📌 PROGRESS — ĐÃ HOÀN THÀNH (KHÔNG ĐỤNG VÀO)

> ⚠️ **Các phần bên dưới đã hoạt động ổn định. KHÔNG sửa lại trừ khi có bug mới.**

### ✅ Foundation (Phase 1)
- [x] Scaffold Electron + Vue 3 + Vite + TypeScript
- [x] Sidebar nav + Router + 6 view shells
- [x] Dark theme + CSS design system
- [x] Main process: `main.ts`, `preload.ts`, IPC handlers
- [x] Custom `local-media://` protocol (Range headers cho video seeking)

### ✅ Video Editor — Preview Player (Phase 3, Buổi 9)
- [x] `VideoPreview.vue` — HTML5 video player hoàn chỉnh
  - Play/Pause, seekbar kéo mượt, frame stepping (← →)
  - Volume control, mute (M), fullscreen (double-click)
  - Loading spinner khi buffer/seek
  - Smart `src` watcher preserve position khi URL swap
  - Keyboard shortcuts: Space, ←, →, M
- [x] `useEditor.ts` — Editor composable
  - Import video → instant play (no delay)
  - `local-media://` protocol cho fast seeking
  - Background auto-remux với frequent keyframes (`-g 30`)
  - Metadata parsing từ FFprobe
- [x] `ffmpeg.ipc.ts` — FFmpeg IPC
  - `probeFile()`, `runFFmpeg()`, `stopFFmpeg()`
  - `remuxForSeeking()` — `-g 30 -preset ultrafast -crf 18 +faststart`
  - Cached in `%TEMP%/aurasplit-preview/`
- [x] `preload.ts` + `electron.d.ts` — IPC bridge + types

### 📋 Files đã ổn định — KHÔNG SỬA:
| File | Trạng thái |
|------|:----------:|
| `src/components/editor/VideoPreview.vue` | ✅ DONE |
| `src/composables/useEditor.ts` | ✅ DONE |
| `electron/ipc/ffmpeg.ipc.ts` | ✅ DONE |
| `electron/preload.ts` | ✅ DONE |
| `electron/main.ts` | ✅ DONE |
| `src/types/electron.d.ts` | ✅ DONE |

### ✅ SK2 — Merge Videos (Phase 3, Buổi 10)
- [x] `MergePanel.vue` — Collapsible panel inside Editor
  - Folder picker (select folder with `videos/` subfolder)
  - Music picker (optional background music)
  - Transition IN/OUT dropdowns (50+ FFmpeg xfade options)
  - Output resolution (1080p, 720p, 9:16)
  - Speed slider (0.5-3.0s), delete originals checkbox
  - RUN / STOP buttons
  - Real-time scrolling log
- [x] `useMerge.ts` — Composable (scan, start, stop, log listener)
- [x] `merge.ipc.ts` — FFmpeg merge engine
  - Folder scan, auto-fix codecs/resolution
  - Concat copy (no transition), xfade transitions
  - Background music mixing with fade-out
  - Temp cleanup, stop support
- [x] `merge-constants.ts` — Transitions, output presets, xfade mapping

### 📋 SK2 Files đã ổn định — KHÔNG SỬA:
| File | Trạng thái |
|------|:----------:|
| `src/components/editor/MergePanel.vue` | ✅ DONE |
| `src/composables/useMerge.ts` | ✅ DONE |
| `electron/ipc/merge.ipc.ts` | ✅ DONE |
| `src/constants/merge-constants.ts` | ✅ DONE |
