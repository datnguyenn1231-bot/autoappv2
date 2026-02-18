# ==============================================================================
# SK3: Image Flow Engine (Ken Burns Effect)
# Transcribe audio -> cut audio -> create video from images with duration
#
# v5.9.26 — FIX: subprocess crash in EXE mode (Antigravity diagnosis)
# ROOT CAUSE: process_task.pyd calls subprocess.run internally
#   → handle inheritance crash in PyInstaller --windowed mode
# FIX: Override _ffprobe_has_video_stream, _make_image_clip, _image_flow_loop
#   with local .py versions using safe_kernel callback pattern (same as SK1)
# ==============================================================================

from __future__ import annotations

import os
import re
import sys
import json
import random
import subprocess
import tempfile
import datetime
import threading
from typing import Callable, List, Tuple


# DEBUG: Write all log output to file for crash analysis (matching SK1 pattern)
DEBUG_LOG_PATH = None
_log_lock = threading.Lock()


def _init_debug_log():
    """Initialize debug log file in app directory."""
    global DEBUG_LOG_PATH
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        DEBUG_LOG_PATH = os.path.join(base_dir, "sk3_debug.log")
        with _log_lock:
            with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
                f.write(f"=== SK3 DEBUG LOG - {datetime.datetime.now()} ===\n")
    except Exception:
        pass


def _debug_log(msg: str):
    """Write to debug log file (thread-safe)."""
    global DEBUG_LOG_PATH
    if DEBUG_LOG_PATH:
        try:
            with _log_lock:
                with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                    f.write(f"{msg}\n")
        except Exception:
            pass


def is_frozen() -> bool:
    """Check if running as compiled EXE (Nuitka/PyInstaller).
    Uses multiple detection methods for reliability.
    """
    # Method 1: PyInstaller sets sys.frozen
    if getattr(sys, 'frozen', False):
        return True
    # Method 2: Check if running from .exe
    if sys.executable.lower().endswith('.exe'):
        # Exclude python.exe from venv
        exe_name = os.path.basename(sys.executable).lower()
        if exe_name not in ('python.exe', 'pythonw.exe'):
            return True
    # Method 3: Check for _MEIPASS (PyInstaller temp folder)
    if hasattr(sys, '_MEIPASS'):
        return True
    return False


def _get_app_root() -> str:
    """Get application root directory."""
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Core imports
from config.paths import _get_app_model_dir
from core.model_manager import (
    MODEL_CACHE, KEEP_MODEL_LOADED, StopRequested,
    aggressive_gc, check_vram_available
)
from core.ffmpeg import get_best_encoder

import safe_kernel

# === PROTECTED IMPORTS from process_task.pyd (Thin Wrapper v5.9.24) ===
# v5.9.26 FIX: REMOVED _ffprobe_has_video_stream, _make_image_clip, _image_flow_loop
# These functions call subprocess internally in .pyd → crash in EXE windowed mode
# Now defined LOCALLY in this .py file using safe_kernel callback pattern
from process_task import (
    _match_words_to_script,
    _extract_words_with_fallback as _extract_words_core,
    _clean_text as clean_text,
    _parse_script as parse_script,
    _normalize_lang_code as normalize_lang_code,
    _list_visual_files_recursive,
    _get_display_name,
)

# Module-level state
STOP_FLAG = False
CONFIG = {
    "audio_full_path": "",
    "script_path": "",
    "video_source_dir": "",
    "image_source_dir": "",
    "output_dir": "",
    "model_cache_dir": _get_app_model_dir(),
    "effect_type": "kenburns",
}


def set_stop_signal(val: bool) -> None:
    global STOP_FLAG
    STOP_FLAG = bool(val)


def set_config(config_dict: dict) -> None:
    global CONFIG
    CONFIG.update(config_dict)


# ==============================================================================
# LOCAL OVERRIDES — Functions that use subprocess (MUST stay in .py)
# These were previously imported from process_task.pyd but crash in
# PyInstaller --windowed mode due to handle inheritance issues.
# Pattern: same fix as safe_kernel.py, core/ffmpeg.py (3-AI Consensus)
# ==============================================================================

