# /safe_kernel.py
# ==============================================================================
# safe_kernel.py
# VAI TRÒ: chạy ffmpeg/ffprobe an toàn + STOP + log + last_failed_cmd
#
# FIX CHỐT:
# - TUYỆT ĐỐI KHÔNG dùng "ffmpeg @args.txt" (vì build ffmpeg của bạn không support).
# - Không tạo tool_ffmpeg_args nữa.
# - Giữ STOP, stream log, và dump last_failed_cmd.txt.
# ==============================================================================

from __future__ import annotations

import os
import shlex
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional, Sequence, Union


_STOP_LOCK = threading.Lock()
_STOP_FLAG: bool = False


def set_stop_signal(val: bool) -> None:
    global _STOP_FLAG
    with _STOP_LOCK:
        _STOP_FLAG = bool(val)


def _is_stopped() -> bool:
    with _STOP_LOCK:
        return _STOP_FLAG


def _cmd_to_args(cmd: Union[List[str], str]) -> List[str]:
    if isinstance(cmd, list):
        return [str(x) for x in cmd]
    return shlex.split(cmd, posix=False)


def _cmd_to_str(cmd: Union[str, Sequence[str]]) -> str:
    if isinstance(cmd, str):
        return cmd
    return " ".join(str(x) for x in cmd)


