"""
process_task.py

Chạy job trong worker process.
- type="cmd": chạy subprocess command
- type="sk1": chạy cutting giống main.process_workflow (không đổi logic)
- type="sk3": chạy image flow giống main.process_image_flow (không đổi logic)

v5.9.25 Bridge Split (3-AI Consensus):
- difflib/SequenceMatcher moved to _seq.py (stays .py, renamed for obfuscation)
- This file is NOW SAFE to compile to .pyd
- All string matching delegated via import from _seq

Lưu ý:
- Worker không dùng UI log_func trực tiếp. Trả logs về result["logs"].
"""

from __future__ import annotations

import os
import re
import json
# difflib REMOVED — moved to matcher_engine.py (crashes as .pyd on Japanese Unicode)
import gc
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

# Windows subprocess flags to prevent CMD window flashing
if sys.platform == "win32":
    _SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _STARTUPINFO.wShowWindow = subprocess.SW_HIDE
else:
    _SUBPROCESS_FLAGS = 0
    _STARTUPINFO = None

Job = Dict[str, Any]
Result = Dict[str, Any]


def _aggressive_gc() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


# _clean_text() and _parse_script() moved to _seq.py (was matcher_engine.py)
from _seq import _clean_text, _parse_script, _match_words_to_script


def _normalize_lang_code(lang_code: Optional[str]) -> Optional[str]:
    if lang_code is None:
        return None
    s = str(lang_code).strip().lower()
    return None if s in ("", "auto", "detect") else s


@lru_cache(maxsize=1)
def _get_best_encoder() -> Tuple[str, str]:
    """Detect best encoder (cached - only runs once per session)."""
    try:
        test_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "nullsrc",
            "-c:v",
            "h264_nvenc",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ]
        cp = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=_SUBPROCESS_FLAGS, startupinfo=_STARTUPINFO)
        if cp.returncode == 0:
            return "h264_nvenc", "p1"
        return "libx264", "ultrafast"
    except Exception:
        return "libx264", "ultrafast"


def _run(cmd: List[str]) -> None:
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace",
                         creationflags=_SUBPROCESS_FLAGS, startupinfo=_STARTUPINFO)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout or "").strip()[:3000])


def _find_video_by_vid_any_ext(video_dir: str, vid: int) -> Optional[str]:
    if not video_dir or not os.path.isdir(video_dir):
        return None
    target = int(vid)
    candidates: List[str] = []
    for name in os.listdir(video_dir):
        path = os.path.join(video_dir, name)
        if not os.path.isfile(path):
            continue
        stem = os.path.splitext(name)[0]
        s = stem.strip()
        # accept "1" or "V1"
        if s.lower().startswith("v"):
            s = s[1:]
        try:
            if int(s) == target:
                candidates.append(path)
        except Exception:
            continue
    candidates.sort()
    return candidates[0] if candidates else None


def _ffprobe_has_video_stream(path: str) -> bool:
    try:
        cp = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "default=noprint_wrappers=1",
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


def _list_visual_files_recursive(folder: str) -> List[str]:
    if not folder or not os.path.isdir(folder):
        return []
    out: List[str] = []
    for root, _, files in os.walk(folder):
        for f in files:
            out.append(os.path.join(root, f))
    out.sort()
    return out


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
    """Create video clip from image/video with Ken Burns effect (GPU accelerated).
    Supports: zoom_in, zoom_out, pan_left, pan_right, random, static/none.
    """
    import random as _rand

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
        internal_effect = _rand.choice(["zoom_in", "zoom_out"])

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

    _run(cmd)


# ==============================================================================
# EXPORTED FUNCTIONS — Used by main.py (protected when compiled to .pyd)
# ==============================================================================

