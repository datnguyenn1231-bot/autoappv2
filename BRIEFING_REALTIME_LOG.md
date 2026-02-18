# BRIEFING: Per-Clip Realtime Log Streaming Bug

## 🎯 MỤC TIÊU
Hiện per-clip log **REALTIME** trong System Log của AuraSplit v2 (Electron + Vue), giống hệt v1 (Python tkinter).

### V1 (HOẠT ĐỘNG TỐT — tkinter GUI):
```
[V68] ✓ Audio + ■ Video | 3.50s | Text: お金が、煙のように消えていく…
[V69] ✓ Audio + ■ Video | 5.79s | Text: 雨後の筍のようなAIスタートアップたち。
[V70] ✓ Audio + ■ Video | 4.02s | Text: 彼らの正体は、ただの「AIラッパー」です。
...140 dòng, mỗi clip hiện ngay khi cắt xong
```

### V2 (BỊ LỖI — Electron IPC):
```
[3/3] Cutting 140 RAW clips...
🚀 TURBO MODE: NVENC+ (GPU)!
[DEBUG] Starting cutting loop: 140 clips...
                                          ← KHÔNG CÓ GÌ Ở ĐÂY
[DEBUG] Loop done: 140 audio, 140 video clips processed
🎉 CUTTING COMPLETED!
```

---

## 🏗️ KIẾN TRÚC IPC (V2)

```
Python subprocess ──stdout──→ Electron main ──IPC──→ Vue renderer
    (api_wrapper.py)     (python.ipc.ts)        (useAICut.ts)
```

### Dòng chảy dữ liệu:
1. **Python** gọi `emit("log", message="...")` → `json.dumps(payload)` → `print(line, flush=True)` → stdout pipe
2. **Electron** `proc.stdout.on('data')` → `buffer.split('\n')` → `JSON.parse(line)` → `win.webContents.send()`
3. **Vue** `window.electronAPI.onPythonMessage()` → `addLog(state, msg.message)` → reactive logs array

### Python subprocess spawn:
```typescript
// electron/ipc/python.ipc.ts
const proc = spawn(pythonExe, [
    '-u',  // Force unbuffered stdout/stderr
    wrapper, '--task', taskType, '--config', configPath,
], {
    env: { PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', ... },
    stdio: ['ignore', 'pipe', 'pipe'],  // stdin=ignore, stdout=pipe, stderr=pipe
})
```

---

## 🐛 VẤN ĐỀ CỤ THỂ

### Messages TRƯỚC cutting loop → HIỆN TỐT ✅
```python
# Các log_func() calls này đều hiện trong System Log:
log_func("🚀 SK1 Starting...")
log_func("✅ Model loaded successfully!")
log_func("[3/3] Cutting 140 RAW clips...")
log_func("🚀 TURBO MODE: NVENC+ (GPU)!")
```

### Messages TRONG cutting loop → KHÔNG HIỆN ❌
```python
# Bên trong _cutting_loop (process_task.py):
for idx, (vid, s_time, e_time, text) in enumerate(matches, 1):
    ffmpeg_runner(audio_cmd)   # → safe_kernel.execute_safe()
    ffmpeg_runner(video_cmd)   # → safe_kernel.execute_safe()
    log_func(f"[{idx}/{total}] [V{vid}] ✓ Audio + ■ Video | {duration:.2f}s | Text: {text}")
    # ↑ Message này KHÔNG BAO GIỜ đến Electron
```

### Messages SAU cutting loop → HIỆN TỐT ✅
```python
log_func("[DEBUG] Loop done: 140 audio, 140 video clips processed")
log_func("🎉 CUTTING COMPLETED!")
```

---

## 🔬 ĐÃ THỬ VÀ KẾT QUẢ

### 1. Sanitize newlines trong JSON ❌
**Lý do thử**: Text script chứa `\r\n`, phá vỡ JSON line protocol
**Kết quả**: Không fix được. Messages vẫn không hiện.
```python
def _sanitize_for_json_line(value):
    if isinstance(value, str):
        return value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
    ...
```

