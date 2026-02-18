# ==============================================================================
# UI Constants for AuraSplit
# ==============================================================================

LANG_OPTIONS = [
    ("auto", "Auto (Detect)"),
    ("vi", "VI - Vietnamese"),
    ("en", "EN - English"),
    ("ja", "JA - Japanese"),
    ("ko", "KO - Korean"),
    ("zh", "ZH - Chinese"),
    ("th", "TH - Thai"),
    ("id", "ID - Indonesian"),
    ("ms", "MS - Malay"),
    ("fr", "FR - French"),
    ("de", "DE - German"),
]

MODEL_OPTIONS = [
    "LITE",
    "STARTER",
    "STANDARD",
    "PRO",
    "ULTRA",
    "PREMIUM",
    "⚡ TURBO",
]

# Model mapping: UI name -> actual WhisperX model name (hidden from users)
MODEL_MAP = {
    "LITE": "tiny",
    "STARTER": "base",
    "STANDARD": "small",
    "PRO": "medium",
    "ULTRA": "large-v2",
    "PREMIUM": "large-v3",
    "⚡ TURBO": "large-v3-turbo",
}

# UI friendly names (engine_merge/pipeline sẽ tự map về xfade)
TRANSITION_OPTIONS = [
    "Không",
    "Ngẫu nhiên",
    "Fade",
    "Wipe Left",
    "Wipe Right",
    "Wipe Up",
    "Wipe Down",
    "Slide Left",
    "Slide Right",
    "Slide Up",
    "Slide Down",
    "Circle Open",
    "Circle Close",
    "Radial",
    "Pixelize",
    "Zoom In",
    "Dissolve",
    "Fade Black",
    "Fade White",
    "Diag TL",
    "Diag TR",
    "Diag BL",
    "Diag BR",
    "HLSlice",
    "HRSlice",
    "VUSlice",
    "VDSlice",
    "HBlur",
    "Fadegrays",
    "Wipe TL",
    "Wipe TR",
    "Wipe BL",
    "Wipe BR",
    "SqueezeH",
    "SqueezeV",
    "FadeFast",
    "FadeSlow",
    "HLWind",
    "HRWind",
    "VUWind",
    "VDWind",
    "Cover Left",
    "Cover Right",
    "Cover Up",
    "Cover Down",
    "Reveal Left",
    "Reveal Right",
    "Reveal Up",
    "Reveal Down",
]

# Final output presets
FINAL_OUTPUT_OPTIONS = [
    "16:9 (1920x1080)",
    "16:9 (1280x720)",
    "9:16 (1080x1920)",
    "9:16 (720x1280)",
]

# FX (VFX overlay / motion) - matching engine_fx.py effects
FX_OPTIONS = [
    "None",
    "Zoom Pulse",
    "Shake",
    "Glitch",
    "Glitch Heavy",
    "Glitch + Shake",
    "Retro VHS",
    "VHS + Shake",
    "Cinematic",
    "Cinematic + Zoom",
    "Dreamy",
]


# Helper: Map display label back to language code
def _get_lang_code(display_label: str) -> str:
    """Convert display label (VI - Vietnamese) to code (vi)"""
    for code, label in LANG_OPTIONS:
        if label == display_label:
            return code
    return "auto"  # fallback
