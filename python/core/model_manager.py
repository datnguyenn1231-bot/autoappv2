# ==============================================================================
# Model management utilities for AuraSplit
# Handles model caching, VRAM checking, and garbage collection
# ==============================================================================

import gc

# Import centralized exceptions
from core.exceptions import StopRequestedError

# Model caching - keep model loaded between tasks
MODEL_CACHE = {
    "model": None,           # Cached whisperx model
    "model_name": None,      # Name of cached model (e.g., "large-v3")
    "device": None,          # Device model was loaded on
    "compute_type": None,    # Compute type used
}
KEEP_MODEL_LOADED = False  # Toggle to enable/disable model caching

# Backward compatibility alias
StopRequested = StopRequestedError


def aggressive_gc():
    """Force garbage collection and clear GPU cache."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def set_stop_signal(val):
    """Set stop signal across all engines."""
    # Import here to avoid circular imports
    try:
        import engine_merge
        engine_merge.set_stop_signal(val)
    except Exception:
        pass
    try:
        import engine_fx
        engine_fx.set_stop_signal(val)
    except Exception:
        pass
    try:
        import safe_kernel
        safe_kernel.set_stop_signal(val)
    except Exception:
        pass


def set_keep_model_loaded(val: bool):
    """Enable/disable keeping model in memory between tasks."""
    global KEEP_MODEL_LOADED
    KEEP_MODEL_LOADED = bool(val)
    print(f"[ModelCache] Keep model loaded: {KEEP_MODEL_LOADED}")
    if not val:
        # Clear cache when disabling
        clear_model_cache()


def clear_model_cache():
    """Clear cached model and free GPU memory."""
    global MODEL_CACHE
    if MODEL_CACHE["model"] is not None:
        print("[ModelCache] Clearing cached model...")
        del MODEL_CACHE["model"]
        MODEL_CACHE["model"] = None
        MODEL_CACHE["model_name"] = None
        MODEL_CACHE["device"] = None
        MODEL_CACHE["compute_type"] = None
        aggressive_gc()


def check_vram_available(log_func=None, min_gb=6):
    """Check if enough VRAM is available. Returns True if OK, False if low."""
    try:
        import torch
    except ImportError:
        if log_func:
            log_func("💻 CPU Mode - torch not loaded")
        return True

    if not torch.cuda.is_available():
        if log_func:
            log_func("💻 CPU Mode - Không cần check VRAM")
        return True

    try:
        total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
        allocated = torch.cuda.memory_allocated(0) / (1024**3)
        free = total - allocated

        if log_func:
            log_func(f"🎮 GPU VRAM: {free:.1f}GB free / {total:.1f}GB total")

        if free < min_gb:
            if log_func:
                log_func(f"⚠️ WARNING: VRAM thấp ({free:.1f}GB < {min_gb}GB). Có thể chậm/crash!")
            return False
        return True
    except Exception as e:
        if log_func:
            log_func(f"⚠️ Không check được VRAM: {e}")
        return True
