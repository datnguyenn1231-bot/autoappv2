# ==============================================================================
# SK1: Video Cutting Engine (WhisperX AI)
# Transcribe audio -> align text -> match script -> cut video/audio
# ==============================================================================

from __future__ import annotations

import os
import re
import sys
import json
import subprocess
import tempfile
import datetime
from typing import Callable, List, Optional, Tuple

# DEBUG: Write all log output to file for crash analysis
DEBUG_LOG_PATH = None
import threading
_log_lock = threading.Lock()  # Thread-safe logging to prevent garbled output

# ==============================================================================
# NOISE FILTER: Suppress 3rd-party library messages from subprocess output
# These are informational/deprecation messages that clutter user logs
# ==============================================================================
_NOISE_PATTERNS = [
    "pkg_resources is deprecated",
    "resume_download",
    "gradient_checkpointing",
    "TensorFloat-32",
    "ReproducibilityWarning",
    "Ignored unknown kwarg",
    "Some weights",
    "not used when initializing",
    "not initialized from the model",
    "TRAIN this model",
    "Lightning automatically upgraded",
    "Model was trained with",
    "Bad things might happen",
    "whisperx.asr",
    "whisperx.vads",
    "Performing voice activity detection",
    "No language specified",
    "pyannote",
    "pytorch_lightning",
    "This IS expected if you are initializing",
    "This IS NOT expected",
    "wav2vec2.encoder.pos_conv_embed",
    "UserWarning:",
    "FutureWarning:",
    "newly initialized:",
    "checkpoint of a model trained on another task",
]

def _is_noise(line: str) -> bool:
    """Check if a line matches noise patterns and should be filtered."""
    return any(pattern in line for pattern in _NOISE_PATTERNS)

def _init_debug_log():
    """Initialize debug log file in app directory."""
    global DEBUG_LOG_PATH
    try:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        DEBUG_LOG_PATH = os.path.join(base_dir, "sk1_debug.log")
        with _log_lock:
            with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as f:
                f.write(f"=== SK1 DEBUG LOG - {datetime.datetime.now()} ===\n")
    except Exception:
        pass

def _debug_log(msg: str):
    """Write to debug log file (thread-safe)."""
    global DEBUG_LOG_PATH
    if DEBUG_LOG_PATH:
        try:
            with _log_lock:  # Ensure only one thread writes at a time
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
from core.exceptions import StopRequestedError
from core.model_manager import (
    MODEL_CACHE, KEEP_MODEL_LOADED,
    aggressive_gc, check_vram_available
)
from core.ffmpeg import FFMPEG_THREADS, get_best_encoder

import safe_kernel

# === PROTECTED IMPORTS from process_task.pyd (Thin Wrapper v5.9.24) ===
from process_task import (
    _match_words_to_script,
    _extract_words_with_fallback as _extract_words_core,
    _clean_text as clean_text,
    _parse_script as parse_script,
    _normalize_lang_code as normalize_lang_code,
    _find_video_by_vid_any_ext as _find_video_source_any_ext,
    _cutting_loop,
    _get_display_name,
)

# Backward compatibility alias
StopRequested = StopRequestedError

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
    """Update CONFIG from external source."""
    global CONFIG
    CONFIG.update(config_dict)

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
        worker_script_name="sk1_worker.py",
        app_root=_get_app_root(),
        log_func=log_func,
        noise_filter=_is_noise,
    )


def _ensure_out_dirs() -> Tuple[str, str]:
    """Create output directories. Uses CONFIG global — stays in wrapper."""
    out_aud = os.path.join(CONFIG["output_dir"], "audios")
    out_vid = os.path.join(CONFIG["output_dir"], "videos")
    os.makedirs(out_aud, exist_ok=True)
    os.makedirs(out_vid, exist_ok=True)
    return out_aud, out_vid

# _find_video_source_any_ext → imported from process_task.pyd


def _get_ffmpeg_path() -> str:
    """Get absolute path to ffmpeg.exe (AI Studio Fix #3)."""
    app_root = _get_app_root()
    # Check root first (where we copied it)
    exe_path = os.path.join(app_root, "ffmpeg.exe")
    if os.path.exists(exe_path):
        return exe_path
    # Fallback to _internal
    exe_path = os.path.join(app_root, "_internal", "ffmpeg.exe")
    if os.path.exists(exe_path):
        return exe_path
    # Last resort: assume it's in PATH
    return "ffmpeg"


