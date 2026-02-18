# AuraSplit v2 — Module AI Cut: Briefing Kỹ Thuật
**Mục đích:** Mô tả chi tiết chức năng AI Cut (SK1 + SK3) để thảo luận bảo vệ code.
**Ngày:** 2026-02-09

---

## 1. Chức năng AI Cut làm gì?

### SK1 — Cắt Video Tự Động
**Input:** Audio/video + Script (.txt) + Thư mục video gốc
**Output:** Nhiều video clip ngắn, mỗi clip khớp 1 dòng script

**Quy trình:**
1. WhisperX AI phiên âm audio → danh sách từ (word + timestamp)
2. Alignment: ghép từ chính xác theo thời gian
3. Match words ↔ script: khớp từng dòng script với đoạn audio tương ứng
4. FFmpeg cắt audio + video theo timestamp đã match

### SK3 — Image Flow (Ken Burns)
**Input:** Audio + Script (.txt) + Thư mục ảnh
**Output:** Video slideshow với hiệu ứng Ken Burns, audio đã cắt khớp script

**Quy trình:**
1. Giống SK1 bước 1-3 (AI phiên âm + match script)
2. Gán ảnh cho mỗi đoạn script
3. Tạo video từ ảnh (Ken Burns zoom/pan effect)
4. Ghép audio cắt + video ảnh

---

## 2. Code đang tổ chức thế nào?

### Tầng 1: UI (Electron + Vue — TypeScript)
```
src/views/AICutView.vue       (226 dòng) — Giao diện: tabs SK1/SK3, file picker, 
                                            drop zone, progress bar, SYSTEM LOG,
                                            SCRIPT VIEW
src/composables/useAICut.ts   (175 dòng) — Logic UI: state management, file picker,
                                            drop zone auto-detect, IPC call to Python
```

### Tầng 2: IPC Bridge (Electron Main Process)
```
electron/main.ts              (98 dòng)  — Đăng ký IPC handlers, tạo window
electron/preload.ts           (60 dòng)  — Expose API cho renderer (runPython,
                                            selectFiles, readFile, scanFolder...)
electron/ipc/python.ipc.ts    (117 dòng) — Spawn Python subprocess, stream JSON 
                                            output về renderer, quản lý active tasks
electron/ipc/ffmpeg.ipc.ts    (104 dòng) — Chạy ffmpeg/ffprobe commands
```

### Tầng 3: Python Engine (subprocess, chạy riêng biệt)
```
python/api_wrapper.py         (123 dòng) — Entry point, đọc config JSON, route
                                            tới sk1 hoặc sk3 engine
python/engines/sk1_cutting.py (349 dòng) — CORE: thuật toán match words ↔ script,
                                            parse script, cutting loop, FFmpeg calls
python/engines/sk3_image_flow.py (650 dòng) — CORE: Ken Burns effect, image flow
                                               loop, FFmpeg video generation
python/ai_scripts/sk1_worker.py  (472 dòng) — WhisperX: load model, transcribe,
                                               align, extract words
python/core/model_manager.py  (91 dòng)  — Download/cache WhisperX models
python/core/ffmpeg.py         (113 dòng) — FFmpeg encoder detection, helpers
```

---

## 3. Flow khi user bấm RUN (chi tiết từng bước)

