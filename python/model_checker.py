#!/usr/bin/env python3
"""
AuraSplit v2 — Model Checker & Downloader
Downloads Whisper models from HuggingFace without symlinks (Windows-safe).

Usage:
    from model_checker import download_model, is_model_ready
    
    if not is_model_ready("large-v3", "models_ai"):
        success, path = download_model("large-v3", target_dir="models_ai")
"""

import os
import sys
import json
import shutil

# Ensure no symlinks
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


# HuggingFace repo IDs for faster-whisper CTranslate2 models
MODEL_REPOS = {
    "tiny":           "Systran/faster-whisper-tiny",
    "base":           "Systran/faster-whisper-base",
    "small":          "Systran/faster-whisper-small",
    "medium":         "Systran/faster-whisper-medium",
    "large-v2":       "Systran/faster-whisper-large-v2",
    "large-v3":       "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "Systran/faster-whisper-large-v3-turbo",
}

# Required files for a CTranslate2 Whisper model
REQUIRED_FILES = ["model.bin", "config.json", "tokenizer.json"]
VOCAB_FILES = ["vocabulary.txt", "vocabulary.json"]  # either one is acceptable


def is_model_ready(model_name: str, target_dir: str = "models_ai") -> bool:
    """Check if model is downloaded and has all required files."""
    model_path = os.path.join(target_dir, model_name)
    if not os.path.isdir(model_path):
        return False
    for f in REQUIRED_FILES:
        if not os.path.isfile(os.path.join(model_path, f)):
            return False
    return True


def get_model_path(model_name: str, target_dir: str = "models_ai") -> str:
    """Get absolute path to model directory."""
    return os.path.abspath(os.path.join(target_dir, model_name))


def download_model(
    model_name: str,
    target_dir: str = "models_ai",
    log_func=None,
    progress_callback=None
) -> tuple:
    """
    Download a faster-whisper model from HuggingFace.
    
    Uses huggingface_hub.snapshot_download with local_dir to avoid symlinks.
    Falls back to direct HTTP download if huggingface_hub is not available.
    
    Returns: (success: bool, model_path: str)
    """
    if log_func is None:
        log_func = print
    
    repo_id = MODEL_REPOS.get(model_name)
    if not repo_id:
        log_func(f"❌ Unknown model: {model_name}")
        return False, ""
    
    model_path = os.path.abspath(os.path.join(target_dir, model_name))
    os.makedirs(model_path, exist_ok=True)
    
    # Check if already downloaded
    if is_model_ready(model_name, target_dir):
        log_func(f"✅ Model already exists: {model_name}")
        return True, model_path
    
    log_func(f"📥 Downloading model: {model_name} from {repo_id}...")
    
    try:
        # Method 1: huggingface_hub snapshot_download (preferred)
        from huggingface_hub import snapshot_download
        
        downloaded_path = snapshot_download(
            repo_id=repo_id,
            local_dir=model_path,
            local_dir_use_symlinks=False,  # CRITICAL: no symlinks on Windows
            resume_download=True,
        )
        
        log_func(f"✅ Model downloaded to: {downloaded_path}")
        return True, model_path
        
    except ImportError:
        log_func("⚠️ huggingface_hub not installed, trying direct download...")
        return _download_direct(repo_id, model_path, log_func)
    except Exception as e:
        log_func(f"⚠️ snapshot_download failed: {e}")
        log_func("   Trying direct HTTP download...")
        return _download_direct(repo_id, model_path, log_func)


def _download_direct(repo_id: str, model_path: str, log_func) -> tuple:
    """Fallback: download model files directly via HTTP."""
    import urllib.request
    
    base_url = f"https://huggingface.co/{repo_id}/resolve/main"
    
    files_to_download = REQUIRED_FILES + [
        "preprocessor_config.json",
        "added_tokens.json", 
        "special_tokens_map.json",
    ]
    
    for filename in files_to_download:
        url = f"{base_url}/{filename}"
        dest = os.path.join(model_path, filename)
        
        if os.path.isfile(dest):
            log_func(f"   ✓ {filename} (exists)")
            continue
        
        try:
            log_func(f"   ↓ Downloading {filename}...")
            urllib.request.urlretrieve(url, dest)
            log_func(f"   ✓ {filename}")
        except Exception as e:
            if filename in REQUIRED_FILES:
                log_func(f"   ❌ Failed: {filename} — {e}")
                return False, model_path
            # Optional files can fail silently
    
    if is_model_ready(os.path.basename(model_path), os.path.dirname(model_path)):
        log_func("✅ Model download complete!")
        return True, model_path
    else:
        log_func("❌ Model download incomplete — missing required files")
        return False, model_path


if __name__ == "__main__":
    # CLI: python model_checker.py large-v3
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("model", default="large-v3", nargs="?")
    parser.add_argument("--dir", default="models_ai")
    args = parser.parse_args()
    
    if is_model_ready(args.model, args.dir):
        print(f"✅ {args.model} is ready at {get_model_path(args.model, args.dir)}")
    else:
        print(f"📥 Downloading {args.model}...")
        ok, p = download_model(args.model, target_dir=args.dir)
        print(f"Result: {'✅ OK' if ok else '❌ FAIL'} — {p}")