def _extract_words_with_fallback(
    result_segments: list, log_func=None
) -> List[dict]:
    """
    Extract words from segments with fallback for missing word-level alignment.
    If words exist → use words. If not → fallback to segment start/end.
    """
    all_words: List[dict] = []
    for seg in result_segments or []:
        if isinstance(seg, dict) and "words" in seg and seg.get("words"):
            all_words.extend([w for w in seg.get("words", []) if "start" in w])
        else:
            try:
                all_words.append({
                    "word": seg.get("text", ""),
                    "start": seg["start"],
                    "end": seg["end"],
                })
            except Exception:
                continue
    if log_func and not all_words:
        log_func("⚠️ Không trích được words/segments để match. Kiểm tra audio/align.")
    return all_words


# _match_words_to_script() moved to _seq.py (3-AI Consensus)\r
# Imported at top: from _seq import _match_words_to_script


def process_task(job: Job) -> Result:
    typ = (job.get("type") or "").lower()
    logs: List[str] = []

    try:
        if typ == "cmd":
            cmd = job.get("cmd")
            if not cmd:
                return {"ok": False, "error": "Missing cmd", "logs": logs}
            _run(cmd)
            return {"ok": True, "logs": logs}

        if typ not in ("sk1", "sk3"):
            return {"ok": False, "error": f"Unsupported type: {typ}", "logs": logs}

        # Heavy imports inside worker
        import torch  # noqa
        import whisperx  # noqa

        audio_full_path = job["audio_full_path"]
        script_path = job["script_path"]
        output_dir = job["output_dir"]
        model_cache_dir = job.get("model_cache_dir", "models_ai")
        lang_code = job.get("lang_code")
        model_name = job.get("model_name", "large-v3")

        os.makedirs(model_cache_dir, exist_ok=True)
        out_aud = os.path.join(output_dir, "audios")
        out_vid = os.path.join(output_dir, "videos")
        os.makedirs(out_aud, exist_ok=True)
        os.makedirs(out_vid, exist_ok=True)

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        # Display name mapping (hide technical names)
        display_names = {"tiny": "LITE", "base": "STARTER", "small": "STANDARD", "medium": "PRO", "large-v2": "ULTRA", "large-v3": "PREMIUM", "large-v3-turbo": "⚡ TURBO"}
        display_name = display_names.get(model_name, "PRO")
        logs.append(f"⚡ AI Engine: {display_name} ({device.upper()})")

        _aggressive_gc()

        # Option B: Pre-download with progress, then load direct path
        # Simple model path (match model_checker structure)
        simple_model_path = os.path.abspath(os.path.join(model_cache_dir, model_name))
        model_bin_path = os.path.join(simple_model_path, "model.bin")
        
        # Check if model needs to be downloaded
        if not os.path.exists(model_bin_path):
            logs.append(f"📥 Downloading AI model ({display_name})...")
            logs.append("   This may take a few minutes on first run...")
            
            # Download with progress via model_checker
            try:
                from model_checker import download_model
                success, downloaded_path = download_model(
                    model_name,
                    target_dir=model_cache_dir,
                    log_func=lambda msg: logs.append(msg),
                    progress_callback=None
                )
                if success:
                    logs.append("✅ Download complete!")
                else:
                    logs.append("❌ Download failed!")
                    return {"status": "error", "logs": logs}
            except Exception as e:
                logs.append(f"❌ Download error: {e}")
                return {"status": "error", "logs": logs}
        
        logs.append("[1/3] Loading AI...")
        
        # Load model - use local path if downloaded, otherwise use model name
        # Check if local model directory has required files
        local_model_ready = (
            os.path.exists(model_bin_path) and
            os.path.exists(os.path.join(simple_model_path, "config.json"))
        )
        
        if local_model_ready:
            logs.append(f"   > Using local model: {simple_model_path}")
            model = whisperx.load_model(simple_model_path, device, compute_type=compute_type)
        else:
            logs.append(f"   > Downloading from HuggingFace...")
            model = whisperx.load_model(model_name, device, compute_type=compute_type, download_root=model_cache_dir)

        logs.append("  > Transcribing...")
        audio = whisperx.load_audio(audio_full_path)

        lang_for_transcribe = _normalize_lang_code(lang_code)
        # PERFORMANCE: batch_size=4 with OOM fallback (Grok recommendation)
        batch_size = 4
        kwargs = {"batch_size": batch_size}
        if lang_for_transcribe is not None:
            kwargs["language"] = lang_for_transcribe
        
        try:
            result = model.transcribe(audio, **kwargs)
        except RuntimeError as e:
            if "out of memory" in str(e).lower() or "CUDA" in str(e):
                logs.append(f"⚠️ OOM with batch={batch_size}, fallback to batch=2")
                _aggressive_gc()
                kwargs["batch_size"] = 2
                result = model.transcribe(audio, **kwargs)
            else:
                raise
        detected_lang = result.get("language") or lang_for_transcribe or "en"
        del model
        _aggressive_gc()

        logs.append(f"[2/3] Aligning... (lang={detected_lang})")
        try:
            model_a, metadata = whisperx.load_align_model(language_code=detected_lang, device=device, model_dir=model_cache_dir)
            result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
            del model_a, metadata
            _aggressive_gc()
        except Exception as e:
            logs.append(f"Align Warning: {e}")

        # words fallback (giữ logic)
        all_words: List[dict] = []
        for seg in result.get("segments", []) or []:
            if isinstance(seg, dict) and seg.get("words"):
                all_words.extend([w for w in seg.get("words", []) if "start" in w])
            else:
                try:
                    all_words.append({"word": seg.get("text", ""), "start": seg["start"], "end": seg["end"]})
                except Exception:
                    pass

        with open(script_path, "r", encoding="utf-8") as f:
            script_items = _parse_script(f.read())

        enc_name, enc_preset = _get_best_encoder()

        # v5.9.25 Bridge Split: use matcher_engine (stays .py) for matching
        # Then loop over matches for cutting — no difflib in this file
        log_func = lambda msg: logs.append(msg)
        matches = _match_words_to_script(all_words, script_items, log_func)

        if typ == "sk1":
            video_source_dir = job.get("video_source_dir", "")
            logs.append(f"[3/3] Cutting {len(matches)} RAW clips...")

            for vid, s_time, e_time, text in matches:
                duration = e_time - s_time

                a_out = os.path.join(out_aud, f"{str(vid).zfill(3)}.mp3")
                # PERFORMANCE: Fast-seek pattern (-ss -t BEFORE -i = 3-10x faster)
                _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss", str(s_time),        # Seek BEFORE input
                        "-t", str(duration),       # Duration (relative), not -to
                        "-i", audio_full_path,     # Input AFTER seek
                        "-vn",
                        "-acodec", "libmp3lame",
                        "-q:a", "2",
                        "-loglevel", "error",
                        a_out,
                    ]
                )

                video_src = _find_video_by_vid_any_ext(video_source_dir, vid)
                if not video_src:
                    logs.append(f"[V{str(vid).zfill(2)}] AUDIO OK | NO VID")
                    continue

                v_out = os.path.join(out_vid, f"{str(vid).zfill(3)}.mp4")

                # Giữ audio gốc nếu copy được; fail -> aac (không đổi logic AI)
                cmd_copy = [
                    "ffmpeg", "-y",
                    "-ss", "0", "-i", video_src, "-t", str(duration),
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30",
                    "-map", "0:v:0", "-map", "0:a?",
                    "-c:v", enc_name, "-preset", enc_preset,
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    "-shortest", "-loglevel", "error", v_out,
                ]
                try:
                    _run(cmd_copy)
                except Exception:
                    cmd_aac = cmd_copy[:]
                    cmd_aac[cmd_aac.index("-c:a") + 1] = "aac"
                    cmd_aac.insert(cmd_aac.index("-shortest"), "192k")
                    cmd_aac.insert(cmd_aac.index("-shortest"), "-b:a")
                    _run(cmd_aac)

                logs.append(f"[V{str(vid).zfill(2)}] AUDIO OK | VIDEO OK | {duration:.2f}s")

            return {"ok": True, "logs": logs}

        # typ == "sk3"
        image_source_dir = job.get("image_source_dir", "")
        files = _list_visual_files_recursive(image_source_dir)
        if not files:
            return {"ok": False, "error": f"Image folder empty: {image_source_dir}", "logs": logs}

        # pick first valid visual for canvas
        canvas_w, canvas_h = 1080, 1920
        start_idx = 0
        for i, p in enumerate(files):
            if _ffprobe_has_video_stream(p):
                start_idx = i
                break

        # v5.9.25: matches already computed above via _match_words_to_script
        logs.append(f"[3/3] Cutting {len(matches)} IMAGE clips...")
        cursor = start_idx

        for vid, s_time, e_time, text in matches:
            duration = max(0.10, e_time - s_time)

            a_out = os.path.join(out_aud, f"{str(vid).zfill(3)}.mp3")
            # PERFORMANCE: Fast-seek pattern (-ss -t BEFORE -i = 3-10x faster)
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss", str(s_time),        # Seek BEFORE input
                    "-t", str(duration),       # Duration (relative), not -to
                    "-i", audio_full_path,     # Input AFTER seek
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-q:a", "2",
                    "-loglevel", "error",
                    a_out,
                ]
            )

            picked = None
            tries = 0
            while tries < len(files):
                p = files[cursor % len(files)]
                cursor += 1
                tries += 1
                if _ffprobe_has_video_stream(p):
                    picked = p
                    break
            if not picked:
                return {"ok": False, "error": "No readable visuals for ffmpeg/ffprobe.", "logs": logs}

            v_out = os.path.join(out_vid, f"{str(vid).zfill(3)}.mp4")
            try:
                _make_image_clip(picked, v_out, duration, canvas_w, canvas_h, enc_name, enc_preset)
            except Exception:
                _make_image_clip(picked, v_out, duration, canvas_w, canvas_h, "libx264", "ultrafast")

            logs.append(f"[V{str(vid).zfill(2)}] AUDIO OK | IMAGE OK | {duration:.2f}s")

        return {"ok": True, "logs": logs}

    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "logs": logs}


