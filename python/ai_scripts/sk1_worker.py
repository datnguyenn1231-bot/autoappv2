# ==============================================================================
# SK1 AI Worker - Standalone WhisperX Transcription
# Runs in python_embed environment via subprocess
# ==============================================================================

import sys
import os
import warnings
import logging
import re

# ==============================================================================
# CRITICAL: Suppress noisy 3rd-party library warnings
# These are informational/deprecation messages, not errors
# ==============================================================================

# Patterns to filter from stderr (these bypass warnings module)
_FILTER_PATTERNS = [
    r"pkg_resources is deprecated",
    r"resume_download.*deprecated",
    r"gradient_checkpointing.*deprecated",
    r"TensorFloat-32.*disabled",
    r"ReproducibilityWarning",
    r"Ignored unknown kwarg",
    r"Some weights.*not used",
    r"Some weights.*not initialized",
    r"TRAIN this model",
    r"Lightning automatically upgraded",
    r"Model was trained with",
    r"Bad things might happen",
    r"whisperx\.asr.*INFO",
    r"whisperx\.vads.*INFO",
    r"Performing voice activity detection",
    r"No language specified",
    r"pyannote.*INFO",
    r"pytorch_lightning",
    r"This IS expected if you are initializing",
    r"This IS NOT expected",
    r"wav2vec2\.encoder\.pos_conv_embed",
    r"UserWarning:",
    r"FutureWarning:",
]

class FilteredStderr:
    """Filter out noisy library messages from stderr."""
    def __init__(self, original):
        self.original = original
        self.pattern = re.compile("|".join(_FILTER_PATTERNS), re.IGNORECASE)
        self.buffer = ""
    
    def write(self, msg):
        # Buffer multiline messages
        self.buffer += msg
        if "\n" in self.buffer:
            lines = self.buffer.split("\n")
            self.buffer = lines[-1]  # Keep incomplete line in buffer
            for line in lines[:-1]:
                if line.strip() and not self.pattern.search(line):
                    self.original.write(line + "\n")
    
    def flush(self):
        if self.buffer.strip() and not self.pattern.search(self.buffer):
            self.original.write(self.buffer)
        self.buffer = ""
        self.original.flush()
    
    def fileno(self):
        return self.original.fileno()

# Replace stderr and stdout with filtered versions
sys.stderr = FilteredStderr(sys.stderr)
sys.stdout = FilteredStderr(sys.stdout)

# Suppress all warnings from these modules
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
warnings.filterwarnings("ignore", message=".*resume_download.*")
warnings.filterwarnings("ignore", message=".*gradient_checkpointing.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*")
warnings.filterwarnings("ignore", message=".*ReproducibilityWarning.*")
warnings.filterwarnings("ignore", message=".*Ignored unknown kwarg.*")
warnings.filterwarnings("ignore", message=".*Some weights.*not used.*")
warnings.filterwarnings("ignore", message=".*Some weights.*not initialized.*")
warnings.filterwarnings("ignore", message=".*TRAIN this model.*")
warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")
warnings.filterwarnings("ignore", message=".*Model was trained with.*")
warnings.filterwarnings("ignore", message=".*Bad things might happen.*")

# Suppress logging from noisy modules
logging.getLogger("pytorch_lightning").setLevel(logging.ERROR)
logging.getLogger("lightning").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("transformers.modeling_utils").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("pyannote").setLevel(logging.ERROR)
logging.getLogger("pyannote.audio").setLevel(logging.ERROR)
logging.getLogger("whisperx").setLevel(logging.ERROR)
logging.getLogger("whisperx.asr").setLevel(logging.ERROR)
logging.getLogger("whisperx.vads").setLevel(logging.ERROR)
logging.getLogger("whisperx.vads.pyannote").setLevel(logging.ERROR)
logging.getLogger("faster_whisper").setLevel(logging.ERROR)

# GROK FIX: Use transformers internal logging API
try:
    import transformers
    transformers.logging.set_verbosity_error()
except Exception:
    pass

# ==============================================================================
# CRITICAL: Environment setup (MUST match DEV mode exactly!)
# This runs BEFORE any HuggingFace/AI imports
# ==============================================================================

# 1. Set HF cache to models_ai folder (next to AuraSplit.exe)
_script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_models_dir = os.path.join(_script_dir, "models_ai")
os.makedirs(_models_dir, exist_ok=True)