```
USER bấm "▶ RUN AI Cut"
    │
    ▼
[1] useAICut.ts → gọi window.electronAPI.runPython('sk1_123', 'sk1', {
      audio_full_path: "C:/...input.mp3",
      script_path: "C:/...script.txt",
      video_source_dir: "C:/...videos/",
      output_dir: "C:/...output/",
      model_name: "base",        ← tên model WhisperX
      lang_code: "auto",         ← ngôn ngữ
      fast_mode: false            ← bỏ qua alignment hay không
    })
    │
    ▼
[2] preload.ts → ipcRenderer.invoke('python:run', {...})
    │
    ▼
[3] python.ipc.ts:
    - Ghi config ra file JSON tạm: C:/temp/sk1_123_config.json
    - Spawn: python_embed/python.exe python/api_wrapper.py --task sk1 --config temp.json
    - Lắng nghe stdout → parse JSON lines → gửi IPC về renderer
    │
    ▼
[4] api_wrapper.py:
    - Đọc --config file
    - Import engines.sk1_cutting
    - Gọi set_config(engine_config)   ← set CONFIG dict giống v1
    - Gọi process_workflow(lang, model, log_func, fast_mode)
    │
    ▼
[5] sk1_cutting.py → process_workflow():
    │
    ├─ Phase 1: AI Transcription
    │   ├─ DEV mode: import whisperx trực tiếp
    │   └─ EXE mode: spawn sk1_worker.py subprocess
    │       ├─ Load/download WhisperX model
    │       ├─ Transcribe audio → segments + words
    │       ├─ Align words (word-level timestamp)
    │       └─ Output: {segments, words, language}
    │
    ├─ Phase 2: Script Matching
    │   ├─ Parse script.txt → danh sách items [V1], [V2]...
    │   ├─ Match words ↔ script items (thuật toán khớp text)
    │   └─ Output: matches[] = [{start, end, text, index}]
    │
    └─ Phase 3: FFmpeg Cutting
        ├─ Mỗi match → cắt audio clip
        ├─ Mỗi match → cắt video clip (nếu có video source)
        ├─ Encoder: NVENC (GPU) hoặc libx264 (CPU)
        └─ Output: output/audio_cut/V01.mp3, output/video_cut/V01.mp4

Trong suốt quá trình, log_func() emit JSON → stdout:
  {"type":"log","message":"[1/3] Transcribing..."}
  {"type":"progress","percent":30,"message":"Loading model..."}
  {"type":"log","message":"[V1] Audio + Video 3.50s Text: ..."}
  {"type":"result","data":{"status":"ok"}}
```

---

## 4. Giao tiếp giữa Electron ↔ Python

**Protocol:** JSON lines qua stdout

```
Python engine print() → stdout → Node.js readline → parse JSON → IPC send to renderer
```

**Các loại message:**
```json
{"type": "progress", "percent": 30, "message": "Loading model..."}
{"type": "log", "message": "[V68] Audio + Video 3.50s Text: お金が..."}
{"type": "result", "data": {"status": "ok", "task": "sk1"}}
{"type": "error", "message": "FileNotFoundError: audio not found"}
```

**Config truyền vào Python:** File JSON tạm (xóa sau khi đọc)
```json
{
  "audio_full_path": "C:/Users/.../input.mp3",
  "script_path": "C:/Users/.../script.txt",
  "video_source_dir": "C:/Users/.../videos/",
  "output_dir": "C:/Users/.../output/",
  "model_name": "base",
  "lang_code": "auto",
  "fast_mode": false,
  "model_cache_dir": "C:/Users/.../models_ai/"
}
```

---

## 5. Dependencies (thư viện cần có)

### Python side:
- **whisperx** — AI speech-to-text + alignment
- **torch** (PyTorch) — GPU inference engine
- **faster-whisper** — WhisperX backend
- **ffmpeg** — video/audio processing (binary, không phải Python lib)

### Electron side:
- **child_process** (Node.js built-in) — spawn Python
- **electron** (ipcMain/ipcRenderer) — IPC channel
- **Vue 3 + Pinia** — UI framework

---

## 6. Câu hỏi thảo luận

1. Kiến trúc Electron (UI) → IPC → Python (Engine) này có phù hợp không?
2. Code Python nào cần bảo vệ mạnh nhất? (sk1_cutting.py có thuật toán match words)
3. JSON stdout protocol có an toàn không? Cần encrypt?
4. Có nên compile Python .pyc hay dùng phương pháp nào khác?
5. Electron main.js + preload.mjs nằm ngoài asar — bảo vệ thế nào?

