---
description: Build AuraSplit EXE với Embedded Python + Cython protection
---

// turbo-all

## Build AuraSplit v2 EXE

### 1. Kill stale processes
```powershell
taskkill /F /IM AuraSplit.exe 2>$null; taskkill /F /IM electron.exe 2>$null; Write-Host "✅ Killed stale processes"
```

### 1.5. Clean Cython build artifacts (prevent electron-builder from copying them)
```powershell
Remove-Item "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\python\build" -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "✅ Cleaned python/build/"
```

### 2. Build (vue-tsc + vite + electron-builder)
```powershell
cd c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2
npm run build
```

### 3. Copy FFmpeg binaries (symlink workaround)
```powershell
New-Item -ItemType Directory -Force "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\resources\binaries" | Out-Null
Copy-Item "c:\Users\datng\Desktop\AI_TOOL\ffmpeg.exe" "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\resources\binaries\ffmpeg.exe"
Copy-Item "c:\Users\datng\Desktop\AI_TOOL\ffprobe.exe" "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\resources\binaries\ffprobe.exe"
Write-Host "✅ Binaries copied"
```

### 3.5. Cython Protection (compile .py → .pyd)
```powershell
cd c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\python
& "c:\Users\datng\Desktop\AI_TOOL\.venv\Scripts\python.exe" setup_cython_v2.py
cd c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2
$dest = "release\0.0.0\win-unpacked\resources\python"
$src = "python"
Copy-Item "$src\process_task.cp311-win_amd64.pyd" "$dest\" -Force
Copy-Item "$src\model_checker.cp311-win_amd64.pyd" "$dest\" -Force
Copy-Item "$src\config\paths.cp311-win_amd64.pyd" "$dest\config\" -Force
Remove-Item "$dest\process_task.py" -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\model_checker.py" -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\config\paths.py" -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\setup_cython_v2.py" -Force -ErrorAction SilentlyContinue
Write-Host "✅ Cython protection applied (3 .pyd, source cleaned)"
```

### 4. Verify build output
```powershell
$exe = "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\AuraSplit.exe"
$pyds = Get-ChildItem "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\resources\python" -Recurse -Filter "*.pyd"
if ((Test-Path $exe) -and ($pyds.Count -ge 3)) { Write-Host "✅ Build OK: $exe ($($pyds.Count) .pyd protected)" } else { Write-Host "❌ BUILD FAILED" }
```

### 5. (Optional) Launch EXE to test
```powershell
Start-Process "c:\Users\datng\Desktop\AI_TOOL\AuraSplit_v2\release\0.0.0\win-unpacked\AuraSplit.exe"
```

## Notes
- Build output: `release/0.0.0/win-unpacked/AuraSplit.exe`
- `binaries/` is a symlink → electron-builder can't follow → manual copy needed
- `python_embed/` resolved via `../python_embed` in electron-builder.json5
- `models_ai/` NOT bundled (too large) → auto-created next to EXE on first run
- Code signing disabled (`signAndEditExecutable: false`)
- **Cython**: 3 files protected (.pyd), 7 files MUST stay .py (see BUILD_EXE_GUIDE.md)
