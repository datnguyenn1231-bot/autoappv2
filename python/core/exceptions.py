# ==============================================================================
# AuraSplit Custom Exceptions - Centralized error handling
# ==============================================================================

"""
Centralized exception classes for AuraSplit.
All custom exceptions inherit from AuraSplitError for easy catching.
"""


class AuraSplitError(Exception):
    """Base exception for all AuraSplit errors"""
    pass


class ModelLoadError(AuraSplitError):
    """AI model (WhisperX, VAD) failed to load"""
    pass


class FFmpegError(AuraSplitError):
    """FFmpeg/ffprobe command failed"""
    pass


class LicenseError(AuraSplitError):
    """License validation or HWID binding failed"""
    pass


class StopRequestedError(AuraSplitError):
    """User pressed STOP button"""
    pass


class InputFileError(AuraSplitError):
    """Input file not found or invalid"""
    pass


class VRAMError(AuraSplitError):
    """Insufficient VRAM for model"""
    pass


class EncodingError(AuraSplitError):
    """Video/audio encoding failed"""
    pass