# Windows subprocess flags to prevent CMD window flashing
if sys.platform == "win32":
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = subprocess.SW_HIDE
else:
    _SUBPROCESS_FLAGS = 0
    _STARTUPINFO = None


def _get_ffmpeg_path() -> str:
    """Get absolute path to ffmpeg.exe (matching SK1 pattern)."""
    app_root = _get_app_root()
    exe_path = os.path.join(app_root, "ffmpeg.exe")
    if os.path.exists(exe_path):
        return exe_path
    exe_path = os.path.join(app_root, "_internal", "ffmpeg.exe")
    if os.path.exists(exe_path):
        return exe_path
    return "ffmpeg"


def _get_ffprobe_path() -> str:
    """Get absolute path to ffprobe.exe."""
    app_root = _get_app_root()
    exe_path = os.path.join(app_root, "ffprobe.exe")
    if os.path.exists(exe_path):
        return exe_path
    exe_path = os.path.join(app_root, "_internal", "ffprobe.exe")
    if os.path.exists(exe_path):
        return exe_path
    return "ffprobe"


def _ffprobe_has_video_stream(path: str) -> bool:
    """LOCAL OVERRIDE — check if file has video stream.
    v5.9.26: Moved from process_task.pyd to .py to avoid subprocess crash.
    """
    try:
        cp = subprocess.run(
            [
                _get_ffprobe_path(),
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "default=noprint_wrappers=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_SUBPROCESS_FLAGS,
            startupinfo=_STARTUPINFO,
        )
        if cp.returncode != 0:
            return False
        w = h = 0
        for line in (cp.stdout or "").splitlines():
            if line.startswith("width="):
                w = int((line.split("=", 1)[-1].strip() or "0"))
            elif line.startswith("height="):
                h = int((line.split("=", 1)[-1].strip() or "0"))
        return w > 0 and h > 0
    except Exception:
        return False


def _run_ffmpeg(cmd: List[str]) -> None:
    """LOCAL — run ffmpeg command with proper flags.
    v5.9.26: Uses safe_kernel.execute_safe with cwd (matching SK1 pattern).
    """
    if STOP_FLAG:
        raise StopRequested()
    # Use absolute ffmpeg path
    if cmd and cmd[0].lower() in ("ffmpeg", "ffmpeg.exe"):
        cmd = list(cmd)
        cmd[0] = _get_ffmpeg_path()
    # Ensure output directory exists
    if len(cmd) > 1:
        output_path = cmd[-1]
        if isinstance(output_path, str) and not output_path.startswith('-'):
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
    try:
        app_root = _get_app_root()
        safe_kernel.execute_safe(cmd, cwd=app_root)
    except RuntimeError as e:
        if "STOPPED" in str(e).upper():
            raise StopRequested()
        raise


def _make_image_clip(
    image_path: str,
    out_path: str,
    duration: float,
    canvas_w: int,
    canvas_h: int,
    enc_name: str,
    enc_preset: str,
    effect_type: str = "kenburns",
) -> None:
    """LOCAL OVERRIDE — create video clip from image with Ken Burns effect.
    v5.9.26: Moved from process_task.pyd to avoid subprocess crash.
    Uses safe_kernel.execute_safe instead of internal _run().
    """
    fps = 30
    dur = max(0.10, float(duration))
    frames = max(1, int(dur * fps))

    # Detect if input is video or image
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    ext = os.path.splitext(image_path)[1].lower()
    is_video = ext in video_exts

    # Map UI names to internal effect names
    effect_lower = (effect_type or "").strip().lower()
    effect_map = {
        "kenburns (zoom)": "zoom_in", "kenburns": "zoom_in",
        "zoom_in": "zoom_in", "zoom in": "zoom_in",
        "zoom in (center)": "zoom_in", "zoom out (center)": "zoom_out",
        "pan left → right": "pan_left", "pan right → left": "pan_right",
        "zoom in + pan": "zoom_pan", "random": "random",
        "không hiệu ứng": "none", "none": "none", "static": "none",
    }
    internal_effect = effect_map.get(effect_lower, effect_lower)

    if internal_effect == "random":
        internal_effect = random.choice(["zoom_in", "zoom_out"])

    scaled_w = int(canvas_w * 1.15)
    scaled_h = int(canvas_h * 1.15)

    # Build VF filter based on effect type
    if internal_effect in ("none", "static"):
        vf = (
            "scale={w}:{h}:force_original_aspect_ratio=increase,"
            "crop={w}:{h},format=yuv420p"
        ).format(w=canvas_w, h=canvas_h)
    elif internal_effect == "zoom_out":
        vf = (
            "scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop={sw}:{sh},"
            "zoompan=z='1.15-0.10*sin(on/{frames}*PI/2)':"
            "x='0':y='0':d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
        ).format(sw=scaled_w, sh=scaled_h, w=canvas_w, h=canvas_h, frames=frames, fps=fps)
    elif internal_effect == "pan_left":
        vf = (
            "scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop={sw}:{sh},"
            "zoompan=z='1.0':x='(iw-ow)*on/{frames}':y='0':"
            "d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
        ).format(sw=scaled_w, sh=scaled_h, w=canvas_w, h=canvas_h, frames=frames, fps=fps)
    elif internal_effect == "pan_right":
        vf = (
            "scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop={sw}:{sh},"
            "zoompan=z='1.0':x='(iw-ow)*(1-on/{frames})':y='0':"
            "d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
        ).format(sw=scaled_w, sh=scaled_h, w=canvas_w, h=canvas_h, frames=frames, fps=fps)
    else:
        # Default: zoom_in — smooth Ken Burns
        vf = (
            "scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop={sw}:{sh},"
            "zoompan=z='1.0+0.10*sin(on/{frames}*PI/2)':"
            "x='0':y='0':d={frames}:s={w}x{h}:fps={fps},format=yuv420p"
        ).format(sw=scaled_w, sh=scaled_h, w=canvas_w, h=canvas_h, frames=frames, fps=fps)

    if is_video:
        cmd = [
            "ffmpeg", "-y", "-i", image_path, "-t", str(dur),
            "-vf", vf, "-an", "-r", str(fps),
            "-c:v", enc_name, "-preset", enc_preset,
            "-pix_fmt", "yuv420p", "-map_metadata", "-1",
            "-movflags", "+faststart", "-loglevel", "error", out_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-frames:v", str(frames), "-vf", vf, "-an", "-r", str(fps),
            "-c:v", enc_name, "-preset", enc_preset,
            "-pix_fmt", "yuv420p", "-map_metadata", "-1",
            "-movflags", "+faststart", "-loglevel", "error", out_path,
        ]

    _run_ffmpeg(cmd)


def _image_flow_loop(
    matches: list,
    audio_path: str,
    out_aud: str,
    out_vid: str,
    files: list,
    start_idx: int,
    canvas_w: int,
    canvas_h: int,
    enc_name: str,
    enc_preset: str,
    effect_type: str,
    ffmpeg_runner,           # callback: run_ffmpeg_fast(cmd_list)
    log_func,                # callback: log_func(msg)
    stop_check,              # callback: lambda: STOP_FLAG
    gc_func=None,            # callback: aggressive_gc()
):
    """LOCAL OVERRIDE — Image flow cutting loop.
    v5.9.26: Moved from process_task.pyd to avoid subprocess crash.
    Uses local _ffprobe_has_video_stream and _make_image_clip (both .py).
    """
    total = len(matches)
    cursor = start_idx
    processed = 0

    for idx, (vid, s_time, e_time, text) in enumerate(matches, 1):
        if stop_check():
            log_func("🛑 STOPPED.")
            break

        # Periodic GC every 20 clips
        if idx % 20 == 0 and gc_func:
            gc_func()

        duration = max(0.10, e_time - s_time)

        # ── Cut Audio ──
        a_out = os.path.join(out_aud, f"{str(vid).zfill(3)}.mp3")
        try:
            ffmpeg_runner([
                "ffmpeg", "-y",
                "-ss", str(s_time),
                "-to", str(e_time),
                "-i", audio_path,
                "-vn", "-acodec", "libmp3lame",
                "-q:a", "2",
                "-loglevel", "error",
                a_out,
            ])
        except Exception as audio_err:
            log_func(f"❌ [V{str(vid).zfill(2)}] Audio cut FAILED: {audio_err}")
            continue

        # ── Pick next readable visual file (round-robin) ──
        picked = None
        tries = 0
        while tries < len(files):
            p = files[cursor % len(files)]
            cursor += 1
            tries += 1
            if _ffprobe_has_video_stream(p):  # LOCAL .py version — no .pyd crash!
                picked = p
                break
        if not picked:
            log_func(f"❌ [V{str(vid).zfill(2)}] No readable visual file found")
            continue

        # ── Create video clip with Ken Burns effect ──
        v_out = os.path.join(out_vid, f"{str(vid).zfill(3)}.mp4")
        try:
            _make_image_clip(  # LOCAL .py version — uses safe_kernel!
                picked, v_out, duration, canvas_w, canvas_h,
                enc_name, enc_preset, effect_type
            )
        except Exception:
            # Fallback: use software encoder
            _make_image_clip(
                picked, v_out, duration, canvas_w, canvas_h,
                "libx264", "ultrafast", effect_type
            )

        text_display = text[:40] + "..." if len(text) > 40 else text
        log_func(
            f"[{str(idx).zfill(2)}/{total}] [V{str(vid).zfill(2)}] "
            f"✓ Audio + 🖼️ Image | {duration:.2f}s | Text: {text_display}"
        )

        processed += 1

    return processed


# All AI logic → process_task.pyd (_get_display_name, _dev_transcribe_pipeline, etc.)


def _run_ai_subprocess(
    audio_path: str,
    model_name: str,
    lang_code: str,
    fast_mode: bool,
    model_cache_dir: str,
    log_func: Callable[[str], None],
) -> dict:
    """EXE mode: Run AI transcription via subprocess — thin wrapper."""
    from process_task import _run_ai_subprocess_generic
    return _run_ai_subprocess_generic(
        audio_path=audio_path,
        model_name=model_name,
        lang_code=lang_code,
        fast_mode=fast_mode,
        model_cache_dir=model_cache_dir,
        worker_script_name="sk3_worker.py",
        app_root=_get_app_root(),
        log_func=log_func,
    )


def _transcribe_with_auto(model, audio, lang_code):
    lang_for_transcribe = normalize_lang_code(lang_code)
    kwargs = {"batch_size": 2}
    if lang_for_transcribe is not None:
        kwargs["language"] = lang_for_transcribe
    result = model.transcribe(audio, **kwargs)
    detected_lang = result.get("language") or lang_for_transcribe or "en"
    return result, detected_lang


# _extract_words_with_fallback → imported from process_task.pyd as _extract_words_core


def _ensure_out_dirs() -> Tuple[str, str]:
    """Create output directories. Uses CONFIG global — stays in wrapper."""
    out_aud = os.path.join(CONFIG["output_dir"], "audios")
    out_vid = os.path.join(CONFIG["output_dir"], "videos")
    os.makedirs(out_aud, exist_ok=True)
    os.makedirs(out_vid, exist_ok=True)
    return out_aud, out_vid

# _list_visual_files_recursive → imported from process_task.pyd (pure Python, no subprocess — safe)


def run_ffmpeg_fast(cmd_list: List[str]) -> None:
    """Execute FFmpeg with stop signal support.
    v5.9.26 FIX: Added cwd=app_root (matching SK1 pattern).
    """
    if STOP_FLAG:
        raise StopRequested()

    # Use absolute path for ffmpeg (matching SK1)
    if cmd_list and cmd_list[0].lower() in ("ffmpeg", "ffmpeg.exe"):
        cmd_list = list(cmd_list)
        cmd_list[0] = _get_ffmpeg_path()

    if len(cmd_list) > 1:
        output_path = cmd_list[-1]
        if isinstance(output_path, str) and not output_path.startswith('-'):
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
    try:
        app_root = _get_app_root()
        safe_kernel.execute_safe(cmd_list, cwd=app_root)  # v5.9.26: Added cwd!
    except RuntimeError as e:
        if "STOPPED" in str(e).upper():
            raise StopRequested()
        raise


def start_download_monitor(model_name, log_func):
    """Disabled download monitor - returns None for compatibility."""
    log_func("      💡 Download progress will appear in terminal/console")
    return None, None


def stop_download_monitor(stop_event):
    if stop_event:
        stop_event.set()


def process_image_flow(lang_code, model_name, log_func: Callable[[str], None], fast_mode=False):
    """
    SK3: Image Flow workflow.
    Transcribe audio -> cut audio -> create video from images.

    DEV mode: Uses whisperx directly from .venv
    EXE mode: Calls python_embed via subprocess
    """
    global STOP_FLAG, MODEL_CACHE

    # v5.9.26 CRASH DETECTIVE — ultra-fine markers (BEFORE try-except!)
    import faulthandler as _fh
    _crash_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    _crash_file = os.path.join(_crash_dir, "SK3_CRASH_DETAIL.txt")
    def _cm(step):
        try:
            with open(_crash_file, "a", encoding="utf-8") as _f:
                import datetime as _dt
                _f.write(f"[{_dt.datetime.now()}] {step}\n")
                _f.flush()
        except Exception:
            pass
    _cm("SK3-A: Entered process_image_flow")

    # Enable faulthandler (writes segfault traceback to file)
    try:
        _fh_file = open(os.path.join(_crash_dir, "SK3_SEGFAULT.txt"), "w")
        _fh.enable(file=_fh_file, all_threads=True)
        _cm("SK3-B: faulthandler enabled")
    except Exception:
        _cm("SK3-B: faulthandler FAILED (non-fatal)")

    try:
        _cm("SK3-C: Before STOP_FLAG=False")
        STOP_FLAG = False
        _cm("SK3-D: Before _ensure_out_dirs")
        out_aud, out_vid = _ensure_out_dirs()
        _cm(f"SK3-E: out_dirs OK: {out_aud}")

        # Initialize debug log for crash analysis (matching SK1 pattern)
        _init_debug_log()
        _cm("SK3-F: debug log initialized")

        # === File-based IPC — start EARLY so AI phase logs reach the UI ===
        import json as _json
        import tempfile as _tempfile
        _progress_file = os.path.join(_tempfile.gettempdir(), f"aurasplit_progress_{os.getpid()}.jsonl")

        def _file_emit(msg_type, **kwargs):
            """Write JSON to progress file — guaranteed to work during GPU load."""
            payload = {k: v.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').strip()
                       if isinstance(v, str) else v
                       for k, v in kwargs.items()}
            payload["type"] = msg_type
            try:
                with open(_progress_file, "a", encoding="utf-8") as f:
                    f.write(_json.dumps(payload, ensure_ascii=False) + '\n')
            except Exception:
                pass

        # Wrap log_func to also write to debug file
        original_log_func = log_func
        def log_func(msg):
            _debug_log(msg)
            original_log_func(msg)

        _cm("SK3-G: Before _list_visual_files_recursive")
        files = _list_visual_files_recursive(CONFIG["image_source_dir"])
        _cm(f"SK3-H: Got {len(files)} files from image dir")
        if not files:
            raise RuntimeError(f"Image folder empty/not found: {CONFIG['image_source_dir']}")

        # v5.9.26: Use LOCAL _ffprobe_has_video_stream (not from .pyd!)
        _cm("SK3-I: Before ffprobe loop")
        start_idx = None
        for i, p in enumerate(files):
            _cm(f"SK3-I-{i}: ffprobe checking: {os.path.basename(p)}")
            if _ffprobe_has_video_stream(p):
                start_idx = i
                _cm(f"SK3-I-{i}: FOUND valid file at index {i}")
                break
        if start_idx is None:
            raise RuntimeError("Không có file ảnh/video nào ffprobe đọc được.")

        _cm("SK3-J: Before aspect ratio detection")
        # Auto-detect aspect ratio
        first_file = files[start_idx]
        try:
            probe_cmd = [
                _get_ffprobe_path(), "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x",
                first_file
            ]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10,
                                          creationflags=_SUBPROCESS_FLAGS, startupinfo=_STARTUPINFO)
            if probe_result.returncode == 0 and probe_result.stdout.strip():
                dims = probe_result.stdout.strip().split("x")
                input_w, input_h = int(dims[0]), int(dims[1])
                if input_w > input_h:
                    canvas_w, canvas_h = 1920, 1080
                    log_func(f"📐 Detected: {input_w}x{input_h} → Output: 16:9 (1920x1080)")
                else:
                    canvas_w, canvas_h = 1080, 1920
                    log_func(f"📐 Detected: {input_w}x{input_h} → Output: 9:16 (1080x1920)")
            else:
                canvas_w, canvas_h = 1080, 1920
                log_func("📐 Could not detect aspect ratio, using default 9:16")
        except Exception as e:
            canvas_w, canvas_h = 1080, 1920
            log_func(f"📐 Error detecting aspect ratio: {e}, using default 9:16")

        _cm("SK3-K: Before AI transcription")
        mode_text = "FAST" if fast_mode else "PRO"
        log_func(f"🖼️ IMAGE FLOW: {_get_display_name(model_name)} | Mode: {mode_text}")

        # ========== AI TRANSCRIPTION (EXE vs DEV mode) ==========
        if is_frozen():
            # EXE MODE: Use subprocess with python_embed
            log_func("[EXE MODE] Using embedded Python for AI...")
            try:
                log_func("[DEBUG-EXE] Calling _run_ai_subprocess...")
                _cm("SK3-L: Before _run_ai_subprocess")
                ai_result = _run_ai_subprocess(
                    audio_path=CONFIG["audio_full_path"],
                    model_name=model_name,
                    lang_code=lang_code,
                    fast_mode=fast_mode,
                    model_cache_dir=CONFIG["model_cache_dir"],
                    log_func=log_func,
                )
                _cm("SK3-M: _run_ai_subprocess returned OK")
                log_func(f"[DEBUG-EXE] ai_result type: {type(ai_result)}")
            except Exception as e:
                import traceback
                log_func(f"[CRASH-1] _run_ai_subprocess failed: {e}")
                _debug_log(f"[CRASH-1] TRACEBACK:\n{traceback.format_exc()}")
                raise

            try:
                all_words = ai_result.get("words", [])
                log_func(f"[DEBUG-EXE] Got {len(all_words)} words from AI result")
                detected_lang = ai_result.get("language", "en")
            except Exception as e:
                import traceback
                log_func(f"[CRASH-2] Word extraction failed: {e}")
                _debug_log(f"[CRASH-2] TRACEBACK:\n{traceback.format_exc()}")
                raise
        else:
            # DEV MODE: Direct import → callbacks to .pyd pipeline
            log_func("[DEV MODE] Using direct whisperx import...")
            import torch
            import whisperx

            check_vram_available(log_func, min_gb=5)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            log_func(f"      > Device: {device.upper()}")

            from process_task import _dev_transcribe_pipeline
            all_words, detected_lang = _dev_transcribe_pipeline(
                audio_path=CONFIG["audio_full_path"],
                model_name=model_name,
                lang_code=lang_code,
                fast_mode=fast_mode,
                model_cache_dir=CONFIG["model_cache_dir"],
                device=device,
                compute_type=compute_type,
                load_model_fn=whisperx.load_model,
                load_audio_fn=whisperx.load_audio,
                load_align_fn=whisperx.load_align_model,
                align_fn=whisperx.align,
                empty_cache_fn=torch.cuda.empty_cache if device == "cuda" else lambda: None,
                model_cache=MODEL_CACHE,
                keep_model_loaded=KEEP_MODEL_LOADED,
                log_func=log_func,
                stop_check=lambda: STOP_FLAG,
                gc_func=aggressive_gc,
            )

        # ========== IMAGE FLOW CUTTING (shared code) ==========
        if STOP_FLAG:
            return log_func("🛑 ĐÃ DỪNG.")

        # AI Studio Fix: Release GPU context before FFmpeg starts
        from process_task import ai_to_ffmpeg_handover
        ai_to_ffmpeg_handover(log_func)

        log_func("[DEBUG] AI result received, preparing cutting phase...")

        try:
            with open(CONFIG["script_path"], "r", encoding="utf-8") as f:
                script_items = parse_script(f.read())
            if not script_items:
                raise RuntimeError("Script parse empty. Format: [V1] ... [V2] ...")
            log_func(f"[DEBUG] Parsed {len(script_items)} script items")
        except Exception as e:
            log_func(f"[ERROR] Script parsing failed: {e}")
            raise

        enc_name, enc_preset = get_best_encoder(log_func)

        # === CORE ALGORITHM: Match words to script (PROTECTED in .pyd) ===
        matches = _match_words_to_script(all_words, script_items, log_func)

        log_func(f"[3/3] Cutting {len(matches)} IMAGE clips...")

        # === Cutting state for per-clip progress ===
        _total_clips = len(matches)

        _clip_counter = {"done": 0}

        def _tracked_log_sk3(msg):
            """Per-clip log via file-based IPC."""
            _file_emit("log", message=msg)
            # Also emit progress for per-clip messages
            if msg and "[V" in msg and "✓" in msg:
                _clip_counter["done"] += 1
                n = _clip_counter["done"]
                pct = int(30 + (n / _total_clips) * 65)
                _file_emit("progress", percent=min(pct, 95), message=f"Clip {n}/{_total_clips}")

        # === IMAGE FLOW LOOP (LOCAL .py version — v5.9.26 FIX) ===
        _image_flow_loop(
            matches=matches,
            audio_path=CONFIG["audio_full_path"],
            out_aud=out_aud,
            out_vid=out_vid,
            files=files,
            start_idx=start_idx,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            enc_name=enc_name,
            enc_preset=enc_preset,
            effect_type=CONFIG.get("effect_type", "kenburns"),
            ffmpeg_runner=run_ffmpeg_fast,
            log_func=_tracked_log_sk3,
            stop_check=lambda: STOP_FLAG,
            gc_func=aggressive_gc,
        )

        aggressive_gc()
        if not STOP_FLAG:
            log_func("🎉 IMAGE FLOW COMPLETED!")

    except StopRequested:
        STOP_FLAG = True
        log_func("🛑 ĐÃ DỪNG (STOP).")
        return
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        log_func(f"❌ IMAGE FLOW ERROR: {str(e)}")
        _debug_log(f"FATAL ERROR: {error_msg}")
        # Write to separate fatal log for analysis
        try:
            if getattr(sys, 'frozen', False):
                fatal_path = os.path.join(os.path.dirname(sys.executable), "FATAL_SK3.log")
            else:
                fatal_path = os.path.join(os.path.dirname(__file__), "FATAL_SK3.log")
            with open(fatal_path, "w", encoding="utf-8") as f:
                f.write(f"=== FATAL SK3 ERROR ===\n")
                f.write(f"Time: {datetime.datetime.now()}\n")
                f.write(f"Error: {str(e)}\n\n")
                f.write(f"Full traceback:\n{error_msg}\n")
        except Exception:
            pass
        raise