# 1.1 FIX: Prevent MKL/OpenMP crash (ACCESS_VIOLATION 0xC0000005)
# From AI Studio analysis - critical for EXE stability
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MKL_THREADING_LAYER"] = "INTEL"  # Or "GNU" if still crash

# 1.2 FIX: Add DLL directory for python_embed
_base_dir = os.path.dirname(_script_dir) if "ai_scripts" in _script_dir else _script_dir
if hasattr(os, 'add_dll_directory'):
    try:
        os.add_dll_directory(_base_dir)
        _py_embed = os.path.join(_script_dir, "python_embed")
        if os.path.exists(_py_embed):
            os.add_dll_directory(_py_embed)
    except Exception:
        pass

# 1.5 CUDA DLL PATH FIX - Add nvidia package paths to PATH
# Required for cublas64_12.dll, cudnn, etc.
_site_packages = os.path.join(_script_dir, "python_embed", "Lib", "site-packages")
_nvidia_paths = [
    os.path.join(_site_packages, "nvidia", "cublas", "bin"),
    os.path.join(_site_packages, "nvidia", "cudnn", "bin"),
    os.path.join(_site_packages, "nvidia", "cuda_runtime", "bin"),
    os.path.join(_site_packages, "nvidia", "cufft", "bin"),
    os.path.join(_site_packages, "nvidia", "curand", "bin"),
]
for _path in _nvidia_paths:
    if os.path.exists(_path) and _path not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _path + os.pathsep + os.environ.get("PATH", "")

os.environ["HF_HUB_CACHE"] = _models_dir
os.environ["HUGGINGFACE_HUB_CACHE"] = _models_dir
os.environ["HF_HOME"] = _models_dir

# 2. Disable symlinks (Windows privilege issues)
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# CRITICAL FIX: Monkeypatch os.symlink to copy instead (for newer huggingface_hub)
# Some versions of huggingface_hub ignore the env var
import shutil
_original_symlink = os.symlink
def _symlink_to_copy(src, dst, **kwargs):
    """Replace symlink with file copy on Windows."""
    try:
        # Try original symlink first
        return _original_symlink(src, dst, **kwargs)
    except OSError as e:
        if e.winerror == 1314:  # Privilege not held
            # Fallback: copy file instead of symlink
            src_abs = os.path.abspath(os.path.join(os.path.dirname(dst), src)) if not os.path.isabs(src) else src
            if os.path.exists(src_abs):
                shutil.copy2(src_abs, dst)
                return
        raise
os.symlink = _symlink_to_copy

# 3. Disable XET (bypass hf_xet requirement - same as DEV)
os.environ["HF_HUB_DISABLE_XET"] = "1"

# 4. SSL certificates for HTTPS (same as DEV)
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    pass

# ==============================================================================
# 5. AGGRESSIVE DOWNLOAD THROTTLING (CRITICAL for weak machines!)
# Without this: 99% RAM, 100% SSD, machine crash, NVIDIA error, auto shutdown
# ==============================================================================

# Disable fast transfer (uses excessive RAM - buffers entire file in memory!)
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

# Force single-thread download (reduces RAM/SSD pressure)
os.environ["HF_HUB_DOWNLOAD_WORKERS"] = "1"

# Timeouts (prevent infinite hangs)
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "600"  # 10 min per file (large models)
os.environ["HF_HUB_ETAG_TIMEOUT"] = "60"  # 1 min metadata check

# Disable parallel downloads inside huggingface_hub
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

# Requests session settings (chunked download)
os.environ["REQUESTS_TIMEOUT"] = "600"

# ==============================================================================
# 6. Progress output for UI (print to stdout so parent can capture)
# ==============================================================================
# Keep progress bars ENABLED so user can see download %
# Parent process captures stdout and displays in UI
os.environ.pop("TQDM_DISABLE", None)  # Remove if exists
os.environ.pop("HF_HUB_DISABLE_PROGRESS_BARS", None)  # Remove if exists

# ==============================================================================
# 7. UNBUFFERED OUTPUT (CRITICAL for subprocess communication!)
# Without this, output buffers in memory causing RAM spike
# ==============================================================================
import io
# Force unbuffered stdout/stderr for real-time output to parent
if hasattr(sys.stdout, 'fileno'):
    try:
        sys.stdout = io.TextIOWrapper(
            open(sys.stdout.fileno(), 'wb', buffering=0),
            encoding='utf-8', errors='replace', write_through=True
        )
        sys.stderr = io.TextIOWrapper(
            open(sys.stderr.fileno(), 'wb', buffering=0),
            encoding='utf-8', errors='replace', write_through=True
        )
    except Exception:
        pass  # Fallback if fileno not available

