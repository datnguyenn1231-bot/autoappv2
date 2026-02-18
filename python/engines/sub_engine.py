"""
sub_engine.py — SUB Feature: Dual-Engine Audio-to-Text Subtitle Generation

Dual Engine Pipeline:
  Asian languages (vi, ja, zh, ko) → Qwen3-ASR (more accurate for CJK/Vietnamese)
  English & European (en, es, fr, de) → faster-whisper (3-4x faster, CTranslate2)
  Auto-detect → Qwen3-ASR (detect language, then route)

Engines:
  - Qwen3-ASR-1.7B / 0.6B + ForcedAligner (Asian languages)
  - faster-whisper large-v3-turbo (English/European)
  - FFmpeg for audio extraction
"""

import os
import sys
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Callable, List, Dict, Any

# ── Suppress warnings before torch import ──
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── Constants ──
SUPPORTED_LANGUAGES = {
    "auto": None,
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "vi": "Vietnamese",
    "ko": "Korean",
    "ja": "Japanese",
    "zh": "Chinese",
}

# Languages that should use Qwen3-ASR (better for Asian)
ASIAN_LANGUAGES = {"vi", "ko", "ja", "zh"}
# Languages that should use faster-whisper (faster for English/European)
WHISPER_LANGUAGES = {"en", "es", "fr", "de"}

DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"
LIGHT_MODEL = "Qwen/Qwen3-ASR-0.6B"
ALIGNER_MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"

# faster-whisper model
FASTER_WHISPER_MODEL = "large-v3-turbo"

# Max audio chunk duration for ForcedAligner (seconds)
ALIGNER_MAX_DURATION = 300  # 5 minutes

# ── Model Cache (skip reload on repeated calls) ──
_model_cache: Dict[str, Any] = {}


def clear_sub_cache():
    """Free all cached models and GPU memory."""
    global _model_cache
    _model_cache.clear()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def get_engine_for_lang(lang: str) -> str:
    """Determine which engine to use based on language.
    Returns 'qwen' or 'whisper'.
    """
    if lang in ASIAN_LANGUAGES:
        return "qwen"
    else:
        return "whisper"


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _extract_audio(video_path: str, output_path: str, log_func: Callable) -> bool:
    """Extract audio from video file using FFmpeg."""
    log_func(f"🎵 Extracting audio from video...")

    # Find FFmpeg: check binaries/ dir first, then system PATH
    _engines_dir = os.path.dirname(os.path.abspath(__file__))
    _root_dir = os.path.dirname(os.path.dirname(_engines_dir))  # AuraSplit_v2/..
    ffmpeg_candidates = [
        os.path.join(os.path.dirname(_engines_dir), "..", "binaries", "ffmpeg.exe"),
        os.path.join(_root_dir, "binaries", "ffmpeg.exe"),
        os.path.join(_root_dir, "ffmpeg.exe"),
        "ffmpeg",  # fallback to system PATH
    ]
    ffmpeg_path = "ffmpeg"
    for candidate in ffmpeg_candidates:
        if os.path.isfile(candidate):
            ffmpeg_path = os.path.abspath(candidate)
            break

    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM WAV
        "-ar", "16000",           # 16kHz sample rate (optimal for ASR)
        "-ac", "1",               # mono
        output_path,
    ]
    try:
        # Hide ffmpeg window on Windows
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            startupinfo=startupinfo, timeout=120,
        )
        if result.returncode != 0:
            log_func(f"⚠️ FFmpeg error: {result.stderr[:200]}")
            return False
        log_func(f"✅ Audio extracted: {output_path}")
        return True
    except Exception as e:
        log_func(f"❌ Audio extraction failed: {e}")
        return False