**Ràng buộc:** KHÔNG dùng Cython .pyd (gây crash ở v1). Ưu tiên ổn định.

---

## 7. Tính toán tổ chức để mã hóa

### 7A. Phân loại file theo mức bảo vệ

```
🔴 BẢO VỆ CAO (thuật toán cốt lõi, không được lộ):
   ├─ engines/sk1_cutting.py   → thuật toán match words ↔ script
   ├─ engines/sk3_image_flow.py → Ken Burns logic + image flow
   └─ core/ffmpeg.py            → encoder tricks, FFmpeg pipeline

🟡 BẢO VỆ TRUNG BÌNH (logic điều khiển, lộ cũng không chết):
   ├─ api_wrapper.py            → entry point, chỉ route task
   ├─ ai_scripts/sk1_worker.py  → gọi whisperx API (public library)
   └─ core/model_manager.py     → download/cache model

🟢 BẢO VỆ THẤP (UI, lộ cũng vô hại):
   ├─ src/views/AICutView.vue    → HTML/CSS giao diện
   ├─ src/composables/useAICut.ts → UI state logic
   └─ electron/preload.ts        → API bridge
```

### 7B. Chiến lược bảo vệ tầng Electron

**HIỆN TẠI (DEV mode):** File .ts, .vue bình thường → dễ đọc, dễ debug
**KHI BUILD PROD:**

```
Bước 1: Vite build
   src/*.vue + src/*.ts  →  dist/assets/index-abc123.js (minified)
   Kết quả: tên biến bị đổi, code nén 1 dòng, khó đọc

Bước 2: Electron main process
   electron/main.ts     →  dist-electron/main.js
   electron/preload.ts  →  dist-electron/preload.mjs
   ⚠️ VẤN ĐỀ: 2 file này nằm NGOÀI asar, có thể đọc được!
   → Cần obfuscate thêm (javascript-obfuscator hoặc bytenode)

Bước 3: Đóng gói asar
   dist/*  →  app.asar (archive, không mở bằng explorer)
   ⚠️ VẤN ĐỀ: Có thể extract bằng `npx asar extract app.asar`
   → Nhưng code bên trong đã minify nên khó đọc

Bước 4: electron-builder → tạo installer/EXE
   app.asar + runtime  →  AuraSplit-Setup.exe
```

**Cấu trúc thư mục sau build:**
```
AuraSplit-win32-x64/
├── AuraSplit.exe
├── resources/
│   ├── app.asar              ← renderer code (minified)
│   └── app.asar.unpacked/    ← assets lớn (nếu có)
├── dist-electron/
│   ├── main.js               ← ⚠️ CẦN OBFUSCATE
│   └── preload.mjs           ← ⚠️ CẦN OBFUSCATE
├── python/                   ← ⚠️ CẦN COMPILE .pyc
├── python_embed/
└── binaries/
```

### 7C. Chiến lược bảo vệ tầng Python

**HIỆN TẠI (DEV mode):** File .py bình thường → dễ debug
**KHI BUILD PROD:**

```
Bước 1: Compile .py → .pyc
   python -m compileall -b engines/ core/
   Kết quả: sk1_cutting.pyc, sk3_image_flow.pyc, ...

Bước 2: Xóa .py gốc cho file nhạy cảm
   del engines\sk1_cutting.py    (chỉ giữ .pyc)
   del engines\sk3_image_flow.py (chỉ giữ .pyc)
   GIỮ: api_wrapper.py          (entry point, không nhạy cảm)

Bước 3: python_embed vẫn chạy .pyc bình thường
   python_embed/python.exe api_wrapper.py
   → api_wrapper.py import engines.sk1_cutting
   → Python tự tìm sk1_cutting.pyc → chạy OK
```