def log(msg):
    """Print with immediate flush to parent process."""
    print(msg, flush=True)

# ==============================================================================
# BRANDED MODEL NAMES - Hide real Whisper model names from users
# ==============================================================================
MODEL_DISPLAY_NAMES = {
    "tiny": "💨 LITE",
    "tiny.en": "💨 LITE (English)",
    "base": "⚡ BASIC",
    "base.en": "⚡ BASIC (English)", 
    "small": "🔷 STANDARD",
    "small.en": "🔷 STANDARD (English)",
    "medium": "🔶 ADVANCED",
    "medium.en": "🔶 ADVANCED (English)",
    "large": "💎 PREMIUM",
    "large-v2": "💎 PREMIUM V2",
    "large-v3": "💎 PREMIUM MAX",
    "large-v3-turbo": "🚀 PREMIUM TURBO",
}

def get_display_name(model_name: str) -> str:
    """Get branded display name for model."""
    return MODEL_DISPLAY_NAMES.get(model_name, f"⚙️ {model_name.upper()}")

import json
import gc

# ==============================================================================
# 8. AURA SPLIT ULTIMATE FIX V2 - PyTorch 2.6+ NUCLEAR FIX
# ==============================================================================
import torch
import omegaconf  # Required to whitelist this module

# Step A: Whitelist omegaconf classes (official PyTorch way)
try:
    torch.serialization.add_safe_globals([
        omegaconf.listconfig.ListConfig,
        omegaconf.dictconfig.DictConfig
    ])
except Exception:
    pass  # Skip if torch version doesn't have this function

# Step B: Force override weights_only=False (nuclear option)
_original_torch_load = torch.load

def _patched_torch_load(f, map_location=None, pickle_module=None, **kwargs):
    """Nuclear patch: FORCE weights_only=False for all torch.load calls."""
    # FORCE disable security check (required for pyannote/whisperx models)
    kwargs['weights_only'] = False
    return _original_torch_load(f, map_location=map_location, pickle_module=pickle_module, **kwargs)

torch.load = _patched_torch_load
# ==============================================================================


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


def normalize_lang_code(lang_code):
    """Return None when user wants auto-detect."""
    if lang_code is None:
        return None
    s = str(lang_code).strip().lower()
    return None if s in ("", "auto", "detect") else s


def transcribe_with_auto(model, audio, lang_code):
    """Transcribe with auto language detection."""
    lang_for_transcribe = normalize_lang_code(lang_code)
    kwargs = {"batch_size": 2}
    if lang_for_transcribe is not None:
        kwargs["language"] = lang_for_transcribe

    result = model.transcribe(audio, **kwargs)
    detected_lang = result.get("language") or lang_for_transcribe or "en"
    return result, detected_lang


def extract_words(result_segments):
    """Extract words from segments with fallback."""
    all_words = []
    for seg_idx, seg in enumerate(result_segments or []):
        if isinstance(seg, dict) and "words" in seg and seg.get("words"):
            # Handle case where words might be strings or dicts
            for w in seg.get("words", []):
                if isinstance(w, dict) and "start" in w:
                    all_words.append(w)
                elif isinstance(w, str):
                    # Word is just a string, skip it (need alignment data)
                    continue
        else:
            try:
                all_words.append({
                    "word": seg.get("text", ""),
                    "start": seg["start"],
                    "end": seg["end"]
                })
            except Exception:
                continue
    return all_words