def _segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert transcript segments to SRT format string."""
    srt_lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        if text:
            srt_lines.append(f"{i}")
            srt_lines.append(f"{start} --> {end}")
            srt_lines.append(text)
            srt_lines.append("")
    return "\n".join(srt_lines)


def _word_timestamps_to_segments(
    time_stamps: list,
    max_words_per_segment: int = 12,
    max_duration_per_segment: float = 5.0,
) -> List[Dict[str, Any]]:
    """
    Group word-level timestamps into natural subtitle segments.
    
    Rules:
    1. Max N words per segment
    2. Max duration per segment
    3. Break at sentence boundaries (., !, ?, 。, etc.)
    """
    if not time_stamps:
        return []

    segments = []
    current_words = []
    current_start = None

    sentence_enders = {'.', '!', '?', '。', '！', '？', '…'}

    for ts in time_stamps:
        # Handle both dict and ForcedAlignItem (dataclass) formats
        if isinstance(ts, dict):
            word = ts.get("text", ts.get("word", "")).strip()
            start = ts.get("start", ts.get("s", 0))
            end = ts.get("end", ts.get("e", 0))
        else:
            # ForcedAlignItem dataclass: .text, .start_time, .end_time
            word = getattr(ts, "text", getattr(ts, "word", ""))
            if word:
                word = word.strip()
            start = getattr(ts, "start_time", getattr(ts, "start", getattr(ts, "s", 0)))
            end = getattr(ts, "end_time", getattr(ts, "end", getattr(ts, "e", 0)))

        if not word:
            continue

        if current_start is None:
            current_start = start

        current_words.append(word)
        current_end = end

        # Check if we should break into a new segment
        is_sentence_end = any(word.endswith(c) for c in sentence_enders)
        too_many_words = len(current_words) >= max_words_per_segment
        too_long = (current_end - current_start) >= max_duration_per_segment

        if is_sentence_end or too_many_words or too_long:
            text = " ".join(current_words)
            # For CJK: join without spaces
            if any('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff'
                   or '\uac00' <= c <= '\ud7af' for c in text):
                text = "".join(current_words)

            segments.append({
                "start": current_start,
                "end": current_end,
                "text": text,
            })
            current_words = []
            current_start = None

    # Flush remaining words
    if current_words and current_start is not None:
        text = " ".join(current_words)
        if any('\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff'
               or '\uac00' <= c <= '\ud7af' for c in text):
            text = "".join(current_words)
        segments.append({
            "start": current_start,
            "end": current_end,
            "text": text,
        })

    return segments


# ══════════════════════════════════════════════════
# ENGINE 2: WhisperX (batched faster-whisper + word alignment)
# ══════════════════════════════════════════════════

def transcribe_with_whisperx(
    video_path: str,
    output_srt_path: str,
    lang: str = "en",
    model_size: str = FASTER_WHISPER_MODEL,
    model_cache_dir: Optional[str] = None,
    log_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    WhisperX pipeline (2-3x faster than plain faster-whisper):
    1. Extract audio from video
    2. Load WhisperX model (batched faster-whisper backend)
    3. Transcribe with batched inference (much faster)
    4. Align with wav2vec2 for precise word-level timestamps
    5. Export SRT file
    """
    if log_func is None:
        log_func = print

    log_func("[ENGINE] 🚀 Using WhisperX (batched + word alignment)")

    # ── Step 1: Extract audio ──
    log_func("[1/4] 🎵 Extracting audio from video...")
    audio_path = os.path.join(
        tempfile.gettempdir(),
        f"aurasplit_wx_{int(time.time())}.wav"
    )
    if not _extract_audio(video_path, audio_path, log_func):
        raise RuntimeError(f"Failed to extract audio from {video_path}")

    try:
        import torch
        import whisperx

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        batch_size = 16 if device == "cuda" else 4

        log_func(f"   Device: {device}, Model: {model_size}, Compute: {compute_type}, Batch: {batch_size}")

        # ── Step 2: Load WhisperX model (cached) ──
        cache_key = f"whisperx:{model_size}:{device}:{compute_type}"
        if cache_key in _model_cache:
            model = _model_cache[cache_key]
            log_func("[2/4] ⚡ WhisperX model loaded from cache!")
        else:
            log_func("[2/4] 🧠 Loading WhisperX model (first time)...")
            model_kwargs = dict(
                whisper_arch=model_size,
                device=device,
                compute_type=compute_type,
            )
            if model_cache_dir:
                model_kwargs["download_root"] = model_cache_dir

            model = whisperx.load_model(**model_kwargs)
            _model_cache[cache_key] = model
            log_func("✅ Model loaded & cached!")

        # ── Step 3: Transcribe (batched — 2-3x faster) ──
        log_func("[3/4] 🎤 Transcribing audio (batched)...")
        audio = whisperx.load_audio(audio_path)

        transcribe_kwargs = dict(
            audio=audio,
            batch_size=batch_size,
        )
        if lang and lang != "auto":
            transcribe_kwargs["language"] = lang

        result = model.transcribe(**transcribe_kwargs)
        detected_lang = result.get("language", lang)

        raw_segments = result.get("segments", [])
        log_func(f"   Detected language: {detected_lang}")
        log_func(f"   Raw segments: {len(raw_segments)}")

        # ── Step 4: Word-level alignment (wav2vec2) ──
        log_func("[4/4] 🎯 Aligning with wav2vec2 for word timestamps...")
        try:
            align_model, align_metadata = whisperx.load_align_model(
                language_code=detected_lang,
                device=device,
            )
            aligned = whisperx.align(
                raw_segments,
                align_model,
                align_metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            aligned_segments = aligned.get("segments", raw_segments)

            # Clean up align model
            del align_model
            log_func(f"✅ Alignment complete! {len(aligned_segments)} segments")
        except Exception as e:
            log_func(f"⚠️ Alignment failed ({e}), using raw segments")
            aligned_segments = raw_segments

        # Build output segments with word-level data
        segments = []
        full_text_parts = []
        for seg in aligned_segments:
            text = seg.get("text", "").strip()
            if not text:
                continue
            segments.append({
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "text": text,
            })
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        log_func(f"✅ Transcription complete! {len(segments)} segments")
        log_func(f"   Text length: {len(full_text)} chars")

        # Write SRT
        srt_content = _segments_to_srt(segments)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        log_func(f"✅ SRT saved: {output_srt_path}")

        # Model stays in cache for reuse
        # Use clear_sub_cache() to free memory explicitly

        return {
            "engine": "whisperx",
            "language": detected_lang,
            "text": full_text,
            "srt_path": output_srt_path,
            "segments_count": len(segments),
            "segments": segments,
        }

    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


# ══════════════════════════════════════════════════
# ENGINE 1: Qwen3-ASR (original)
# ══════════════════════════════════════════════════

def transcribe_and_generate_srt(
    video_path: str,
    output_srt_path: str,
    lang: str = "auto",
    model_name: str = DEFAULT_MODEL,
    use_aligner: bool = True,
    model_cache_dir: Optional[str] = None,
    log_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Main SUB pipeline:
    1. Extract audio from video
    2. Load Qwen3-ASR model
    3. Transcribe with auto language detection
    4. Generate word-level timestamps (optional)
    5. Export SRT file

    Args:
        video_path: Path to input video
        output_srt_path: Path to save SRT file
        lang: Language code or "auto" for auto-detection
        model_name: HuggingFace model name
        use_aligner: Whether to use ForcedAligner for word timestamps
        model_cache_dir: Cache directory for models
        log_func: Callback for progress messages

    Returns:
        dict with keys: language, text, srt_path, segments_count
    """
    if log_func is None:
        log_func = print

    # ── Step 1: Extract audio ──
    log_func("[1/4] 🎵 Extracting audio from video...")
    audio_path = os.path.join(
        tempfile.gettempdir(),
        f"aurasplit_sub_{int(time.time())}.wav"
    )

    if not _extract_audio(video_path, audio_path, log_func):
        raise RuntimeError(f"Failed to extract audio from {video_path}")

    try:
        import torch
        from qwen_asr import Qwen3ASRModel

        # Set cache dir if provided
        if model_cache_dir:
            os.environ["HF_HOME"] = model_cache_dir
            os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(model_cache_dir, "hub")

        # Determine device
        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

        log_func(f"   Device: {device}, Model: {model_name}")

        # ── Step 2: Load model (cached) ──
        cache_key = f"qwen:{model_name}:{device}:{use_aligner}"
        if cache_key in _model_cache:
            model = _model_cache[cache_key]
            log_func("[2/4] ⚡ Qwen3-ASR model loaded from cache!")
        else:
            log_func("[2/4] 🧠 Loading Qwen3-ASR model (first time)...")
            # Build model kwargs
            model_kwargs = dict(
                dtype=dtype,
                device_map=device,
                max_inference_batch_size=1,
                max_new_tokens=512,
            )

            # Add forced aligner if requested
            if use_aligner:
                log_func(f"   + ForcedAligner: {ALIGNER_MODEL}")
                model_kwargs["forced_aligner"] = ALIGNER_MODEL
                model_kwargs["forced_aligner_kwargs"] = dict(
                    dtype=dtype,
                    device_map=device,
                )

            model = Qwen3ASRModel.from_pretrained(model_name, **model_kwargs)
            _model_cache[cache_key] = model
            log_func("✅ Model loaded & cached!")

        # ── Step 3: Transcribe ──
        log_func("[3/4] 🎤 Transcribing audio...")

        # Determine language parameter
        language_param = SUPPORTED_LANGUAGES.get(lang, None)
        if lang == "auto":
            language_param = None

        transcribe_kwargs = dict(
            audio=audio_path,
            language=language_param,
        )
        if use_aligner:
            transcribe_kwargs["return_time_stamps"] = True

        results = model.transcribe(**transcribe_kwargs)

        if not results:
            raise RuntimeError("Transcription returned empty results")

        result = results[0]
        detected_lang = getattr(result, "language", lang)
        text = getattr(result, "text", "")
        time_stamps = getattr(result, "time_stamps", None)

        log_func(f"✅ Transcription complete!")
        log_func(f"   Language: {detected_lang}")
        log_func(f"   Text length: {len(text)} chars")

        # ── Step 4: Generate SRT ──
        log_func("[4/4] 📝 Generating SRT subtitle file...")

        if use_aligner and time_stamps:
            # Word-level timestamps → group into segments
            segments = _word_timestamps_to_segments(time_stamps)
            log_func(f"   Word-level timestamps: {len(time_stamps)} words → {len(segments)} segments")
        else:
            # Segment-level only (fallback)
            segments = []
            if hasattr(result, "segments"):
                for seg in result.segments:
                    segments.append({
                        "start": getattr(seg, "start", 0),
                        "end": getattr(seg, "end", 0),
                        "text": getattr(seg, "text", ""),
                    })
            elif text:
                # Single segment fallback
                segments = [{"start": 0, "end": 30, "text": text}]
            log_func(f"   Segment-level: {len(segments)} segments")

        # Write SRT
        srt_content = _segments_to_srt(segments)
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        log_func(f"✅ SRT saved: {output_srt_path}")
        log_func(f"   Total segments: {len(segments)}")

        # Model stays in cache for reuse
        # Use clear_sub_cache() to free memory explicitly

        return {
            "engine": "qwen",
            "language": detected_lang,
            "text": text,
            "srt_path": output_srt_path,
            "segments_count": len(segments),
            "segments": segments,  # Return for preview
        }

    finally:
        # Clean up temp audio
        try:
            os.remove(audio_path)
        except OSError:
            pass