# ==============================================================================
# CUTTING LOOP — Callback Bridge (v5.9.24 Phase D — 3-AI Consensus)
# Protected in .pyd: cutting logic, cmd building, error handling, GC
# Callbacks from .py: ffmpeg_runner, log_func, stop_check
# ==============================================================================

def _cutting_loop(
    matches: list,
    audio_path: str,
    video_source_dir: str,
    out_aud: str,
    out_vid: str,
    enc_name: str,
    enc_preset: str,
    ffmpeg_threads: list,
    ffmpeg_runner,           # callback: run_ffmpeg_fast(cmd_list) — stays in .py
    log_func,                # callback: log_func(msg) — stays in .py
    stop_check,              # callback: lambda: STOP_FLAG — stays in .py
    gc_func=None,            # callback: aggressive_gc() — optional
):
    """
    Core cutting loop — audio + video cut for each matched segment.
    
    Used by main.py and sk1_cutting.py.
    Subprocess calls are passed via ffmpeg_runner callback to avoid
    circular imports and Cython subprocess handle issues.
    
    Returns number of clips successfully processed.
    """
    total = len(matches)
    processed = 0

    for idx, (vid, s_time, e_time, text) in enumerate(matches, 1):
        if stop_check():
            log_func("🛑 STOPPED.")
            break

        # Periodic GC every 20 clips to prevent memory buildup
        if idx % 20 == 0 and gc_func:
            gc_func()

        duration = e_time - s_time

        # ── Cut Audio (voice) ──
        a_out = os.path.join(out_aud, f"{str(vid).zfill(3)}.mp3")
        os.makedirs(os.path.dirname(a_out), exist_ok=True)

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

        # ── Cut Video: find by ID, keep original audio ──
        video_src = _find_video_by_vid_any_ext(video_source_dir, vid)
        if video_src:
            v_out = os.path.join(out_vid, f"{str(vid).zfill(3)}.mp4")

            cmd_copy = [
                "ffmpeg", "-y",
                *ffmpeg_threads,
                "-ss", "0",
                "-i", video_src,
                "-t", str(duration),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=30",
                "-map", "0:v:0",
                "-map", "0:a?",
                "-c:v", enc_name,
                "-preset", enc_preset,
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-shortest",
                "-map_metadata", "-1",
                "-loglevel", "error",
                v_out,
            ]

            try:
                ffmpeg_runner(cmd_copy)
            except Exception:
                # Fallback: re-encode audio as AAC if copy fails
                cmd_aac = cmd_copy[:]
                cmd_aac[cmd_aac.index("-c:a") + 1] = "aac"
                cmd_aac.insert(cmd_aac.index("-shortest"), "192k")
                cmd_aac.insert(cmd_aac.index("-shortest"), "-b:a")
                ffmpeg_runner(cmd_aac)

            text_display = text[:40] + "..." if len(text) > 40 else text
            log_func(
                f"[{str(idx).zfill(2)}/{total}] [V{str(vid).zfill(2)}] "
                f"✓ Audio + ■ Video | {duration:.2f}s | Text: {text_display}"
            )
        else:
            text_display = text[:40] + "..." if len(text) > 40 else text
            log_func(
                f"[{str(idx).zfill(2)}/{total}] [V{str(vid).zfill(2)}] "
                f"✓ Audio + ❌ Video | {duration:.2f}s | Text: {text_display}"
            )

        processed += 1

    return processed