def _write_last_failed_cmd(cmd: Union[str, Sequence[str]], cwd: Optional[str] = None) -> str:
    base_dir = cwd or os.getcwd()
    path = os.path.join(base_dir, "last_failed_cmd.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(_cmd_to_str(cmd))
    except Exception:
        pass
    return path


def _raise_cmd_not_found(cmd: Union[str, Sequence[str]], err: Exception, cwd: Optional[str]) -> None:
    last = _write_last_failed_cmd(cmd, cwd=cwd)
    raise RuntimeError(
        "CMD NOT FOUND:\n"
        f"CMD: {cmd if isinstance(cmd, str) else (cmd[0] if cmd else '')}\n"
        "=> Kiểm tra ffmpeg/ffprobe trong PATH.\n"
        f"(Updated to: {last})"
    ) from err


def _raise_ffmpeg_crash(
    cmd: Union[str, Sequence[str]],
    stderr: str,
    stdout: str,
    returncode: int,
    cwd: Optional[str],
) -> None:
    last = _write_last_failed_cmd(cmd, cwd=cwd)

    def clip(s: str, max_len: int = 8000) -> str:
        if s is None:
            return ""
        s = str(s)
        return s if len(s) <= max_len else s[:max_len] + "\n...[TRUNCATED]...\n"

    raise RuntimeError(
        "FFMPEG CRASHED:\n"
        f"CMD: {clip(_cmd_to_str(cmd), 4000)}\n\n"
        f"STDERR:\n{clip(stderr)}\n\n"
        f"STDOUT:\n{clip(stdout)}\n\n"
        f"returncode={returncode}\n"
        f"(Updated to: {last})"
    )


def execute_safe(
    cmd: Union[List[str], str],
    *,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    log_func: Optional[Callable[[str], None]] = None,
    stream: bool = True,
    check: bool = True,
    text_mode: bool = True,
    allow_retry: bool = True,  # giữ signature để không vỡ code khác
    **_ignored_kwargs,
) -> subprocess.CompletedProcess:
    """
    Chạy subprocess an toàn.
    - stream=True: đọc stderr realtime để UI log
    - STOP: terminate/kill
    """
    if _is_stopped():
        raise RuntimeError("STOPPED")

    args = _cmd_to_args(cmd)

    if not stream:
        try:
            # AI Studio Fix: Clean environment to prevent DLL conflicts
            clean_env = (env or os.environ).copy()
            # Remove torch/CUDA paths to prevent FFmpeg loading wrong DLLs
            if "PATH" in clean_env:
                clean_env["PATH"] = ";".join([
                    p for p in clean_env["PATH"].split(";") 
                    if "torch" not in p.lower() and "cuda" not in p.lower()
                ])
            
            # AI Studio Fix: STARTUPINFO for windowed mode
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE  # Super Grok Fix
            
            cp = subprocess.run(
                args,
                cwd=cwd,
                env=clean_env,
                stdout=subprocess.DEVNULL,  # AI Studio: Force redirect to null
                stderr=subprocess.PIPE,     # Keep stderr for error capture
                stdin=subprocess.DEVNULL,   # AI Studio: FFmpeg sometimes waits for 'q'
                text=text_mode,
                encoding="utf-8" if text_mode else None,
                errors="replace" if text_mode else None,
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=False,            # FIX: close_fds=True corrupts parent stdout pipe on Windows
                startupinfo=startupinfo,
            )
        except subprocess.TimeoutExpired as e:
            last = _write_last_failed_cmd(args, cwd=cwd)
            raise RuntimeError(f"TIMEOUT\n(Updated to: {last})") from e
        except FileNotFoundError as e:
            _raise_cmd_not_found(args, e, cwd)
        except OSError as e:
            _raise_cmd_not_found(args, e, cwd)

        if _is_stopped():
            raise RuntimeError("STOPPED")

        if check and cp.returncode != 0:
            _raise_ffmpeg_crash(args, cp.stderr or "", cp.stdout or "", cp.returncode, cwd)

        return cp

    # stream mode
    # AI Studio Fix: Use DEVNULL instead of PIPE to prevent buffer deadlock
    # When ffmpeg outputs too much data, 64KB buffer fills up causing deadlock
    try:
        # AI Studio Fix: Clean environment for stream mode too
        clean_env = (env or os.environ).copy()
        if "PATH" in clean_env:
            clean_env["PATH"] = ";".join([
                p for p in clean_env["PATH"].split(";") 
                if "torch" not in p.lower() and "cuda" not in p.lower()
            ])
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE  # Super Grok Fix
        
        try:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                env=clean_env,
                stdout=subprocess.DEVNULL,  # FIX: Prevent buffer deadlock
                stderr=subprocess.PIPE,     # Keep stderr for error capture
                stdin=subprocess.DEVNULL,   # AI Studio: FFmpeg waits for 'q'
                text=text_mode,
                encoding="utf-8" if text_mode else None,
                errors="replace" if text_mode else None,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=False,            # FIX: close_fds=True corrupts parent stdout pipe on Windows
                startupinfo=startupinfo,
            )
        except FileNotFoundError as e:
            _raise_cmd_not_found(args, e, cwd)
        except OSError as e:
            _raise_cmd_not_found(args, e, cwd)

        stderr_acc: List[str] = []
        start = time.time()

        while True:
            if _is_stopped():
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                raise RuntimeError("STOPPED")

            if timeout is not None and (time.time() - start) > float(timeout):
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                raise RuntimeError("TIMEOUT")

            line = proc.stderr.readline() if proc.stderr else ""
            if line:
                stderr_acc.append(line)
                if log_func:
                    try:
                        log_func(line.rstrip("\n"))
                    except Exception:
                        pass
            else:
                if proc.poll() is not None:
                    break
                time.sleep(0.01)

        out = proc.stdout.read() if proc.stdout else ""
        err = "".join(stderr_acc)

        cp = subprocess.CompletedProcess(args=args, returncode=proc.returncode, stdout=out, stderr=err)

    except subprocess.TimeoutExpired as e:
        last = _write_last_failed_cmd(args, cwd=cwd)
        raise RuntimeError(f"TIMEOUT\n(Updated to: {last})") from e

    if _is_stopped():
        raise RuntimeError("STOPPED")

    if check and cp.returncode != 0:
        _raise_ffmpeg_crash(args, cp.stderr or "", cp.stdout or "", cp.returncode, cwd)

    return cp