**Cấu trúc Python sau build:**
```
python/
├── api_wrapper.py            ← .py (entry point, giữ nguyên)
├── engines/
│   ├── sk1_cutting.pyc       ← .pyc ONLY (xóa .py)
│   ├── sk3_image_flow.pyc    ← .pyc ONLY (xóa .py)
│   └── __init__.pyc
├── ai_scripts/
│   └── sk1_worker.py         ← .py (không nhạy cảm, gọi whisperx)
└── core/
    ├── model_manager.pyc     ← .pyc (xóa .py)
    └── ffmpeg.pyc            ← .pyc (xóa .py)
```

### 7D. Code đã viết sẵn để hỗ trợ mã hóa chưa?

| Phần | Trạng thái | Ghi chú |
|------|------------|---------|
| Vite minify config | ⚠️ CHƯA CÓ | Cần thêm terser config vào vite.config.ts |
| Obfuscate main.js/preload.mjs | ⚠️ CHƯA CÓ | Cần build script riêng |
| Python compile script | ⚠️ CHƯA CÓ | Cần build.bat hoặc build.py |
| DEV/PROD mode switch | ✅ ĐÃ CÓ | api_wrapper.py + python.ipc.ts hỗ trợ cả 2 |
| Tách entry point / logic | ✅ ĐÃ CÓ | api_wrapper.py (public) vs engines/ (private) |
| IPC JSON protocol | ✅ ĐÃ CÓ | JSON stdout, không expose Python trực tiếp |

### 7E. Build Pipeline đề xuất

```
DEV:
  npm run dev → code .ts/.vue/.py bình thường

PROD:
  [1] npm run build        → Vite minify renderer code
  [2] obfuscate-main.js    → javascript-obfuscator dist-electron/
  [3] compile-python.bat   → compileall engines/ core/ → .pyc
  [4] clean-py-sources     → xóa .py gốc nhạy cảm
  [5] electron-builder     → đóng gói thành .exe installer
```

**Toàn bộ pipeline này CHƯA ĐƯỢC VIẾT — cần implement khi xong app.**

---

## 8. Consensus Review (Antigravity + Grok + AI Studio — 2026-02-09)

### 8A. Cả 3 đồng ý:
- ✅ Kiến trúc Electron → IPC → Python: **GIỮU NGUYÊN, rất tốt**
- ✅ IPC JSON stdout: **KHÔNG encrypt** — giấu logic, không giấu data
- ✅ Không dùng Cython .pyd (crash v1)
- ✅ api_wrapper.py nên nâng bảo vệ lên TRUNG BÌNH (lộ routing → hook)
- ✅ Python dùng stderr cho debug, stdout chỉ cho JSON protocol

### 8B. Phương án bảo vệ đã thống nhất:

| Tầng | Phase 1 (Dev/Beta) | Phase 2 (Production) |
|------|-------------------|---------------------|
| **Electron Renderer** | Vite minify (mặc định) | + JS obfuscator plugin |
| **Electron Main/Preload** | Chưa cần | bytenode .jsc (Grok) hoặc obfuscator (AI Studio) |
| **Python engines/** | `.pyc` compileall | PyArmor obfuscate (cả 2 đồng ý) |
| **ASAR** | Mặc định | + integrity SHA256 (Grok) |

### 8C. Action Items (theo thứ tự ưu tiên):
1. 🔴 **Test logic SK1/SK3** — chạy thật, fix bug → ĐANG LÀM
2. 🟡 **Refactor Python >300 dòng** — sk3_image_flow (650), sk1_worker (472)
3. 🟢 **Implement build pipeline** — khi xong app
4. 🟢 **PyArmor / bytenode** — khi sản phẩm thương mại

### 8D. Ghi nhớ kỹ thuật từ AI Studio:
- `sys.stderr` cho debug log — `stdout` chỉ cho JSON IPC
- Không đóng gói `.map` file (source map)
- `electron-builder.yml`: dùng `extraResources` cho Python
- Hot-update: tách file nhỏ → chỉ gửi 1 `.pyc` thay vì cả engine