# ==============================================================================
# IMAGE FLOW LOOP — Callback Bridge (v5.9.24 Phase D — 3-AI Consensus)
# Protected in .pyd: image picking, Ken Burns, cmd building
# Callbacks from .py: ffmpeg_runner, log_func, stop_check
# ==============================================================================

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
    ffmpeg_runner,           # callback: run_ffmpeg_fast(cmd_list) — stays in .py
    log_func,                # callback: log_func(msg) — stays in .py
    stop_check,              # callback: lambda: STOP_FLAG — stays in .py
    gc_func=None,            # callback: aggressive_gc() — optional
):
    """
    Image flow cutting loop — audio cut + Ken Burns video from images.
    
    Used by sk3_image_flow.py.
    Picks visual files round-robin, creates video with Ken Burns effect.
    Subprocess calls are passed via ffmpeg_runner callback.
    
    Returns number of clips successfully processed.
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
            if _ffprobe_has_video_stream(p):
                picked = p
                break
        if not picked:
            log_func(f"❌ [V{str(vid).zfill(2)}] No readable visual file found")
            continue

        # ── Create video clip with Ken Burns effect ──
        v_out = os.path.join(out_vid, f"{str(vid).zfill(3)}.mp4")
        try:
            _make_image_clip(
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
        # Log every clip (matching SK1 behavior)
        log_func(
            f"[{str(idx).zfill(2)}/{total}] [V{str(vid).zfill(2)}] "
            f"✓ Audio + 🖼️ Image | {duration:.2f}s | Text: {text_display}"
        )

        processed += 1

    return processed


# ============================================================
# PHASE E1: _run_ai_subprocess_generic (consolidated from 3 files)
# Callback bridge: subprocess_runner stays in .py wrapper
# ============================================================

# HuggingFace env vars — hidden in .pyd (competitor can't see config)
_HF_ENV_VARS = {
    "HF_HUB_DISABLE_SYMLINKS": "1",
    "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
    "HF_HUB_DISABLE_XET": "1",
    "HF_HUB_ENABLE_HF_TRANSFER": "0",
    "HF_HUB_DOWNLOAD_WORKERS": "1",
    "HF_HUB_DOWNLOAD_TIMEOUT": "600",
    "HF_HUB_ETAG_TIMEOUT": "60",
    "TQDM_DISABLE": "",
    "HF_HUB_DISABLE_PROGRESS_BARS": "",
}


def _build_subprocess_env(model_cache_dir):
    """Build environment dict for AI subprocess — PROTECTED.
    
    Hides HuggingFace config details (cache paths, symlink fixes,
    download throttling) from decompilers.
    """
    env = os.environ.copy()
    env.update(_HF_ENV_VARS)
    env["HF_HOME"] = model_cache_dir
    env["HF_HUB_CACHE"] = model_cache_dir
    env["HUGGINGFACE_HUB_CACHE"] = model_cache_dir
    return env


def _run_ai_subprocess_generic(
    audio_path,
    model_name,
    lang_code,
    fast_mode,
    model_cache_dir,
    worker_script_name,
    app_root,
    log_func,
    noise_filter=None,
):
    """Run AI transcription via subprocess — PROTECTED in .pyd.
    
    Consolidated from main.py, sk1_cutting.py, sk3_image_flow.py.
    Hides: env vars, config structure, temp file handling, output parsing.
    
    Args:
        audio_path: Path to audio file
        model_name: WhisperX model name
        lang_code: Language code
        fast_mode: Skip alignment if True
        model_cache_dir: HuggingFace model cache directory
        worker_script_name: Worker script (e.g. 'sk1_worker.py')
        app_root: Application root directory
        log_func: Logging callback
        noise_filter: Optional callable(line) -> bool, True = skip line
    
    Returns:
        dict with 'segments', 'words', 'language' keys
    """
    python_exe = os.path.join(app_root, "python_embed", "python.exe")
    worker_script = os.path.join(app_root, "ai_scripts", worker_script_name)

    if not os.path.exists(python_exe):
        raise FileNotFoundError(f"python_embed not found: {python_exe}")
    if not os.path.exists(worker_script):
        raise FileNotFoundError(f"AI worker not found: {worker_script}")

    # Create temp config + output path
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.json', delete=False, encoding='utf-8'
    ) as f:
        config_path = f.name
        config_data = {
            "audio_path": audio_path,
            "model_name": model_name,
            "device": "cuda",
            "compute_type": "float16",
            "lang_code": lang_code,
            "fast_mode": fast_mode,
            "model_cache_dir": model_cache_dir,
            "output_path": config_path.replace('.json', '_result.json'),
        }
        json.dump(config_data, f, ensure_ascii=False)

    output_path = config_data["output_path"]

    try:
        subprocess_env = _build_subprocess_env(model_cache_dir)

        log_func("[AI] Starting AI subprocess...")
        process = subprocess.Popen(
            [python_exe, worker_script, config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=app_root,
            env=subprocess_env,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        # Stream output — filter noise if callback provided
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            if noise_filter and noise_filter(line):
                continue
            log_func(line)

        process.wait()

        # Wait for output file (subprocess may not flush immediately)
        max_wait = 5.0
        wait_start = time.time()
        while not os.path.exists(output_path) and (time.time() - wait_start) < max_wait:
            time.sleep(0.1)

        if process.returncode != 0:
            raise RuntimeError(
                f"AI subprocess failed (exit code {process.returncode})"
            )

        if not os.path.exists(output_path):
            raise FileNotFoundError(f"AI output not found: {output_path}")

        with open(output_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        return result

    finally:
        # Cleanup temp files
        for p in (config_path, output_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# ============================================================
# PHASE E2: DEV AI Transcription Pipeline (3-AI Consensus)
# Dependency Injection: torch/whisperx passed as callbacks
# ============================================================

# Model display names — hide actual WhisperX model identifiers
_MODEL_DISPLAY_NAME = {
    "tiny": "LITE",
    "base": "STARTER",
    "small": "STANDARD",
    "medium": "PRO",
    "large-v2": "ULTRA",
    "large-v3": "PREMIUM",
    "large-v3-turbo": "⚡ TURBO",
}


def _get_display_name(model_name):
    """Get UI display name for model (hides actual WhisperX model name).
    
    PROTECTED in .pyd — competitor sees 'PREMIUM' not 'large-v3'.
    """
    return _MODEL_DISPLAY_NAME.get(model_name, model_name.upper())


def _dev_transcribe_pipeline(
    audio_path,
    model_name,
    lang_code,
    fast_mode,
    model_cache_dir,
    device,
    compute_type,
    # Callbacks — torch/whisperx stay in .py wrapper
    load_model_fn,
    load_audio_fn,
    load_align_fn,
    align_fn,
    empty_cache_fn,
    # State references
    model_cache,
    keep_model_loaded,
    # Control callbacks
    log_func,
    stop_check,
    gc_func,
):
    """Full DEV mode AI transcription pipeline — PROTECTED in .pyd.

    Hides: model caching strategy, transcription flow, auto lang detect,
    alignment logic, word extraction, VRAM management timing.

    Args:
        audio_path: Path to audio file
        model_name: WhisperX model name (e.g. 'large-v3')
        lang_code: Language code or 'auto'
        fast_mode: Skip alignment if True
        model_cache_dir: HuggingFace model cache directory
        device: 'cuda' or 'cpu' (pre-calculated in wrapper)
        compute_type: 'float16' or 'int8' (pre-calculated in wrapper)
        load_model_fn: whisperx.load_model callback
        load_audio_fn: whisperx.load_audio callback
        load_align_fn: whisperx.load_align_model callback
        align_fn: whisperx.align callback
        empty_cache_fn: torch.cuda.empty_cache callback (or no-op for CPU)
        model_cache: MODEL_CACHE dict reference (mutable)
        keep_model_loaded: Whether to cache model between tasks
        log_func: Logging callback
        stop_check: Lambda returning STOP_FLAG
        gc_func: aggressive_gc callback

    Returns:
        tuple (all_words, detected_lang)
    """
    display_name = _get_display_name(model_name)

    # File-based IPC: write directly to progress file for UI real-time updates
    # This bypasses stdout pipe buffer that can delay messages during heavy ops
    _pf = os.path.join(tempfile.gettempdir(), f"aurasplit_progress_{os.getpid()}.jsonl")
    def _pf_emit(msg_type, **kwargs):
        try:
            payload = {"type": msg_type, **kwargs}
            with open(_pf, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + '\n')
        except Exception:
            pass

    # --- Step 1: Model load/cache (HIDDEN strategy) ---
    use_cached = (
        keep_model_loaded
        and model_cache.get("model") is not None
        and model_cache.get("model_name") == model_name
        and model_cache.get("device") == device
        and model_cache.get("compute_type") == compute_type
    )

    if use_cached:
        log_func(f"[1/3] Using cached AI model ({display_name}) ✓")
        _pf_emit("log", message=f"[1/3] Using cached AI model ({display_name}) ✓")
        model = model_cache["model"]
    else:
        # Pre-load cleanup
        if not (keep_model_loaded and model_cache.get("model") is not None):
            gc_func()

        log_func(f"[1/3] Loading AI ({display_name})...")
        _pf_emit("log", message=f"[1/3] Loading AI ({display_name})...")
        _pf_emit("progress", percent=8, message=f"Loading AI ({display_name})...")

        # Check if model needs to be downloaded (first-time use)
        _model_dir = os.path.join(model_cache_dir, model_name)
        _model_bin = os.path.join(_model_dir, "model.bin")

        # Clean up stale .incomplete files from interrupted downloads
        _blobs_dir = os.path.join(model_cache_dir, f"models--Systran--faster-whisper-{model_name}", "blobs")
        if os.path.exists(_blobs_dir):
            for f in os.listdir(_blobs_dir):
                if f.endswith(".incomplete"):
                    try:
                        os.remove(os.path.join(_blobs_dir, f))
                    except OSError:
                        pass

        if not os.path.exists(_model_bin):
            # PRE-DOWNLOAD via model_checker (symlink-free! Avoids WinError 1314)
            _pf_emit("log", message=f"📥 Downloading model '{display_name}' for first time...")
            _pf_emit("log", message="⏳ This may take a few minutes. Please wait...")
            _pf_emit("progress", percent=10, message=f"Downloading {display_name}...")
            try:
                from model_checker import download_model as _dl_model
                _ok, _path = _dl_model(model_name, target_dir=model_cache_dir, log_func=log_func)
                if _ok:
                    log_func(f"✅ Model downloaded OK")
                else:
                    log_func("⚠️ Pre-download failed, whisperx will try its own download...")
            except Exception as _e:
                log_func(f"⚠️ model_checker failed: {_e}, falling back to whisperx download")

        # Load model: use DIRECT PATH if files exist locally (bypass HF Hub symlinks!)
        _local_model_dir = os.path.join(model_cache_dir, model_name)
        _local_model_bin = os.path.join(_local_model_dir, "model.bin")
        if os.path.exists(_local_model_bin):
            # Model files exist → pass directory path → faster-whisper loads directly
            log_func(f"Loading from local: {_local_model_dir}")
            model = load_model_fn(
                _local_model_dir,
                device,
                compute_type=compute_type,
            )
        else:
            # Fallback: let whisperx download via HF Hub (may need admin for symlinks)
            log_func("⚠️ Local model not found, falling back to HF Hub download...")
            model = load_model_fn(
                model_name,
                device,
                compute_type=compute_type,
                download_root=model_cache_dir,
            )
        log_func("✅ Model loaded successfully!")
        empty_cache_fn()

        if keep_model_loaded:
            model_cache["model"] = model
            model_cache["model_name"] = model_name
            model_cache["device"] = device
            model_cache["compute_type"] = compute_type
            log_func("      > Model cached for future tasks")

    # --- Step 2: Transcribe + auto lang detect (HIDDEN flow) ---
    log_func("> Transcribing...")
    audio = load_audio_fn(audio_path)

    # Auto language detection (secret recipe — hidden in .pyd)
    if lang_code and lang_code.lower() not in ("auto", ""):
        result = model.transcribe(audio, language=lang_code)
        detected_lang = lang_code
    else:
        result = model.transcribe(audio)
        detected_lang = result.get("language", "en")
    log_func(f"      > Detected language: {detected_lang}")

    # Cleanup model if not caching
    if not keep_model_loaded:
        del model
        gc_func()

    if stop_check():
        return [], detected_lang

    # --- Step 3: Alignment (HIDDEN params — beam_size, char_alignments) ---
    if fast_mode:
        log_func("[2/3] Skip Align (Fast mode) - using segment timestamps")
    else:
        log_func(f"[2/3] Aligning... (lang={detected_lang})")
        try:
            model_a, metadata = load_align_fn(
                language_code=detected_lang,
                device=device,
                model_dir=model_cache_dir,
            )
            result = align_fn(
                result["segments"],
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            del model_a
            del metadata
            gc_func()
            empty_cache_fn()
        except Exception as e:
            log_func(f"⚠️ Align Warning: {e}")

    # --- Step 4: Word extraction (already in .pyd) ---
    all_words = _extract_words_with_fallback(
        result.get("segments", []), log_func
    )

    return all_words, detected_lang


# =============================================================================
# Phase E3: ai_to_ffmpeg_handover (3-AI Consensus)
# Hard reset GPU context between WhisperX and FFmpeg to prevent silent crash.
# =============================================================================

def ai_to_ffmpeg_handover(log_func=None):
    """
    AI Studio Fix: Release GPU context before FFmpeg starts.
    WhisperX just finished → GPU holding large context.
    FFmpeg (CUDA-enabled) starts → two contexts fight = silent crash.
    """
    # Force garbage collection
    gc.collect()

    # Clear CUDA cache if available (torch may not be importable in EXE mode)
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass

    # Wait for OS to release GPU handles
    time.sleep(2)

    if log_func:
        log_func("[DEBUG] AI→FFmpeg handover complete ✅")
