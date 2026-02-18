#!/usr/bin/env python3
"""
AuraSplit v2 — Persistent SUB Server
Stays alive between subtitle generation calls to keep AI models cached in GPU memory.

Protocol (stdin → stdout, JSON lines):
  → {"task_id":"sub_123", "video_path":"...", "lang_code":"vi", ...}
  ← {"task_id":"sub_123", "type":"progress", "percent":10, "message":"..."}
  ← {"task_id":"sub_123", "type":"result", "data":{...}}
  → {"cmd":"shutdown"}

Models are cached in sub_engine._model_cache and persist across calls.
"""

import sys
import os
import json
import traceback

# ── Fix Windows console encoding ──
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

# Add script dir to path
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)


def _emit(task_id: str, msg_type: str, **kwargs):
    """Send a JSON-line message to stdout."""
    payload = {"task_id": task_id, "type": msg_type, **kwargs}
    line = json.dumps(payload, ensure_ascii=False)
    line = line.replace("\n", " ").replace("\r", "")
    print(line, flush=True)
    sys.stdout.flush()


def handle_sub_task(task: dict):
    """Run a single SUB task, reusing cached models."""
    task_id = task.get("task_id", "unknown")

    try:
        from engines.sub_engine import (
            transcribe_and_generate_srt,
            transcribe_with_whisperx,
            get_engine_for_lang,
        )

        video_path = task.get("video_path", "")
        output_srt = task.get("output_srt_path", "")
        lang = task.get("lang_code", "auto")
        model_name = task.get("model_name", "Qwen/Qwen3-ASR-0.6B")
        use_aligner = task.get("use_aligner", True)
        force_engine = task.get("engine", "")
        model_cache_dir = task.get("model_cache_dir",
            os.path.join(_script_dir, "..", "models_ai"))

        if not video_path or not os.path.isfile(video_path):
            _emit(task_id, "error", message=f"Video file not found: {video_path}")
            return

        # Auto-generate output SRT path
        if not output_srt:
            base = os.path.splitext(video_path)[0]
            output_srt = base + ".srt"

        # Determine engine
        if force_engine in ("qwen", "whisper"):
            engine = force_engine
        else:
            engine = get_engine_for_lang(lang)

        engine_label = "WhisperX 🚀" if engine == "whisper" else "Qwen3-ASR 🧠"

        def log_func(msg: str):
            _emit(task_id, "log", message=msg)
            import re
            matches = re.findall(r'\[(\d+)/(\d+)\]', msg)
            if matches:
                cur, total = int(matches[-1][0]), int(matches[-1][1])
                if total > 0:
                    pct = int(5 + (cur / total) * 85)
                    _emit(task_id, "progress", percent=min(pct, 90), message=msg)

        _emit(task_id, "progress", percent=5,
              message=f"Language: {lang} → Engine: {engine_label}")
        _emit(task_id, "log",
              message=f"[ROUTE] Language: {lang} → Engine: {engine_label}")

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

        # Build result payload
        raw_segments = result.get("segments", [])[:50]
        segments = []
        for seg in raw_segments:
            segments.append({
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": str(seg.get("text", "")),
            })

        _emit(task_id, "result", data={
            "status": "ok",
            "task": "sub",
            "engine": result.get("engine", engine),
            "language": str(result.get("language", "")),
            "srt_path": str(result.get("srt_path", "")),
            "segments_count": int(result.get("segments_count", 0)),
            "segments": segments,
        })
        _emit(task_id, "progress", percent=100, message="✅ SUB Complete!")

    except Exception as e:
        _emit(task_id, "error", message=f"SUB error: {e}\n{traceback.format_exc()}")


def main():
    """Main loop — read JSON tasks from stdin, process them, stay alive."""
    # Signal ready
    _emit("server", "log", message="🚀 SUB Server started — models will be cached!")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            task = json.loads(line)
        except json.JSONDecodeError as e:
            _emit("server", "error", message=f"Invalid JSON: {e}")
            continue

        # Shutdown command
        if task.get("cmd") == "shutdown":
            _emit("server", "log", message="🛑 SUB Server shutting down...")
            break

        # Ping/health check
        if task.get("cmd") == "ping":
            _emit("server", "log", message="🏓 pong")
            continue

        # Process SUB task
        handle_sub_task(task)

    # Cleanup
    try:
        from engines.sub_engine import clear_sub_cache
        clear_sub_cache()
    except Exception:
        pass


if __name__ == "__main__":
    main()