def main():
    if len(sys.argv) < 2:
        print("[AI] ERROR: Missing config file path", file=sys.stderr)
        sys.exit(1)

    config_path = sys.argv[1]

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[AI] ERROR: Failed to read config: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract config
    audio_path = config.get("audio_path", "")
    model_name = config.get("model_name", "large-v3-turbo")
    device = config.get("device", "cuda")
    compute_type = config.get("compute_type", "float16")
    lang_code = config.get("lang_code", None)
    fast_mode = config.get("fast_mode", False)
    model_cache_dir = config.get("model_cache_dir", None)
    output_path = config.get("output_path", "result.json")

    # Validate
    if not audio_path or not os.path.exists(audio_path):
        print(f"[AI] ERROR: Audio file not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Import AI libraries
        print("[AI] Importing libraries...")
        import torch
        import whisperx

        # Check device
        if device == "cuda" and not torch.cuda.is_available():
            print("[AI] WARNING: CUDA not available, falling back to CPU")
            device = "cpu"
            compute_type = "int8"

        if device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"[AI] GPU: {gpu_name} ({total_vram:.1f}GB)")
        else:
            print("[AI] Running on CPU")

        # Load model
        print(f"[AI] Loading model: {get_display_name(model_name)}...")
        
        # CRITICAL FIX: Clean up .incomplete files from previous failed downloads
        # These cause WinError 32 (file in use) and system freeze
        if model_cache_dir and os.path.exists(model_cache_dir):
            from pathlib import Path
            incomplete_files = list(Path(model_cache_dir).rglob("*.incomplete"))
            if incomplete_files:
                print(f"[AI] 🧹 Cleaning {len(incomplete_files)} incomplete download(s)...")
                for p in incomplete_files:
                    try:
                        os.remove(p)
                        print(f"[AI]    Removed: {p.name}")
                    except Exception as e:
                        print(f"[AI]    ⚠️ Could not remove {p.name}: {e}")
        
        # Check if model needs download
        model_folder = os.path.join(model_cache_dir, f"models--Systran--faster-whisper-{model_name}") if model_cache_dir else None
        if model_folder and not os.path.exists(model_folder):
            print("[AI] ⚠️ First run: Downloading model (~3GB). Please wait...")
            print("[AI] 📥 Download may take 5-10 min depending on network...")
        sys.stdout.flush()  # Force output immediately
        
        load_kwargs = {
            "whisper_arch": model_name,
            "device": device,
            "compute_type": compute_type,
        }
        if model_cache_dir:
            load_kwargs["download_root"] = model_cache_dir

        model = whisperx.load_model(**load_kwargs)
        print("[AI] ✅ Model loaded successfully!")

        # Load audio
        print("[AI] Loading audio...")
        audio = whisperx.load_audio(audio_path)

        # Transcribe
        print("[AI] Transcribing...")
        result, detected_lang = transcribe_with_auto(model, audio, lang_code)
        print(f"[AI] Detected language: {detected_lang}")

        # Free transcription model
        del model
        aggressive_gc()

        # Alignment
        if fast_mode:
            print("[AI] Fast mode - skipping alignment")
        else:
            print(f"[AI] Aligning ({detected_lang})...")
            try:
                align_kwargs = {
                    "language_code": detected_lang,
                    "device": device,
                }
                if model_cache_dir:
                    align_kwargs["model_dir"] = model_cache_dir

                model_a, metadata = whisperx.load_align_model(**align_kwargs)
                result = whisperx.align(
                    result["segments"],
                    model_a,
                    metadata,
                    audio,
                    device,
                    return_char_alignments=False,
                )
                del model_a
                del metadata
                aggressive_gc()
                print("[AI] Alignment complete!")
            except Exception as e:
                print(f"[AI] WARNING: Alignment failed: {e}")

        # Extract words
        segments = result.get("segments", [])
        words = extract_words(segments)

        # Prepare output
        output_data = {
            "segments": segments,
            "language": detected_lang,
            "words": words,
        }

        # Write output
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"[AI] Output saved: {output_path}")
        print(f"[AI] Segments: {len(segments)}, Words: {len(words)}")

        # Cleanup
        aggressive_gc()
        print("[AI] Done!")
        
        # ================================================================
        # SAFER EXIT: Ensure file is written, then exit cleanly
        # TerminateProcess may cause issues with parent reading files
        # ================================================================
        import time
        time.sleep(1.0)  # Extra wait for file I/O to complete
        
        # Force release CUDA memory before exit
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()  # Wait for CUDA to finish
        except Exception:
            pass
        
        # Flush all file handles
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        
        # Use os._exit instead of TerminateProcess - cleaner for parent
        os._exit(0)

    except Exception as e:
        print(f"[AI] ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        # Use TerminateProcess even on error
        try:
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(
                ctypes.windll.kernel32.GetCurrentProcess(), 1
            )
        except Exception:
            os._exit(1)


if __name__ == "__main__":
    main()
