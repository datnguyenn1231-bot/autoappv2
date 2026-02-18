#!/usr/bin/env python3
"""
AuraSplit v2 — API Wrapper (v1-compatible)
Bridges Electron IPC → v1 Python engines.

Architecture:
  Electron → python_embed/python.exe api_wrapper.py --task sk1 --config config.json
  The wrapper reads config, sets up CONFIG dict (matching v1 main.py), and calls engines.

SK1 flow: sk1_worker.py (AI transcription) → sk1_cutting.py (FFmpeg cut)
SK3 flow: sk1_worker.py (AI transcription) → sk3_image_flow.py (Ken Burns + FFmpeg)

Output (stdout): JSON lines for progress tracking
  {"type":"progress","percent":10,"message":"Loading model..."}
  {"type":"log","message":"..."}
  {"type":"result","data":{...}}
  {"type":"error","message":"..."}
"""

import sys
import os
import json
import argparse
import traceback

# ── Set HuggingFace env vars BEFORE any import that touches HF ──
# Fixes WinError 1314 (symlink privilege) on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["PYTHONIOENCODING"] = "utf-8"

# Add parent dir to path
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)


def _sanitize_for_json_line(value):
    """Remove newlines from strings to keep JSON output as single line."""
    if isinstance(value, str):
        return value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').strip()
    if isinstance(value, dict):
        return {k: _sanitize_for_json_line(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json_line(v) for v in value]
    return value


def emit(msg_type: str, **kwargs):
    """JSON message to stdout → Electron captures via IPC.
    Each call outputs exactly ONE line of JSON (no embedded newlines).
    """
    payload = {"type": msg_type, **kwargs}
    payload = _sanitize_for_json_line(payload)
    line = json.dumps(payload, ensure_ascii=False)
    line = line.replace('\n', ' ').replace('\r', '')
    print(line, flush=True)
    sys.stdout.flush()


def emit_progress(percent: int, message: str = ""):
    emit("progress", percent=percent, message=message)


def emit_log(message: str):
    emit("log", message=message)


# ── SK1: AI Cut ──────────────────────────────────

def run_sk1(config: dict):
    """
    SK1 two-phase flow:
    Phase 1: AI transcription (sk1_worker.py subprocess OR direct import)
    Phase 2: Script matching + FFmpeg cutting (sk1_cutting.py)
    """
    emit_progress(0, "🚀 SK1 Starting...")

    from engines.sk1_cutting import set_config, process_workflow

    # Map config to v1 CONFIG format
    engine_config = {
        "audio_full_path": config.get("audio_full_path", ""),
        "script_path": config.get("script_path", ""),
        "video_source_dir": config.get("video_source_dir", ""),
        "image_source_dir": config.get("image_source_dir", ""),
        "output_dir": config.get("output_dir", ""),
        "model_cache_dir": config.get("model_cache_dir",
            os.path.join(_script_dir, "..", "models_ai")),
        "effect_type": config.get("effect_type", "kenburns"),
    }
    set_config(engine_config)

    lang = config.get("lang_code", "auto")
    model = config.get("model_name", "base")
    fast = config.get("fast_mode", False)

    def log_func(msg: str):
        emit_log(msg)
        # Smart progress: distinguish phase markers [1/3] from clip progress [01/140]
        import re
        matches = re.findall(r'\[(\d+)/(\d+)\]', msg)
        if matches:
            # Use the LAST match (most specific)
            cur, total = int(matches[-1][0]), int(matches[-1][1])
            if total > 0:
                if total <= 5:
                    # Phase marker like [1/3], [2/3], [3/3] → map to 5-30% range
                    phase_pct = int(5 + (cur / total) * 25)
                    emit_progress(min(phase_pct, 30), msg)
                else:
                    # Per-clip progress like [01/140] → map to 30-95% range
                    clip_pct = int(30 + (cur / total) * 65)
                    emit_progress(min(clip_pct, 95), msg)

    emit_progress(5, f"Model: {model}, Language: {lang}")
    process_workflow(lang, model, log_func, fast_mode=fast)
    emit_progress(100, "✅ SK1 Complete!")
    emit("result", data={"status": "ok", "task": "sk1"})


# ── SUB: Subtitle Generation ────────────────────

def run_sub(config: dict):
    """
    SUB: Dual-engine subtitle generation.
    Asian languages → Qwen3-ASR, English/European → faster-whisper.
    """
    emit_progress(0, "📝 SUB Starting...")

    from engines.sub_engine import (
        transcribe_and_generate_srt,
        transcribe_with_whisperx,
        get_engine_for_lang,
    )

    video_path = config.get("video_path", "")
    output_srt = config.get("output_srt_path", "")
    lang = config.get("lang_code", "auto")
    model_name = config.get("model_name", "Qwen/Qwen3-ASR-0.6B")
    use_aligner = config.get("use_aligner", True)
    force_engine = config.get("engine", "")  # "" = auto, "qwen", "whisper"
    model_cache_dir = config.get("model_cache_dir",
        os.path.join(_script_dir, "..", "models_ai"))

    if not video_path or not os.path.isfile(video_path):
        emit("error", message=f"Video file not found: {video_path}")
        return

    # Auto-generate output SRT path if not specified
    if not output_srt:
        base = os.path.splitext(video_path)[0]
        output_srt = base + ".srt"

    # Determine engine
    if force_engine in ("qwen", "whisper"):
        engine = force_engine
    else:
        engine = get_engine_for_lang(lang)

    def log_func(msg: str):
        emit_log(msg)
        import re
        matches = re.findall(r'\[(\d+)/(\d+)\]', msg)
        if matches:
            cur, total = int(matches[-1][0]), int(matches[-1][1])
            if total > 0:
                pct = int(5 + (cur / total) * 85)
                emit_progress(min(pct, 90), msg)

    try:
        engine_label = "WhisperX 🚀" if engine == "whisper" else "Qwen3-ASR 🧠"
        emit_progress(5, f"Language: {lang} → Engine: {engine_label}")
        emit_log(f"[ROUTE] Language: {lang} → Engine: {engine_label}")

        if engine == "whisper":
            result = transcribe_with_whisperx(
                video_path=video_path,
                output_srt_path=output_srt,
                lang=lang,
                model_cache_dir=model_cache_dir,
                log_func=log_func,
            )
        else:
            result = transcribe_and_generate_srt(
                video_path=video_path,
                output_srt_path=output_srt,
                lang=lang,
                model_name=model_name,
                use_aligner=use_aligner,
                model_cache_dir=model_cache_dir,
                log_func=log_func,
            )

        # Convert segments — force native Python types (numpy float32 not JSON-serializable)
        raw_segments = result.get("segments", [])[:50]
        segments = []
        for seg in raw_segments:
            segments.append({
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            })

        result_payload = {
            "type": "result",
            "data": {
                "status": "ok",
                "task": "sub",
                "engine": result.get("engine", engine),
                "language": str(result.get("language", "")),
                "srt_path": str(result.get("srt_path", "")),
                "segments_count": int(result.get("segments_count", 0)),
                "segments": segments,
            }
        }

        # Write result to BOTH stdout and progress file for reliability
        result_line = json.dumps(result_payload, ensure_ascii=False)
        result_line = result_line.replace('\n', ' ').replace('\r', '')

        # 1) Write to progress file (polled by Electron — proven reliable)
        import tempfile
        progress_file = os.path.join(tempfile.gettempdir(), f"aurasplit_progress_{os.getpid()}.jsonl")
        with open(progress_file, "a", encoding="utf-8") as pf:
            pf.write(result_line + "\n")

        # 2) Also write to stdout
        print(result_line, flush=True)
        sys.stdout.flush()

        # Progress 100% sent LAST — acts as "delivery confirmation"
        emit_progress(100, "✅ SUB Complete!")
    except Exception as e:
        emit("error", message=f"SUB failed: {e}")
        raise


# ── SK3: Image Flow ──────────────────────────────

def run_sk3(config: dict):
    """
    SK3: Audio transcription → cut audio → Ken Burns video from images.
    """
    emit_progress(0, "🖼️ SK3 Starting...")

    from engines.sk3_image_flow import set_config, process_image_flow

    engine_config = {
        "audio_full_path": config.get("audio_full_path", ""),
        "script_path": config.get("script_path", ""),
        "video_source_dir": config.get("video_source_dir", ""),
        "image_source_dir": config.get("image_source_dir", ""),
        "output_dir": config.get("output_dir", ""),
        "model_cache_dir": config.get("model_cache_dir",
            os.path.join(_script_dir, "..", "models_ai")),
        "effect_type": config.get("effect_type", "kenburns"),
    }
    set_config(engine_config)

    lang = config.get("lang_code", "auto")
    model = config.get("model_name", "base")
    fast = config.get("fast_mode", False)

    def log_func(msg: str):
        emit_log(msg)
        import re
        matches = re.findall(r'\[(\d+)/(\d+)\]', msg)
        if matches:
            cur, total = int(matches[-1][0]), int(matches[-1][1])
            if total > 0:
                if total <= 5:
                    phase_pct = int(5 + (cur / total) * 25)
                    emit_progress(min(phase_pct, 30), msg)
                else:
                    clip_pct = int(30 + (cur / total) * 65)
                    emit_progress(min(clip_pct, 95), msg)

    emit_progress(5, f"Model: {model}, Language: {lang}")
    process_image_flow(lang, model, log_func, fast_mode=fast)
    emit_progress(100, "✅ SK3 Complete!")
    emit("result", data={"status": "ok", "task": "sk3"})


# ── Task Router ──────────────────────────────────

TASK_MAP = {"sk1": run_sk1, "sk3": run_sk3, "sub": run_sub}


def main():
    import time
    parser = argparse.ArgumentParser(description="AuraSplit v2 API Wrapper")
    parser.add_argument("--task", required=True, choices=list(TASK_MAP.keys()))
    parser.add_argument("--config", required=True, help="JSON config file path")
    args = parser.parse_args()

    try:
        with open(args.config, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        emit("error", message=f"Config read failed: {e}")
        sys.exit(1)

    try:
        TASK_MAP[args.task](config)
    except Exception as e:
        emit("error", message=f"{type(e).__name__}: {e}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    # Ensure all stdout is flushed before process exits
    # (Node.js pipe reader needs time to drain the buffer)
    sys.stdout.flush()
    sys.stderr.flush()
    time.sleep(0.2)


if __name__ == "__main__":
    main()