### 2. sys.stdout.write() + flush() ❌
**Kết quả**: Không hiện. Data ghi vào stdout nhưng không đến Node.js pipe.
```python
sys.stdout.write(json_line + '\n')
sys.stdout.flush()
```

### 3. os.write(1, data) — Raw file descriptor ❌
**Kết quả**: `os.write(1, ...)` KHÔNG raise exception, nhưng data biến mất!
Không có error log → fd 1 vẫn "mở" nhưng data không đến Electron.
```python
os.write(1, (json_line + '\n').encode('utf-8'))
# Succeeds! No exception! But data vanishes!
```

### 4. sys.stderr.write() — Bypass stdout entirely ❌
**Kết quả RIÊNG TỪ NGOÀI loop**: Message "Starting cutting loop (via stderr)" ĐÃ HIỆN ✅
**Kết quả TRONG loop**: Messages vẫn không hiện ❌

```python
# BEFORE loop → WORKS:
_stderr_emit("log", message="Starting cutting loop...")  # ← HIỆN ✅

# INSIDE loop (after FFmpeg) → FAILS:
_stderr_emit("log", message="Clip 1/140 done")  # ← KHÔNG HIỆN ❌
```

### 5. DevTools Console trace ❌
**Kết quả**: Electron main process KHÔNG nhận bất kỳ stdout hay stderr data nào từ Python trong suốt cutting loop. Console chỉ hiện messages trước và sau loop.

---

## 🔍 NGHI VẤN GỐC: `safe_kernel.execute_safe()`

Đây là hàm chạy FFmpeg subprocess. Mỗi clip gọi 2 lần (audio + video):

```python
# python/safe_kernel.py — execute_safe() stream mode
proc = subprocess.Popen(
    args,                                    # FFmpeg command
    cwd=cwd,
    env=clean_env,
    stdout=subprocess.DEVNULL,               # FFmpeg stdout → /dev/null
    stderr=subprocess.PIPE,                  # FFmpeg stderr → pipe (for error capture)
    stdin=subprocess.DEVNULL,
    bufsize=1,
    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    close_fds=True,                          # ⚠️ NGHI VẤN: có ảnh hưởng parent's stdout?
    startupinfo=startupinfo,                 # STARTF_USESHOWWINDOW + SW_HIDE
)

# Blocking loop reads FFmpeg stderr:
while True:
    line = proc.stderr.readline()
    if line:
        stderr_acc.append(line)
    else:
        if proc.poll() is not None:
            break
        time.sleep(0.01)
```

### Tại sao nghi `execute_safe`:
1. Tất cả `print()`/`sys.stdout.write()`/`os.write(1)` **TRƯỚC** `execute_safe` lần đầu → **HOẠT ĐỘNG**
2. Tất cả writes **TRONG** loop (giữa các `execute_safe` calls) → **THẤT BẠI**  
3. Tất cả writes **SAU** loop kết thúc → **HOẠT ĐỘNG**
4. File writes (`open()` + `write()`) **TRONG** loop → **HOẠT ĐỘNG** (sk1_debug.log chứng minh)

### Giả thuyết:
- `close_fds=True` trên Windows có thể gây side-effect với parent process's stdout/stderr handles
- `CREATE_NEW_PROCESS_GROUP` có thể ảnh hưởng pipe inheritance
- FFmpeg subprocess's `stdout=subprocess.DEVNULL` có thể corrupt parent's fd 1 trên Windows
- `subprocess.PIPE` cho stderr có thể block parent's stderr writes

---

## 📊 BẰNG CHỨNG QUAN TRỌNG

### ✅ `cutting_debug.log` (ghi bằng file I/O — HOẠT ĐỘNG):
```
Total matches: 140
Audio clips processed: 140
Video clips processed: 140
```
→ Chứng minh `_tracked_ffmpeg()` và `_tracked_log()` ĐƯỢC GỌI đủ 140 lần.

