# ==============================================================================
# Path configuration for AuraSplit
# ==============================================================================

import os
import sys

# CACHED model directory - computed once at startup
_CACHED_MODEL_DIR = None


def _get_app_model_dir():
    """Determine model directory based on execution context. CACHED for speed."""
    global _CACHED_MODEL_DIR
    if _CACHED_MODEL_DIR is not None:
        return _CACHED_MODEL_DIR

    # Get the directory where this script is located
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        # For config module, go up one level to get project root
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Check if DEV mode: models_ai folder exists next to script
    local_models = os.path.join(script_dir, "models_ai")
    if os.path.exists(local_models):
        _CACHED_MODEL_DIR = local_models
        return _CACHED_MODEL_DIR

    # Customer: use AppData (writable location)
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        model_dir = os.path.join(appdata, "AuraSplit", "models")
    else:
        model_dir = os.path.join(os.path.expanduser("~"), ".aurasplit", "models")

    os.makedirs(model_dir, exist_ok=True)
    _CACHED_MODEL_DIR = model_dir
    return _CACHED_MODEL_DIR
