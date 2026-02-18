"""
Async Logger — Threaded Queue for Realtime Log Streaming
=========================================================
Solves: Main thread blocked by FFmpeg readline() → stdout writes starved.
Pattern: Producer (main thread) → Queue → Consumer (daemon thread → stdout).
"""
import sys
import json
import threading
import queue

_log_queue: queue.Queue = queue.Queue()
_shutdown = False


def _sanitize(value):
    """Remove newlines from strings for single-line JSON."""
    if isinstance(value, str):
        return value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ').strip()
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _log_worker():
    """Daemon thread: dedicated stdout writer. Never blocked by FFmpeg."""
    while True:
        try:
            payload = _log_queue.get(timeout=1.0)
        except queue.Empty:
            if _shutdown:
                break
            continue

        if payload is None:
            break

        try:
            payload = _sanitize(payload)
            line = json.dumps(payload, ensure_ascii=False)
            line = line.replace('\n', ' ').replace('\r', '')
            # Use print() — proven to work for stdout pipe to Electron
            print(line, flush=True)
        except Exception as e:
            # Fallback: write error to stderr so we can debug
            try:
                sys.stderr.write(f"[ASYNC_LOGGER ERROR] {e}\n")
                sys.stderr.flush()
            except Exception:
                pass
        finally:
            _log_queue.task_done()


# Start daemon thread on module import
_worker_thread = threading.Thread(target=_log_worker, daemon=True, name="AsyncLogger")
_worker_thread.start()


def emit_async(event_type: str, **kwargs):
    """Non-blocking emit: push to queue → daemon thread writes to stdout."""
    payload = {"type": event_type, **kwargs}
    _log_queue.put(payload)


def shutdown():
    """Graceful shutdown."""
    global _shutdown
    _shutdown = True
    _log_queue.put(None)
    _worker_thread.join(timeout=3.0)
