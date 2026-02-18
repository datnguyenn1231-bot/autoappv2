# AuraSplit v2 — PROGRESS TRACKER
> **MỌI AI PHẢI đọc file này trước khi code và update sau khi code xong.**

---

## 📊 Status

| | Value |
|--------|-------|
| **Phase** | Phase 2 — AI Cut |
| **Module** | Module 2: AI Cut ✅ (UI + IPC done) |
| **Next** | Module 2: Test SK1/SK3 chạy thật |
| **Start** | 2026-02-09 |

---

## ✅ Module 1: Shell — DONE
**Files:** 13 | **Lines:** 1,080 | **Max:** 235 (Sidebar.vue)

- [x] electron-vite scaffold (Vue + TypeScript)
- [x] Tailwind CSS + @tailwindcss/vite
- [x] Dark theme (style.css — HSL palette, glassmorphism)
- [x] Lucide SVG icons (lucide-vue-next)
- [x] Sidebar navigation (gradient brand, active indicator)
- [x] 6 view shells (AI Cut, Editor, TTS, Download, Metadata, Settings)
- [x] Vue Router (hash history, lazy-loaded)
- [x] Pinia store (app.store.ts)
- [x] Frameless Electron window + custom title bar
- [x] `npm run dev` → OK ✅
- [x] `RUN_DEV.bat` → OK ✅

### Cài đặt đã hoàn thành:
```
Node.js:           v24.12.0
npm packages:      vue-router@4, pinia, tailwindcss, @tailwindcss/vite, lucide-vue-next
Vite plugins:      tailwindcss(), vue(), electron()
Electron window:   frameless, titleBarOverlay, dark bg #0f0f13
```

---

## ✅ Module 2: AI Cut — UI + IPC DONE
**Phase 2 — Buổi 2**

### Pre-requisites:
- [x] Copy `python_embed/` vào AuraSplit_v2/ (junction link)
- [x] Copy `ai_scripts/sk1_worker.py` + `sk3_worker.py`
- [x] Copy `engines/sk1_cutting.py` + `sk3_image_flow.py`
- [x] Copy `binaries/` vào AuraSplit_v2/ (junction link)
- [x] Copy `core/` + `config/` dependencies

### Tasks:
- [x] Tạo `api_wrapper.py` (JSON I/O chuẩn hóa)
- [x] Tạo `ipc/python.ipc.ts` (spawn Python subprocess)
- [x] Tạo `ipc/ffmpeg.ipc.ts` (FFmpeg commands)
- [x] Tạo `preload.ts` (electron API bridge)
- [x] Tạo `electron.d.ts` (TypeScript declarations)
- [x] Dialog IPC (file picker, folder picker)
- [x] SK1 UI hoàn chỉnh (file picker, model selector, progress, logs)
- [x] SK3 UI hoàn chỉnh (image list, audio picker, progress)
- [x] Composable `useAICut.ts` (logic tách riêng < 300 lines)
- [ ] Test DEV mode → confirm SK1 cắt video OK
- [ ] Test DEV mode → confirm SK3 ghép video OK

### Verify TRƯỚC KHI qua Module 3:
- [ ] SK1 chạy ok DEV
- [ ] SK3 chạy ok DEV
- [x] Module 1 (Shell) vẫn OK → `npm run dev` OK ✅
- [x] Tất cả files < 300 dòng ✅ (max: Sidebar 235)

### Cài đặt mới:
```
Files mới:     api_wrapper.py, python.ipc.ts, ffmpeg.ipc.ts, preload.ts,
               electron.d.ts, useAICut.ts
Files cập nhật: main.ts (+dialog IPC), AICutView.vue (full UI)
Junction links: python_embed/, binaries/
Copied:         ai_scripts/, engines/, core/, config/
```

---

## ⬜ Module 3: Video Editor
**Phase 3 — Buổi 8-14 (nặng nhất)**

- [ ] Konva.js Canvas timeline
- [ ] HTML5 video preview + Canvas wrapper
- [ ] Cut/join basic (SK2)
- [ ] Text overlay (Konva drag & drop)
- [ ] Subtitle AI (WhisperX → SubEditor → burn SRT)
- [ ] Effects (SK4 HDR + SK5)
- [ ] Export pipeline
- [ ] Verify: Module 1 + 2 vẫn OK

---

## ⬜ Module 4: TTS
- [ ] EdgeTTS default (instant, free)
- [ ] Provider factory pattern
- [ ] LocalModelMgr (Kokoro download)
- [ ] Verify: Module 1-3 vẫn OK

## ⬜ Module 5: Download
- [ ] yt-dlp IPC
- [ ] URL input + progress
- [ ] Verify: Module 1-4 vẫn OK

## ⬜ Module 6: Metadata
- [ ] FFmpeg strip metadata
- [ ] Batch process
- [ ] Verify: Module 1-5 vẫn OK

## ⬜ Module 7: Settings
- [ ] Config form
- [ ] About page
- [ ] Verify: Module 1-6 vẫn OK

## ⬜ Module 8: License (LAST)
- [ ] Supabase + HWID
- [ ] Verify: ALL modules OK

## ⬜ Module 9: Polish + Ship
- [ ] UI animations
- [ ] NSIS installer
- [ ] Auto-update
- [ ] Final full test

---

## 📝 Changelog

### 2026-02-09 — Buổi 1
- Scaffold electron-vite + Vue + Tailwind
- 6 views + sidebar + router + pinia
- Premium UI redesign (Lucide icons, glassmorphism, gradients)
- Frameless window + custom title bar
- `npm run dev` → OK

### 2026-02-09 — Buổi 2
- Copy v1 Python files (ai_scripts, engines, core, config)
- Junction link python_embed + binaries
- `api_wrapper.py` — v1-compatible CONFIG mapping (audio, script, video_dir, output)
- `python.ipc.ts` — spawn subprocess + stream JSON
- `ffmpeg.ipc.ts` — probe + run FFmpeg
- `preload.ts` — electron API bridge
- `electron.d.ts` — TypeScript type declarations
- Dialog IPC handlers (file picker, folder picker)
- `useAICut.ts` composable (4-input state, v1 MODEL_MAP, LANG_OPTIONS)
- `AICutView.vue` full UI (SK1: audio+script+video_dir+output, SK3: audio+script+images+output)
- v1 CONFIG keys: audio_full_path, script_path, video_source_dir, image_source_dir, output_dir
- All NEW files < 300 lines ✅ (v1 legacy files kept as-is)
- `npm run dev` → OK ✅

---

## ⚠️ Nhắc nhở

> **Mỗi lần code xong → UPDATE file này!**
> **Mỗi lần bắt đầu → ĐỌC file này!**
> **Verify module cũ TRƯỚC KHI làm module mới!**