def run_ffmpeg_fast(cmd_list: List[str]) -> None:
    """Execute FFmpeg with stop signal support."""
    if STOP_FLAG:
        raise StopRequested()

    # AI Studio Fix #3: Use absolute path for ffmpeg
    if cmd_list and cmd_list[0].lower() in ("ffmpeg", "ffmpeg.exe"):
        cmd_list = list(cmd_list)  # Make copy to avoid mutating
        cmd_list[0] = _get_ffmpeg_path()

    if len(cmd_list) > 1:
        output_path = cmd_list[-1]
        if isinstance(output_path, str) and not output_path.startswith('-'):
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

    try:
        # EXE mode fix: pass cwd so subprocess finds ffmpeg in app directory
        app_root = _get_app_root()
        safe_kernel.execute_safe(cmd_list, cwd=app_root)
    except RuntimeError as e:
        if "STOPPED" in str(e).upper():
            raise StopRequested()
        raise



def process_workflow(lang_code, model_name, log_func: Callable[[str], None], fast_mode=False):
    """
    SK1: Main cutting workflow.
    Transcribe audio -> align -> match script -> cut audio + video.

    DEV mode: Uses whisperx directly from .venv
    EXE mode: Calls python_embed via subprocess
    """
    global STOP_FLAG, MODEL_CACHE

    try:
        STOP_FLAG = False
        out_aud, out_vid = _ensure_out_dirs()
        
        # Initialize debug log for crash analysis
        _init_debug_log()

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
            _debug_log(msg)  # Write to debug file
            original_log_func(msg)  # Write to stdout (api_wrapper emit_log)

        mode_text = "FAST" if fast_mode else "PRO CUT"
        log_func(f"⚡ AI Engine: {_get_display_name(model_name)} | Mode: {mode_text}")

        # ========== AI TRANSCRIPTION (EXE vs DEV mode) ==========
        if is_frozen():
            # EXE MODE: Use subprocess with python_embed
            log_func("[EXE MODE] Using embedded Python for AI...")
            try:
                log_func("[DEBUG-EXE] Calling _run_ai_subprocess...")
                ai_result = _run_ai_subprocess(
                    audio_path=CONFIG["audio_full_path"],
                    model_name=model_name,
                    lang_code=lang_code,
                    fast_mode=fast_mode,
                    model_cache_dir=CONFIG["model_cache_dir"],
                    log_func=log_func,
                )
                log_func(f"[DEBUG-EXE] ai_result type: {type(ai_result)}")
                log_func(f"[DEBUG-EXE] ai_result keys: {list(ai_result.keys()) if isinstance(ai_result, dict) else 'NOT DICT'}")
            except Exception as e:
                import traceback
                log_func(f"[CRASH-1] _run_ai_subprocess failed: {e}")
                _debug_log(f"[CRASH-1] TRACEBACK:\n{traceback.format_exc()}")
                raise

            try:
                all_words = ai_result.get("words", [])
                log_func(f"[DEBUG-EXE] Got {len(all_words)} words from AI result")
                detected_lang = ai_result.get("language", "en")
                log_func(f"[DEBUG-EXE] Detected language: {detected_lang}")
            except Exception as e:
                import traceback
                log_func(f"[CRASH-2] Word extraction failed: {e}")
                _debug_log(f"[CRASH-2] TRACEBACK:\n{traceback.format_exc()}")
                raise
        else:
            # DEV MODE: Direct import → callbacks to .pyd pipeline
            log_func("⏳ Loading AI dependencies (torch + whisperx)...")
            _file_emit("log", message="⏳ Loading AI dependencies (torch + whisperx)...")
            _file_emit("progress", percent=5, message="Loading AI dependencies...")
            import torch
            import whisperx
            log_func("✅ AI dependencies loaded!")

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

        # ========== CUTTING (shared code) ==========
        if STOP_FLAG:
            return log_func("🛑 ĐÃ DỪNG.")

        # AI Studio Fix: Release GPU context before FFmpeg starts
        from process_task import ai_to_ffmpeg_handover
        ai_to_ffmpeg_handover(log_func)

        # DEBUG: Log progress to find crash point
        log_func("[DEBUG] AI result received, preparing cutting phase...")
        
        try:
            log_func(f"[DEBUG] Script path: {CONFIG['script_path']}")
            with open(CONFIG["script_path"], "r", encoding="utf-8") as f:
                script_content = f.read()
            log_func(f"[DEBUG] Script content length: {len(script_content)} chars")
            script_items = parse_script(script_content)
            log_func(f"[DEBUG] Parsed {len(script_items)} script items")
        except Exception as e:
            log_func(f"[ERROR] Script parsing failed: {e}")
            raise

        # === CORE ALGORITHM: Match words to script (PROTECTED in .pyd) ===
        matches = _match_words_to_script(all_words, script_items, log_func)

        log_func(f"[3/3] Cutting {len(matches)} RAW clips...")
        enc_name, enc_preset = get_best_encoder(log_func)

        # === Cutting state for per-clip progress ===
        _total_clips = len(matches)
        _clip_state = {"audio_done": 0, "video_done": 0}

        def _tracked_ffmpeg(cmd_list):
            """Wraps run_ffmpeg_fast — tracks clip progress via file IPC."""
            run_ffmpeg_fast(cmd_list)
            if cmd_list:
                out_file = str(cmd_list[-1])
                if out_file.endswith('.mp3'):
                    _clip_state["audio_done"] += 1
                elif out_file.endswith('.mp4'):
                    _clip_state["video_done"] += 1
                    n = _clip_state["video_done"]
                    pct = int(30 + (n / _total_clips) * 65)
                    # Only emit progress here; detailed log comes from _tracked_log
                    _file_emit("progress", percent=min(pct, 95), message=f"Clip {n}/{_total_clips}")

        def _tracked_log(msg):
            """Per-clip log via file-based IPC."""
            _file_emit("log", message=msg)

        log_func(f"[DEBUG] Starting cutting loop: {_total_clips} clips...")

        # === CUTTING LOOP (PROTECTED in .pyd — callback bridge) ===
        _cutting_loop(
            matches=matches,
            audio_path=CONFIG["audio_full_path"],
            video_source_dir=CONFIG["video_source_dir"],
            out_aud=out_aud,
            out_vid=out_vid,
            enc_name=enc_name,
            enc_preset=enc_preset,
            ffmpeg_threads=FFMPEG_THREADS,
            ffmpeg_runner=_tracked_ffmpeg,
            log_func=_tracked_log,
            stop_check=lambda: STOP_FLAG,
            gc_func=aggressive_gc,
        )

        # Report final clip count — emitted via log_func (stdout works after loop)
        log_func(f"[DEBUG] Loop done: {_clip_state['audio_done']} audio, {_clip_state['video_done']} video clips processed")

        # ── Per-clip summary: duration stats ──
        total_duration = sum(e - s for _, s, e, _ in matches)
        avg_duration = total_duration / len(matches) if matches else 0
        min_dur = min((e - s for _, s, e, _ in matches), default=0)
        max_dur = max((e - s for _, s, e, _ in matches), default=0)
        log_func(f"📊 CLIP SUMMARY: {_clip_state['audio_done']} clips | Total: {total_duration:.1f}s | Avg: {avg_duration:.1f}s | Min: {min_dur:.1f}s | Max: {max_dur:.1f}s")

        # Show first 5 and last 3 clips for quick verification
        sample_lines = []
        show_clips = matches[:5] + ([('...', 0, 0, '...')] if len(matches) > 8 else []) + matches[-3:] if len(matches) > 8 else matches
        for idx_m, (vid, s, e, txt) in enumerate(show_clips):
            if vid == '...':
                sample_lines.append("   ...")
            else:
                txt_short = txt.replace('\n', ' ').replace('\r', '')[:35]
                sample_lines.append(f"   [V{str(vid).zfill(2)}] {s:.2f}s→{e:.2f}s ({e-s:.2f}s) | {txt_short}")
        for sl in sample_lines:
            log_func(sl)

        # Show output directory path
        out_dir = CONFIG.get("output_dir", "")
        log_func(f"📁 Output: {out_dir}")

        # Write clip debug info to file for diagnostics
        try:
            debug_path = os.path.join(os.path.dirname(__file__), "cutting_debug.log")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(f"Total matches: {_total_clips}\n")
                f.write(f"Audio clips processed: {_clip_state['audio_done']}\n")
                f.write(f"Video clips processed: {_clip_state['video_done']}\n")
                f.write(f"Total duration: {total_duration:.1f}s\n")
                f.write(f"Avg duration: {avg_duration:.1f}s | Min: {min_dur:.1f}s | Max: {max_dur:.1f}s\n")
                for vid, s, e, txt in matches:
                    txt_clean = txt.replace('\n', ' ').replace('\r', '')[:50]
                    f.write(f"[V{str(vid).zfill(2)}] {s:.2f}→{e:.2f} ({e-s:.2f}s) {txt_clean}\n")
        except Exception:
            pass

        aggressive_gc()
        if not STOP_FLAG:
            log_func("🎉 CUTTING COMPLETED!")

    except StopRequested:
        STOP_FLAG = True
        log_func("🛑 ĐÃ DỪNG (STOP).")
        return
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        log_func(f"❌ CRITICAL CUTTING ERROR: {str(e)}")
        _debug_log(f"FATAL ERROR: {error_msg}")
        # Write to separate fatal log for analysis
        try:
            if getattr(sys, 'frozen', False):
                fatal_path = os.path.join(os.path.dirname(sys.executable), "FATAL_STEP_3.log")
            else:
                fatal_path = os.path.join(os.path.dirname(__file__), "FATAL_STEP_3.log")
            with open(fatal_path, "w", encoding="utf-8") as f:
                f.write(f"=== FATAL CUTTING ERROR ===\n")
                f.write(f"Time: {datetime.datetime.now()}\n")
                f.write(f"Error: {str(e)}\n\n")
                f.write(f"Full traceback:\n{error_msg}\n")
        except Exception:
            pass
        raise
