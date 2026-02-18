# ==============================================================================
# FFmpeg utilities for AuraSplit
# ==============================================================================

import os
import subprocess
from functools import lru_cache

import safe_kernel
from core.exceptions import StopRequestedError, FFmpegError

# FFmpeg threading optimization - use all CPU cores
FFMPEG_THREADS = ["-threads", "0"]

# Module-level stop flag (will be synced with main)
_STOP_FLAG = False


def set_stop_flag(val):
    """Set the stop flag for this module."""
    global _STOP_FLAG
    _STOP_FLAG = bool(val)


def run_ffmpeg_fast(cmd_list):
    """Execute FFmpeg command with stop signal support."""
    if _STOP_FLAG:
        raise StopRequestedError("User stopped the operation")

    # Auto-create output directory if needed
    # The last argument is typically the output file
    if len(cmd_list) > 1:
        output_path = cmd_list[-1]
        if isinstance(output_path, str) and not output_path.startswith('-'):
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

    try:
        safe_kernel.execute_safe(cmd_list)
    except RuntimeError as e:
        if "STOPPED" in str(e).upper():
            raise StopRequestedError("User stopped the operation")
        raise FFmpegError(f"FFmpeg command failed: {e}")


@lru_cache(maxsize=1)
def check_cuda_decode_available():
    """
    Check if CUDA hardware decode is available.
    Cached - only checks once per session.
    """
    try:
        # Test simple CUDA decode with a synthetic source
        test_cmd = [
            "ffmpeg", "-v", "error",
            "-hwaccel", "cuda",
            "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
            "-frames:v", "1", "-f", "null", "-"
        ]
        result = subprocess.run(
            test_cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,  # CRITICAL for PyInstaller
        )
        return result.returncode == 0
    except Exception:
        return False


def get_hwaccel_flags():
    """
    Get hardware acceleration flags for FFmpeg input.
    Returns empty list if CUDA decode not available.
    
    Usage:
        cmd = ["ffmpeg", "-y"] + get_hwaccel_flags() + ["-i", input, ...]
    """
    if check_cuda_decode_available():
        # Only use -hwaccel cuda (not -hwaccel_output_format cuda)
        # because output_format cuda keeps frames in GPU memory,
        # which is incompatible with CPU-based filters (scale, pad, format, etc.)
        return ["-hwaccel", "cuda"]
    return []


def get_best_encoder(log_func=None):
    """Chọn encoder tốt nhất: ưu tiên NVENC nếu khả dụng, fallback libx264."""
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
        result = subprocess.run(
            test_cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.PIPE,
            timeout=10,  # Add timeout for safety
            creationflags=subprocess.CREATE_NO_WINDOW,  # CRITICAL for PyInstaller
        )
        if result.returncode == 0:
            if log_func:
                hwaccel = "+" if check_cuda_decode_available() else ""
                log_func(f"🚀 TURBO MODE: NVENC{hwaccel} (GPU)!")
            return "h264_nvenc", "p1"  # p1 = fastest encoding
        else:
            if log_func:
                log_func("🛡️ SAFE MODE: Chạy CPU (libx264).")
            return "libx264", "ultrafast"
    except subprocess.TimeoutExpired:
        if log_func:
            log_func("⚠️ Encoder probe timeout, using CPU fallback.")
        return "libx264", "ultrafast"
    except Exception:
        return "libx264", "ultrafast"