### ✅ `sk1_debug.log` (ghi bằng file I/O — HOẠT ĐỘNG):
```
[01/140] [V01] ✓ Audio + ■ Video | 3.85s | Text: ちょっと、想像してみてください
[02/140] [V02] ✓ Audio + ■ Video | 3.84s | Text: 地球上で最も注目されているテック企業
...140 dòng
```
→ Chứng minh `log_func()` callback ĐƯỢC GỌI và message content ĐÚNG.

### ❌ Electron DevTools Console:
```
[PYTHON] sk1_xxx > {type: 'log', message: '[DEBUG] Starting cutting loop: 140 clips (via stderr)...'}
[PYTHON] sk1_xxx > {type: 'log', message: '[DEBUG] Loop done: 140 audio, 140 video clips processed'}
```
→ KHÔNG có bất kỳ message nào giữa 2 dòng này.

---

## 📁 FILES LIÊN QUAN

```
AuraSplit_v2/
├── electron/
│   ├── main.ts                    # Electron main + IPC setup
│   ├── preload.ts                 # contextBridge API
│   └── ipc/
│       └── python.ipc.ts          # spawn Python, stdout/stderr handlers
├── src/
│   ├── composables/
│   │   └── useAICut.ts            # Vue composable: startTask, onPythonMessage
│   └── views/
│       └── AICutView.vue          # UI: System Log, buttons
└── python/
    ├── api_wrapper.py             # emit(), emit_log() → print() to stdout
    ├── safe_kernel.py             # execute_safe() → subprocess.Popen (FFmpeg)
    ├── process_task.py            # _cutting_loop() → ffmpeg_runner + log_func callbacks
    └── engines/
        └── sk1_cutting.py         # process_workflow() → wraps callbacks → calls _cutting_loop
```

---

## ❓ CẦN GIẢI QUYẾT

1. **Tại sao** stdout/stderr writes thành công (không exception) nhưng data không đến Node.js pipe **CHỈ TRONG** `execute_safe` loop?

2. **`close_fds=True`** trên Windows cụ thể làm gì? Có close parent's inherited handles không?

3. **`CREATE_NEW_PROCESS_GROUP`** có ảnh hưởng parent process's pipe handles không?

4. **Giải pháp thay thế**: 
   - File-based polling (Python ghi file, Electron poll mỗi 200ms)?
   - Named pipe / Socket riêng cho per-clip logs?
   - Tắt `close_fds=True` / `CREATE_NEW_PROCESS_GROUP` cho FFmpeg subprocess?
   - Dùng threading để write stdout từ separate thread?

---

## 💡 GỢI Ý FIX TIỀM NĂNG

### Option A: Tắt `close_fds=True`
```python
# safe_kernel.py — thử close_fds=False
proc = subprocess.Popen(args, ..., close_fds=False, ...)
```

### Option B: File-based IPC cho per-clip logs
```python
# Python: ghi progress vào file
with open("clip_progress.jsonl", "a") as f:
    f.write(json.dumps({"clip": idx, "total": total, ...}) + "\n")

# Electron: poll file mỗi 200ms
setInterval(() => { readAndSendNewLines("clip_progress.jsonl") }, 200)
```

### Option C: Separate thread cho stdout writes
```python
import threading, queue
_log_queue = queue.Queue()

def _log_writer():
    while True:
        msg = _log_queue.get()
        if msg is None: break
        sys.stdout.write(json.dumps(msg) + '\n')
        sys.stdout.flush()

threading.Thread(target=_log_writer, daemon=True).start()

# Trong _tracked_log:
_log_queue.put({"type": "log", "message": msg})
```

### Option D: Tắt `CREATE_NEW_PROCESS_GROUP`
```python
creationflags = subprocess.CREATE_NO_WINDOW  # Bỏ CREATE_NEW_PROCESS_GROUP
```
